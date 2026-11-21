"""T-112: explicit, source-independent result fetch for selected calendar events.

Uses the four existing adapters. Does NOT alter the scheduled collector, WP feed,
rankings, classifications or point approvals. Real fetching requires --fetch.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path

from . import build

EARLIEST = date(2026, 1, 1)
MAX_SELECTED = 10
ARCHIVE = build.OUT / "stan.json"


def validate_selection(archive: dict, urls: list[str], *, today: date) -> list[dict]:
    """All targets must come from the actual calendar, never an arbitrary URL."""
    if not isinstance(urls, list) or not 1 <= len(urls) <= MAX_SELECTED:
        raise ValueError("Wskaż od 1 do 10 turniejów z kalendarza.")
    if len(set(urls)) != len(urls) or any(not isinstance(x, str) or not x.strip() for x in urls):
        raise ValueError("Wykryto powtórzony lub pusty adres.")
    known = archive.get("known")
    if not isinstance(known, dict):
        raise ValueError("Brak rejestru kalendarza w archiwum.")
    targets = []
    for url in urls:
        item = known.get(url)
        if not isinstance(item, dict) or item.get("url") != url:
            raise ValueError("Turniej nie należy do znanego kalendarza.")
        source = item.get("zrodlo")
        if source not in build.ADAPTERS:
            raise ValueError("Źródło nie ma obsługiwanego parsera.")
        try:
            start = date.fromisoformat(item["data_od"])
        except (TypeError, ValueError, KeyError):
            raise ValueError("Turniej nie ma prawidłowej daty początkowej.") from None
        if not EARLIEST <= start <= today:
            raise ValueError("Turniej jest poza zakresem GP Tour od 1.01.2026.")
        targets.append(item)
    return targets


def fetch_selected(archive: dict, urls: list[str], *, session,
                   today: date, adapters=None) -> list[dict]:
    """Fetch only selected events; persist results only when non-regressing.

    A missing results page is a status for review, not zero points or a missing
    tournament. Existing good RAW is never deleted by a failed retry.
    """
    targets = validate_selection(archive, urls, today=today)
    adapters = adapters if adapters is not None else build.ADAPTERS
    archive.setdefault("results", {})
    archive.setdefault("attempts", {})
    reports = []
    stamp = datetime.now(timezone.utc).isoformat()
    for item in targets:
        url, source = item["url"], item["zrodlo"]
        info = {"url": url, "source": source, "matches": 0}
        try:
            result = adapters[source](item, session)
            prefix = {"PLT": "plt:", "Cuply": "cuply:",
                      "Kluby.org": "kluby:", "PZT TOP": "pzt:"}[source]
            if (not isinstance(result, dict)
                    or not isinstance(result.get("id"), str)
                    or not result["id"].startswith(prefix)
                    or result.get("zrodlo") != source
                    or result.get("url") != url
                    or not isinstance(result.get("mecze"), list)):
                raise ValueError("Adapter zwrócił niespójny turniej lub mecze.")
            matches = result["mecze"]
            info["matches"] = len(matches)
            previous = archive["results"].get(result["id"])
            if not matches:
                info["status"] = "PARTIAL" if previous else "NO_RESULTS"
            elif previous and len(matches) < len(previous.get("mecze", [])):
                info["status"] = "PARTIAL"
            else:
                archive["results"][result["id"]] = result
                # Editorial gotowy=false does NOT imply missing sporting results.
                info["status"] = ("PARTIAL" if any(
                    m.get("zakonczony") is False for m in matches
                    if isinstance(m, dict)) else "FETCHED")
            info["result_id"] = result["id"]
        except Exception as exc:
            info["status"] = "ERROR"
            info["error"] = type(exc).__name__
        archive["attempts"][url] = {
            "date": today.isoformat(),
            "checked_at": stamp,
            "status": info["status"],
            "ready": info["status"] == "FETCHED",
            "matches_count": info["matches"],
        }
        reports.append(info)
    return reports


def project_statuses(existing: dict, archive: dict, urls: list[str]) -> dict:
    """Small public metadata projection; never includes participant or match data."""
    if not isinstance(existing, dict) or existing.get("schema_version") != 1:
        existing = {"schema_version": 1, "entries": {}}
    entries = existing.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    for url in urls:
        info = archive["attempts"][url]
        entries[url] = {
            "status": info["status"],
            "checked_at": info["checked_at"],
            "date": info["date"],
            "matches_count": info["matches_count"],
        }
    return {"schema_version": 1, "entries": entries}


def main(argv=None):
    p = argparse.ArgumentParser(description="Ręczne pobieranie wskazanych wyników GP Tour")
    p.add_argument("--url", action="append", default=[], help="Dokładny URL z kalendarza (maks. 10)")
    p.add_argument("--from-env", action="store_true",
                   help="Czytaj URLs z SELECTED_TOURNAMENT_URLS (po jednym w wierszu)")
    p.add_argument("--archive", type=Path, default=ARCHIVE)
    p.add_argument("--status-output", type=Path,
                   default=build.OUT / "selected_status.json")
    p.add_argument("--fetch", action="store_true", help="Świadome pobranie i zapis do archiwum")
    args = p.parse_args(argv)
    urls = list(args.url)
    if args.from_env:
        urls += [line.strip() for line in
                 os.environ.get("SELECTED_TOURNAMENT_URLS", "").splitlines()
                 if line.strip()]
    archive = build.load(args.archive, {"known": {}, "results": {}, "attempts": {}})
    # Include fresh and archived calendar metadata without rewriting calendars.
    archive.setdefault("known", {}).update(build.discover())
    today = datetime.now(build.ZoneInfo("Europe/Warsaw")).date()
    selected = validate_selection(archive, urls, today=today)
    if not args.fetch:
        print(json.dumps({"mode": "DRY_RUN", "selected": len(selected)},
                         ensure_ascii=False))
        return 0
    import requests
    with requests.Session() as session:
        report = fetch_selected(archive, urls, session=session, today=today)
    build.save(args.archive, archive)
    status = build.load(args.status_output, {"schema_version": 1, "entries": {}})
    build.save(args.status_output, project_statuses(status, archive, urls))
    counts = {status: sum(x["status"] == status for x in report)
              for status in ("FETCHED", "PARTIAL", "NO_RESULTS", "ERROR")}
    print(json.dumps({"mode": "FETCHED_UNAPPROVED", "attempts": counts},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
