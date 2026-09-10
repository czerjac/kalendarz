import unittest
from bs4 import BeautifulSoup

from wyniki_news.kluby import category_links, final_id, parse_matches, parse_standings


MATCHES = '''
<html><body><table>
<thead><tr><th>Runda</th><th>Gracz 1</th><th>Gracz 2</th><th>Wynik</th><th>Wygrany</th></tr></thead>
<tbody>
<tr><td colspan="5">Grupa A</td></tr>
<tr><td>Kolejka 1</td><td><a href="/gracze/1">Jan Kowalski</a></td><td><a href="/gracze/2">Adam Nowak</a></td><td>6:3 6:4</td><td><a href="/gracze/1">Jan Kowalski</a></td></tr>
<tr><td colspan="5">Drabinka finałowa</td></tr>
<tr><td>1/2 finału</td><td><a href="/gracze/1">Jan Kowalski</a></td><td><a href="/gracze/3">Piotr Lis</a></td><td>6:2 6:2</td><td><a href="/gracze/1">Jan Kowalski</a></td></tr>
<tr><td>finał</td><td><a href="/gracze/1">Jan Kowalski</a></td><td><a href="/gracze/4">Marek Kot</a></td><td>6:4 3:6 10:7</td><td><a href="/gracze/1">Jan Kowalski</a></td></tr>
</tbody></table></body></html>
'''

STANDINGS = '''
<table><thead><tr><th>#</th><th>Gracz</th><th>Miejsce</th><th>Etap</th><th>Wygrane</th></tr></thead><tbody>
<tr><td>1</td><td><a href="/gracze/1">Jan Kowalski</a></td><td>1</td><td>Zwycięzca</td><td>3</td></tr>
<tr><td>2</td><td><a href="/gracze/4">Marek Kot</a></td><td>2</td><td>Finalista</td><td>2</td></tr>
</tbody></table>
'''

DOUBLES = '''
<table><thead><tr><th>Runda</th><th>Gracz 1</th><th>Gracz 2</th><th>Wynik</th><th>Wygrany</th></tr></thead><tbody>
<tr><td>finał</td>
<td><a href="/gracze/10">Anna A</a><br><a href="/gracze/11">Adam A</a></td>
<td><a href="/gracze/20">Beata B</a><br><a href="/gracze/21">Bartosz B</a></td>
<td>6:4 6:4</td>
<td><a href="/gracze/10">Anna A</a><br><a href="/gracze/11">Adam A</a></td></tr>
</tbody></table>
'''


class KlubyParserTest(unittest.TestCase):
    def test_group_and_knockout(self):
        matches, warnings = parse_matches(MATCHES, '123', '7', 'OPEN')
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0]['typ_fazy'], 'grupa')
        self.assertEqual(matches[-1]['typ_fazy'], 'puchar')
        self.assertEqual(matches[-1]['zwyciezca'], 'a')
        self.assertTrue(matches[-1]['zakonczony'])
        self.assertEqual(matches[-1]['wynik'], '6:4 3:6 10:7')
        self.assertEqual(warnings, [])

    def test_final_verified_by_standings(self):
        matches, warnings = parse_matches(MATCHES, '123', '7', 'OPEN')
        standings = parse_standings(STANDINGS)
        self.assertEqual(len(standings), 2)
        fid = final_id(matches, standings, warnings)
        self.assertEqual(fid, matches[-1]['id'])
        self.assertEqual(warnings, [])

    def test_doubles_are_one_side_with_two_players(self):
        matches, warnings = parse_matches(DOUBLES, '124', '9', 'DEBEL MIKST')
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['strona_a']['typ'], 'para')
        self.assertEqual(len(matches[0]['strona_a']['zawodnicy']), 2)
        self.assertEqual(matches[0]['zwyciezca'], 'a')
        self.assertEqual(warnings, [])

    def test_categories_from_links_and_options(self):
        soup = BeautifulSoup('''<a href="/turnieje/1/mecze?kategoria=10">OPEN</a>
        <select><option value="11">DEBEL</option></select>''', 'html.parser')
        cats = category_links(soup, '')
        self.assertEqual({x['id'] for x in cats}, {'10', '11'})

    def test_score_conflict_blocks_clean_result(self):
        bad = MATCHES.replace('<td><a href="/gracze/1">Jan Kowalski</a></td></tr>', '<td><a href="/gracze/4">Marek Kot</a></td></tr>', 1)
        matches, warnings = parse_matches(bad, '123', '7', 'OPEN')
        self.assertTrue(any('sprzeczny' in x for x in warnings))


if __name__ == '__main__':
    unittest.main()
