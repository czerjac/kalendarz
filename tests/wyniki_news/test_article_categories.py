import unittest

from wyniki_news.build import article


class ArticleCategoryTest(unittest.TestCase):
    def test_source_category_is_visible_for_multicategory_matches(self):
        tournament = {
            'id': 'pzt:test', 'zrodlo': 'PZT TOP', 'url': 'https://portal.pzt.pl/test',
            'nazwa': 'Test wielokategorii', 'kategoria': 'Open; 50+',
            'data_od': '2026-09-01', 'data_do': '2026-09-01', 'miasto': 'Warszawa',
            'final_id': None, 'gotowy': False, 'uwagi': ['Turniej wielokategoriowy — news wymaga kontroli redakcyjnej'],
            'mecze': [{
                'id': 'm1', 'grupa_id': 'e1:final', 'faza': 'Finał', 'typ_fazy': 'puchar',
                'kategoria_zrodlowa': 'Open. Gra pojedyncza. Mężczyźni',
                'strona_a': {'typ': 'osoba', 'zawodnicy': [{'nazwa': 'Jan Kowalski'}]},
                'strona_b': {'typ': 'osoba', 'zawodnicy': [{'nazwa': 'Adam Nowak'}]},
                'wynik': '6:4 6:3', 'zwyciezca': 'a', 'zakonczony': True,
            }],
        }
        post = article(tournament)
        self.assertIn('<h2>Open. Gra pojedyncza. Mężczyźni</h2>', post['content'])
        self.assertIn('<h3>Finał</h3>', post['content'])
        self.assertFalse(post['ready'])


if __name__ == '__main__':
    unittest.main()
