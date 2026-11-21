"""T-112: selected collection only, entirely offline tests."""
from datetime import date
import unittest

from wyniki_news import build
from wyniki_news.fetch_selected import validate_selection, fetch_selected

URL = "https://portal.pzt.pl/TournamentResults.aspx?TournamentID=TEST"
TODAY = date(2026, 11, 21)


def fixture():
    return {
        "known": {
            URL: {"url": URL, "zrodlo": "PZT TOP", "nazwa": "Testowy turniej",
                  "data_od": "2026-03-27", "data_do": "2026-04-02"}
        },
        "results": {}, "attempts": {},
    }


def result(matches):
    return {"id": "pzt:test", "zrodlo": "PZT TOP", "url": URL,
            "data_od": "2026-03-27", "data_do": "2026-04-02",
            "mecze": matches, "gotowy": False, "uwagi": ["wiele kategorii"]}


class SelectedFetchTests(unittest.TestCase):
    def test_2026_pre_july_is_eligible_for_sport_not_news(self):
        self.assertEqual(len(validate_selection(fixture(), [URL], today=TODAY)), 1)
        self.assertFalse(build.eligible_news_result(result([{"zakonczony": True}])))
        self.assertTrue(build.eligible_news_result(
            {"data_od": "2026-08-08", "data_do": "2026-08-14"}))

    def test_missing_and_unknown_targets_rejected_before_network(self):
        with self.assertRaisesRegex(ValueError, "znanego kalendarza"):
            validate_selection(fixture(), ["https://unknown.test/turniej"], today=TODAY)
        with self.assertRaisesRegex(ValueError, "powtórzony"):
            validate_selection(fixture(), [URL, URL], today=TODAY)
        with self.assertRaisesRegex(ValueError, "1 do 10"):
            validate_selection(fixture(), [], today=TODAY)
        with self.assertRaisesRegex(ValueError, "poza zakresem"):
            d = fixture()
            d["known"][URL]["data_od"] = "2025-12-31"
            validate_selection(d, [URL], today=TODAY)

    def test_complete_matches_are_fetched_even_if_not_ready_for_news(self):
        archive = fixture()
        rows = fetch_selected(archive, [URL], session=object(), today=TODAY,
                              adapters={"PZT TOP": lambda item, session: result(
                                  [{"zakonczony": True}])})
        self.assertEqual(rows[0]["status"], "FETCHED")
        self.assertIn("pzt:test", archive["results"])
        self.assertEqual(archive["attempts"][URL]["matches_count"], 1)

    def test_no_published_results_is_not_a_fetch_error(self):
        archive = fixture()
        rows = fetch_selected(archive, [URL], session=object(), today=TODAY,
                              adapters={"PZT TOP": lambda item, session: result([])})
        self.assertEqual(rows[0]["status"], "NO_RESULTS")
        self.assertFalse(archive["results"])
        self.assertEqual(archive["attempts"][URL]["status"], "NO_RESULTS")

    def test_failed_or_regressed_retry_preserves_previous_raw(self):
        archive = fixture()
        archive["results"]["pzt:test"] = result([
            {"zakonczony": True}, {"zakonczony": True}])
        rows = fetch_selected(archive, [URL], session=object(), today=TODAY,
                              adapters={"PZT TOP": lambda item, session: result([
                                  {"zakonczony": True}])})
        self.assertEqual(rows[0]["status"], "PARTIAL")
        self.assertEqual(len(archive["results"]["pzt:test"]["mecze"]), 2)

        def fails(item, session):
            raise ConnectionError("offline test")
        rows = fetch_selected(archive, [URL], session=object(), today=TODAY,
                              adapters={"PZT TOP": fails})
        self.assertEqual(rows[0]["status"], "ERROR")
        self.assertEqual(len(archive["results"]["pzt:test"]["mecze"]), 2)

    def test_ongoing_match_marks_partial_but_keeps_raw(self):
        archive = fixture()
        rows = fetch_selected(archive, [URL], session=object(), today=TODAY,
                              adapters={"PZT TOP": lambda item, session: result([
                                  {"zakonczony": False}])})
        self.assertEqual(rows[0]["status"], "PARTIAL")
        self.assertIn("pzt:test", archive["results"])


if __name__ == "__main__":
    unittest.main()
