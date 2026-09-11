import unittest

from wyniki_news.build import ADAPTERS


class AdapterMapTest(unittest.TestCase):
    def test_all_four_sources_are_enabled(self):
        self.assertEqual(set(ADAPTERS), {'PLT', 'Cuply', 'Kluby.org', 'PZT TOP'})


if __name__ == '__main__':
    unittest.main()
