"""T-027: ranking-only source evidence, with unchanged editorial news behavior.

Fixtures are invented and do not contain real tournament/player records.
No network calls, no GitHub writes and no private data in audit output.
"""
import copy
import unittest
from unittest.mock import patch

from wyniki_news.build import article
from wyniki_news.kluby import fetch as kluby_fetch, ranking_result_markers
from wyniki_news.pzt import fetch as pzt_fetch
from wyniki_news.ranking_audit import audit_snapshot, player_has_fallback_id
from tests.wyniki_news.test_kluby import MATCHES, STANDINGS
from tests.wyniki_news.test_pzt import INDEX, SINGLES, DOUBLES, WINNERS


class RankingEvidenceTests(unittest.TestCase):
    def test_kluby_markers_separate_retirement_from_walkover(self):
        self.assertEqual(ranking_result_markers("6:3 2:1 krecz"),
                         {"tekst_walkower": False, "tekst_krecz_ret": True})
        self.assertEqual(ranking_result_markers("walkower"),
                         {"tekst_walkower": True, "tekst_krecz_ret": False})
        self.assertEqual(ranking_result_markers("6:4 6:4"),
                         {"tekst_walkower": False, "tekst_krecz_ret": False})

    def test_kluby_reuses_existing_standings_download_without_changing_news(self):
        item = {
            "url": "https://kluby.org/turnieje/123",
            "nazwa": "Fikcyjny puchar",
            "kategoria_zrodla": "OPEN",
            "data_od": "2026-09-01", "data_do": "2026-09-01", "miasto": "Test",
        }
        requested = []
        def get(_session, url, optional=False):
            requested.append(url)
            return STANDINGS if "/kolejnosc" in url else MATCHES

        with patch("wyniki_news.kluby.get", side_effect=get):
            news = kluby_fetch(item, None)
        evidence = news["ranking_evidence"]
        self.assertEqual(evidence["schema_version"], 1)
        self.assertEqual(len(evidence["klasyfikacje_zrodla"]), 1)
        rows = evidence["klasyfikacje_zrodla"][0]["wiersze"]
        self.assertEqual([r["miejsce"] for r in rows], ["1", "2"])
        self.assertEqual(evidence["klasyfikacje_zrodla"][0]["status"],
                         "DANE_ZRODLOWE_NIEZWERYFIKOWANE")
        self.assertEqual(sum("/kolejnosc" in x for x in requested), 1)
        self.assertEqual(news["gotowy"], True)
        without = copy.deepcopy(news)
        del without["ranking_evidence"]
        self.assertEqual(article(news), article(without))

    def test_pzt_retains_only_top_two_not_fabricated_full_standings(self):
        item = {
            "url": "https://portal.pzt.pl/TournamentResults.aspx?"
                   "CategoryID=AIS&TournamentID=7B170278-F7BB-4B0A-BEA5-49A199E798BC",
            "nazwa": "Fikcyjny turniej PZT",
            "data_od": "2026-09-01", "data_do": "2026-09-01",
            "miasto": "Test",
        }
        requested = []
        def get(_session, url):
            requested.append(url)
            if "TournamentMatchesPlay.aspx" in url:
                return INDEX
            if "TournamentTabResults.aspx" in url:
                return WINNERS
            if "EVOVC0x" in url:
                return SINGLES
            if "EVOVC0y" in url:
                return DOUBLES
            raise AssertionError("Unexpected source URL in fictional test")

        with patch("wyniki_news.pzt.get", side_effect=get):
            news = pzt_fetch(item, None)
        evidence = news["ranking_evidence"]
        self.assertEqual(evidence["schema_version"], 1)
        self.assertEqual(len(evidence["klasyfikacje_zrodla"]), 2)
        self.assertTrue(all(t["zakres"] == "TYLKO_MIEJSCA_1_2"
                            for t in evidence["klasyfikacje_zrodla"]))
        self.assertTrue(all(len(t["wiersze"]) <= 2
                            for t in evidence["klasyfikacje_zrodla"]))
        self.assertEqual(sum("TournamentTabResults.aspx" in x for x in requested), 1)
        without = copy.deepcopy(news)
        del without["ranking_evidence"]
        self.assertEqual(article(news), article(without))

    def test_aggregate_has_no_names_and_never_equates_ready_news_to_points(self):
        match = {
            "id": "fake-match-1",
            "kategoria_zrodlowa": "TEST A",
            "walkower": True,
            "zakonczony": True,
            "wynik": "walkower",
            "strona_a": {"zawodnicy": [{"id": "pzt-nazwa:fiction", "nazwa": "Osoba Alfa"}]},
            "strona_b": {"zawodnicy": [{"id": "pzt-nazwa:fiction2", "nazwa": "Osoba Beta"}]},
        }
        snapshot = {"results": {"fake": {
            "zrodlo": "PZT TOP", "gotowy": True, "uwagi": [],
            "mecze": [match],
        }}}
        report = audit_snapshot(snapshot)
        self.assertEqual(report["PZT TOP"]["newsy_gotowe"], 1)
        self.assertEqual(report["PZT TOP"]["walkowery_flagowane"], 1)
        self.assertEqual(report["PZT TOP"]["wystapienia_bez_stabilnego_id"], 2)
        self.assertNotIn("Osoba Alfa", str(report))
        self.assertNotIn("fake-match-1", str(report))

    def test_fallback_id_is_not_suitable_for_automatic_player_matching(self):
        self.assertTrue(player_has_fallback_id({"id": "nazwa:hashed"}))
        self.assertTrue(player_has_fallback_id({"id": "pzt-nazwa:hashed"}))
        self.assertTrue(player_has_fallback_id({}))
        self.assertFalse(player_has_fallback_id({"id": "/gracze/123"}))


if __name__ == "__main__":
    unittest.main()
