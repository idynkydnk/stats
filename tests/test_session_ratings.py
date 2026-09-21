"""Session-only ratings and crowns using the September 20 late-arrival case."""
import unittest
from unittest.mock import patch

from email_content import (
    _session_beach_royalty_names, _session_beach_royalty_lock,
    _session_performance_staging_lock, session_stats_for_illustration,
)
from ios_api import _ranking
from stat_functions import (
    calculate_stats_from_games, calculate_session_ratings, convert_ampm,
    todays_doubles_dashboard_payload,
)


def session_games():
    names = dict(J='Justin Chow', T='Tyler Stock', K='Kyle Thomson',
                 C='Chris Goshow', S='Sam Greenleaf')
    results = [
        ('08:14', 'JT', 'KC', 21, 19), ('08:34', 'JT', 'KC', 21, 13),
        ('09:04', 'TK', 'JC', 24, 22), ('09:30', 'JC', 'TK', 23, 21),
        ('09:56', 'JK', 'CT', 22, 20), ('10:16', 'KJ', 'CT', 21, 14),
        ('10:41', 'CJ', 'KT', 23, 21), ('11:12', 'JS', 'CK', 24, 22),
    ]
    return [(i, f'2026-09-20 {time}:00', names[w[0]], names[w[1]], ws,
             names[l[0]], names[l[1]], ls, None, '', 'America/Los_Angeles')
            for i, (time, w, l, ws, ls) in enumerate(results)]


class SessionRatingTests(unittest.TestCase):
    def test_late_arrival_does_not_take_crown(self):
        stats = calculate_stats_from_games(session_games())
        self.assertEqual([(r[0], r[5]) for r in stats], [
            ('Justin Chow', 20.40), ('Tyler Stock', 7.70),
            ('Kyle Thomson', 5.29), ('Chris Goshow', 4.06),
            ('Sam Greenleaf', 1.95),
        ])
        self.assertEqual(stats[-1][1:5], [1, 0, 1.0, 2])
        self.assertEqual(_session_beach_royalty_names(stats), ['Justin Chow'])
        players = [r[0] for r in stats]
        lock = _session_beach_royalty_lock(players, stats)
        self.assertIn('Justin Chow is the only king', lock)
        self.assertIn('highest session rating', lock)
        staging = _session_performance_staging_lock(players, stats)
        self.assertIn('Justin Chow (7-1, 88%, +23 point differential) — the session leader', staging)
        self.assertNotIn('Sam Greenleaf (1-0, 100%, +2 point differential) — the session leader', staging)

    def test_raw_and_display_dates_and_input_order_agree(self):
        games = session_games()
        expected = calculate_stats_from_games(games)
        self.assertEqual(calculate_stats_from_games(list(reversed(games))), expected)
        self.assertEqual(calculate_stats_from_games(convert_ampm(list(reversed(games)))), expected)
        self.assertEqual(session_stats_for_illustration('doubles', games), expected)

    def test_each_session_resets_and_empty_session_is_safe(self):
        games = session_games()
        calculate_session_ratings(games)
        single = calculate_session_ratings(games[-1:])
        winners = [r for r in single if r['wins']]
        self.assertEqual(winners[0]['rating'], winners[1]['rating'])
        self.assertEqual(calculate_session_ratings([]), [])
        self.assertEqual(calculate_stats_from_games([]), [])

    def test_dashboard_and_ios_keep_rating_separate_from_point_margin(self):
        games = session_games()
        stats = calculate_stats_from_games(games)
        with patch('stat_functions.todays_games', return_value=games):
            dashboard = todays_doubles_dashboard_payload()
        self.assertEqual(dashboard['stats'], stats)
        ios = _ranking(stats[0], rating_key='plus_minus')
        self.assertEqual(ios['rating'], 20.40)
        self.assertEqual(ios['plus_minus'], 23)
        self.assertEqual(_ranking(['Alex', 1, 0, 1.0, 12.5])['rating'], 12.5)

    def test_equal_ratings_share_crown_even_with_different_win_percentages(self):
        rows = [['Alex', 1, 0, 1.0, 2, 5.0], ['Blair', 3, 2, .6, 4, 5.0]]
        self.assertEqual(_session_beach_royalty_names(rows), ['Alex', 'Blair'])


if __name__ == '__main__':
    unittest.main()
