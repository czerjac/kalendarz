from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

DATA_DIR = Path("data")
OUTPUT_FILE = DATA_DIR / "turnieje.json"
SOURCES = [
    DATA_DIR / "turnieje_pzt.json",
    DATA_DIR / "turnieje_cuply.json",
    DATA_DIR / "turnieje_plt.json",
    DATA_DIR / "turnieje_kluby.json",
    DATA_DIR / "turnieje_skanda.json",
]
YOUTH_RE = re.compile(r"\b(JUNIORZY|JUNIORKI|TENIS10|U1[02468])\b", re.I)


def clean(text: str | None) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def stable_id(source: str, url: str, name: str, start: str) -> str:
    # Zwykle URL konkretnego turnieju jest stabilniejszy niż nazwa/data.
    # Skanda publikuje jednak cały sezon na jednej wspólnej stronie, więc dla
    # tego źródła identyfikatorem musi być nazwa + data, inaczej wszystkie
    # wydarzenia dostałyby ten sam ID.
    if source == "TKKF Skanda":
        identity = f"{source}|{name}|{start}"
    else:
        identity = f"{source}|{url}" if url else f"{source}|{name}|{start}"
    return hashlib.sha1(identity.encode("utf-8")).hexdigest()[:14]


def normalize_name(text: str) -> str:
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = value.casefold()
    value = re.sub(r"\b(?:puchar plt|plt kobiet|1\.? liga|2\.? liga|top pzt tour)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalize_city(text: str) -> str:
    return normalize_name(text)


def is_adult_amateur(item: dict) -> bool:
    if item.get("zrodlo") != "Kluby.org":
        return True
    categories = clean(item.get("kategorie"))
    return not bool(YOUTH_RE.search(categories))


def normalize_item(item: dict) -> dict:
    source = clean(item.get("zrodlo"))
    name = clean(item.get("nazwa"))
    start = clean(item.get("data_od"))
    end = clean(item.get("data_do")) or start
    city = clean(item.get("miasto"))
    url = clean(item.get("url"))

    categories = clean(item.get("kategorie"))
    cycle = clean(item.get("kategoria")) if source == "PLT" else ""

    result = {
        "id": stable_id(source, url, name, start),
        "zrodlo": source,
        "cykl": cycle,
        "nazwa": name,
        "data_od": start,
        "data_do": end,
        "miasto": city,
        "miejsce": clean(item.get("miejsce")),
        "kategorie": categories,
        "typ_gry": clean(item.get("typ_gry")),
        "poziom": clean(item.get("poziom")),
        "plec": clean(item.get("plec")),
        "wpisowe": clean(item.get("wpisowe")),
        "ranga": clean(item.get("ranga")),
        "url": url,
    }

    # Niektóre źródła (np. Skanda) podają pełne dane już na stronie zbiorczej,
    # więc zachowujemy je od razu zamiast zmuszać warstwę szczegółów do
    # ponownego pobierania tej samej strony dla każdego wydarzenia.
    passthrough = [
        "wojewodztwo", "adres", "organizator", "kontakt",
        "telefon_organizatora", "email_organizatora", "cykl_szczegolowy",
        "zapisy_url", "opis", "system_gier", "limit_uczestnikow",
        "nawierzchnia", "start_turnieju", "rangi", "dyrektor_turnieju",
        "sedzia_naczelny", "pilka", "termin_zgloszen",
    ]
    for key in passthrough:
        value = clean(item.get(key))
        if value:
            result[key] = value

    today = date.today().isoformat()
    result["status"] = "trwa" if start <= today <= end else "nadchodzacy"
    return result


def duplicate_candidates(items: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            if a["zrodlo"] == b["zrodlo"]:
                continue
            if a["data_od"] != b["data_od"]:
                continue
            if normalize_city(a["miasto"]) != normalize_city(b["miasto"]):
                continue

            na = normalize_name(a["nazwa"])
            nb = normalize_name(b["nazwa"])
            if not na or not nb:
                continue
            score = SequenceMatcher(None, na, nb).ratio()
            if score >= 0.84:
                groups.append(
                    {
                        "id_a": a["id"],
                        "id_b": b["id"],
                        "zgodnosc_nazwy": round(score, 3),
                        "data": a["data_od"],
                        "miasto": a["miasto"],
                    }
                )
    return groups


def main() -> None:
    today = date.today().isoformat()
    items: list[dict] = []
    counts: dict[str, int] = {}
    excluded_youth = 0

    for path in SOURCES:
        if not path.exists():
            print(f"UWAGA: brak pliku {path}; pomijam źródło")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for raw in payload.get("turnieje", []):
            if clean(raw.get("data_do")) < today:
                continue
            if not is_adult_amateur(raw):
                excluded_youth += 1
                continue
            item = normalize_item(raw)
            if not item["nazwa"] or not item["data_od"]:
                continue
            items.append(item)
            counts[item["zrodlo"]] = counts.get(item["zrodlo"], 0) + 1

    unique: dict[str, dict] = {}
    for item in items:
        unique[item["id"]] = item
    items = sorted(unique.values(), key=lambda x: (x["data_od"], x["miasto"], x["nazwa"], x["zrodlo"]))

    candidates = duplicate_candidates(items)
    output = {
        "wygenerowano_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "liczba_turniejow": len(items),
        "liczba_wg_zrodla": counts,
        "odfiltrowano_turnieje_mlodziezowe": excluded_youth,
        "liczba_potencjalnych_par_duplikatow": len(candidates),
        "potencjalne_duplikaty": candidates,
        "turnieje": items,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RAZEM: {len(items)} turniejów -> {OUTPUT_FILE}")
    print(f"Źródła: {counts}")
    print(f"Odfiltrowano młodzieżowe: {excluded_youth}")
    print(f"Potencjalne pary duplikatów: {len(candidates)}")


if __name__ == "__main__":
    main()
