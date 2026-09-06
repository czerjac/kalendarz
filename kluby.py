from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_URL = "https://kluby.org"
OUTPUT_FILE = Path("data/turnieje_kluby.json")
DETAIL_RE = re.compile(r"^/turnieje/(\d+)(?:/.*)?$")
DATE_RE = re.compile(
    r"Termin\s*:\s*(\d{4}/\d{2}/\d{2})(?:\s*\([^)]*\))?"
    r"(?:\s*-\s*(\d{4}/\d{2}/\d{2})(?:\s*\([^)]*\))?)?",
    re.I,
)
PLACE_RE = re.compile(r"Miejsce\s*:\s*(.+?)(?=\s+Kategorie\s*:|$)", re.I)
CATEGORIES_RE = re.compile(r"Kategorie\s*:\s*(.+)$", re.I)
CTA_RE = re.compile(r"^(?:ZAPISZ\s+SIĘ(?:\s+ONLINE)?\s+|ZAPISZ\s+SIE(?:\s+ONLINE)?\s+)", re.I)


def clean(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def calendar_url() -> str:
    start = date.today()
    end = start + timedelta(days=180)
    params = {
        "data_od": start.isoformat(),
        "data_do": end.isoformat(),
        "filtr": "1",
        "opcja": "kalendarz",
        "zakladka": "1",
    }
    return f"{BASE_URL}/tenis/turnieje?{urlencode(params)}"


def canonical_detail_url(href: str) -> str | None:
    try:
        parsed = urlparse(href)
    except ValueError:
        return None
    if parsed.netloc not in {"kluby.org", "www.kluby.org"}:
        return None
    match = DETAIL_RE.match(parsed.path.rstrip("/"))
    if not match:
        return None
    return urlunparse(("https", "kluby.org", f"/turnieje/{match.group(1)}", "", "", ""))


def parse_card_text(text: str, url: str) -> dict | None:
    value = clean(text)
    date_match = DATE_RE.search(value)
    if not date_match:
        return None

    before_date = clean(value[: date_match.start()])
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


def extract_cards(page) -> list[dict]:
    try:
        page.wait_for_function(
            "() => document.body && /Termin\\s*:/.test(document.body.innerText)",
            timeout=20000,
        )
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(1500)

    body_text = clean(page.locator("body").inner_text())
    blocked_tokens = ["403 forbidden", "access denied", "captcha", "cloudflare"]
    if any(token in body_text.casefold() for token in blocked_tokens):
        raise RuntimeError(f"Kluby.org zablokowało przeglądarkę. Początek strony: {body_text[:300]}")

    raw_cards = page.evaluate(
        r"""
        () => {
          const result = [];
          const seen = new Set();
          const anchors = [...document.querySelectorAll('a[href]')];
          for (const a of anchors) {
            let u;
            try { u = new URL(a.href, location.href); } catch { continue; }
            const match = u.pathname.match(/^\/turnieje\/(\d+)(?:\/.*)?$/);
            if (!match) continue;
            const id = match[1];
            if (seen.has(id)) continue;

            let node = a;
            let chosen = null;
            for (let i = 0; i < 10 && node; i++) {
              node = node.parentElement;
              if (!node) break;
              const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
              if (/Termin\s*:/.test(text) && /Kategorie\s*:/.test(text) && text.length <= 2000) {
                chosen = node;
                break;
              }
            }
            if (!chosen) continue;
            result.push({
              href: a.href,
              text: (chosen.innerText || '').replace(/\s+/g, ' ').trim()
            });
            seen.add(id);
          }
          return result;
        }
        """
    )

    if not raw_cards:
        debug = page.evaluate(
            r"""
            () => ({
              title: document.title,
              body: (document.body?.innerText || '').slice(0, 5000),
              links: [...document.querySelectorAll('a[href]')]
                .filter(a => (a.href || '').includes('turniej'))
                .slice(0, 80)
                .map(a => ({text: (a.innerText || '').replace(/\s+/g, ' ').trim(), href: a.href}))
            })
            """
        )
        print("KLUBY_DEBUG=" + json.dumps(debug, ensure_ascii=False))

    by_url: dict[str, dict] = {}
    for raw in raw_cards:
        url = canonical_detail_url(raw.get("href", ""))
        if not url:
            continue
        item = parse_card_text(raw.get("text", ""), url)
        if item:
            by_url[url] = item
    return list(by_url.values())


def main() -> None:
    source_url = calendar_url()
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
        response = page.goto(source_url, wait_until="domcontentloaded", timeout=45000)
        status = response.status if response else None
        print(f"Kluby.org: status HTTP przeglądarki: {status}")
        turnieje = extract_cards(page)
        browser.close()

    today = date.today().isoformat()
    turnieje = [item for item in turnieje if item["data_do"] >= today]
    turnieje.sort(key=lambda x: (x["data_od"], x["miasto"], x["nazwa"]))

    if not turnieje:
        raise RuntimeError(
            "Nie znaleziono żadnych przyszłych turniejów Kluby.org. "
            "W logu KLUBY_DEBUG znajduje się struktura strony do dopasowania parsera."
        )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    wynik = {
        "zrodlo": "Kluby.org",
        "adres_zrodla": source_url,
        "pobrano_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "liczba_turniejow": len(turnieje),
        "turnieje": turnieje,
    }
    OUTPUT_FILE.write_text(
        json.dumps(wynik, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Kluby.org: pobrano {len(turnieje)} turniejów -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
