from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

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
STRUCT_RE = re.compile(
    r"grup|faza|puchar|drabink|mecz|wynik|fina|ćwierć|cwierc|półfina|polfina|"
    r"turniej główny|turniej glowny|system turnieju|gra pojedyncza|gra podwójna|mieszany",
    re.I,
)
POPUP_RE = re.compile(r"popUpGroup\(['\"]([^'\"]+)['\"]\)", re.I)


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def clean(value) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def get(url: str, timeout: int = 40) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r


def structural_lines(text: str, limit: int = 80) -> list[str]:
    lines = []
    seen = set()
    for raw in (text or "").splitlines():
        line = clean(raw)
        if not line or not STRUCT_RE.search(line):
            continue
        # Nie zapisujemy długich wierszy zawierających dane osób; interesują nas etykiety struktury.
        if len(line) > 180:
            continue
        if line not in seen:
            seen.add(line)
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def html_shape(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    links = []
    popup_urls = []
    for el in soup.find_all(["a", "button"]):
        label = clean(el.get_text(" ", strip=True))
        href = clean(el.get("href"))
        onclick = clean(el.get("onclick"))
        blob = " ".join([label, href, onclick])
        if STRUCT_RE.search(blob):
            links.append({
                "tekst": label[:120],
                "href": urljoin(base_url, href) if href and not href.lower().startswith("javascript:") else href,
                "onclick": onclick[:300],
            })
        for value in [href, onclick]:
            m = POPUP_RE.search(value or "")
            if m:
                popup_urls.append(urljoin(base_url, m.group(1)))
    table_rows = [len(t.find_all("tr")) for t in soup.find_all("table")]
    return {
        "tytul": clean(soup.title.get_text(" ", strip=True) if soup.title else ""),
        "liczba_tabel": len(table_rows),
        "wiersze_tabel": table_rows[:50],
        "liczba_draw_frame": len(soup.select(".draw-frame")),
        "liczba_draw": len(soup.select(".draw")),
        "liczba_form": len(soup.find_all("form")),
        "liczba_input": len(soup.find_all("input")),
        "linie_strukturalne": structural_lines(text),
        "linki_strukturalne": links[:80],
        "popup_urls": list(dict.fromkeys(popup_urls))[:80],
    }


def choose_pzt() -> dict:
    cache = load(ROOT / "pzt_szczegoly.json", {"turnieje": {}}).get("turnieje", {})
    rows = []
    for entry in cache.values():
        data = entry.get("dane", {})
        rows.append({
            "nazwa": clean(entry.get("nazwa")),
            "url": clean(entry.get("url")),
            "kategorie": clean(data.get("kategorie")),
            "wyniki": bool(data.get("wyniki_potwierdzone")),
        })
    rows.sort(key=lambda x: x["kategorie"].count(","), reverse=True)
    for row in rows:
        if "mistrzostw polski" in row["nazwa"].casefold() and row["wyniki"]:
            return row
    return next(x for x in rows if x["wyniki"])


def probe_pzt() -> dict:
    sample = choose_pzt()
    r = get(sample["url"])
    main = html_shape(r.text, r.url)
    popup_summaries = []
    # Kilka reprezentatywnych okien: grupy i drabinki; bez kopiowania nazw zawodników.
    for popup_url in main.get("popup_urls", [])[:12]:
        try:
            pr = get(popup_url)
            shape = html_shape(pr.text, pr.url)
            popup_summaries.append({"url": pr.url, **shape})
        except Exception as exc:
            popup_summaries.append({"url": popup_url, "blad": f"{type(exc).__name__}: {exc}"})
    return {
        "nazwa": sample["nazwa"],
        "url": sample["url"],
        "kategorie_zrodlowe": sample["kategorie"],
        "final_url": r.url,
        "strona_glowna_wynikow": main,
        "okna_wynikowe": popup_summaries,
    }


def plt_samples() -> list[dict]:
    rows = load(ROOT / "zrodla/plt.json", {"turnieje": []}).get("turnieje", [])
    picks = []
    rules = [
        lambda x: clean(x.get("kategoria")).casefold() == "1. liga",
        lambda x: "MIKST" in clean(x.get("nazwa")).upper(),
        lambda x: "DEBEL" in clean(x.get("nazwa")).upper(),
    ]
    seen = set()
    for rule in rules:
        for row in rows:
            if rule(row) and row.get("url") not in seen:
                picks.append(row)
                seen.add(row.get("url"))
                break
    return picks


def safe_round_summary(payload: dict) -> dict:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    out = {
        "pola_turnieju": sorted(data.keys()) if isinstance(data, dict) else [],
    }
    if not isinstance(data, dict):
        return out
    for key in ["id", "slug", "gaming_sys_id", "type_ranking_id", "registered_players_count", "is_cup_phase"]:
        if key in data:
            out[key] = data[key]
    groups = (data.get("groups") or {}).get("data", []) if isinstance(data.get("groups"), dict) else []
    if groups:
        out["liczba_grup"] = len(groups)
        out["pola_grupy"] = sorted(groups[0].keys())
        match_count = 0
        pair_match_count = 0
        player_row_fields = set()
        match_fields = set()
        for group in groups:
            gp = (group.get("groupPlayers") or {}).get("data", []) if isinstance(group.get("groupPlayers"), dict) else []
            if gp:
                player_row_fields.update(gp[0].keys())
            matches = (group.get("resultMatches") or {}).get("data", []) if isinstance(group.get("resultMatches"), dict) else []
            match_count += len(matches)
            for match in matches:
                match_fields.update(match.keys())
                first_pair = (match.get("firstPair") or {}).get("data", []) if isinstance(match.get("firstPair"), dict) else []
                second_pair = (match.get("secondPair") or {}).get("data", []) if isinstance(match.get("secondPair"), dict) else []
                if first_pair or second_pair:
                    pair_match_count += 1
        out["liczba_meczow_grupowych"] = match_count
        out["liczba_meczow_z_obiektami_par"] = pair_match_count
        out["pola_wiersza_tabeli_grupy"] = sorted(player_row_fields)
        out["pola_meczu"] = sorted(match_fields)
    # Faza pucharowa może występować pod różnymi kluczami zależnie od endpointu.
    for key in ["cup", "bracket", "brackets", "cupPhase", "cup_phase", "ladder"]:
        if key in data:
            value = data[key]
            out[f"typ_{key}"] = type(value).__name__
            if isinstance(value, dict):
                out[f"pola_{key}"] = sorted(value.keys())
            elif isinstance(value, list):
                out[f"liczba_{key}"] = len(value)
    return out


def probe_plt(browser) -> list[dict]:
    output = []
    for sample in plt_samples():
        base = sample["url"].rsplit("/", 1)[0]
        context = browser.new_context(locale="pl-PL", user_agent=HEADERS["User-Agent"])
        page = context.new_page()
        api_urls = []

        def on_response(response):
            url = response.url
            if url.startswith("https://api.polskaligatenisa.pl/api/V1/rounds/") and response.status == 200:
                api_urls.append(url)

        page.on("response", on_response)
        try:
            for suffix in ["wyniki", "grupy", "faza-pucharowa"]:
                page.goto(f"{base}/{suffix}", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2200)
            summaries = []
            for api_url in dict.fromkeys(api_urls):
                try:
                    ar = get(api_url)
                    summaries.append({
                        "url": api_url,
                        "schemat": safe_round_summary(ar.json()),
                    })
                except Exception as exc:
                    summaries.append({"url": api_url, "blad": f"{type(exc).__name__}: {exc}"})
            output.append({
                "nazwa": clean(sample.get("nazwa")),
                "kategoria": clean(sample.get("kategoria")),
                "url": sample["url"],
                "api": summaries,
            })
        finally:
            context.close()
    return output


def cuply_samples() -> list[dict]:
    rows = load(ROOT / "zrodla/cuply.json", {"turnieje": []}).get("turnieje", [])
    special = [x for x in rows if re.search(r"debel|mikst|duo", clean(x.get("nazwa")), re.I)]
    ordinary = [x for x in rows if x not in special]
    picks = []
    for row in special + ordinary:
        if row.get("url") and row.get("url") not in {x.get("url") for x in picks}:
            picks.append(row)
        if len(picks) >= 2:
            break
    return picks


def page_tab_shape(page) -> dict:
    text = page.locator("body").inner_text(timeout=5000)
    return page.evaluate(
        r"""
        () => ({
          tables: document.querySelectorAll('table').length,
          rows: document.querySelectorAll('table tr').length,
          cards: document.querySelectorAll('[class*="card"], [class*="Card"]').length,
          grids: document.querySelectorAll('[class*="grid"]').length,
          svgs: document.querySelectorAll('svg').length
        })
        """
    ) | {"linie_strukturalne": structural_lines(text)}


def probe_cuply(browser) -> list[dict]:
    output = []
    for sample in cuply_samples():
        context = browser.new_context(locale="pl-PL", user_agent=HEADERS["User-Agent"])
        page = context.new_page()
        network_urls = []

        def on_response(response):
            u = response.url
            host = urlparse(u).netloc
            if host.endswith("cuply.pl") and response.request.resource_type in {"xhr", "fetch"}:
                network_urls.append(u)

        page.on("response", on_response)
        try:
            page.goto(sample["url"], wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1800)
            tabs = {}
            for label in ["Informacje", "Pary", "Grupy", "Fazy pucharowe", "Wyniki"]:
                locator = page.get_by_text(label, exact=True)
                if locator.count() == 0:
                    continue
                try:
                    locator.first.click(timeout=5000)
                    page.wait_for_timeout(900)
                    tabs[label] = page_tab_shape(page)
                except Exception as exc:
                    tabs[label] = {"blad": f"{type(exc).__name__}: {exc}"}
            output.append({
                "nazwa": clean(sample.get("nazwa")),
                "url": sample["url"],
                "zakladki": tabs,
                "wywolania_sieciowe_cuply": list(dict.fromkeys(network_urls))[:80],
            })
        finally:
            context.close()
    return output


def kluby_samples() -> list[dict]:
    rows = load(ROOT / "zrodla/kluby.json", {"turnieje": []}).get("turnieje", [])
    special = [x for x in rows if re.search(r"debel|mikst", clean(x.get("kategorie")) + " " + clean(x.get("nazwa")), re.I)]
    picks = []
    for row in special:
        if row.get("url") and row.get("url") not in {x.get("url") for x in picks}:
            picks.append(row)
        if len(picks) >= 2:
            break
    return picks


def probe_kluby() -> list[dict]:
    output = []
    for sample in kluby_samples():
        base = sample["url"].rstrip("/")
        pages = {}
        for suffix in ["wyniki", "mecze"]:
            url = f"{base}/{suffix}"
            try:
                r = get(url)
                pages[suffix] = {"url": r.url, **html_shape(r.text, r.url)}
            except Exception as exc:
                pages[suffix] = {"url": url, "blad": f"{type(exc).__name__}: {exc}"}
        output.append({
            "nazwa": clean(sample.get("nazwa")),
            "kategorie": clean(sample.get("kategorie")),
            "url": sample["url"],
            "podstrony": pages,
        })
    return output


def main() -> None:
    payload = {
        "cel": "Rozpoznanie schematów publikacji wyników. Raport zapisuje strukturę, nie pełne dane uczestników ani dane kontaktowe.",
        "pzt": probe_pzt(),
        "kluby_org": probe_kluby(),
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        payload["plt"] = probe_plt(browser)
        payload["cuply"] = probe_cuply(browser)
        browser.close()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Zapisano bezpieczny raport strukturalny: {OUT} ({OUT.stat().st_size} B)")


if __name__ == "__main__":
    main()
