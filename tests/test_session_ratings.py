"""Daily score-aware ratings, including rotation and late-arrival regressions."""
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


def rotation_games():
    names = dict(G='Chris Goshow', B='Ben Apstein', J='Justin Chow', K='Kyle Thomson')
    results = [('GB', 'KJ', 19), ('GB', 'KJ', 18), ('GJ', 'BK', 13),
               ('JG', 'BK', 13), ('BJ', 'GK', 19), ('JB', 'GK', 16)]
    return [(i, f'2026-09-23 10:{i:02d}:00', names[w[0]], names[w[1]], 21,
             names[l[0]], names[l[1]], score)
            for i, (w, l, score) in enumerate(results)]


class SessionRatingTests(unittest.TestCase):
    def test_late_arrival_does_not_take_crown(self):
        stats = calculate_stats_from_games(session_games())
        self.assertEqual(stats[0][0], 'Justin Chow')
        late_arrival = next(r for r in stats if r[0] == 'Sam Greenleaf')
        self.assertEqual(late_arrival[1:5], [1, 0, 1.0, 2])
        self.assertGreater(stats[0][5], late_arrival[5])
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
        self.assertEqual(ios['rating'], stats[0][5])
        self.assertEqual(ios['plus_minus'], 23)
        self.assertEqual(_ranking(['Alex', 1, 0, 1.0, 12.5])['rating'], 12.5)

    def test_september_23_rotation_rewards_chows_better_scores(self):
        games = rotation_games()
        stats = calculate_stats_from_games(games)
        self.assertEqual([r[0] for r in stats],
                         ['Justin Chow', 'Chris Goshow', 'Ben Apstein', 'Kyle Thomson'])
        self.assertEqual([r[1:3] for r in stats[:3]], [[4, 2]] * 3)
        self.assertEqual([r[4] for r in stats[:3]], [18, 14, -4])
        self.assertEqual(_session_beach_royalty_names(stats), ['Justin Chow'])

    def test_reversing_actual_play_order_cannot_change_ratings(self):
        games = rotation_games()
        # Change the timestamps and IDs, not just the input list order.
        reversed_play = [(100 - g[0], games[-i - 1][1], *g[2:])
                         for i, g in enumerate(games)]
        self.assertEqual(calculate_stats_from_games(games),
                         calculate_stats_from_games(reversed_play))

    def test_bigger_win_and_closer_loss_improve_rating(self):
        close = [(1, '2026-09-23', 'A', 'B', 21, 'C', 'D', 19)]
        wide = [(1, '2026-09-23', 'A', 'B', 21, 'C', 'D', 5)]
        close_ratings = {r['player']: r['rating'] for r in calculate_session_ratings(close)}
        wide_ratings = {r['player']: r['rating'] for r in calculate_session_ratings(wide)}
        self.assertGreater(wide_ratings['A'], close_ratings['A'])
        self.assertGreater(close_ratings['C'], wide_ratings['C'])

    def test_equal_results_and_scores_have_equal_ratings(self):
        games = [(g[0], g[1], g[2], g[3], 21, g[5], g[6], 19)
                 for g in rotation_games()]
        stats = calculate_stats_from_games(games)
        self.assertEqual(len({r[5] for r in stats[:3]}), 1)
        self.assertEqual(set(_session_beach_royalty_names(stats)),
                         {'Chris Goshow', 'Ben Apstein', 'Justin Chow'})

    def test_score_scale_does_not_change_rating(self):
        games = rotation_games()
        scaled = [(g[0], g[1], g[2], g[3], g[4] * 2, g[5], g[6], g[7] * 2)
                  for g in games]
        self.assertEqual(calculate_session_ratings(games), calculate_session_ratings(scaled))

    def test_unscored_or_invalid_scores_still_use_result(self):
        expected = None
        for ws, ls in [(0, 0), (None, None), ('', ''), (21, -1),
                       (19, 21), (float('nan'), 1), (float('inf'), 1)]:
            games = [(1, '2026-09-23', 'A', 'B', ws, 'C', 'D', ls)]
            ratings = calculate_session_ratings(games)
            if expected is None:
                expected = ratings
            self.assertEqual(ratings, expected)
            self.assertGreater(ratings[0]['rating'], ratings[-1]['rating'])

    def test_unknown_players_do_not_get_ratings(self):
        games = [(1, '2026-09-23', 'A', '?', 21, 'B', '???', 19)]
        self.assertEqual({r['player'] for r in calculate_session_ratings(games)}, {'A', 'B'})

    def test_equal_ratings_share_crown_even_with_different_win_percentages(self):
        rows = [['Alex', 1, 0, 1.0, 2, 5.0], ['Blair', 3, 2, .6, 4, 5.0]]
        self.assertEqual(_session_beach_royalty_names(rows), ['Alex', 'Blair'])


if __name__ == '__main__':
    unittest.main()
