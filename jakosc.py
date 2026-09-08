from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

CALENDAR_FILE = Path("data/turnieje.json")
REJECTED_FILE = Path("data/odrzucone_jakosc.json")
HEADERS = {
    "User-Agent": "TenisNET-Kalendarz-Jakosc/1.0 (+https://www.tenis.net.pl/)"
}

# Reguły celowo są ostrożne i źródłowe. Nie wolno np. odrzucać słowa
# "Liga" globalnie, bo 1. i 2. Liga PLT to normalne jednodniowe turnieje.
PZT_NON_TOURNAMENT_RE = re.compile(
    r"\b(liga|challenge|challange|drabinka|ladder)\b", re.I
)


def clean(value) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", clean(value))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()


def parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(clean(value))
    except Exception:
        return None


def duration_days(item: dict) -> int | None:
    start = parse_day(item.get("data_od", ""))
    end = parse_day(item.get("data_do", "")) or start
    if not start or not end:
        return None
    return (end - start).days + 1


def pzt_page_has_no_activity(item: dict, today: date) -> bool:
    """Dodatkowy sygnał jakości dla trwających, dłuższych rekordów PZT.

    Jeżeli wydarzenie zaczęło się co najmniej 7 dni temu, nadal trwa, a PZT
    wciąż pokazuje jednocześnie brak wyników drabinek i brak wyników meczów,
    traktujemy je jako nieaktywne. Błąd sieci nigdy sam nie powoduje odrzucenia.
    """
    start = parse_day(item.get("data_od", ""))
    end = parse_day(item.get("data_do", "")) or start
    if not start or not end:
        return False
    if not (start <= today <= end):
        return False
    if today - start < timedelta(days=7):
        return False
    url = clean(item.get("url"))
    if not url:
        return False
    url = re.sub(r"^http://", "https://", url, flags=re.I)
    try:
        response = requests.get(url, timeout=20, headers=HEADERS)
        response.raise_for_status()
        text = fold(response.text)
    except Exception as exc:
        print(f"UWAGA jakość PZT: nie udało się sprawdzić {url}: {exc}")
        return False

    return (
        "drabinki (brak wynikow)" in text
        and "mecze (brak wynikow)" in text
    )


def rejection_reasons(item: dict, today: date) -> list[str]:
    if clean(item.get("zrodlo")) != "PZT TOP":
        return []

    reasons: list[str] = []
    name = fold(item.get("nazwa", ""))
    days = duration_days(item)

    # Typowa liga/challenge trwająca tygodniami nie jest turniejem kalendarzowym.
    if days is not None and days >= 15 and PZT_NON_TOURNAMENT_RE.search(name):
        reasons.append("rozgrywki_ligowe_lub_challenge")

    # Bardzo długi rekord w PZT z definicji nie odpowiada pojedynczemu turniejowi.
    if days is not None and days >= 45:
        reasons.append("wydarzenie_wielotygodniowe")

    # Dodatkowa kontrola martwych rekordów PZT, które formalnie nadal są "trwające".
    if pzt_page_has_no_activity(item, today):
        reasons.append("brak_drabinki_i_meczow_po_7_dniach_od_startu")

    return reasons


def main() -> None:
    payload = json.loads(CALENDAR_FILE.read_text(encoding="utf-8"))
    items = payload.get("turnieje", [])
    today = date.today()

    kept: list[dict] = []
    rejected: list[dict] = []

    for item in items:
        reasons = rejection_reasons(item, today)
        if reasons:
            rejected.append({
                "id": item.get("id", ""),
                "zrodlo": item.get("zrodlo", ""),
                "nazwa": item.get("nazwa", ""),
                "data_od": item.get("data_od", ""),
                "data_do": item.get("data_do", ""),
                "miasto": item.get("miasto", ""),
                "url": item.get("url", ""),
                "powody": reasons,
            })
        else:
            kept.append(item)

    counts: dict[str, int] = {}
    for item in kept:
        source = clean(item.get("zrodlo"))
        counts[source] = counts.get(source, 0) + 1

    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload["turnieje"] = kept
    payload["liczba_turniejow"] = len(kept)
    payload["liczba_wg_zrodla"] = counts
    payload["kontrola_jakosci"] = {
        "sprawdzono_utc": checked_at,
        "liczba_przed": len(items),
        "liczba_po": len(kept),
        "odrzucono": len(rejected),
        "zasada": "PZT: odrzucamy wielotygodniowe ligi/challenge oraz trwające rekordy bez drabinki i meczów co najmniej 7 dni po starcie",
    }

    CALENDAR_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    REJECTED_FILE.write_text(
        json.dumps(
            {
                "sprawdzono_utc": checked_at,
                "liczba_odrzuconych": len(rejected),
                "turnieje": rejected,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"KONTROLA JAKOŚCI: {len(items)} -> {len(kept)}; odrzucono {len(rejected)}")
    for item in rejected:
        print(f"ODRZUCONO: {item['nazwa']} | {', '.join(item['powody'])}")


if __name__ == "__main__":
    main()
