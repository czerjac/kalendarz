from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

CALENDAR_FILE = Path("data/turnieje.json")

SINGLES_PLT_CATEGORIES = {
    "1. liga",
    "2. liga",
    "puchar plt",
    "plt kobiet",
    "kategorie wiekowe",
}


def clean(value: str | None) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def ascii_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.casefold().replace("ł", "l")


def combined_text(item: dict) -> str:
    fields = [
        item.get("nazwa"),
        item.get("kategorie"),
        item.get("typ_gry"),
        item.get("plec"),
        item.get("poziom"),
        item.get("rangi"),
        item.get("kategoria_zrodla"),
    ]
    return ascii_text(" | ".join(clean(x) for x in fields if clean(x)))


def normalize_game_types(item: dict) -> list[str]:
    text = combined_text(item)
    kinds: list[str] = []

    if re.search(r"\b(singiel|singla|singlow\w*|gra pojedyncza)\b", text):
        kinds.append("singiel")
    if re.search(r"\b(debel|debla|deble|deblow\w*|gra podwojna)\b", text):
        kinds.append("debel")
    if re.search(r"\b(mikst|miksty|mikstow\w*|mixt|mixed)\b", text):
        kinds.append("mikst")

    source = clean(item.get("zrodlo"))
    source_category = clean(item.get("kategoria_zrodla")).casefold()

    # PLT rozdziela kalendarze singlowe od osobnego działu Deble i Miksty.
    if source == "PLT" and not kinds:
        if source_category in SINGLES_PLT_CATEGORIES:
            kinds.append("singiel")
        elif source_category == "deble i miksty":
            # Jeżeli sama nazwa nie rozstrzyga, wydarzenie ma być widoczne
            # pod oboma filtrami, zamiast zgadywać jedną z dwóch kategorii.
            kinds.extend(["debel", "mikst"])

    # W Kluby.org gra pojedyncza jest często kategorią domyślną i nie jest
    # zapisana słowem „singiel”. Jeśli nie ma śladu debla/miksta ani turnieju
    # drużynowego, traktujemy taki turniej jako singlowy.
    if source == "Kluby.org" and not kinds:
        if not re.search(r"\b(druzyn\w*|team)\b", text):
            kinds.append("singiel")

    order = ["singiel", "debel", "mikst"]
    return [kind for kind in order if kind in kinds]


def normalize_participant_groups(item: dict, game_types: list[str]) -> list[str]:
    text = combined_text(item)
    groups: list[str] = []

    if re.search(r"\b(kobiety|kobiet|kobiecy|kobiece|panie|pan|ladies|women)\b", text):
        groups.append("kobiety")
    if re.search(r"\b(mezczyzni|mezczyzn|meski|meskie|panowie|men)\b", text):
        groups.append("mężczyźni")

    # Wyraźne „wszyscy/dla wszystkich” oznacza otwartość dla obu grup.
    if re.search(r"\b(wszyscy|dla wszystkich)\b", text):
        groups.extend(["kobiety", "mężczyźni"])

    source_category = clean(item.get("kategoria_zrodla")).casefold()
    if source_category == "plt kobiet":
        groups.append("kobiety")

    # Mikst z definicji obejmuje zawodniczki i zawodników.
    if "mikst" in game_types:
        groups.extend(["kobiety", "mężczyźni"])

    order = ["kobiety", "mężczyźni"]
    return [group for group in order if group in groups]


def main() -> None:
    if not CALENDAR_FILE.exists():
        raise RuntimeError("Brak data/turnieje.json")

    calendar = json.loads(CALENDAR_FILE.read_text(encoding="utf-8"))
    items = calendar.get("turnieje", [])
    if not items:
        raise RuntimeError("Brak turniejów w data/turnieje.json")

    missing_game_type: list[dict] = []
    missing_groups = 0

    for item in items:
        game_types = normalize_game_types(item)
        groups = normalize_participant_groups(item, game_types)
        item["rodzaje_gry"] = game_types
        item["grupy_uczestnikow"] = groups

        if not game_types:
            missing_game_type.append({
                "id": item.get("id", ""),
                "zrodlo": item.get("zrodlo", ""),
                "nazwa": item.get("nazwa", ""),
                "kategorie": item.get("kategorie", ""),
                "typ_gry": item.get("typ_gry", ""),
            })
        if not groups:
            missing_groups += 1

    filters = calendar.setdefault("filtry", {})
    game_filter_order = ["singiel", "debel", "mikst"]
    group_filter_order = ["kobiety", "mężczyźni"]
    present_games = {g for item in items for g in item.get("rodzaje_gry", [])}
    present_groups = {g for item in items for g in item.get("grupy_uczestnikow", [])}
    filters["rodzaje_gry"] = [g for g in game_filter_order if g in present_games]
    filters["grupy_uczestnikow"] = [g for g in group_filter_order if g in present_groups]

    calendar["jakosc_normalizacji"] = {
        "liczba_bez_rodzaju_gry": len(missing_game_type),
        "liczba_bez_grupy_uczestnikow": missing_groups,
        "przyklady_bez_rodzaju_gry": missing_game_type[:15],
    }

    CALENDAR_FILE.write_text(
        json.dumps(calendar, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"Normalizacja: rodzaj gry rozpoznano {len(items) - len(missing_game_type)}/{len(items)}, "
        f"grupę uczestników {len(items) - missing_groups}/{len(items)}"
    )
    print("Rodzaje gry:", " | ".join(filters["rodzaje_gry"]))
    print("Grupy uczestników:", " | ".join(filters["grupy_uczestnikow"]))
    if missing_game_type:
        print("Bez rodzaju gry (przykłady):")
        for row in missing_game_type[:10]:
            print(f"- {row['zrodlo']}: {row['nazwa']}")


if __name__ == "__main__":
    main()
