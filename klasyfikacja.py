from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

CALENDAR_FILE = Path("data/turnieje.json")

ORGANIZACJA_BY_SOURCE = {
    "PZT TOP": "TOP PZT",
    "PLT": "Polska Liga Tenisa",
    "Cuply": "Cuply",
    "Kluby.org": "Kluby.org",
}

CYKL_CANONICAL = {
    "grand prix podlasia i mazur": "Grand Prix Podlasia i Mazur",
    "gp podlasia i mazur": "Grand Prix Podlasia i Mazur",
    "grand prix mazowsza": "Grand Prix Mazowsza",
    "mazowsze cup": "Mazowsze Cup",
    "grand prix warszawy": "Grand Prix Warszawy",
    "gp warszawy": "Grand Prix Warszawy",
    "liga klubowa mma": "Liga Klubowa MMA",
    "liga klubowa gpw": "Liga Klubowa GPW",
    "mistrzostwa warszawy amatorów": "Mistrzostwa Warszawy Amatorów",
    "mistrzostwa warszawy amatorow": "Mistrzostwa Warszawy Amatorów",
    "ziaja grand prix wybrzeża": "Ziaja Grand Prix Wybrzeża",
    "ziaja grand prix wybrzeza": "Ziaja Grand Prix Wybrzeża",
}

GENERIC_CYCLES = set()


def clean(value: str | None) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def canonical_cycle(value: str | None) -> str:
    value = clean(value)
    if not value:
        return ""
    key = value.casefold()
    if key in GENERIC_CYCLES:
        return ""
    return CYKL_CANONICAL.get(key, value)


def classify(item: dict) -> None:
    source = clean(item.get("zrodlo"))
    item["organizacja"] = ORGANIZACJA_BY_SOURCE.get(source, source)

    # W starym modelu pole "cykl" w PLT przechowywało kategorię systemu
    # (1. Liga, 2. Liga, Puchar PLT itd.). Zachowujemy ją osobno.
    legacy_cycle = clean(item.get("cykl"))
    if source == "PLT":
        item["kategoria_zrodla"] = clean(item.get("kategoria_zrodla")) or legacy_cycle
    else:
        item["kategoria_zrodla"] = clean(item.get("kategoria_zrodla"))

    # Reguły redakcyjne Tenis NET:
    # - wszystkie turnieje z systemu Polska Liga Tenisa mają wspólny cykl „PLT”;
    # - wszystkie wydarzenia pobrane z kalendarza TOP PZT należą do cyklu „TOP PZT”;
    # - wszystkie turnieje pobrane z Cuply należą do cyklu „Cuply”.
    # Szczegółowe nazwy/kategorie źródłowe zachowujemy w osobnych polach.
    if source == "PLT":
        item["cykl"] = "PLT"
        return
    if source == "PZT TOP":
        item["cykl"] = "TOP PZT"
        return
    if source == "Cuply":
        item["cykl"] = "Cuply"
        return

    # Dla pozostałych źródeł właściwy cykl pochodzi ze strony szczegółów,
    # jeżeli źródło go podaje; w przeciwnym razie zachowujemy rozpoznanie z listy.
    detailed_cycle = clean(item.get("cykl_szczegolowy"))
    if detailed_cycle:
        item["cykl"] = canonical_cycle(detailed_cycle)
    else:
        item["cykl"] = canonical_cycle(legacy_cycle)


def main() -> None:
    if not CALENDAR_FILE.exists():
        raise RuntimeError("Brak data/turnieje.json")

    calendar = json.loads(CALENDAR_FILE.read_text(encoding="utf-8"))
    items = calendar.get("turnieje", [])
    if not items:
        raise RuntimeError("Brak turniejów w data/turnieje.json")

    for item in items:
        classify(item)

    organizations = sorted({clean(x.get("organizacja")) for x in items if clean(x.get("organizacja"))})
    cycles = sorted({clean(x.get("cykl")) for x in items if clean(x.get("cykl"))})
    source_categories = sorted({clean(x.get("kategoria_zrodla")) for x in items if clean(x.get("kategoria_zrodla"))})
    voivodeships = sorted({clean(x.get("wojewodztwo")) for x in items if clean(x.get("wojewodztwo"))})

    counts = Counter(clean(x.get("organizacja")) for x in items if clean(x.get("organizacja")))
    calendar["liczba_wg_organizacji"] = dict(sorted(counts.items()))
    calendar["filtry"] = {
        "organizacje": organizations,
        "cykle": cycles,
        "kategorie_zrodla": source_categories,
        "wojewodztwa": voivodeships,
    }

    CALENDAR_FILE.write_text(
        json.dumps(calendar, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Klasyfikacja: organizacje={len(organizations)}, cykle={len(cycles)}, kategorie źródła={len(source_categories)}")
    if cycles:
        print("Cykle:", " | ".join(cycles))


if __name__ == "__main__":
    main()
