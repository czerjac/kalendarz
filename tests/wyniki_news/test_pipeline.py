import copy
import json
import unittest
from datetime import date
from wyniki_news.plt import parse
from wyniki_news.build import eligible, article

ITEM = {'url': 'https://polskaligatenisa.pl/turnieje/cykl/test-123/wyniki', 'nazwa': 'Test', 'data_od': '2026-07-04', 'data_do': '2026-07-05', 'kategoria': '1. Liga'}


def player(id):
    return {'data': {'id': id, 'name': 'Imię', 'surname': str(id), 'email': 'NEVER_EXPORT', 'phone': 'NEVER_EXPORT'}}


def payload():
    return {'data': {'id': 123, 'slug': 'test-123', 'title': 'Turniej <script>alert(1)</script>', 'is_cup_phase': True,
        'groups': {'data': [{'id': 55, 'name': 'FINAŁ', 'type_id': 2, 'resultMatches': {'data': [{
            'id': 11, 'firstPlayer': player(1), 'secondPlayer': player(2), 'winner_id': 2,
            'score': json.dumps({'set_1_1': 3, 'set_1_2': 6, 'set_2_1': 4, 'set_2_2': 6})} ]}}]}}}


class ResultsTest(unittest.TestCase):
    def test_boundary_and_future(self):
        for end, expected in [('2026-07-01', False), ('2026-07-02', True), ('2026-09-10', False), ('bad', False)]:
            self.assertEqual(eligible(dict(ITEM, data_do=end), date(2026, 9, 10)), expected)

    def test_final_and_privacy(self):
        t = parse(payload(), ITEM)
        self.assertTrue(t['gotowy']); self.assertEqual(t['mecze'][0]['zwyciezca'], 'b')
        self.assertNotIn('NEVER_EXPORT', json.dumps(t))
        post = article(t)
        self.assertNotIn('<script>', post['content'])
        self.assertIn('3:6, 4:6', post['content'])
        self.assertEqual(post['fingerprint'], article(t)['fingerprint'])

    def test_conflicting_winner_blocks_publish(self):
        p = payload(); p['data']['groups']['data'][0]['resultMatches']['data'][0]['winner_id'] = 1
        self.assertFalse(parse(p, ITEM)['gotowy'])

    def test_missing_opponent_and_score_block(self):
        for key in ['secondPlayer', 'score', 'winner_id']:
            p = payload(); del p['data']['groups']['data'][0]['resultMatches']['data'][0][key]
            self.assertFalse(parse(p, ITEM)['gotowy'])

    def test_walkover_without_numeric_score(self):
        p = payload(); m = p['data']['groups']['data'][0]['resultMatches']['data'][0]
        m['score'] = None; m['is_walkover'] = 1
        self.assertTrue(parse(p, ITEM)['gotowy'])

    def test_pairs_winner_is_pair_not_person(self):
        p = payload(); m = p['data']['groups']['data'][0]['resultMatches']['data'][0]
        for label, pid in [('first', 50), ('second', 60)]:
            m[label + 'Player'] = {'data': []}
            m[label + 'Pair'] = {'data': {'id': pid, 'leadPlayer': player(pid+1), 'secondPlayer': player(pid+2)}}
        m['winner_id'] = 60
        t = parse(p, ITEM); self.assertTrue(t['gotowy'])
        self.assertEqual(t['mecze'][0]['strona_b']['id'], 'para:60')
        self.assertEqual(len(t['mecze'][0]['strona_b']['zawodnicy']), 2)

    def test_groups_are_not_final(self):
        p = payload(); p['data']['groups']['data'][0]['name'] = 'Grupa A'; p['data']['groups']['data'][0]['type_id'] = 1
        self.assertFalse(parse(p, ITEM)['gotowy'])
        p['data']['is_cup_phase'] = False
        self.assertTrue(parse(p, ITEM)['gotowy'])
        self.assertIsNone(parse(p, ITEM)['final_id'])

    def test_duplicate_and_wrong_event(self):
        p = payload(); p['data']['groups']['data'].append(copy.deepcopy(p['data']['groups']['data'][0]))
        self.assertFalse(parse(p, ITEM)['gotowy'])
        p = payload(); p['data']['slug'] = 'wrong'
        with self.assertRaises(ValueError): parse(p, ITEM)


if __name__ == '__main__': unittest.main()
