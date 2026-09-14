import unittest
from datetime import date
from wyniki_news.build import overlaps_date_range

class DateRangeTests(unittest.TestCase):
    def test_overlap_includes_spanning_tournament(self):
        item={'data_od':'2026-09-04','data_do':'2026-09-06'}
        self.assertTrue(overlaps_date_range(item,date(2026,9,5),date(2026,9,6)))
    def test_non_overlap_is_excluded(self):
        item={'data_od':'2026-08-29','data_do':'2026-08-30'}
        self.assertFalse(overlaps_date_range(item,date(2026,9,5),date(2026,9,6)))

if __name__=='__main__': unittest.main()
