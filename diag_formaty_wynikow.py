from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path("data/archiwum/2026")
OUT = Path("data/diagnostyka_wynikow_2026.json")

PZT_SAMPLES = [
    {
        "label": "PZT_MP_TOP_2026",
        "url": "https://portal.pzt.pl/TournamentResults.aspx?CategoryID=AIS&Male=&TournamentID=32C58E6F-6764-4169-BF5E-8384BE371F3E",
    },
    {
        "label": "PZT_MP_LEKARZY_2026",
        "url": "https://portal.pzt.pl/TournamentResults.aspx?CategoryID=AIS&Male=&TournamentID=58D439BD-7886-4A0A-B3BC-B88DCDB1810B",
    },
    {
        "label": "PZT_MIXT_ARKADEMIA_2026",
        "url": "https://portal.pzt.pl/TournamentResults.aspx?CategoryID=AIS&Male=&TournamentID=E6FA8E4E-5F51-4FEC-9F38-C71D438B323E",
    },
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pick_samples() -> list[dict]:
    samples = list(PZT_SAMPLES)

    plt_items = load(ROOT / "zrodla/plt.json").get("turnieje", [])
    wanted_plt = ["1. Liga", "2. Liga", "Puchar PLT", "PLT Kobiet", "Deble i Miksty", "Kategorie wiekowe"]
    for cat in wanted_plt:
        item = next((x for x in plt_items if x.get("kategoria") == cat and x.get("url")), None)
        if item:
            samples.append({"label": f"PLT_{cat}", "url": item["url"], "meta": item})

    cuply_items = load(ROOT / "zrodla/cuply.json").get("turnieje", [])
    for i, item in enumerate(cuply_items[:3], 1):
        if item.get("url"):
            samples.append({"label": f"Cuply_{i}", "url": item["url"], "meta": item})

    kluby_items = load(ROOT / "zrodla/kluby.json").get("turnieje", [])
    predicates = [
        ("Kluby_MIKST", lambda x: "MIKST" in (x.get("kategorie") or "").upper() or "MIXT" in (x.get("nazwa") or "").upper()),
        ("Kluby_DEBEL", lambda x: "DEBEL" in (x.get("kategorie") or "").upper()),
        ("Kluby_WIELE_KAT", lambda x: len((x.get("kategorie") or "").split()) >= 5),
    ]
    used = set()
    for label, pred in predicates:
        item = next((x for x in kluby_items if x.get("url") and x.get("url") not in used and pred(x)), None)
        if item:
            used.add(item["url"])
            samples.append({"label": label, "url": item["url"], "meta": item})

    return samples


def host_ok(url: str) -> bool:
    return urlparse(url).netloc in {
        "portal.pzt.pl",
        "polskaligatenisa.pl", "www.polskaligatenisa.pl",
        "cuply.pl", "www.cuply.pl",
        "kluby.org", "www.kluby.org",
    }


def inspect_page(context, sample: dict) -> dict:
    page = context.new_page()
    network = []
    popups = []

    def on_response(resp):
        if not host_ok(resp.url):
            return
        rt = resp.request.resource_type
        ctype = resp.headers.get("content-type", "")
        if rt in {"xhr", "fetch", "document"} or "json" in ctype.lower():
            network.append({
                "url": resp.url,
                "status": resp.status,
                "resource_type": rt,
                "content_type": ctype,
                "method": resp.request.method,
            })

    def on_popup(p):
        try:
            p.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        try:
            popups.append({"url": p.url, "title": p.title(), "text": p.locator("body").inner_text()[:12000]})
        except Exception as exc:
            popups.append({"url": p.url, "error": f"{type(exc).__name__}: {exc}"})

    page.on("response", on_response)
    page.on("popup", on_popup)
    result = {"label": sample["label"], "url": sample["url"], "meta": sample.get("meta", {})}
    try:
        page.goto(sample["url"], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        result["final_url"] = page.url
        result["title"] = page.title()
        result["body_text"] = page.locator("body").inner_text()[:30000]
        result["elements"] = page.evaluate(
            r"""
            () => [...document.querySelectorAll('a,button,input,[onclick]')]
              .map((el, i) => ({
                i,
                tag: el.tagName,
                text: ((el.innerText || el.value || el.getAttribute('aria-label') || '') + '').replace(/\s+/g,' ').trim().slice(0,250),
                href: el.href || el.getAttribute('href') || '',
                onclick: el.getAttribute('onclick') || '',
                target: el.getAttribute('target') || '',
                type: el.getAttribute('type') || '',
                id: el.id || '',
                name: el.getAttribute('name') || ''
              }))
              .filter(x => x.text || x.href || x.onclick)
              .slice(0,600)
            """
        )

        # W PZT sprawdź elementy wyglądające na uruchamiające szczegóły drabinki.
        if "portal.pzt.pl" in page.url:
            candidates = page.locator("[onclick], a[target='_blank'], a[href*='Draw'], a[href*='Match']")
            for idx in range(min(candidates.count(), 12)):
                el = candidates.nth(idx)
                try:
                    txt = (el.inner_text() or el.get_attribute("value") or "").strip()
                    onclick = el.get_attribute("onclick") or ""
                    href = el.get_attribute("href") or ""
                    if not (re.search(r"draw|drab|group|grup|match|mecz|window\.open", f"{txt} {onclick} {href}", re.I)):
                        continue
                    try:
                        with page.expect_popup(timeout=2500):
                            el.click(timeout=2500)
                        page.wait_for_timeout(500)
                    except Exception:
                        pass
                except Exception:
                    pass

        result["network"] = network[:400]
        result["popups"] = popups[:30]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["network"] = network[:400]
        result["popups"] = popups[:30]
    finally:
        page.close()
    return result


def main() -> None:
    samples = pick_samples()
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="pl-PL")
        for sample in samples:
            print("DIAG:", sample["label"], sample["url"])
            results.append(inspect_page(context, sample))
        browser.close()

    payload = {"liczba_probek": len(results), "probki": results}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Zapisano", OUT, "próbek:", len(results))


if __name__ == "__main__":
    main()
