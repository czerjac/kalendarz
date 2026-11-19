"""PZT main draw and consolation must not share a final or round in TenisNET.

Every name and score below is fictional; no network or real-player fixture.
"""
import base64
import unittest

from wyniki_news import pzt
from wyniki_news.build import article


TOURNAMENT_ID = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"


def url(level):
    qs = base64.b64encode(f"EventID=FICTITIOUS-OPEN&Level={level}".encode()).decode()
    return "https://portal.pzt.pl/TournamentMatches.aspx?QS=" + qs


def match_page(final_winner, final_loser, quarter_winner, quarter_loser):
    return f"""
    <html><body><div>Kategoria: Open Typ: Gra pojedyncza; Mężczyźni</div>
    <table>
     <tr><th colspan="6">Ćwierćfinał</th></tr>
     <tr><th>lp</th><th>Zawodnik</th><th>Set 1</th><th>Set 2</th><th>Set 3</th><th>Zawodnik</th></tr>
     <tr><td>1</td><td>{quarter_winner}</td><td>6:2</td><td>6:3</td><td></td><td>{quarter_loser}</td></tr>
     <tr><th colspan="6">Finał</th></tr>
     <tr><th>lp</th><th>Zawodnik</th><th>Set 1</th><th>Set 2</th><th>Set 3</th><th>Zawodnik</th></tr>
     <tr><td>1</td><td>{final_winner}</td><td>6:4</td><td>6:2</td><td></td><td>{final_loser}</td></tr>
    </table></body></html>
    """


MAIN_HTML = match_page(
    "Dawid Syntetyczny", "Wojciech Testowy", "Dawid Syntetyczny", "Adam Fikcyjny",
)
CONSOLATION_HTML = match_page(
    "Łukasz Przykładowy", "Grzegorz Testowy", "Łukasz Przykładowy", "Marek Sztuczny",
)
WINNERS_HTML = """
<html><body>
 <div>Kategoria: Open. Typ: Gra pojedyncza; Mężczyźni</div>
 <div>Turniej główny</div>
 <table><tr><td>1</td><td>Dawid Syntetyczny</td></tr>
        <tr><td>2</td><td>Wojciech Testowy</td></tr></table>
 <div>Turniej pocieszenia</div>
 <table><tr><td>1</td><td>Łukasz Przykładowy</td></tr>
        <tr><td>2</td><td>Grzegorz Testowy</td></tr></table>
</body></html>
"""


class FakeResponse:
    encoding = "utf-8"
    apparent_encoding = "utf-8"

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self):
        # Intentionally return consolation first, to ensure the output orders
        # main before secondary regardless of the PZT source page order.
        self.index = (
            "<a href=\"javascript:popUp('/TournamentMatches.aspx?QS="
            + url("C").split("QS=")[1] + "');\">Pocieszenie</a>"
            + "<a href=\"javascript:popUp('/TournamentMatches.aspx?QS="
            + url("M").split("QS=")[1] + "');\">Główna</a>"
        )

    def get(self, target, **kwargs):
        if "TournamentMatchesPlay.aspx" in target:
            return FakeResponse(self.index)
        if "TournamentTabResults.aspx" in target:
            return FakeResponse(WINNERS_HTML)
        if target == url("M"):
            return FakeResponse(MAIN_HTML)
        if target == url("C"):
            return FakeResponse(CONSOLATION_HTML)
        raise AssertionError("Unexpected GET: " + target)


class PztDrawSplitTest(unittest.TestCase):
    def test_level_is_source_of_truth_and_unknown_is_not_main(self):
        self.assertEqual(pzt.draw_kind(url("M")), "glowna")
        self.assertEqual(pzt.draw_kind(url("C")), "pocieszenia")
        self.assertEqual(pzt.draw_kind(url("X")), "nieustalona")
        self.assertEqual(pzt.draw_kind(url("X"), "<p>Turniej pocieszenia</p>"), "pocieszenia")

    def test_two_finals_in_one_category_are_separate_and_main_is_verified(self):
        item = {
            "url": "https://portal.pzt.pl/TournamentDrawsheet.aspx?CategoryID=AIS&Male=&TournamentID="
                   + TOURNAMENT_ID,
            "nazwa": "Turniej testowy",
            "data_od": "2026-11-01", "data_do": "2026-11-02", "miasto": "Miejscowość Testowa",
        }
        result = pzt.fetch(item, FakeSession())
        self.assertTrue(result["gotowy"], result["uwagi"])
        self.assertEqual(len(result["mecze"]), 4)
        self.assertEqual([m["drabinka"] for m in result["mecze"]],
                         ["glowna", "glowna", "pocieszenia", "pocieszenia"])
        finals = [m for m in result["mecze"] if m["faza"] == "Finał"]
        self.assertEqual(len(finals), 2)
        self.assertNotEqual(finals[0]["grupa_id"], finals[1]["grupa_id"])
        self.assertNotEqual(finals[0]["id"], finals[1]["id"])
        self.assertEqual(result["final_id"], finals[0]["id"])
        self.assertEqual(finals[0]["strona_a"]["zawodnicy"][0]["nazwa"], "Dawid Syntetyczny")
        self.assertEqual(finals[1]["strona_a"]["zawodnicy"][0]["nazwa"], "Łukasz Przykładowy")

        post = article(result)
        self.assertTrue(post["ready"])
        self.assertIn("Dawid Syntetyczny triumfuje", post["title"])
        self.assertNotIn("Łukasz Przykładowy triumfuje", post["title"])
        self.assertEqual(post["content"].count("<h4>Finał</h4>"), 2)
        main_start = post["content"].index("<h2>Turniej główny</h2>")
        secondary_start = post["content"].index("<h2>Turniej pocieszenia — wyniki dodatkowe</h2>")
        self.assertLess(main_start, secondary_start)
        self.assertLess(post["content"].index("Dawid Syntetyczny", main_start), secondary_start)
        self.assertIn("Mecze pocieszenia nie są zaliczane do punktacji GP Tour.", post["content"])
        self.assertIn("Łukasz Przykładowy", post["content"][secondary_start:])

    def test_without_reliable_draw_does_not_invent_main_winner(self):
        unknown = pzt.parse_event(
            MAIN_HTML,
            url("X"),
        )
        self.assertEqual({m["drabinka"] for m in unknown[1]}, {"nieustalona"})
        self.assertTrue(any("Nieustalony rodzaj drabinki" in w for w in unknown[2]))

    def test_consolation_winners_cannot_override_main_standings(self):
        winners = pzt.parse_winners(WINNERS_HTML)["open|gra pojedyncza|mezczyzni"]
        self.assertEqual(winners["miejsca"]["1"]["zawodnicy"][0]["nazwa"], "Dawid Syntetyczny")
        self.assertEqual(winners["miejsca"]["2"]["zawodnicy"][0]["nazwa"], "Wojciech Testowy")


if __name__ == "__main__":
    unittest.main()
