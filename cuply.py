from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://cuply.pl/turnieje"
OUTPUT_FILE = Path("data/turnieje_cuply.json")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0 Safari/537.36"
    )
}
DATE_RANGE_RE = re.compile(
    r"Termin:\s*(\d{2}\.\d{2})(?:\.\d{4})?\s*-\s*(\d{2}\.\d{2}\.\d{4})",
    re.I,
)
DATE_SINGLE_RE = re.compile(r"Termin:\s*(\d{2}\.\d{2}\.\d{4})", re.I)
CTA_PREFIXES = ("weź udział", "wez udzial", "zapisz się", "zapisz sie", "lista rezerwowa")


def clean(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, timeout=30, headers=HEADERS)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def parse_date_range(text: str) -> tuple[str, str] | None:
    match = DATE_RANGE_RE.search(text)
    if match:
        start_short, end_full = match.groups()
        end = datetime.strptime(end_full, "%d.%m.%Y").date()
        start_day, start_month = map(int, start_short.split("."))
        start_year = end.year - 1 if start_month > end.month else end.year
        start = datetime(start_year, start_month, start_day).date()
        return start.isoformat(), end.isoformat()

    match = DATE_SINGLE_RE.search(text)
    if match:
        value = datetime.strptime(match.group(1), "%d.%m.%Y").date().isoformat()
        return value, value
    return None


def find_card(anchor) -> object | None:
    node = anchor
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            return None
        text = clean(node.get_text(" ", strip=True))
        if "Termin:" in text and "Miejsce:" in text:
            return node
    return None


def extract_place(card_text: str) -> str:
    match = re.search(
        r"Miejsce:\s*(.+?)(?=\s+(?:Weź udział|Zapisz się|Zapisy od|$))",
        card_text,
        re.I,
    )
    return clean(match.group(1)) if match else ""


def extract_city(place: str) -> str:
    if not place:
        return ""
    parts = [clean(part) for part in place.split(",") if clean(part)]
    return parts[-1] if parts else place


def pobierz_turnieje() -> list[dict]:
    session = requests.Session()
    pages_to_visit = [SOURCE_URL]
    visited_pages: set[str] = set()
    by_url: dict[str, dict] = {}

    while pages_to_visit and len(visited_pages) < 10:
        page_url = pages_to_visit.pop(0)
        if page_url in visited_pages:
            continue
        visited_pages.add(page_url)
        soup = get_soup(session, page_url)

        for link in soup.find_all("a", href=True):
            absolute = urljoin(page_url, link["href"])
            parsed = urlparse(absolute)
            if parsed.netloc == "cuply.pl" and parsed.path.rstrip("/") == "/turnieje":
                if "page" in parse_qs(parsed.query) and absolute not in visited_pages:
                    pages_to_visit.append(absolute)

        for anchor in soup.find_all("a", href=True):
            absolute = urljoin(page_url, anchor["href"])
            parsed = urlparse(absolute)
            path = parsed.path.rstrip("/")
            if parsed.netloc != "cuply.pl" or not path.startswith("/turnieje/"):
                continue

            name = clean(anchor.get_text(" ", strip=True))
            if not name or name.casefold().startswith(CTA_PREFIXES):
                continue

            card = find_card(anchor)
            if card is None:
                continue
            card_text = clean(card.get_text(" ", strip=True))
            dates = parse_date_range(card_text)
            if not dates:
                continue

            place = extract_place(card_text)
            data_od, data_do = dates
            by_url.setdefault(
                absolute,
                {
                    "zrodlo": "Cuply",
                    "nazwa": name,
                    "data_od": data_od,
                    "data_do": data_do,
                    "miasto": extract_city(place),
                    "miejsce": place,
                    "typ_gry": "",
                    "poziom": "",
                    "plec": "",
                    "wpisowe": "",
                    "url": absolute,
                },
            )

    turnieje = list(by_url.values())
    if not turnieje:
        raise RuntimeError("Nie znaleziono żadnych turniejów Cuply. Strona mogła zmienić układ.")

    # Szczegóły (typ gry, poziom, wpisowe itd.) pobiera wspólny moduł szczegoly.py
    # i zapisuje je w cache. Dzięki temu nie odwiedzamy każdej podstrony Cuply codziennie.
    turnieje.sort(key=lambda x: (x["data_od"], x["miasto"], x["nazwa"]))
    return turnieje


def main() -> None:
    turnieje = pobierz_turnieje()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    wynik = {
        "zrodlo": "Cuply",
        "adres_zrodla": SOURCE_URL,
        "pobrano_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "liczba_turniejow": len(turnieje),
        "turnieje": turnieje,
    }
    OUTPUT_FILE.write_text(json.dumps(wynik, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Cuply: pobrano {len(turnieje)} turniejów -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
