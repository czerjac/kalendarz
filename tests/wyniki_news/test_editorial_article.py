import unittest

from wyniki_news.build import article


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
        self.assertIn('Zwyciężyła para Mariusz Osiak, Włodek Brzusek', post['content'])
        self.assertIn(
            'Mariusz Osiak, Włodek Brzusek – Jan Kowalski, Sebastian Nowak <strong>7:5</strong>',
            post['content'],
        )
        self.assertNotIn('Sebastian Nowak — <strong>7:5</strong>', post['content'])
        self.assertEqual(post['voivodeship'], 'mazowieckie')
        self.assertEqual(post['tags'], ['Grand Prix Mazowsza'])

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
