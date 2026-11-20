"""Manual, opt-in PZT TOP championship backfill for GP Tour 2026.

Reads the existing TenisNET archive and reuses wyniki_news.pzt.fetch().
Does NOT alter data/wyniki_news/stan.json, published feed, WordPress, a
production database or scheduled jobs. No network I/O without --fetch.

Output is a PRIVATE, locally stored, curated two-result JSON for a later
TenisOne RAW review, not an approved sporting classification.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import parse_qs, urlsplit

import requests

from . import pzt

CHAMPIONSHIPS_2026 = {
    "32C58E6F-6764-4169-BF5E-8384BE371F3E": ("Gdynia", "2026-08-08", "2026-08-14"),
    "E4F40025-FC0A-44FD-A065-C0DFB9F44016": ("Kozerki", "2026-03-27", "2026-04-02"),
}
# Matches are stored in ONE PZT Tournament JSON record in the current
# TenisOne import format. Never silently truncate a large championship.
MAX_MATCHES_PER_TOURNAMENT = 500
MAX_REQUESTS = 250
MIN_REQUEST_INTERVAL_S = 1.5


def official_guid(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "portal.pzt.pl"
            or parsed.username or parsed.password or parsed.port):
        return None
    ids = parse_qs(parsed.query).get("TournamentID", [])
    guid = ids[0].upper() if len(ids) == 1 else None
    return guid if guid in CHAMPIONSHIPS_2026 else None


def locate_championships(archive: dict) -> dict[str, dict]:
    """Only exact source TournamentID; never trust title substring matching."""
    known = archive.get("known")
    if not isinstance(known, dict):
        raise ValueError("Archiwum nie zawiera słownika known.")
    found = {}
    for key, value in known.items():
        guid = official_guid(key)
        if guid is None or not isinstance(value, dict):
            continue
        if guid in found:
            raise ValueError("Powtórzony oficjalny identyfikator PZT.")
        city, start, end = CHAMPIONSHIPS_2026[guid]
        if (value.get("zrodlo") != "PZT TOP"
                or value.get("data_od") != start or value.get("data_do") != end):
            raise ValueError(f"{city}: sprzeczne metadane źródłowe.")
        found[guid] = {
            "url": key, "zrodlo": value["zrodlo"],
            "nazwa": value.get("nazwa") or "",
            "data_od": start, "data_do": end,
            "miasto": value.get("miasto") or city,
        }
    if set(found) != set(CHAMPIONSHIPS_2026):
        missing = sorted(set(CHAMPIONSHIPS_2026) - set(found))
        raise ValueError("Brak metadanych jednego z mistrzostw PZT: " + ", ".join(missing))
    return found


class ThrottledSession:
    """Protect PZT from unbounded request bursts in an explicit manual run."""

    def __init__(self, *, underlying=None, min_interval=MIN_REQUEST_INTERVAL_S):
        self.underlying = underlying or requests.Session()
        self.min_interval = min_interval
        self.calls = 0
        self.previous = None

    def get(self, url, **kwargs):
        if self.calls >= MAX_REQUESTS:
            raise RuntimeError("Limit żądań PZT osiągnięty; bez częściowego zapisu.")
        now = time.monotonic()
        if self.previous is not None:
            pause = self.min_interval - (now - self.previous)
            if pause > 0:
                time.sleep(pause)
        self.previous = time.monotonic()
        self.calls += 1
        return self.underlying.get(url, **kwargs)


def build_review_bundle(*, archive, fetcher=pzt.fetch, session):
    """Only after BOTH validated fetches return, produce review-only JSON."""
    metadata = locate_championships(archive)
    results = {}
    report = {}
    for guid, item in metadata.items():
        city = CHAMPIONSHIPS_2026[guid][0]
        result = fetcher(item, session)
        if not isinstance(result, dict):
            raise ValueError(f"{city}: parser nie zwrócił obiektu.")
        expected_id = "pzt:" + guid
        if (result.get("id") != expected_id
                or result.get("zrodlo") != "PZT TOP"
                or official_guid(result.get("url")) != guid
                or result.get("data_od") != item["data_od"]
                or result.get("data_do") != item["data_do"]):
            raise ValueError(f"{city}: niezgodne identyfikatory/daty wyniku.")
        matches = result.get("mecze")
        if not isinstance(matches, list) or not matches:
            raise ValueError(f"{city}: brak meczów, nie zapisujemy pustego wyniku.")
        if len(matches) > MAX_MATCHES_PER_TOURNAMENT:
            raise ValueError(
                f"{city}: {len(matches)} meczów przekracza limit importu "
                f"{MAX_MATCHES_PER_TOURNAMENT}; wymaga przeglądu, bez obcinania."
            )
        # Collector marks multievent news drafts. Keep its warnings, and
        # never claim Foundation verification or point approval here.
        results[expected_id] = result
        report[city] = {
            "id": expected_id,
            "matches": len(matches),
            "category_labels": len({
                m.get("kategoria_zrodlowa")
                for m in matches if isinstance(m, dict)
                and isinstance(m.get("kategoria_zrodlowa"), str)
            }),
            "collector_ready": result.get("gotowy") is True,
            "collector_warnings": len(result.get("uwagi") or []),
            "gp_tour_approved": False,
        }
    return {
        "known": {item["url"]: item for item in metadata.values()},
        "attempts": {},
        "results": results,
    }, report


def private_output(path: Path, data: dict):
    """Exclusive creation; no overwrite, restrictive mode, no partial file."""
    if path.exists():
        raise FileExistsError("Nie nadpisujemy poprzedniej paczki; wybierz nową ścieżkę.")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".pzt_review_")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        # Reject concurrent creation and keep existing output untouched.
        os.link(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="PZT MP 2026: ręczny bezpieczny backfill, bez zmian archiwum i Cyber_GO.",
    )
    parser.add_argument("--archive", default="data/wyniki_news/stan.json")
    parser.add_argument("--fetch", action="store_true",
                        help="Wykonaj ograniczone, rzeczywiste pobranie z PZT.")
    parser.add_argument("--output", default=".private_pzt_mp/review_mp_2026.json",
                        help="Prywatny plik wyników, nigdy dane publikowane w repo.")
    args = parser.parse_args(argv)
    path = Path(args.archive)
    if not path.is_file() or path.stat().st_size > 25_000_000:
        raise SystemExit("Wymagane lokalne archiwum JSON do 25 MB.")
    archive = json.loads(path.read_text(encoding="utf-8"))
    metadata = locate_championships(archive)
    print("Zidentyfikowano źródła:", ", ".join(CHAMPIONSHIPS_2026[guid][0]
                                               for guid in metadata))
    if not args.fetch:
        print("DRY-RUN: bez żądań do PZT i bez zapisów. Dodaj --fetch świadomie.")
        return 0
    session = ThrottledSession()
    try:
        bundle, report = build_review_bundle(archive=archive, session=session)
        private_output(Path(args.output), bundle)
    except Exception as exc:
        raise SystemExit(f"Nie zapisano wyniku: {exc}") from exc
    # Never print names / scores to console; review output stays local/private.
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("Zapisano prywatną paczkę RAW do kontroli. Bez publikacji i punktów.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
