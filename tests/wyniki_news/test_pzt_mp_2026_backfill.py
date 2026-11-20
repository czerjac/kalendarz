"""PZT MP 2026 one-off extraction: no network or publication in tests."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from wyniki_news.pzt_mp_2026_backfill import (
    CHAMPIONSHIPS_2026, build_review_bundle, locate_championships,
    main, official_guid, private_output,
)


def sample_archive():
    known = {}
    for guid, (city, start, end) in CHAMPIONSHIPS_2026.items():
        url = ("https://portal.pzt.pl/TournamentResults.aspx?"
               "CategoryID=AIS&Male=&TournamentID=" + guid)
        known[url] = {
            "url": url, "zrodlo": "PZT TOP",
            "nazwa": "Fikcyjne " + city,
            "data_od": start, "data_do": end,
            "miasto": city,
        }
    return {"known": known, "attempts": {}, "results": {}}


def fake_fetcher(item, session):
    guid = official_guid(item["url"])
    assert guid in CHAMPIONSHIPS_2026
    return {
        "id": "pzt:" + guid, "url": item["url"], "zrodlo": "PZT TOP",
        "nazwa": item["nazwa"], "data_od": item["data_od"],
        "data_do": item["data_do"], "miasto": item["miasto"],
        "kategoria": "45+. Gra pojedyncza. Mężczyźni",
        "mecze": [{
            "id": "fake1", "kategoria_zrodlowa": "45+. Gra pojedyncza. Mężczyźni",
            "event_key": "m45_s", "strona_a": {"typ": "osoba", "zawodnicy": [
                {"id": "pzt-nazwa:x", "nazwa": "Jan Fikcyjny"},
            ]}, "strona_b": {"typ": "osoba", "zawodnicy": [
                {"id": "pzt-nazwa:y", "nazwa": "Adam Fikcyjny"},
            ]},
            "wynik": "6:2 6:3", "zwyciezca": "a",
            "zakonczony": True, "walkower": False,
        }],
        "gotowy": False,
        "uwagi": ["Wynik wymaga kontroli redakcyjnej."],
    }


class PZTChampionshipOneOffTests(unittest.TestCase):
    def test_locate_only_exact_two_guids_not_tournament_name(self):
        source = sample_archive()
        ids = locate_championships(source)
        self.assertEqual(set(ids), set(CHAMPIONSHIPS_2026))
        self.assertIsNone(official_guid(
            "https://fake.pzt.pl/TournamentResults.aspx?TournamentID="
            + next(iter(CHAMPIONSHIPS_2026))
        ))
        self.assertIsNone(official_guid(
            "http://portal.pzt.pl/TournamentResults.aspx?TournamentID="
            + next(iter(CHAMPIONSHIPS_2026))
        ))
        source["known"]["https://portal.pzt.pl/TournamentResults.aspx?TournamentID=OTHER"] = {
            "nazwa": "42. Mistrzostwa Polski Gdynia",
        }
        self.assertEqual(len(locate_championships(source)), 2)

    def test_missing_or_wrong_date_blocks_complete_bundle(self):
        data = sample_archive()
        key = next(iter(data["known"]))
        data["known"][key]["data_do"] = "2027-01-01"
        with self.assertRaisesRegex(ValueError, "sprzeczne"):
            locate_championships(data)
        with self.assertRaisesRegex(ValueError, "Brak metadanych"):
            locate_championships({"known": {}, "results": {}})

    def test_two_fake_results_are_private_raw_not_approved_points(self):
        bundle, report = build_review_bundle(
            archive=sample_archive(), fetcher=fake_fetcher, session=object(),
        )
        self.assertEqual(len(bundle["results"]), 2)
        self.assertEqual(len(bundle["known"]), 2)
        self.assertEqual(set(report), {"Gdynia", "Kozerki"})
        for info in report.values():
            self.assertEqual(info["matches"], 1)
            self.assertEqual(info["category_labels"], 1)
            self.assertEqual(info["gp_tour_approved"], False)
            self.assertFalse(info["collector_ready"])
        self.assertIn("pzt-nazwa:", json.dumps(bundle))
        # Never translate a name-based pseudo ID into verified Player identity.

    def test_empty_or_excessive_results_are_rejected_without_truncation(self):
        def empty(item, session):
            d = fake_fetcher(item, session)
            d["mecze"] = []
            return d
        with self.assertRaisesRegex(ValueError, "brak meczów"):
            build_review_bundle(archive=sample_archive(),
                                fetcher=empty, session=object())

        def huge(item, session):
            d = fake_fetcher(item, session)
            d["mecze"] = d["mecze"] * 501
            return d
        with self.assertRaisesRegex(ValueError, "przekracza limit"):
            build_review_bundle(archive=sample_archive(),
                                fetcher=huge, session=object())

    def test_strict_private_write_and_dry_run_does_not_fetch(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "private" / "pzt.json"
            private_output(path, {"results": {"test": "fictitious"}})
            self.assertTrue(path.exists())
            with self.assertRaises(FileExistsError):
                private_output(path, {"results": {"test": "overwrite"}})
            self.assertEqual(json.loads(path.read_text())["results"],
                             {"test": "fictitious"})
            archive = Path(tmp) / "archive.json"
            archive.write_text(json.dumps(sample_archive()))
            self.assertEqual(main(["--archive", str(archive)]), 0)
            # No network and no second output produced.
            self.assertEqual(len(list(Path(tmp).rglob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
