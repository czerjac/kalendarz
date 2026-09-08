from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import requests
from bs4 import BeautifulSoup

YEAR = 2026
TODAY = date.today()
ROOT = Path(f"data/archiwum/{YEAR}")
ARCHIVE_FILE = ROOT / "turnieje.json"
REPORT_FILE = ROOT / "raport.json"
DUP_FILE = ROOT / "duplikaty_do_weryfikacji.json"
PZT_CACHE_FILE = ROOT / "pzt_szczegoly.json"
PZT_PARSER_VERSION = 2
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
    )
}
POSTAL_CITY_RE = re.compile(r"\b\d{2}-\d{3}\s+([^,;/]+)")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value: str | None) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ascii_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.casefold().replace("ł", "l")


def text_lines(soup: BeautifulSoup) -> list[str]:
    return [clean(x) for x in soup.get_text("\n", strip=True).splitlines() if clean(x)]


def value_after(lines: list[str], labels: list[str]) -> str:
    wanted = [ascii_text(x).rstrip(":") for x in labels]
    for i, line in enumerate(lines):
        folded = ascii_text(line)
        stripped = folded.rstrip(":")
        for label in wanted:
            if stripped == label and i + 1 < len(lines):
                return clean(lines[i + 1])
            prefix = label + ":"
            if folded.startswith(prefix):
                value = clean(line[len(prefix):])
                if value:
                    return value
    return ""


def city_from_address(address: str) -> str:
    value = clean(address)
    if not value:
        return ""
    match = POSTAL_CITY_RE.search(value)
    if match:
        city = clean(match.group(1))
        city = re.split(r"\s+(?:ul\.|al\.|aleja|pl\.)\s+", city, maxsplit=1, flags=re.I)[0]
        return city.strip(" -")
    first = clean(value.split(",", 1)[0])
    if first and not re.search(r"\b(?:ul\.|aleja|al\.|pl\.|korty|centrum|hala|obiekt)\b", first, re.I):
        if len(first.split()) <= 4:
            return first
    return ""


def pzt_cache_key(item: dict) -> str:
    url = clean(item.get("url"))
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:18]


def parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(clean(value))
    except ValueError:
        return None


def cache_due(item: dict, entry: dict) -> bool:
    if entry.get("wersja_parsera") != PZT_PARSER_VERSION:
        return True
    if not entry.get("ostatnie_poprawne_pobranie_utc"):
        return True
    if not entry.get("dane"):
        return True
    details = entry.get("dane", {})
    end = parse_iso_date(item.get("data_do"))
    if end and not details.get("wyniki_potwierdzone") and 0 <= (TODAY - end).days <= 35:
        try:
            last = datetime.fromisoformat(entry["ostatnie_poprawne_pobranie_utc"].replace("Z", "+00:00")).date()
            return (TODAY - last).days >= 6
        except Exception:
            return True
    return False


def fetch_pzt_detail(session: requests.Session, item: dict) -> dict:
    url = clean(item.get("url"))
    response = session.get(url, timeout=35, headers=HEADERS)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    lines = text_lines(soup)
    flat = clean(soup.get_text(" ", strip=True))
    folded = ascii_text(flat)

    organizer = value_after(lines, ["Organizator"])
    address = value_after(lines, ["Miejsce turnieju"])
    categories = value_after(lines, ["Kategorie"])
    deadline = value_after(lines, ["Termin zgłoszeń"])
    director = value_after(lines, ["Dyrektor turnieju"])

    # Nie traktujemy samego wystąpienia etykiet „Drabinki”, „Mecze” lub „Zwycięzcy”
    # jako dowodu rozegrania turnieju, bo są elementami interfejsu PZT.
    # Potwierdzeniem jest co najmniej jedna sekcja Drabinki/Mecze bez adnotacji „brak wyników”.
    no_draws = "drabinki (brak wynikow)" in folded
    no_matches = "mecze (brak wynikow)" in folded
    has_draws = "drabinki" in folded and not no_draws
    has_matches = "mecze" in folded and not no_matches
    results_confirmed = bool(has_draws or has_matches)

    details = {
        "organizator": organizer,
        "adres": address,
        "miasto": city_from_address(address),
        "kategorie": categories,
        "termin_zgloszen": deadline,
        "dyrektor_turnieju": director,
        "wyniki_potwierdzone": results_confirmed,
        "status_wynikow": (
            "sa_dane_wynikowe" if results_confirmed
            else "brak_drabinki_i_meczow" if no_draws and no_matches
            else "niejednoznaczny"
        ),
    }
    return {k: v for k, v in details.items() if v not in ("", None)}


def enrich_pzt(items: list[dict]) -> tuple[dict, dict]:
    payload = load_json(PZT_CACHE_FILE, {"turnieje": {}})
    cache = payload.setdefault("turnieje", {})
    session = requests.Session()
    fetched = 0
    failed = 0

    pzt_items = [x for x in items if clean(x.get("zrodlo")) == "PZT TOP"]
    for item in pzt_items:
        key = pzt_cache_key(item)
        entry = cache.setdefault(key, {
            "url": clean(item.get("url")),
            "nazwa": clean(item.get("nazwa")),
            "dane": {},
        })
        entry["url"] = clean(item.get("url"))
        entry["nazwa"] = clean(item.get("nazwa"))
        entry["ostatnio_widziany_w_archiwum_utc"] = now_iso()
        if cache_due(item, entry):
            entry["ostatnia_proba_utc"] = now_iso()
            try:
                entry["dane"] = fetch_pzt_detail(session, item)
                entry["wersja_parsera"] = PZT_PARSER_VERSION
                entry["ostatnie_poprawne_pobranie_utc"] = now_iso()
                entry.pop("ostatni_blad", None)
                fetched += 1
            except Exception as exc:
                entry["ostatni_blad"] = f"{type(exc).__name__}: {exc}"
                failed += 1
            time.sleep(0.12)

        details = entry.get("dane", {})
        for field in ["organizator", "adres", "termin_zgloszen", "dyrektor_turnieju", "status_wynikow"]:
            if details.get(field):
                item[field] = details[field]
        if details.get("miasto"):
            item["miasto"] = details["miasto"]
        if details.get("kategorie") and not clean(item.get("kategorie")):
            item["kategorie"] = details["kategorie"]
        item["wyniki_potwierdzone"] = bool(details.get("wyniki_potwierdzone"))

        source_status = ascii_text(clean(item.get("status_zrodla")))
        if item["wyniki_potwierdzone"]:
            item["status_archiwum"] = "rozegrany"
        elif "zakoncz" in source_status:
            item["status_archiwum"] = "zakonczony_wg_zrodla"
        else:
            item["status_archiwum"] = "niezweryfikowany"

        organizer = clean(item.get("organizator"))
        name = clean(item.get("nazwa"))
        if organizer and ascii_text(name).endswith(ascii_text(organizer)):
            if name.casefold().endswith(organizer.casefold()):
                core = name[: -len(organizer)].rstrip(" ,-/")
                if core:
                    item["nazwa_turnieju"] = core

    payload["aktualizacja_utc"] = now_iso()
    payload["wersja_parsera"] = PZT_PARSER_VERSION
    payload["liczba_rekordow"] = len(cache)
    save_json(PZT_CACHE_FILE, payload)

    stats = {
        "pzt_liczba": len(pzt_items),
        "pzt_szczegoly_pobrane_w_tym_przebiegu": fetched,
        "pzt_bledy_szczegolow": failed,
        "pzt_z_miastem": sum(1 for x in pzt_items if clean(x.get("miasto"))),
        "pzt_z_potwierdzonymi_wynikami": sum(1 for x in pzt_items if x.get("wyniki_potwierdzone")),
        "pzt_bez_potwierdzonych_wynikow": sum(1 for x in pzt_items if not x.get("wyniki_potwierdzone")),
    }
    return payload, stats


def match_name(item: dict) -> str:
    value = clean(item.get("nazwa_turnieju")) or clean(item.get("nazwa"))
    value = ascii_text(value)
    value = re.sub(r"\b(?:puchar\s+plt|plt\s+kobiet|1\.?\s*liga|2\.?\s*liga|top\s+pzt(?:\s+tour)?|cuply)\b", " ", value)
    value = re.sub(r"\b2026\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def match_city(value: str) -> str:
    city = ascii_text(clean(value))
    city = re.sub(r"\s+k\.?\s+.+$", "", city)
    city = re.sub(r"[^a-z0-9]+", " ", city)
    return " ".join(city.split())


def date_distance(a: dict, b: dict) -> int | None:
    da = parse_iso_date(a.get("data_od"))
    db = parse_iso_date(b.get("data_od"))
    if not da or not db:
        return None
    return abs((da - db).days)


def duplicate_candidates(items: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if clean(a.get("zrodlo")) == clean(b.get("zrodlo")):
                continue
            distance = date_distance(a, b)
            if distance is None or distance > 1:
                continue

            name_a = match_name(a)
            name_b = match_name(b)
            if not name_a or not name_b:
                continue
            score = SequenceMatcher(None, name_a, name_b).ratio()
            city_a = match_city(clean(a.get("miasto")))
            city_b = match_city(clean(b.get("miasto")))
            same_city = bool(city_a and city_b and city_a == city_b)
            one_city_missing = not city_a or not city_b

            confidence = ""
            reason = ""
            if distance == 0 and same_city and score >= 0.88:
                confidence, reason = "wysokie", "ta_sama_data_miasto_i_bardzo_podobna_nazwa"
            elif distance == 0 and same_city and score >= 0.72:
                confidence, reason = "srednie", "ta_sama_data_i_miasto_podobna_nazwa"
            elif distance == 0 and one_city_missing and score >= 0.92:
                confidence, reason = "wysokie", "ta_sama_data_bardzo_podobna_nazwa_brak_lokalizacji_w_jednym_zrodle"
            elif distance == 1 and same_city and score >= 0.92:
                confidence, reason = "srednie", "roznica_jednego_dnia_to_samo_miasto_bardzo_podobna_nazwa"
            if not confidence:
                continue

            candidates.append({
                "id_a": a.get("id"),
                "id_b": b.get("id"),
                "zrodlo_a": a.get("zrodlo"),
                "zrodlo_b": b.get("zrodlo"),
                "nazwa_a": a.get("nazwa"),
                "nazwa_b": b.get("nazwa"),
                "nazwa_porownawcza_a": name_a,
                "nazwa_porownawcza_b": name_b,
                "data_a": a.get("data_od"),
                "data_b": b.get("data_od"),
                "miasto_a": a.get("miasto"),
                "miasto_b": b.get("miasto"),
                "zgodnosc_nazwy": round(score, 3),
                "pewnosc": confidence,
                "powod": reason,
            })

    order = {"wysokie": 0, "srednie": 1}
    candidates.sort(key=lambda x: (order.get(x["pewnosc"], 9), -x["zgodnosc_nazwy"], x["data_a"] or ""))
    return candidates


def main() -> None:
    archive = load_json(ARCHIVE_FILE, {})
    items = archive.get("turnieje", [])
    if not items:
        raise RuntimeError(f"Brak danych w {ARCHIVE_FILE}")

    _, pzt_stats = enrich_pzt(items)
    duplicates = duplicate_candidates(items)
    duplicate_counts = Counter(x["pewnosc"] for x in duplicates)
    status_counts = Counter(clean(x.get("status_archiwum")) for x in items if clean(x.get("status_archiwum")))

    archive["aktualizacja_audytu_utc"] = now_iso()
    archive["liczba_potencjalnych_par_duplikatow"] = len(duplicates)
    archive["liczba_potencjalnych_par_duplikatow_wg_pewnosci"] = dict(sorted(duplicate_counts.items()))
    archive["liczba_z_potwierdzonymi_wynikami_pzt"] = pzt_stats["pzt_z_potwierdzonymi_wynikami"]
    archive["liczba_wg_statusu_archiwum"] = dict(sorted(status_counts.items()))
    save_json(ARCHIVE_FILE, archive)

    save_json(DUP_FILE, {
        "rok": YEAR,
        "aktualizacja_utc": now_iso(),
        "uwaga": "To są wyłącznie kandydaci do ręcznej weryfikacji. Skrypt nie scala rekordów automatycznie.",
        "liczba": len(duplicates),
        "liczba_wg_pewnosci": dict(sorted(duplicate_counts.items())),
        "pary": duplicates,
    })

    report = load_json(REPORT_FILE, {"rok": YEAR})
    report["liczba_niezweryfikowanych"] = status_counts.get("niezweryfikowany", 0)
    report["liczba_wg_statusu_archiwum"] = dict(sorted(status_counts.items()))
    report["audyt"] = {
        "aktualizacja_utc": now_iso(),
        **pzt_stats,
        "liczba_kandydatow_duplikatow": len(duplicates),
        "kandydaci_wg_pewnosci": dict(sorted(duplicate_counts.items())),
    }
    save_json(REPORT_FILE, report)

    print("\n=== AUDYT ARCHIWUM 2026 ===")
    print("PZT:", pzt_stats)
    print("Statusy archiwum:", dict(status_counts))
    print("Kandydaci duplikatów:", len(duplicates), dict(duplicate_counts))
    for row in duplicates[:30]:
        print(
            f"[{row['pewnosc']}] {row['data_a']} | {row['zrodlo_a']}: {row['nazwa_a']} "
            f"<=> {row['zrodlo_b']}: {row['nazwa_b']} | {row['miasto_a']} / {row['miasto_b']} "
            f"| score={row['zgodnosc_nazwy']}"
        )


if __name__ == "__main__":
    main()
