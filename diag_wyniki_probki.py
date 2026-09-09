from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ROOT = Path("data/archiwum/2026")
OUT = ROOT / "diag_wyniki_probki.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
    )
}
KEYWORDS = re.compile(r"wynik|drabink|mecz|grup|faza|play.?off|zwyci|klasyfik", re.I)


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def clean(value) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def clip(value: str, limit: int = 20000) -> str:
    value = value or ""
    return value if len(value) <= limit else value[:limit] + "\n...[ucięto]"


def uniq_samples(rows: list[dict], limit: int) -> list[dict]:
    out = []
    seen = set()
    for row in rows:
        url = clean(row.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def choose_samples() -> list[dict]:
    result: list[dict] = []

    # PZT: turniej wielokategoriowy / mistrzostwa + zwykły + przykład bez wyników.
    pzt_cache = load(ROOT / "pzt_szczegoly.json", {"turnieje": {}}).get("turnieje", {})
    pzt_rows = []
    for entry in pzt_cache.values():
        data = entry.get("dane", {})
        pzt_rows.append({
            "zrodlo": "PZT TOP",
            "nazwa": entry.get("nazwa", ""),
            "url": entry.get("url", ""),
            "kategorie": data.get("kategorie", ""),
            "wyniki_potwierdzone": bool(data.get("wyniki_potwierdzone")),
        })
    pzt_rows.sort(key=lambda x: clean(x.get("kategorie")).count(","), reverse=True)
    pzt_pick = []
    pzt_pick += [x for x in pzt_rows if "mistrzostw polski" in clean(x.get("nazwa")).casefold()][:2]
    pzt_pick += [x for x in pzt_rows if x.get("wyniki_potwierdzone")][:2]
    pzt_pick += [x for x in pzt_rows if not x.get("wyniki_potwierdzone")][:1]
    result += uniq_samples(pzt_pick, 5)

    # PLT: po jednym przykładzie głównych systemów/kategorii.
    plt_rows = load(ROOT / "zrodla/plt.json", {"turnieje": []}).get("turnieje", [])
    priorities = ["Puchar PLT", "1. Liga", "2. Liga", "PLT Kobiet", "Deble i Miksty", "Kategorie wiekowe"]
    for cat in priorities:
        candidates = [x for x in plt_rows if clean(x.get("kategoria")).casefold() == cat.casefold()]
        if candidates:
            result.append(candidates[0])
    # Jeśli źródłowe etykiety deblowe/mikstowe są bardziej szczegółowe, dobierz po nazwie.
    for token in ["DEBEL", "MIKST"]:
        candidates = [x for x in plt_rows if token in clean(x.get("nazwa")).upper()]
        if candidates:
            result += uniq_samples(candidates, 1)

    # Cuply: zwykły + potencjalny debel/mikst/grupy.
    cuply_rows = load(ROOT / "zrodla/cuply.json", {"turnieje": []}).get("turnieje", [])
    special = [x for x in cuply_rows if re.search(r"debel|mikst|double|mix", clean(x.get("nazwa")), re.I)]
    result += uniq_samples(special + cuply_rows, 3)

    # Kluby.org: debel/mikst + singiel.
    kluby_rows = load(ROOT / "zrodla/kluby.json", {"turnieje": []}).get("turnieje", [])
    special = [x for x in kluby_rows if re.search(r"debel|mikst", clean(x.get("kategorie")) + " " + clean(x.get("nazwa")), re.I)]
    singles = [x for x in kluby_rows if re.search(r"open|sing", clean(x.get("kategorie")) + " " + clean(x.get("nazwa")), re.I)]
    result += uniq_samples(special + singles, 3)

    # Usuń duplikaty URL między wszystkimi źródłami.
    final = []
    seen = set()
    for row in result:
        url = clean(row.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        final.append({
            "zrodlo": clean(row.get("zrodlo")),
            "nazwa": clean(row.get("nazwa")),
            "url": url,
            "kategoria": clean(row.get("kategoria")),
            "kategorie": clean(row.get("kategorie")),
        })
    return final


def static_probe(sample: dict) -> dict:
    url = sample["url"]
    try:
        r = requests.get(url, headers=HEADERS, timeout=35)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        body = clean(soup.get_text("\n", strip=True))
        links = []
        for a in soup.find_all(["a", "button", "input"]):
            text = clean(a.get_text(" ", strip=True) or a.get("value") or a.get("title"))
            href = clean(a.get("href"))
            onclick = clean(a.get("onclick"))
            blob = " ".join([text, href, onclick])
            if KEYWORDS.search(blob):
                links.append({"text": text, "href": href, "onclick": onclick, "target": clean(a.get("target"))})
        scripts = []
        for script in soup.find_all("script"):
            txt = script.string or script.get_text(" ", strip=True)
            if txt and (KEYWORDS.search(txt) or "window.open" in txt):
                scripts.append(clip(clean(txt), 4000))
        return {
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("content-type", ""),
            "text": clip(body),
            "relevant_controls": links[:100],
            "relevant_scripts": scripts[:20],
        }
    except Exception as exc:
        return {"blad": f"{type(exc).__name__}: {exc}"}


def browser_probe(browser, sample: dict) -> dict:
    context = browser.new_context(locale="pl-PL", user_agent=HEADERS["User-Agent"])
    page = context.new_page()
    network = []

    def on_response(response):
        try:
            req_type = response.request.resource_type
            content_type = response.headers.get("content-type", "")
            if req_type not in {"xhr", "fetch"} and "json" not in content_type.lower():
                return
            row = {
                "url": response.url,
                "status": response.status,
                "resource_type": req_type,
                "content_type": content_type,
            }
            try:
                if any(x in content_type.lower() for x in ["json", "text", "javascript"]):
                    row["body"] = clip(response.text(), 12000)
            except Exception:
                pass
            network.append(row)
        except Exception:
            pass

    page.on("response", on_response)
    try:
        page.goto(sample["url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4500)
        try:
            body_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            body_text = ""

        controls = page.evaluate(
            r"""
            () => [...document.querySelectorAll('a,button,input[type="button"],input[type="submit"]')]
              .map(el => ({
                tag: el.tagName,
                text: (el.innerText || el.value || el.title || '').replace(/\s+/g,' ').trim(),
                href: el.href || el.getAttribute('href') || '',
                onclick: el.getAttribute('onclick') || '',
                target: el.getAttribute('target') || '',
                id: el.id || '',
                cls: el.className || ''
              }))
              .filter(x => /wynik|drabink|mecz|grup|faza|play.?off|zwyci|klasyfik/i.test(
                 [x.text,x.href,x.onclick,x.id,String(x.cls)].join(' ')
              ))
              .slice(0,150)
            """
        )
        frames = [f.url for f in page.frames if f.url]
        return {
            "final_url": page.url,
            "title": page.title(),
            "text": clip(body_text),
            "relevant_controls": controls,
            "frames": frames,
            "network": network[:120],
        }
    except Exception as exc:
        return {"blad": f"{type(exc).__name__}: {exc}", "network": network[:120]}
    finally:
        context.close()


def main() -> None:
    samples = choose_samples()
    payload = {"liczba_probek": len(samples), "probki": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for i, sample in enumerate(samples, 1):
            print(f"[{i}/{len(samples)}] {sample['zrodlo']}: {sample['nazwa']}")
            payload["probki"].append({
                **sample,
                "static": static_probe(sample),
                "browser": browser_probe(browser, sample),
            })
        browser.close()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Zapisano {OUT} ({OUT.stat().st_size} B)")


if __name__ == "__main__":
    main()
