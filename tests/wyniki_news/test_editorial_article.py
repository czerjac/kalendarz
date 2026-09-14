import unittest

from wyniki_news.build import article, metadata_for_result, voivodeship_for


class EditorialArticleTest(unittest.TestCase):
    def test_doubles_article_is_prose_and_plain_results(self):
        tournament = {
            'id': 'kluby:999',
            'zrodlo': 'Kluby.org',
            'url': 'https://kluby.org/turnieje/999',
            'nazwa': 'Deblowy Masters Zima',
            'kategoria': 'debel 40+',
            'data_od': '2026-09-12',
            'data_do': '2026-09-12',
            'miasto': 'Warszawa',
            'final_id': 'f1',
            'gotowy': True,
            'uwagi': [],
            'mecze': [{
                'id': 'f1',
                'grupa_id': 'final',
                'faza': 'Finał',
                'typ_fazy': 'puchar',
                'kategoria_zrodlowa': 'debel 40+',
                'strona_a': {'typ': 'para', 'zawodnicy': [{'nazwa': 'Mariusz Osiak'}, {'nazwa': 'Włodek Brzusek'}]},
                'strona_b': {'typ': 'para', 'zawodnicy': [{'nazwa': 'Jan Kowalski'}, {'nazwa': 'Sebastian Nowak'}]},
                'wynik': '7:5',
                'zwyciezca': 'a',
                'zakonczony': True,
            }],
        }
        meta = {
            'wojewodztwo': 'mazowieckie',
            'miasto': 'Warszawa',
            'miejsce': 'Klub Tenisowy Orzeł',
            'kategorie': 'debel 40+',
            'cykl': 'Grand Prix Mazowsza',
        }
        post = article(tournament, meta)
        self.assertEqual(
            post['title'],
            'Warszawa: Mariusz Osiak, Włodek Brzusek triumfują w turnieju Deblowy Masters Zima',
        )
        self.assertNotIn('<table', post['content'])
        self.assertNotIn('Zawodnik / para A', post['content'])
        self.assertIn('W dniu 12 września 2026', post['content'])
        self.assertIn('turniej <em>„Deblowy Masters Zima”</em>', post['content'])
        self.assertIn('W turnieju triumfuje para <strong>Mariusz Osiak, Włodek Brzusek</strong>.', post['content'])
        lead = post['content'].split('</p>', 1)[0]
        self.assertNotIn('7:5', lead)
        self.assertNotIn('Jan Kowalski', lead)
        self.assertIn(
            '<strong>Mariusz Osiak, Włodek Brzusek</strong> – Jan Kowalski, Sebastian Nowak 7:5',
            post['content'],
        )
        self.assertNotIn('<strong>7:5</strong>', post['content'])
        self.assertEqual(post['voivodeship'], 'mazowieckie')
        self.assertEqual(post['tags'], ['Grand Prix Mazowsza'])

    def test_plt_lead_uses_clean_name_and_full_cycle_name(self):
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

    def test_plt_results_url_recovers_calendar_metadata(self):
        known = {
            'https://polskaligatenisa.pl/turnieje/puchar-plt/test-5143': {
                'url': 'https://polskaligatenisa.pl/turnieje/puchar-plt/test-5143',
                'zrodlo': 'PLT',
                'nazwa': 'Test',
                'data_od': '2026-07-04',
                'wojewodztwo': 'wielkopolskie',
            }
        }
        result = {
            'id': 'plt:5143',
            'zrodlo': 'PLT',
            'url': 'https://polskaligatenisa.pl/turnieje/puchar-plt/test-5143/wyniki',
            'nazwa': 'Test',
            'data_od': '2026-07-04',
        }
        self.assertEqual(metadata_for_result(result, known)['wojewodztwo'], 'wielkopolskie')

    def test_historical_plt_city_fallback_supplies_voivodeship(self):
        self.assertEqual(voivodeship_for({'zrodlo': 'PLT', 'miasto': 'Szamotuły'}, {}), 'wielkopolskie')
        self.assertEqual(voivodeship_for({'zrodlo': 'PLT', 'miasto': 'Gdańsk'}, {}), 'pomorskie')
        self.assertEqual(voivodeship_for({'zrodlo': 'PLT', 'miasto': 'Szczecin'}, {}), 'zachodniopomorskie')
        self.assertEqual(voivodeship_for({'zrodlo': 'PLT', 'miasto': 'Chełmek k. Oświęcimia'}, {}), 'małopolskie')
        self.assertEqual(voivodeship_for({'zrodlo': 'PLT', 'miasto': 'Sobota k. Poznania'}, {}), 'wielkopolskie')

    def test_explicit_voivodeship_wins_over_city_fallback(self):
        self.assertEqual(
            voivodeship_for({'zrodlo': 'PLT', 'miasto': 'Szamotuły'}, {'wojewodztwo': 'mazowieckie'}),
            'mazowieckie',
        )

    def test_source_tags_are_controlled(self):
        base = {
            'mecze': [], 'final_id': None, 'gotowy': False, 'uwagi': [], 'nazwa': 'T',
            'kategoria': '', 'data_od': '2026-09-01', 'data_do': '2026-09-01',
            'miasto': '', 'url': 'https://example.test',
        }
        for source, expected in (
            ('PLT', 'Polska Liga Tenisa'),
            ('Cuply', 'Cuply'),
            ('PZT TOP', 'Tenis Open Polska PZT'),
        ):
            tournament = dict(base, id=source.lower(), zrodlo=source)
            self.assertEqual(article(tournament, {})['tags'], [expected])

    def test_only_supported_cycle_tags_are_added(self):
        tournament = {
            'id': 'kluby:1', 'zrodlo': 'Kluby.org', 'url': 'https://example.test',
            'nazwa': 'T', 'kategoria': '', 'data_od': '2026-09-01', 'data_do': '2026-09-01',
            'miasto': '', 'mecze': [], 'final_id': None, 'gotowy': False, 'uwagi': [],
        }
        self.assertEqual(article(tournament, {'cykl': 'Ziaja Grand Prix Wybrzeża'})['tags'], ['Grand Prix Wybrzeża'])
        self.assertEqual(article(tournament, {'cykl': 'Inny Cykl'})['tags'], [])


if __name__ == '__main__':
    unittest.main()
