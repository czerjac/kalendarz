"""Aggregated suitability audit for GP Tour, built from existing stan.json.

This script never fetches websites, changes files, or prints player details.
A result marked 'gotowy' is only ready for editorial news, not for scoring.
Run: python -m wyniki_news.ranking_audit
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import re


DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[1] / "data/wyniki_news/stan.json"
SOURCES = ("PLT", "Cuply", "Kluby.org", "PZT TOP")
FALLBACK_ID = re.compile(r"(?:^|:)nazwa:|(?:^|:)pzt-nazwa:|(?:^|:)cuply-nazwa:")


def player_has_fallback_id(player):
    if not isinstance(player, dict):
        return True
    value = str(player.get("id_zrodlowe") or player.get("id") or "")
    return not value or bool(FALLBACK_ID.search(value))


def audit_snapshot(snapshot: dict) -> dict:
    """Deterministic totals only. No raw names, source URLs, IDs or timestamps."""
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("results"), dict):
        raise ValueError("Brak słownika results w archiwum.")
    result = {}
    for source in SOURCES:
        result[source] = Counter()
    for event in snapshot["results"].values():
        if not isinstance(event, dict):
            continue
        source = event.get("zrodlo")
        if source not in result:
            continue
        c = result[source]
        c["turnieje"] += 1
        if event.get("gotowy") is True:
            c["newsy_gotowe"] += 1
        if event.get("uwagi"):
            c["z_ostrzezeniami"] += 1
        matches = event.get("mecze") or []
        if not matches:
            c["bez_meczow"] += 1
        categories = set()
        for match in matches:
            if not isinstance(match, dict):
                continue
            c["mecze"] += 1
            if match.get("zakonczony") is True:
                c["zakonczone"] += 1
            if match.get("walkower") is True:
                c["walkowery_flagowane"] += 1
            if any(token in str(match.get("wynik") or "").casefold()
                   for token in ("ret.", "krecz", "kreczu", "retired")):
                c["krecz_lub_ret_w_tekście"] += 1
            name = match.get("kategoria_zrodlowa")
            if isinstance(name, str) and name.strip():
                categories.add(name.strip())
            for side in ("strona_a", "strona_b"):
                players = (match.get(side) or {}).get("zawodnicy") or []
                for player in players:
                    c["wystapienia_graczy_w_meczach"] += 1
                    if player_has_fallback_id(player):
                        c["wystapienia_bez_stabilnego_id"] += 1
        if len(categories) > 1:
            c["wiele_kategorii_w_turnieju"] += 1
        # The current news archive has no approved full EventPlacements.
        # ranking_evidence may add source tables later, never approvals.
        evidence = event.get("ranking_evidence") or {}
        if evidence.get("klasyfikacje_zrodla"):
            c["z_zachowana_tabela_zrodla"] += 1
    return {source: dict(sorted(c.items())) for source, c in result.items()}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Statystyki przydatności danych sportowych do GP Tour (bez PII).")
    parser.add_argument("--input", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8") as stream:
        snapshot = json.load(stream)
    # Aggregate only. Never write/emit the raw snapshot into CI logs.
    report = audit_snapshot(snapshot)
    print("Audyt RAW Tenis NET → GP Tour (liczniki, bez nazwisk):")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    print("To statystyki z archiwum newsów, nie potwierdzone punkty GP Tour.")


if __name__ == "__main__":
    main()
