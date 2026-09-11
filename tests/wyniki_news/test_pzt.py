import unittest

from wyniki_news.pzt import (
    event_meta,
    extract_match_urls,
    final_match,
    parse_event,
    parse_winners,
    score_winner,
    tournament_id,
    verify_final,
)


INDEX = '''
<html><body>
<a href="javascript:popUp('/TournamentMatches.aspx?QS=RXZlbnRJRD1FVkVOVC0xJkxldmVsPU0=');">Mecze</a>
<a href="javascript:popUp('/TournamentMatches.aspx?QS=RXZlbnRJRD1FVkVOVC0yJkxldmVsPU0=');">Mecze</a>
<a href="javascript:popUp('/TournamentMatches.aspx?QS=RXZlbnRJRD1FVkVOVC0xJkxldmVsPU0=');">duplikat</a>
</body></html>
'''

SINGLES = '''
<html><body>
<div>Turniej główny: TEST, Od: 2026-07-10 Do: 2026-07-11,</div>
<div>Kategoria: Open Typ: Gra pojedyncza; Mężczyźni</div>
<table>
<tr><th colspan="6"><strong>Runda: 1</strong></th></tr>
<tr><th>lp</th><th>Zawodnik</th><th>Set 1</th><th>Set 2</th><th>Set 3</th><th>Zawodnik</th></tr>
<tr><td>1</td><td>Jan Kowalski</td><td></td><td></td><td></td><td>BYE</td></tr>
<tr><td>2</td><td>Adam Nowak</td><td>6:2</td><td>6:3</td><td></td><td>Piotr Lis</td></tr>
<tr><th colspan="6"><strong>Półfinał</strong></th></tr>
<tr><th>lp</th><th>Zawodnik</th><th>Set 1</th><th>Set 2</th><th>Set 3</th><th>Zawodnik</th></tr>
<tr><td>1</td><td>Jan Kowalski</td><td>3:6</td><td>6:4</td><td>10:7</td><td>Adam Nowak</td></tr>
<tr><th colspan="6"><strong>Finał</strong></th></tr>
<tr><th>lp</th><th>Zawodnik</th><th>Set 1</th><th>Set 2</th><th>Set 3</th><th>Zawodnik</th></tr>
<tr><td>1</td><td>Jan Kowalski</td><td>6:4</td><td>6:3</td><td></td><td>Marek Kot</td></tr>
</table>
</body></html>
'''

DOUBLES = '''
<html><body><div>Kategoria: Open Typ: Gra podwójna; Mężczyźni</div>
<table>
<tr><th colspan="6"><strong>Finał</strong></th></tr>
<tr><th>lp</th><th>Zawodnik</th><th>Set 1</th><th>Set 2</th><th>Set 3</th><th>Zawodnik</th></tr>
<tr><td>1</td><td>Jan Kowalski<br/>Adam Nowak</td><td>7:5</td><td>6:4</td><td></td><td>Piotr Lis<br/>Marek Kot</td></tr>
</table></body></html>
'''

GROUP = '''
<html><body><div>Kategoria: 50+ Typ: Gra pojedyncza; Mężczyźni</div>
<table>
<tr><th colspan="6"><strong>Grupa A</strong></th></tr>
<tr><th>lp</th><th>Zawodnik</th><th>Set 1</th><th>Set 2</th><th>Set 3</th><th>Zawodnik</th></tr>
<tr><td>1</td><td>Jan Kowalski</td><td>6:1</td><td>6:0</td><td></td><td>Adam Nowak</td></tr>
<tr><td>2</td><td>Jan Kowalski</td><td>w.o.</td><td></td><td></td><td>Piotr Lis</td></tr>
</table></body></html>
'''

RETIREMENT = '''
<html><body><div>Kategoria: Open Typ: Gra pojedyncza; Mężczyźni</div>
<table>
<tr><th colspan="6"><strong>Ćwierćfinał</strong></th></tr>
<tr><th>lp</th><th>Zawodnik</th><th>Set 1</th><th>Set 2</th><th>Set 3</th><th>Zawodnik</th></tr>
<tr><td>1</td><td>Jan Kowalski</td><td>3:6</td><td>4:3</td><td>:ret.</td><td>Adam Nowak</td></tr>
<tr><td>2</td><td>Piotr Lis</td><td>5:2</td><td></td><td>ret.:0</td><td>Marek Kot</td></tr>
<tr><td>3</td><td>Matras Grzegorz</td><td>6:1</td><td>3:0</td><td>ret.:</td><td>Ciuła Paweł</td></tr>
<tr><td>4</td><td>Anna A</td><td>2:6</td><td>ret.</td><td></td><td>Beata B</td></tr>
</table></body></html>
'''

WINNERS = '''
<html><body>
<div>Kategoria: Open. Typ: Gra pojedyncza; Mężczyźni</div>
<table><tr><td>1</td><td>Jan Kowalski</td></tr><tr><td>2</td><td>Marek Kot</td></tr><tr><td>3-4</td><td>Adam Nowak</td></tr></table>
<div>Kategoria: Open. Typ: Gra podwójna; Mężczyźni</div>
<table><tr><td>1</td><td>Jan Kowalski<br/>Adam Nowak</td></tr><tr><td>2</td><td>Piotr Lis<br/>Marek Kot</td></tr></table>
</body></html>
'''


class PztParserTest(unittest.TestCase):
    def test_tournament_id_from_existing_http_url(self):
        tid = '7B170278-F7BB-4B0A-BEA5-49A199E798BC'
        url = f'http://portal.pzt.pl/TournamentResults.aspx?CategoryID=AIS&TournamentID={tid}'
        self.assertEqual(tournament_id(url), tid)

    def test_extract_popup_match_urls_deduplicates(self):
        urls = extract_match_urls(INDEX)
        self.assertEqual(len(urls), 2)
        self.assertTrue(all(x.startswith('https://portal.pzt.pl/TournamentMatches.aspx?QS=') for x in urls))

    def test_event_metadata(self):
        meta = event_meta(DOUBLES)
        self.assertEqual(meta['kategoria'], 'Open')
        self.assertEqual(meta['typ'], 'Gra podwójna')
        self.assertEqual(meta['plec'], 'Mężczyźni')

    def test_knockout_singles_and_bye(self):
        meta, matches, warnings = parse_event(SINGLES, 'https://portal.pzt.pl/TournamentMatches.aspx?QS=RXZlbnRJRD1FVkVOVC0xJkxldmVsPU0=')
        self.assertEqual(meta['kategoria'], 'Open')
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0]['faza'], 'Runda: 1')
        self.assertEqual(matches[-1]['faza'], 'Finał')
        self.assertEqual(matches[-1]['zwyciezca'], 'a')
        self.assertEqual(matches[-1]['wynik'], '6:4 6:3')
        self.assertEqual(warnings, [])

    def test_doubles_are_two_players_per_side(self):
        _, matches, warnings = parse_event(DOUBLES, 'https://portal.pzt.pl/TournamentMatches.aspx?QS=RXZlbnRJRD1FVkVOVC0yJkxldmVsPU0=')
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['strona_a']['typ'], 'para')
        self.assertEqual(matches[0]['strona_b']['typ'], 'para')
        self.assertEqual(len(matches[0]['strona_a']['zawodnicy']), 2)
        self.assertEqual(warnings, [])

    def test_group_and_walkover(self):
        _, matches, warnings = parse_event(GROUP, 'https://portal.pzt.pl/TournamentMatches.aspx?QS=RXZlbnRJRD1FVkVOVC0zJkxldmVsPU0=')
        self.assertEqual(len(matches), 2)
        self.assertTrue(all(x['typ_fazy'] == 'grupa' for x in matches))
        self.assertTrue(matches[1]['walkower'])
        self.assertEqual(matches[1]['zwyciezca'], 'a')
        self.assertEqual(warnings, [])

    def test_retirement_rows_keep_pzt_winner_on_left(self):
        _, matches, warnings = parse_event(RETIREMENT, 'https://portal.pzt.pl/TournamentMatches.aspx?QS=RXZlbnRJRD1FVkVOVC00JkxldmVsPU0=')
        self.assertEqual(len(matches), 4)
        self.assertTrue(all(m['zwyciezca'] == 'a' for m in matches))
        self.assertEqual(matches[2]['wynik'], '6:1 3:0 ret.:')
        self.assertEqual(warnings, [])

    def test_winners_singles_and_doubles(self):
        result = parse_winners(WINNERS)
        singles = result['open|gra pojedyncza|mezczyzni']
        doubles = result['open|gra podwojna|mezczyzni']
        self.assertEqual([p['nazwa'] for p in singles['miejsca']['1']['zawodnicy']], ['Jan Kowalski'])
        self.assertEqual(len(doubles['miejsca']['1']['zawodnicy']), 2)
        self.assertEqual(len(doubles['miejsca']['2']['zawodnicy']), 2)

    def test_final_verified_against_winners(self):
        _, matches, warnings = parse_event(SINGLES, 'https://portal.pzt.pl/TournamentMatches.aspx?QS=RXZlbnRJRD1FVkVOVC0xJkxldmVsPU0=')
        standings = parse_winners(WINNERS)['open|gra pojedyncza|mezczyzni']
        fid = verify_final(matches, standings, warnings)
        self.assertEqual(fid, final_match(matches)[0]['id'])
        self.assertEqual(warnings, [])

    def test_wrong_winner_blocks_final(self):
        bad = WINNERS.replace('Jan Kowalski</td></tr><tr><td>2</td><td>Marek Kot', 'Adam Nowak</td></tr><tr><td>2</td><td>Marek Kot', 1)
        _, matches, warnings = parse_event(SINGLES, 'https://portal.pzt.pl/TournamentMatches.aspx?QS=RXZlbnRJRD1FVkVOVC0xJkxldmVsPU0=')
        standings = parse_winners(bad)['open|gra pojedyncza|mezczyzni']
        self.assertIsNone(verify_final(matches, standings, warnings))
        self.assertTrue(any('sprzeczny' in x for x in warnings))

    def test_score_winner_handles_deciding_tiebreak(self):
        self.assertEqual(score_winner(['2:6', '6:3', '10:3']), 'a')
        self.assertEqual(score_winner(['6:2', '6:3', '']), 'a')


if __name__ == '__main__':
    unittest.main()
