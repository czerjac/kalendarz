from pathlib import Path

build = Path('wyniki_news/build.py')
s = build.read_text(encoding='utf-8')

s = s.replace('import os\nimport time\n', 'import os\nimport re\nimport time\n', 1)

needle = """def city_key(value):
    return ' '.join(fold_text(value).replace('.', ' ').split())


def voivodeship_for(t, meta):
"""
replacement = """def city_key(value):
    return ' '.join(fold_text(value).replace('.', ' ').split())


def display_tournament_name(t):
    name = str(t.get('nazwa') or '').strip()
    if t.get('zrodlo') == 'PLT':
        name = re.sub(r'^\\s*(?:1\\.?\\s*LIGA|2\\.?\\s*LIGA)\\.?\\s*', '', name, flags=re.I)
    return name.strip()


def display_cycle(t, cycle):
    if t.get('zrodlo') == 'PLT' and fold_text(cycle) == 'plt':
        return 'Polska Liga Tenisa'
    return cycle


def voivodeship_for(t, meta):
"""
assert needle in s
s = s.replace(needle, replacement, 1)

s = s.replace(
    "    category = str(meta.get('kategorie') or meta.get('kategoria_zrodla') or t.get('kategoria') or '')\n    cycle = str(meta.get('cykl') or '')\n",
    "    category = str(meta.get('kategorie') or meta.get('kategoria_zrodla') or t.get('kategoria') or '')\n    cycle = str(meta.get('cykl') or '')\n    cycle_name = display_cycle(t, cycle)\n    display_name = display_tournament_name(t)\n",
    1,
)

s = s.replace(
    "    intro = f'{date_intro} {esc(date_text)}{location} rozegrano turniej {esc(t[\"nazwa\"])}'\n",
    "    intro = f'{date_intro} {esc(date_text)}{location} rozegrano turniej <em>„{esc(display_name)}”</em>'\n",
    1,
)

s = s.replace(
    "    if cycle and fold_text(cycle) not in {'brak', 'none'}:\n        intro += f' Zawody były częścią cyklu {esc(cycle)}.'\n",
    "    if cycle_name and fold_text(cycle_name) not in {'brak', 'none'}:\n        intro += f' Zawody były częścią cyklu {esc(cycle_name)}.'\n",
    1,
)

s = s.replace(
    "        winner_label = esc(label(winner))\n",
    "        winner_label = '<strong>' + esc(label(winner)) + '</strong>'\n",
    1,
)

old_lines = """        for match in group:
            result = match['wynik'] if match['zakonczony'] else 'Brak potwierdzonego wyniku'
            lines.append(
                esc(label(match['strona_a'])) + ' – ' + esc(label(match['strona_b'])) +
                ' <strong>' + esc(result) + '</strong>'
            )
"""
new_lines = """        for match in group:
            result = match['wynik'] if match['zakonczony'] else 'Brak potwierdzonego wyniku'
            left = esc(label(match['strona_a']))
            right = esc(label(match['strona_b']))
            if match.get('zwyciezca') == 'a':
                left = '<strong>' + left + '</strong>'
            elif match.get('zwyciezca') == 'b':
                right = '<strong>' + right + '</strong>'
            lines.append(left + ' – ' + right + ' ' + esc(result))
"""
assert old_lines in s
s = s.replace(old_lines, new_lines, 1)

s = s.replace(
    "        title = prefix + label(winner) + f' {verb} w turnieju ' + t['nazwa']\n    else:\n        title = t['nazwa'] + ' — wyniki (' + t['data_od'] + ')'\n",
    "        title = prefix + label(winner) + f' {verb} w turnieju ' + display_name\n    else:\n        title = display_name + ' — wyniki (' + t['data_od'] + ')'\n",
    1,
)

build.write_text(s, encoding='utf-8')

test = Path('tests/wyniki_news/test_editorial_article.py')
t = test.read_text(encoding='utf-8')
t = t.replace(
    "        self.assertIn('W turnieju triumfuje para Mariusz Osiak, Włodek Brzusek.', post['content'])\n",
    "        self.assertIn('turniej <em>„Deblowy Masters Zima”</em>', post['content'])\n        self.assertIn('W turnieju triumfuje para <strong>Mariusz Osiak, Włodek Brzusek</strong>.', post['content'])\n",
    1,
)
t = t.replace(
    "            'Mariusz Osiak, Włodek Brzusek – Jan Kowalski, Sebastian Nowak <strong>7:5</strong>',\n",
    "            '<strong>Mariusz Osiak, Włodek Brzusek</strong> – Jan Kowalski, Sebastian Nowak 7:5',\n",
    1,
)
t = t.replace(
    "        self.assertNotIn('Sebastian Nowak — <strong>7:5</strong>', post['content'])\n",
    "        self.assertNotIn('<strong>7:5</strong>', post['content'])\n",
    1,
)

anchor = """    def test_plt_results_url_recovers_calendar_metadata(self):
"""
extra = """    def test_plt_lead_uses_clean_name_and_full_cycle_name(self):
        tournament = {
            'id': 'plt:5143',
            'zrodlo': 'PLT',
            'url': 'https://polskaligatenisa.pl/turnieje/polska-i-liga-tenisa/test-5143/wyniki',
            'nazwa': '1. LIGA. Otwarte Letnie Mistrzostwa Szamotuł 2026',
            'kategoria': '1. Liga',
            'data_od': '2026-07-04',
            'data_do': '2026-07-04',
            'miasto': 'Szamotuły',
            'final_id': 'f1',
            'gotowy': True,
            'uwagi': [],
            'mecze': [{
                'id': 'f1', 'grupa_id': 'final', 'faza': 'FINAŁ', 'typ_fazy': 'puchar',
                'strona_a': {'typ': 'osoba', 'zawodnicy': [{'nazwa': 'Kuba Wawrzyniak'}]},
                'strona_b': {'typ': 'osoba', 'zawodnicy': [{'nazwa': 'Adam Dąbrowski'}]},
                'wynik': '3:4, 1:4', 'zwyciezca': 'b', 'zakonczony': True,
            }],
        }
        meta = {'miasto': 'Szamotuły', 'kategoria_zrodla': '1. Liga', 'cykl': 'PLT'}
        post = article(tournament, meta)
        lead = post['content'].split('</p>', 1)[0]
        self.assertIn('turniej <em>„Otwarte Letnie Mistrzostwa Szamotuł 2026”</em> w kategorii 1. Liga', lead)
        self.assertIn('Zawody były częścią cyklu Polska Liga Tenisa.', lead)
        self.assertIn('W turnieju triumfuje <strong>Adam Dąbrowski</strong>.', lead)
        self.assertNotIn('1. LIGA. Otwarte', lead)
        self.assertEqual(post['title'], 'Szamotuły: Adam Dąbrowski triumfuje w turnieju Otwarte Letnie Mistrzostwa Szamotuł 2026')
        self.assertIn('Kuba Wawrzyniak – <strong>Adam Dąbrowski</strong> 3:4, 1:4', post['content'])

"""
assert anchor in t
t = t.replace(anchor, extra + anchor, 1)
test.write_text(t, encoding='utf-8')
