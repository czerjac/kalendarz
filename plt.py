from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_URL = "https://polskaligatenisa.pl"
START_URL = f"{BASE_URL}/turnieje/puchar-plt/lista-rund"
OUTPUT_FILE = Path("data/turnieje_plt.json")

FALLBACK_CATEGORIES = {
    "Puchar PLT": f"{BASE_URL}/turnieje/puchar-plt/lista-rund",
    "1. Liga": f"{BASE_URL}/turnieje/polska-i-liga-tenisa/lista-rund",
    "2. Liga": f"{BASE_URL}/turnieje/polska-ii-liga-tenisa/lista-rund",
    "PLT Kobiet": f"{BASE_URL}/turnieje/polska-liga-tenisa-kobiet/lista-rund",
    "Deble i Miksty": f"{BASE_URL}/turnieje/deble-miksty/lista-rund",
    "Kategorie wiekowe": f"{BASE_URL}/turnieje/polska-liga-tenisa-45/lista-rund",
}

MONTHS = {
    "stycznia": 1, "styczen": 1, "styczeń": 1,
    "lutego": 2, "luty": 2,
    "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecien": 4, "kwiecień": 4,
    "maja": 5, "maj": 5,
    "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7,
    "sierpnia": 8, "sierpien": 8, "sierpień": 8,
    "wrzesnia": 9, "września": 9, "wrzesien": 9, "wrzesień": 9,
    "pazdziernika": 10, "października": 10, "pazdziernik": 10, "październik": 10,
    "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzien": 12, "grudzień": 12,
}

CTA_RE = re.compile(r"^(zobacz więcej|sprawdź wyniki|wez udział|weź udział)$", re.I)
DATE_LINE_RE = re.compile(
    r"^\d{1,2}(?:\s*-\s*\d{1,2})?\s+[A-Za-zĄąĆćĘęŁłŃńÓóŚśŹźŻż]+(?:\s*-\s*\d{1,2}\s+[A-Za-zĄąĆćĘęŁłŃńÓóŚśŹźŻż]+)?(?:\s+\d{4})?$"
)


def clean(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def canonical_list_url(href: str) -> str | None:
    try:
        parsed = urlparse(href)
    except ValueError:
        return None
    if parsed.netloc not in {"polskaligatenisa.pl", "www.polskaligatenisa.pl"}:
        return None
    if "/turnieje/" not in parsed.path or not parsed.path.rstrip("/").endswith("/lista-rund"):
        return None
    return urlunparse(("https", "polskaligatenisa.pl", parsed.path.rstrip("/"), "", "", ""))


def parse_polish_date_line(text: str, season_year: int) -> tuple[str, str] | None:
    value = clean(text).lower().replace("–", "-").replace("—", "-")

    m = re.fullmatch(
        r"(\d{1,2})\s+([a-ząćęłńóśźż]+)\s*-\s*(\d{1,2})\s+([a-ząćęłńóśźż]+)(?:\s+(\d{4}))?",
        value,
    )
    if m:
        d1, mon1, d2, mon2, year = m.groups()
        if mon1 not in MONTHS or mon2 not in MONTHS:
            return None
        y2 = int(year or season_year)
        y1 = y2 - 1 if MONTHS[mon1] > MONTHS[mon2] else y2
        return (
            date(y1, MONTHS[mon1], int(d1)).isoformat(),
            date(y2, MONTHS[mon2], int(d2)).isoformat(),
        )

    m = re.fullmatch(
        r"(\d{1,2})\s*-\s*(\d{1,2})\s+([a-ząćęłńóśźż]+)(?:\s+(\d{4}))?",
        value,
    )
    if m:
        d1, d2, month, year = m.groups()
        if month not in MONTHS:
            return None
        y = int(year or season_year)
        return (
            date(y, MONTHS[month], int(d1)).isoformat(),
            date(y, MONTHS[month], int(d2)).isoformat(),
        )

    m = re.fullmatch(r"(\d{1,2})\s+([a-ząćęłńóśźż]+)(?:\s+(\d{4}))?", value)
    if m:
        day, month, year = m.groups()
        if month not in MONTHS:
            return None
        y = int(year or season_year)
        d = date(y, MONTHS[month], int(day)).isoformat()
        return d, d
    return None


def title_from_lines(lines: list[str], date_index: int) -> str:
    cta_index = next((i for i, line in enumerate(lines) if CTA_RE.match(line)), date_index)
    candidates = []
    for line in lines[:cta_index]:
        low = line.casefold()
        if len(line) < 5:
            continue
        if low.startswith("turniej cyklu") or re.fullmatch(r"x\d+", low):
            continue
        if low in {"logo", "katering"} or "sezon 20" in low:
            continue
        candidates.append(line)
    if not candidates:
        candidates = [line for line in lines[:date_index] if len(line) >= 5 and not CTA_RE.match(line)]
    return max(candidates, key=len) if candidates else ""


def city_from_lines(lines: list[str], date_index: int, title: str) -> str:
    for i in range(date_index - 1, -1, -1):
        line = lines[i]
        low = line.casefold()
        if line == title or CTA_RE.match(line):
            continue
        if low.startswith("turniej cyklu") or re.fullmatch(r"x\d+", low):
            continue
        if low in {"logo", "katering"} or len(line) > 80:
            continue
        return line
    return ""


def extract_cards(page, category_name: str) -> list[dict]:
    try:
        page.wait_for_function(
            "() => !document.body.innerText.includes('Trwa ładowanie...')",
            timeout=12000,
        )
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(1200)
    season_year = datetime.now().year
    body_text = clean(page.locator("body").inner_text())
    m = re.search(r"Sezon\s+(20\d{2})", body_text, re.I)
    if m:
        season_year = int(m.group(1))

    raw_cards = page.evaluate(
        r"""
        () => {
          const ctaRe = /^(Zobacz więcej|Sprawdź wyniki|Weź udział|Wez udział)$/i;
          const monthRe = /(stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|wrzesnia|października|pazdziernika|listopada|grudnia)/i;
          const result = [];
          const seen = new Set();
          const links = [...document.querySelectorAll('a')].filter(a => ctaRe.test((a.innerText || '').trim()));

          for (const a of links) {
            const href = a.href;
            if (!href || seen.has(href)) continue;

            let node = a;
            let chosen = null;
            let fallback = null;
            for (let i = 0; i < 10 && node; i++) {
              node = node.parentElement;
              if (!node) break;
              const txt = (node.innerText || '').trim();
              if (txt.length < 25 || txt.length > 1600 || !monthRe.test(txt)) continue;

              if (!fallback) fallback = node;
              const hasTitleYear = /20\d{2}/.test(txt);
              const ctaCount = [...node.querySelectorAll('a')].filter(x => ctaRe.test((x.innerText || '').trim())).length;
              if (hasTitleYear && ctaCount >= 1 && ctaCount <= 4) {
                chosen = node;
                break;
              }
            }
            chosen = chosen || fallback;
            if (!chosen) continue;

            const lines = (chosen.innerText || '')
              .split(/\n+/)
              .map(x => x.replace(/\s+/g, ' ').trim())
              .filter(Boolean);
            result.push({href, lines});
            seen.add(href);
          }
          return result;
        }
        """
    )

    items: list[dict] = []
    for raw in raw_cards:
        lines = [clean(x) for x in raw.get("lines", []) if clean(x)]
        date_index = -1
        parsed_dates = None
        for i, line in enumerate(lines):
            if DATE_LINE_RE.match(line):
                parsed_dates = parse_polish_date_line(line, season_year)
                if parsed_dates:
                    date_index = i
                    break
        if date_index < 0 or not parsed_dates:
            continue

        title = title_from_lines(lines, date_index)
        city = city_from_lines(lines, date_index, title)
        if not title:
            continue
        data_od, data_do = parsed_dates
        items.append({
            "zrodlo": "PLT",
            "kategoria": category_name,
            "nazwa": title,
            "data_od": data_od,
            "data_do": data_do,
            "miasto": city,
            "url": raw["href"],
        })
    return items


def discover_categories(page) -> dict[str, str]:
    categories = dict(FALLBACK_CATEGORIES)
    page.goto(START_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1800)
    links = page.evaluate(
        r"""
        () => [...document.querySelectorAll('a[href]')].map(a => ({
          text: (a.innerText || '').replace(/\s+/g, ' ').trim(),
          href: a.href
        }))
        """
    )
    for item in links:
        url = canonical_list_url(item.get("href", ""))
        text = clean(item.get("text", ""))
        if not url or not text:
            continue
        folded = text.casefold()
        if any(token in folded for token in ["puchar plt", "1. liga", "2. liga", "plt kobiet", "deble", "miksty", "wiekowe", "45+"]):
            categories[text] = url

    by_url: dict[str, str] = {}
    for name, url in categories.items():
        if url not in by_url or len(name) < len(by_url[url]):
            by_url[url] = name
    return {name: url for url, name in by_url.items()}


def main() -> None:
    all_items: list[dict] = []
    errors: list[str] = []
    checked: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="pl-PL",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(15000)
        categories = discover_categories(page)

        for category_name, base_url in categories.items():
            incoming_url = f"{base_url}?incoming=true"
            try:
                page.goto(incoming_url, wait_until="domcontentloaded", timeout=45000)
                items = extract_cards(page, category_name)
                checked.append({"kategoria": category_name, "url": incoming_url, "liczba": len(items)})
                all_items.extend(items)
                print(f"PLT: {category_name}: {len(items)} turniejów")
            except Exception as exc:
                errors.append(f"{category_name}: {type(exc).__name__}: {exc}")
                print(f"PLT: błąd dla {category_name}: {exc}")
        browser.close()

    unique: dict[tuple[str, str, str, str], dict] = {}
    for item in all_items:
        key = (item["kategoria"], item["nazwa"], item["data_od"], item["miasto"])
        unique[key] = item

    turnieje = sorted(unique.values(), key=lambda x: (x["data_od"], x["miasto"], x["nazwa"]))
    if not turnieje:
        raise RuntimeError("Nie znaleziono żadnych nadchodzących turniejów PLT.")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    wynik = {
        "zrodlo": "PLT",
        "adres_startowy": START_URL,
        "pobrano_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "liczba_turniejow": len(turnieje),
        "kategorie_sprawdzone": checked,
        "bledy": errors,
        "turnieje": turnieje,
    }
    OUTPUT_FILE.write_text(json.dumps(wynik, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PLT: łącznie pobrano {len(turnieje)} turniejów -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
