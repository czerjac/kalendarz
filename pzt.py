from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://top.pzt.pl/Kalendarz.aspx"
OUTPUT_FILE = Path("data/turnieje_pzt.json")
DATE_RANGE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})")


def clean(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def pobierz_turnieje() -> list[dict]:
    response = requests.get(
        SOURCE_URL,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0 Safari/537.36"
            )
        },
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"

    soup = BeautifulSoup(response.text, "html.parser")
    turnieje: list[dict] = []

    for row in soup.find_all("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 5:
            continue

        lp = clean(cells[0].get_text(" ", strip=True))
        if not lp.isdigit():
            continue

        date_text = clean(cells[4].get_text(" ", strip=True))
        match = DATE_RANGE_RE.search(date_text)
        if not match:
            continue

        name_cell = cells[1]
        link = name_cell.find("a", href=True)
        if not link:
            continue

        name = clean(link.get_text(" ", strip=True))
        details = clean(name_cell.get_text(" ", strip=True))
        categories = ""
        if "Kategorie:" in details:
            categories = details.split("Kategorie:", 1)[1].strip(" ,")

        turnieje.append(
            {
                "zrodlo": "PZT TOP",
                "nazwa": name,
                "data_od": match.group(1),
                "data_do": match.group(2),
                "miasto": clean(cells[3].get_text(" ", strip=True)),
                "ranga": clean(cells[2].get_text(" ", strip=True)),
                "kategorie": categories,
                "url": urljoin(SOURCE_URL, link["href"]),
            }
        )

    if not turnieje:
        raise RuntimeError(
            "Nie znaleziono żadnych turniejów PZT. Strona mogła zmienić układ."
        )

    turnieje.sort(key=lambda x: (x["data_od"], x["miasto"], x["nazwa"]))
    return turnieje


def main() -> None:
    turnieje = pobierz_turnieje()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    wynik = {
        "zrodlo": "PZT TOP",
        "adres_zrodla": SOURCE_URL,
        "pobrano_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "liczba_turniejow": len(turnieje),
        "turnieje": turnieje,
    }

    OUTPUT_FILE.write_text(
        json.dumps(wynik, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"PZT: pobrano {len(turnieje)} turniejów -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
