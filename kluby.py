from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_URL = "https://kluby.org"
OUTPUT_FILE = Path("data/turnieje_kluby.json")
DETAIL_RE = re.compile(r"^/turnieje/(\d+)(?:/.*)?$")
DETAIL_IN_HTML_RE = re.compile(r"(?:https?://(?:www\.)?kluby\.org)?(/turnieje/\d+)")
DATE_RE = re.compile(
    r"Termin\s*:\s*(\d{4}/\d{2}/\d{2})(?:\s*\([^)]*\))?"
    r"(?:\s*-\s*(\d{4}/\d{2}/\d{2})(?:\s*\([^)]*\))?)?",
    re.I,
)
PLACE_RE = re.compile(r"Miejsce\s*:\s*(.+?)(?=\s+Kategorie\s*:|$)", re.I)
CATEGORIES_RE = re.compile(r"Kategorie\s*:\s*(.+)$", re.I)
CTA_RE = re.compile(r"^(?:ZAPISZ\s+SIĘ(?:\s+ONLINE)?|ZAPISZ\s+SIE(?:\s+ONLINE)?)\s*", re.I)
DAY_HEADER_RE = re.compile(
    r"^(?:Poniedziałek|Wtorek|Środa|Czwartek|Piątek|Sobota|Niedziela),\s+"
    r"\d{1,2}\s+[A-Za-zĄąĆćĘęŁłŃńÓóŚśŹźŻż]+\s+\d{4}r?\.?(?:\s+|$)",
    re.I,
)


def clean(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def add_months(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(total, 12)
    return date(year, month0 + 1, 1)


def month_urls(months_ahead: int = 6) -> list[str]:
    first = date.today().replace(day=1)
    urls: list[str] = []
    for offset in range(months_ahead + 1):
        start = add_months(first, offset)
        last_day = calendar.monthrange(start.year, start.month)[1]
        end = date(start.year, start.month, last_day)
        params = {
            "filtr": "1",
            "opcja": "kalendarz",
            "data_od": start.isoformat(),
            "data_do": end.isoformat(),
            # 0 = wszystkie kategorie; 1 oznacza tylko OPEN.
            "zakladka": "0",
        }
        urls.append(f"{BASE_URL}/tenis/turnieje?{urlencode(params)}")
    return urls


def canonical_detail_url(href: str) -> str | None:
    try:
        parsed = urlparse(href)
    except ValueError:
        return None
    if parsed.netloc and parsed.netloc not in {"kluby.org", "www.kluby.org"}:
        return None
    match = DETAIL_RE.match(parsed.path.rstrip("/"))
    if not match:
        return None
    return urlunparse(("https", "kluby.org", f"/turnieje/{match.group(1)}", "", "", ""))


def detail_url_from_raw(raw: dict, fallback_url: str) -> str:
    href = raw.get("href") or ""
    canonical = canonical_detail_url(href)
    if canonical:
        return canonical

    html = raw.get("html") or ""
    match = DETAIL_IN_HTML_RE.search(html)
    if match:
        return f"{BASE_URL}{match.group(1)}"
    return fallback_url


def parse_card_text(text: str, url: str) -> dict | None:
    value = clean(text)
    date_match = DATE_RE.search(value)
    if not date_match:
        return None

    before_date = clean(value[: date_match.start()])
    before_date = DAY_HEADER_RE.sub("", before_date).strip()
    name = CTA_RE.sub("", before_date).strip(" -–—")
    if not name or len(name) < 3:
        return None

    start_raw, end_raw = date_match.groups()
    start = datetime.strptime(start_raw, "%Y/%m/%d").date().isoformat()
    end = datetime.strptime(end_raw or start_raw, "%Y/%m/%d").date().isoformat()

    place_match = PLACE_RE.search(value)
    place = clean(place_match.group(1)) if place_match else ""
    city = ""
    if place:
        parts = [clean(part) for part in place.split(",") if clean(part)]
        city = parts[-1] if parts else place

    categories_match = CATEGORIES_RE.search(value)
    categories = clean(categories_match.group(1)) if categories_match else ""

    return {
        "zrodlo": "Kluby.org",
        "nazwa": name,
        "data_od": start,
        "data_do": end,
        "miasto": city,
        "miejsce": place,
        "kategorie": categories,
        "url": url,
    }


def extract_cards(page, source_url: str) -> list[dict]:
    try:
        page.wait_for_function(
            "() => document.body && /Termin\\s*:/.test(document.body.innerText)",
            timeout=15000,
        )
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(800)

    body_text = clean(page.locator("body").inner_text())
    blocked_tokens = ["403 forbidden", "access denied", "captcha", "cloudflare"]
    if any(token in body_text.casefold() for token in blocked_tokens):
        raise RuntimeError("Kluby.org zablokowało automatyczną przeglądarkę")

    raw_cards = page.evaluate(
        r"""
        () => {
          const selectors = 'div, li, article, section, td';
          const all = [...document.querySelectorAll(selectors)];
          const candidates = all.filter(el => {
            const text = (el.innerText || '').replace(/\s+/g, ' ').trim();
            const terminCount = (text.match(/Termin\s*:/g) || []).length;
            return terminCount === 1 && /Kategorie\s*:/.test(text) && text.length >= 25 && text.length <= 2000;
          });

          // Zostaw najmniejszy sensowny element zawierający dokładnie jeden turniej.
          const minimal = candidates.filter(el => ![...el.children].some(ch => {
            const text = (ch.innerText || '').replace(/\s+/g, ' ').trim();
            return (text.match(/Termin\s*:/g) || []).length === 1 && /Kategorie\s*:/.test(text) && text.length >= 25;
          }));

          return minimal.map(el => {
            const link = el.querySelector('a[href*="/turnieje/"]') || el.closest('a[href*="/turnieje/"]');
            return {
              text: (el.innerText || '').replace(/\s+/g, ' ').trim(),
              href: link ? link.href : '',
              html: el.outerHTML.slice(0, 5000)
            };
          });
        }
        """
    )

    by_key: dict[tuple[str, str, str, str], dict] = {}
    for raw in raw_cards:
        url = detail_url_from_raw(raw, source_url)
        item = parse_card_text(raw.get("text", ""), url)
        if not item:
            continue
        key = (item["nazwa"], item["data_od"], item["data_do"], item["miasto"])
        by_key[key] = item
    return list(by_key.values())


def main() -> None:
    urls = month_urls(6)
    all_items: list[dict] = []
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
        page.set_default_timeout(20000)

        for source_url in urls:
            response = page.goto(source_url, wait_until="domcontentloaded", timeout=45000)
            status = response.status if response else None
            if status and status >= 400:
                raise RuntimeError(f"Kluby.org zwróciło HTTP {status}: {source_url}")
            items = extract_cards(page, source_url)
            checked.append({"url": source_url, "liczba": len(items)})
            all_items.extend(items)
            print(f"Kluby.org: {source_url}: {len(items)} turniejów")

        browser.close()

    today = date.today().isoformat()
    unique: dict[tuple[str, str, str, str], dict] = {}
    for item in all_items:
        if item["data_do"] < today:
            continue
        key = (item["nazwa"], item["data_od"], item["data_do"], item["miasto"])
        # Preferuj bezpośredni link do turnieju, jeśli któryś duplikat go ma.
        current = unique.get(key)
        if current is None or ("/turnieje/" in item["url"] and "/tenis/turnieje?" in current["url"]):
            unique[key] = item

    turnieje = sorted(unique.values(), key=lambda x: (x["data_od"], x["miasto"], x["nazwa"]))
    if not turnieje:
        raise RuntimeError("Nie znaleziono żadnych przyszłych turniejów Kluby.org")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    wynik = {
        "zrodlo": "Kluby.org",
        "pobrano_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "liczba_turniejow": len(turnieje),
        "miesiace_sprawdzone": checked,
        "turnieje": turnieje,
    }
    OUTPUT_FILE.write_text(
        json.dumps(wynik, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Kluby.org: łącznie pobrano {len(turnieje)} turniejów -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
