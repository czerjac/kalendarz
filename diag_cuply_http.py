from __future__ import annotations

import html as html_lib
import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

SAMPLES = [
    ("singiel", "https://cuply.pl/turnieje/cuply-challenger-gryfino-i"),
    ("debel", "https://cuply.pl/turnieje/duo-zoom-brejk-open-iii"),
]
UA = "Mozilla/5.0 (compatible; TenisNET/1.0; +https://www.tenis.net.pl/)"
CALL_RE = re.compile(r"setActiveGroup\((?:'|&apos;|&#039;|\")([^'\"&)]+)")
SCORE_RE = re.compile(r"\b\d{1,2}:\d{1,2}\b")


def initial(session, url):
    r = session.get(url, headers={"User-Agent": UA}, timeout=40)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    script = soup.find("script", attrs={"data-update-uri": True, "data-csrf": True})
    root = soup.find(attrs={"wire:name": "tournament-page-tabs", "wire:snapshot": True})
    if not script or not root:
        raise RuntimeError("Brak komponentu Livewire Cuply")
    update_uri = script["data-update-uri"]
    if urlparse(update_uri).hostname not in {"cuply.pl", "www.cuply.pl"}:
        raise RuntimeError("Nieprawidłowy endpoint Livewire")
    return script["data-csrf"], update_uri, root["wire:snapshot"]


def call(session, url, token, update_uri, snapshot, method, params):
    payload = {
        "_token": token,
        "components": [{"snapshot": snapshot, "updates": {}, "calls": [{"method": method, "params": params, "metadata": {}}]}],
    }
    r = session.post(
        update_uri,
        json=payload,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Livewire": "true",
            "Origin": "https://cuply.pl",
            "Referer": url,
        },
        timeout=40,
    )
    r.raise_for_status()
    data = r.json()
    component = data["components"][0]
    return component["snapshot"], component.get("effects", {}).get("html", "")


def phase_buttons(markup):
    soup = BeautifulSoup(markup, "html.parser")
    out = []
    for btn in soup.find_all(attrs={"wire:click": True}):
        raw = html_lib.unescape(btn.get("wire:click", ""))
        m = re.search(r"setActiveGroup\(['\"]([^'\"]+)['\"]\)", raw)
        if m:
            out.append((m.group(1), " ".join(btn.stripped_strings)))
    return out


def row_debug(markup):
    soup = BeautifulSoup(markup, "html.parser")
    result = []
    for table in soup.find_all("table"):
        headers = [" ".join(x.stripped_strings) for x in table.find_all("th")]
        if not any("MECZ" in x.upper() for x in headers) or not any("WYNIK" in x.upper() for x in headers):
            continue
        for tr in table.find_all("tr"):
            cells = tr.find_all("td", recursive=False)
            if len(cells) < 3:
                continue
            result.append({
                "cells": [" | ".join(c.stripped_strings) for c in cells],
                "players": [
                    {"text": " ".join(a.stripped_strings), "href": a.get("href", "")}
                    for a in cells[1].find_all("a", href=True)
                    if "/zawodnicy/" in a.get("href", "")
                ],
                "score_spans": [" ".join(x.stripped_strings) for x in cells[2].find_all(["span", "strong", "b"]) if SCORE_RE.search(" ".join(x.stripped_strings))],
                "cell1_html": str(cells[1])[:5000],
            })
    return result


def main():
    with requests.Session() as session:
        for label, url in SAMPLES:
            token, update_uri, snapshot = initial(session, url)
            snapshot, results_html = call(session, url, token, update_uri, snapshot, "setTab", ["terminarz-wyniki"])
            buttons = phase_buttons(results_html)
            print("SAMPLE", label, "endpoint", update_uri, "phases", buttons)
            if not buttons:
                raise SystemExit("Brak faz w wynikach " + label)
            for slug, name in buttons:
                snapshot, phase_html = call(session, url, token, update_uri, snapshot, "setActiveGroup", [slug])
                rows = row_debug(phase_html)
                print("PHASE", label, slug, name, "rows", len(rows))
                for row in rows[:3]:
                    print(json.dumps(row, ensure_ascii=False))
            print("DONE", label)


if __name__ == "__main__":
    main()
