import json
import unittest
from unittest.mock import Mock

from wyniki_news.cuply import (
    initial,
    phase_buttons,
    parse_phase,
    score_parts,
    source_winner,
    split_participants,
    validate_url,
)
from bs4 import BeautifulSoup


SINGLES = '''
<div>
<button wire:click="setActiveGroup('grupa-a')">Grupa A</button>
<button wire:click="setActiveGroup('polfinaly')">Półfinały</button>
<button wire:click="setActiveGroup('final')">Finał</button>
<table><thead><tr><th>#</th><th>MECZ</th><th>WYNIK</th><th>DATA</th><th>KORT</th></tr></thead><tbody>
<tr><td>1</td><td>
<a href="https://cuply.pl/zawodnicy/jan-kowalski"></a><a href="https://cuply.pl/zawodnicy/jan-kowalski">Jan Kowalski</a>
<span>vs</span>
<a href="https://cuply.pl/zawodnicy/adam-nowak">Adam Nowak</a>
</td><td><span>4:2</span><span>4:1</span></td><td>06.09.2026 10:00</td><td>Kort 2</td></tr>
</tbody></table></div>
'''

HIGHLIGHT = '''
<table><thead><tr><th>#</th><th>MECZ</th><th>WYNIK</th><th>DATA</th><th>KORT</th></tr></thead><tbody>
<tr><td>1</td><td><div>
<span class="font-medium text-primary"><a href="https://cuply.pl/zawodnicy/jan-kowalski">Jan Kowalski</a></span>
<span>vs</span>
<span class="font-medium text-primary font-bold"><mark class="bg-featured"><a href="https://cuply.pl/zawodnicy/adam-nowak">Adam Nowak</a></mark></span>
</div></td><td><span>2:4</span><span>1:4</span></td><td>06.09.2026</td><td>—</td></tr>
</tbody></table>
'''

DOUBLES = '''
<table><thead><tr><th>#</th><th>MECZ</th><th>WYNIK</th><th>DATA</th><th>KORT</th></tr></thead><tbody>
<tr><td>7</td><td>
<a href="https://cuply.pl/zawodnicy/a-one">A One</a> / <a href="https://cuply.pl/zawodnicy/a-two">A Two</a>
<span>vs</span>
<a href="https://cuply.pl/zawodnicy/b-one">B One</a> / <a href="https://cuply.pl/zawodnicy/b-two">B Two</a>
</td><td><span>2:4</span><span>4:1</span><span>10:7</span></td><td>09.05.2026</td><td>Kort 1</td></tr>
</tbody></table>
'''

INITIAL = '''
<html><body>
<div><span>Typ gry:</span><span>Debel</span></div>
<div><span>Poziom:</span><span>OPEN</span></div>
<div><span>System gier:</span><span>Grupowy + pucharowy</span></div>
<div wire:name="tournament-page-tabs" wire:snapshot='{snapshot}'></div>
<script data-csrf="TOKEN" data-update-uri="https://cuply.pl/livewire-abc/update"></script>
</body></html>
'''


class Response:
    def __init__(self, text): self.text = text; self.apparent_encoding = 'utf-8'
    def raise_for_status(self): pass


class CuplyParserTest(unittest.TestCase):
    def test_url_validation(self):
        self.assertEqual(validate_url('https://cuply.pl/turnieje/test-event'), 'test-event')
        with self.assertRaises(ValueError): validate_url('https://evil.example/turnieje/test-event')
        with self.assertRaises(ValueError): validate_url('https://cuply.pl/ranking')

    def test_phase_buttons_keep_order(self):
        self.assertEqual(phase_buttons(SINGLES), [('grupa-a', 'Grupa A'), ('polfinaly', 'Półfinały'), ('final', 'Finał')])

    def test_singles_match(self):
        matches, warnings = parse_phase(SINGLES, '91', 'final', 'Finał')
        self.assertEqual(warnings, [])
        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual(m['strona_a']['zawodnicy'][0]['id'], 'cuply:jan-kowalski')
        self.assertEqual(m['strona_b']['zawodnicy'][0]['nazwa'], 'Adam Nowak')
        self.assertEqual(m['zwyciezca'], 'a')
        self.assertEqual(m['wynik'], '4:2, 4:1')
        self.assertTrue(m['zakonczony'])
        self.assertEqual(m['typ_fazy'], 'puchar')

    def test_source_winner_from_cuply_highlight(self):
        soup = BeautifulSoup(HIGHLIGHT, 'html.parser')
        cell = soup.find('tbody').find_all('td')[1]
        self.assertEqual(source_winner(cell), 'b')
        matches, warnings = parse_phase(HIGHLIGHT, '91', 'final', 'Finał')
        self.assertEqual(warnings, [])
        self.assertEqual(matches[0]['zwyciezca'], 'b')
        self.assertTrue(matches[0]['zakonczony'])

    def test_conflicting_highlight_and_score_blocks_match(self):
        conflict = HIGHLIGHT.replace('<span>2:4</span><span>1:4</span>', '<span>4:2</span><span>4:1</span>')
        matches, warnings = parse_phase(conflict, '91', 'final', 'Finał')
        self.assertFalse(matches[0]['zakonczony'])
        self.assertIsNone(matches[0]['zwyciezca'])
        self.assertTrue(any('sprzeczne' in x for x in warnings))

    def test_doubles_pair_and_super_tiebreak(self):
        matches, warnings = parse_phase(DOUBLES, '44', 'final', 'Finał')
        self.assertEqual(warnings, [])
        m = matches[0]
        self.assertEqual(m['strona_a']['typ'], 'para')
        self.assertEqual(m['strona_b']['typ'], 'para')
        self.assertEqual(len(m['strona_a']['zawodnicy']), 2)
        self.assertEqual(m['zwyciezca'], 'a')
        self.assertEqual(m['sety'][-1], {'a': 10, 'b': 7})

    def test_duplicate_avatar_links_are_deduplicated(self):
        soup = BeautifulSoup(SINGLES, 'html.parser')
        cell = soup.find('tbody').find_all('td')[1]
        a, b = split_participants(cell)
        self.assertEqual(len(a['zawodnicy']), 1)
        self.assertEqual(len(b['zawodnicy']), 1)

    def test_group_phase(self):
        matches, warnings = parse_phase(SINGLES, '91', 'grupa-a', 'Grupa A')
        self.assertEqual(warnings, [])
        self.assertEqual(matches[0]['typ_fazy'], 'grupa')

    def test_missing_score_blocks_ready_match(self):
        broken = SINGLES.replace('<span>4:2</span><span>4:1</span>', '')
        matches, warnings = parse_phase(broken, '91', 'final', 'Finał')
        self.assertFalse(matches[0]['zakonczony'])
        self.assertTrue(any('brak potwierdzonego wyniku' in x for x in warnings))

    def test_walkover_without_source_winner_is_not_guessed(self):
        broken = SINGLES.replace('<span>4:2</span><span>4:1</span>', '<span>w.o.</span>')
        matches, warnings = parse_phase(broken, '91', 'final', 'Finał')
        self.assertTrue(matches[0]['walkower'])
        self.assertFalse(matches[0]['zakonczony'])
        self.assertTrue(any('walkower' in x for x in warnings))

    def test_walkover_with_source_winner_is_complete(self):
        walkover = HIGHLIGHT.replace('<span>2:4</span><span>1:4</span>', '<span>w.o.</span>')
        matches, warnings = parse_phase(walkover, '91', 'final', 'Finał')
        self.assertEqual(warnings, [])
        self.assertTrue(matches[0]['walkower'])
        self.assertTrue(matches[0]['zakonczony'])
        self.assertEqual(matches[0]['zwyciezca'], 'b')

    def test_score_winner_from_a_perspective(self):
        cell = BeautifulSoup('<td><span>3:4</span><span>4:2</span><span>10:6</span></td>', 'html.parser').td
        sets, result, _, winner = score_parts(cell)
        self.assertEqual(winner, 'a')
        self.assertEqual(result, '3:4, 4:2, 10:6')
        self.assertEqual(len(sets), 3)

    def test_initial_validates_component_and_reads_metadata(self):
        state = {'data': {'tournamentId': 123}, 'memo': {'name': 'tournament-page-tabs', 'path': 'turnieje/test-event'}}
        markup = INITIAL.format(snapshot=json.dumps(state).replace("'", '&#39;'))
        session = Mock()
        session.get.return_value = Response(markup)
        got = initial(session, 'https://cuply.pl/turnieje/test-event')
        self.assertEqual(got['tournament_id'], '123')
        self.assertEqual(got['typ_gry'], 'Debel')
        self.assertEqual(got['poziom'], 'OPEN')
        self.assertEqual(got['system_gier'], 'Grupowy + pucharowy')
        self.assertEqual(got['token'], 'TOKEN')


if __name__ == '__main__': unittest.main()
