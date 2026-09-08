from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TURNIEJE_URL = "http://kortyskanda.pl/turnieje.html"
KONTAKT_URL = "http://kortyskanda.pl/kontakt.html"
OUTPUT_FILE = Path("data/turnieje_skanda.json")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
    )
}
DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.?\s*-.*?(?:-\s*(\d{1,2})[\.:](\d{2}))?\s*$", re.I)
CANCELLED = ("nie odbył się", "nie odbyl sie", "nie rozegrano", "odwołany", "odwolany")


def clean(value: str | None) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def soup_from_url(url: str) -> BeautifulSoup:
    response = requests.get(url, timeout=30, headers=HEADERS)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def contact_data() -> dict:
    soup = soup_from_url(KONTAKT_URL)
    text = soup.get_text("\n", strip=True)
    lines = [clean(x) for x in text.splitlines() if clean(x)]

    email = ""
    mail = soup.select_one('a[href^="mailto:"]')
    if mail:
        email = clean(mail.get("href", "").replace("mailto:", "", 1))
    if not email:
        m = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
        if m:
            email = m.group(0)

    phone = ""
    for line in lines:
        if re.fullmatch(r"(?:\+48\s*)?(?:\d[\s-]*){9}", line):
            phone = clean(line)
            break
    if not phone:
        phone = "500 036 039"

    street = next((x for x in lines if x.casefold().startswith("ul. ")), "ul. Wyszyńskiego 12a")
    postal = next((x for x in lines if re.match(r"^\d{2}-\d{3}\s+Olsztyn$", x, re.I)), "10-457 Olsztyn")

    return {
        "organizator": 'TKKF "Skanda"',
        "miejsce": "TKKF Skanda",
        "adres": f"{street}, {postal}",
        "miasto": "Olsztyn",
        "wojewodztwo": "warmińsko-mazurskie",
        "telefon_organizatora": phone,
        "email_organizatora": email or "kortyskanda@gmail.com",
        "kontakt": " | ".join(x for x in [phone, email or "kortyskanda@gmail.com"] if x),
    }


def schedule_lines(soup: BeautifulSoup) -> tuple[int, list[str]]:
    candidates = []
    for table in soup.find_all("table"):
        text = clean(table.get_text(" ", strip=True))
        if "Harmonogram turniejów" in text:
            candidates.append(table)
    if not candidates:
        raise RuntimeError("Skanda: nie znaleziono tabeli harmonogramu")

    # Strona ma zagnieżdżoną tabelę główną. Najmniejsza tabela zawierająca
    # nagłówek harmonogramu jest właściwą tabelą z samymi turniejami.
    table = min(candidates, key=lambda t: len(t.get_text(" ", strip=True)))
    lines = [clean(x) for x in table.get_text("\n", strip=True).splitlines() if clean(x)]
    heading_index = next(i for i, line in enumerate(lines) if "Harmonogram turniejów" in line)
    heading = lines[heading_index]
    m = re.search(r"(20\d{2})", heading)
    if not m:
        raise RuntimeError("Skanda: brak roku w nagłówku harmonogramu")
    return int(m.group(1)), lines[heading_index + 1 :]


def cycle_for(name: str) -> str:
    folded = name.casefold()
    if "grand prix skandy" in folded:
        return "Grand Prix Skandy"
    if "seniorów olsztyna" in folded or "seniorow olsztyna" in folded:
        return "Seniorzy Olsztyna"
    if "debel pań" in folded or "debel pan" in folded:
        return "Debel Pań"
    if "seniorski debel" in folded:
        return "Seniorski Debel"
    return ""


def category_for(game_line: str) -> str:
    folded = game_line.casefold()
    if "kobiet i mężczyzn" in folded or "kobiet i mezczyzn" in folded:
        return "Kobiety i mężczyźni open"
    if "mężczyzn" in folded or "mezczyzn" in folded:
        if "50" in folded:
            return "Mężczyźni 50+"
        return "Mężczyźni"
    if "kobiet" in folded:
        return "Kobiety"
    if "50" in folded:
        return "50+"
    return ""


def parse_date_line(line: str, year: int) -> tuple[str, str] | None:
    m = DATE_RE.match(line)
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    try:
        event_date = date(year, month, day).isoformat()
    except ValueError:
        return None
    time_text = ""
    # Czas jest ostatnim elementem po myślniku, np. "12.09 - sobota - 10.00".
    tm = re.search(r"-\s*(\d{1,2})[\.:](\d{2})\s*$", line)
    if tm:
        time_text = f"{int(tm.group(1)):02d}:{int(tm.group(2)):02d}"
    return event_date, time_text


def events_from_bucket(event_date: str, start_time: str, bucket: list[str], contact: dict) -> tuple[list[dict], int]:
    events: list[dict] = []
    cancelled_count = 0
    buffer: list[str] = []

    for line in bucket:
        if line.casefold().startswith("gra "):
            raw_name_lines = buffer
            buffer = []
            is_cancelled = any(any(token in x.casefold() for token in CANCELLED) for x in raw_name_lines)
            name_lines = [x for x in raw_name_lines if not any(token in x.casefold() for token in CANCELLED)]
            name = clean(" ".join(name_lines))
            if not name:
                continue
            if is_cancelled:
                cancelled_count += 1
                continue

            item = {
                "zrodlo": "TKKF Skanda",
                "nazwa": name,
                "data_od": event_date,
                "data_do": event_date,
                "miasto": contact["miasto"],
                "miejsce": contact["miejsce"],
                "wojewodztwo": contact["wojewodztwo"],
                "adres": contact["adres"],
                "organizator": contact["organizator"],
                "telefon_organizatora": contact["telefon_organizatora"],
                "email_organizatora": contact["email_organizatora"],
                "kontakt": contact["kontakt"],
                "typ_gry": line,
                "kategorie": category_for(line),
                "cykl_szczegolowy": cycle_for(name),
                "url": TURNIEJE_URL,
            }
            if start_time:
                item["start_turnieju"] = start_time
                item["opis"] = f"Start: {start_time}. Informacje i zapisy u organizatora."
            else:
                item["opis"] = "Informacje i zapisy u organizatora."
            events.append(item)
        else:
            buffer.append(line)

    return events, cancelled_count


def main() -> None:
    soup = soup_from_url(TURNIEJE_URL)
    contact = contact_data()
    year, lines = schedule_lines(soup)
    today = date.today().isoformat()

    all_events: list[dict] = []
    cancelled_count = 0
    current_date = ""
    current_time = ""
    bucket: list[str] = []

    def flush() -> None:
        nonlocal cancelled_count, bucket
        if not current_date:
            bucket = []
            return
        parsed, cancelled = events_from_bucket(current_date, current_time, bucket, contact)
        all_events.extend(parsed)
        cancelled_count += cancelled
        bucket = []

    for line in lines:
        parsed_date = parse_date_line(line, year)
        if parsed_date:
            flush()
            current_date, current_time = parsed_date
            continue
        # Po harmonogramie zaczynają się linki do PDF/archiwum/cennika.
        if line.casefold().startswith(("harmonogram turniejów do pobrania", "regulamin turniejów", "archiwum turniejów", "cennik ")):
            break
        bucket.append(line)
    flush()

    future = [x for x in all_events if x["data_do"] >= today]
    future.sort(key=lambda x: (x["data_od"], x["nazwa"]))

    payload = {
        "zrodlo": "TKKF Skanda",
        "pobrano_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "liczba_turniejow": len(future),
        "odrzucono_odwolane": cancelled_count,
        "turnieje": future,
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"TKKF Skanda: {len(future)} przyszłych turniejów -> {OUTPUT_FILE}")
    print(f"TKKF Skanda: pominięto oznaczone jako odwołane/nie rozegrane: {cancelled_count}")
    for item in future:
        print(f"- {item['data_od']} | {item['nazwa']} | {item.get('cykl_szczegolowy') or 'bez cyklu'}")


if __name__ == "__main__":
    main()
