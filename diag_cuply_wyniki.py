from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

OUT = Path("data/diagnostyka_cuply_wyniki.json")
SAMPLES = [
    {
        "label": "singiel_grupy_playoff",
        "url": "https://cuply.pl/turnieje/cuply-challenger-gryfino-i",
    },
    {
        "label": "singiel_masters",
        "url": "https://cuply.pl/turnieje/cuply-stargard-masters-zaawansowani-amatorzy",
    },
    {
        "label": "debel",
        "url": "https://cuply.pl/turnieje/duo-zoom-brejk-open-iii",
    },
]
TABS = ["Uczestnicy", "Pary", "Grupy", "Fazy pucharowe", "Wyniki"]


def is_cuply(url: str) -> bool:
    return urlparse(url).netloc in {"cuply.pl", "www.cuply.pl"}


def compact(value: str, limit: int = 120000) -> str:
    return (value or "")[:limit]


def inspect(page, sample: dict) -> dict:
    network = []

    def on_response(resp):
        if not is_cuply(resp.url):
            return
        rt = resp.request.resource_type
        ctype = resp.headers.get("content-type", "")
        if rt not in {"xhr", "fetch", "document"} and "json" not in ctype.lower():
            return
        entry = {
            "url": resp.url,
            "status": resp.status,
            "resource_type": rt,
            "content_type": ctype,
            "method": resp.request.method,
            "post_data": compact(resp.request.post_data or "", 30000),
        }
        if rt in {"xhr", "fetch"} and any(x in ctype.lower() for x in ("json", "text", "html")):
            try:
                entry["body"] = compact(resp.text(), 100000)
            except Exception as exc:
                entry["body_error"] = f"{type(exc).__name__}: {exc}"
        network.append(entry)

    page.on("response", on_response)
    result = {"label": sample["label"], "url": sample["url"], "tabs": {}}
    page.goto(sample["url"], wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500)

    result["final_url"] = page.url
    result["title"] = page.title()
    result["initial_text"] = compact(page.locator("body").inner_text(), 30000)
    result["scripts"] = page.eval_on_selector_all(
        "script[src]", "els => els.map(x => x.src).filter(Boolean)"
    )
    result["wire_elements"] = page.evaluate(
        r"""
        () => [...document.querySelectorAll('*')]
          .filter(el => [...el.attributes].some(a => a.name.startsWith('wire:')))
          .slice(0,300)
          .map(el => ({
            tag: el.tagName,
            text: (el.innerText || '').replace(/\s+/g,' ').trim().slice(0,300),
            attrs: Object.fromEntries([...el.attributes]
              .filter(a => a.name.startsWith('wire:'))
              .map(a => [a.name, a.value]))
          }))
        """
    )
    result["buttons"] = page.evaluate(
        r"""
        () => [...document.querySelectorAll('button,a')].map(el => ({
          tag: el.tagName,
          text: (el.innerText || '').replace(/\s+/g,' ').trim(),
          href: el.href || '',
          cls: el.className || '',
          type: el.getAttribute('type') || ''
        })).filter(x => x.text).slice(0,500)
        """
    )

    for tab in TABS:
        before = len(network)
        locator = page.get_by_text(tab, exact=True)
        if locator.count() == 0:
            result["tabs"][tab] = {"found": False}
            continue
        try:
            locator.first.click(timeout=5000)
            page.wait_for_timeout(1800)
            result["tabs"][tab] = {
                "found": True,
                "url": page.url,
                "text": compact(page.locator("body").inner_text(), 50000),
                "html": compact(page.locator("body").inner_html(), 140000),
                "new_network": network[before:],
            }
        except Exception as exc:
            result["tabs"][tab] = {"found": True, "error": f"{type(exc).__name__}: {exc}"}

    result["network"] = network[:250]
    return result


def main() -> None:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="pl-PL", viewport={"width": 1440, "height": 1200})
        for sample in SAMPLES:
            page = context.new_page()
            try:
                print("CUPLY DIAG", sample["label"], sample["url"], flush=True)
                results.append(inspect(page, sample))
            except Exception as exc:
                results.append({**sample, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                page.close()
        browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"samples": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Zapisano", OUT, flush=True)


if __name__ == "__main__":
    main()
