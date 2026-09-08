import unittest

from player_identity import is_unknown_player
from stat_functions import sort_by_winpct_with_minimum


class UnknownPlayerSortingTests(unittest.TestCase):
    def test_placeholder_names(self):
        for name in ('??? ???', ' ???  ??? ', '???', '？？？ ？？？'):
            self.assertTrue(is_unknown_player(name))
        for name in ('Alice', 'Who?', '', None):
            self.assertFalse(is_unknown_player(name))

    def test_unknowns_follow_every_sample_band_and_stay_out_of_preview(self):
        for name_key in ('partner', 'opponent'):
            with self.subTest(name_key=name_key):
                rows = [
                    {name_key: '??? ???', 'total_games': 1000, 'win_percentage': 1},
                    {name_key: 'Tiny', 'total_games': 1, 'win_percentage': 0},
                    {name_key: 'Regular', 'total_games': 30, 'win_percentage': .5},
                    {name_key: 'Smaller', 'total_games': 5, 'win_percentage': .8},
                ]
                result = sort_by_winpct_with_minimum(rows, 10, preview_limit=3)
                self.assertEqual([row[name_key] for row in result],
                                 ['Regular', 'Smaller', 'Tiny', '??? ???'])
                self.assertEqual([row['preview_hidden'] for row in result],
                                 [False, False, False, True])
