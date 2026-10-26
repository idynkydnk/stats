"""Score-aware skill updates and reproducible, pre-game comparisons."""
import math
import unittest
from unittest.mock import patch

from doubles_skill import calculate_ratings, score_margin_multiplier
from scripts.compare_doubles_ratings import compare, game_tuple, standings


def game(winner_score=21, loser_score=19, ident=1, winners=('A', 'B'), losers=('C', 'D')):
    return (ident, f'2026-01-{ident:02d} 10:00:00', *winners, winner_score, *losers, loser_score)


def ratings(games, **kwargs):
    return {row['player']: row for row in calculate_ratings(games, **kwargs)}


class DoublesSkillTests(unittest.TestCase):
    def test_legacy_first_game_is_preserved_when_score_adjustment_disabled(self):
        row = ratings([game()], score_aware=False)['A']
        # Analytic first-game result under the existing two-team implementation.
        sigma, beta, tau = 8.333, 4.167, .0833
        c = math.sqrt(4 * sigma ** 2 + 2 * beta ** 2)
        v = math.sqrt(2 / math.pi)
        mu = 25 + (sigma ** 2 + tau ** 2) / c * v
        updated_sigma = math.sqrt((sigma ** 2 + tau ** 2) *
                                  (1 - (sigma ** 2 + tau ** 2) / c ** 2 * v ** 2))
        self.assertEqual(row['mu'], round(mu, 2))
        self.assertEqual(row['sigma'], round(updated_sigma, 2))
        self.assertEqual(row['rating'], round(mu - 3 * updated_sigma, 2))

    def test_wider_win_and_closer_loss_get_more_credit(self):
        close, wide = ratings([game()]), ratings([game(21, 5)])
        self.assertGreater(wide['A']['rating'], close['A']['rating'])
        self.assertGreater(close['C']['rating'], wide['C']['rating'])
        self.assertGreater(close['A']['mu'], 25)
        self.assertLess(close['C']['mu'], 25)
        self.assertEqual(wide['A']['sigma'], close['A']['sigma'])
        self.assertEqual(wide['A'], wide['B'] | {'player': 'A'})

    def test_adjustment_is_bounded_and_uses_team_expectations(self):
        self.assertGreater(score_margin_multiplier(21, 12, -1),
                           score_margin_multiplier(21, 12, 1))
        for score in (0, 1, 10, 20, 20.99):
            for strength in (-100, -5, 0, 5, 100):
                multiplier = score_margin_multiplier(21, score, strength)
                self.assertGreaterEqual(multiplier, .8)
                self.assertLessEqual(multiplier, 1.2)
        self.assertEqual(ratings([game(21, 0)]), ratings([game(2100, 0)]))

    def test_score_scaling_and_team_member_order_do_not_change_results(self):
        games = [game(21, 10), game(15, 13, ident=2, winners=('C', 'A'), losers=('B', 'D'))]
        scaled = [(g[0], g[1], g[2], g[3], g[4] * 2, g[5], g[6], g[7] * 2) for g in games]
        swapped = [(g[0], g[1], g[3], g[2], g[4], g[6], g[5], g[7]) for g in games]
        self.assertEqual(ratings(games), ratings(scaled))
        self.assertEqual(ratings(games), ratings(swapped))

    def test_invalid_scores_use_exact_result_only_updates(self):
        expected = calculate_ratings([game()], score_aware=False)
        for winner, loser in [(None, None), ('', ''), ('bad', 19), (0, 0), (21, 21),
                              (19, 21), (21, -1), (math.nan, 1), (math.inf, 1), (21, math.inf)]:
            with self.subTest(winner=winner, loser=loser):
                self.assertEqual(calculate_ratings([game(winner, loser)]), expected)

    def test_incomplete_or_duplicate_rosters_keep_legacy_result_handling(self):
        for sample in [game(winners=('A', '?')), game(winners=('A', 'A')),
                       game(winners=('?', '??'))]:
            self.assertEqual(calculate_ratings([sample]), calculate_ratings([sample], score_aware=False))
        self.assertEqual(calculate_ratings([]), [])

    def test_prediction_does_not_see_current_or_future_scores_or_results(self):
        previous = [game(21, 5)]
        predictions = []
        for sample in (game(21, 0, ident=2), game(21, 20, ident=2)):
            observed = []
            calculate_ratings(previous + [sample], prediction_observer=lambda i, p: observed.append(p))
            predictions.append(observed)
        self.assertEqual(predictions[0], predictions[1])
        self.assertEqual(predictions[0][0], .5)
        reverse = []
        calculate_ratings(previous + [game(21, 19, ident=2, winners=('C', 'D'), losers=('A', 'B'))],
                          prediction_observer=lambda i, p: reverse.append(p))
        self.assertAlmostEqual(predictions[0][1] + reverse[1], 1)

    def test_observer_counts_each_game_once_per_player(self):
        samples = [game(), game(21, 5, ident=2)]
        observed = []
        rows = ratings(samples, rating_observer=lambda i, p, r: observed.append((i, p, r)))
        self.assertEqual(len(observed), 8)
        for index, player, rating in observed:
            if index == 1:
                self.assertEqual(rating, rows[player]['rating'])
        self.assertTrue(all(r['games_played'] == 2 for r in rows.values()))

    def test_result_only_database_cache_cannot_supply_new_standings(self):
        import stat_functions as doubles
        doubles.clear_stats_cache()
        self.addCleanup(doubles.clear_stats_cache)
        expected = calculate_ratings([game()])
        with patch.object(doubles, '_calculate_trueskill_rankings_fresh', return_value=expected) as fresh, \
             patch('database_functions.get_trueskill_from_db', return_value=[{'rating': -999}]) as legacy:
            self.assertEqual(doubles.calculate_trueskill_rankings('2026'), expected)
            doubles.calculate_trueskill_rankings('2026')
            fresh.assert_called_once_with('2026')
            legacy.assert_not_called()


class ComparisonTests(unittest.TestCase):
    def test_comparison_checks_published_baseline_and_qualification(self):
        keys = ('id', 'game_date', 'winner1', 'winner2', 'winner_score', 'loser1', 'loser2', 'loser_score')
        games = [game(21, 10, ident=i) for i in range(1, 61)]
        games[-1] = (*games[-1][:2], 'Late', *games[-1][3:])
        # Valid sortable dates, with 60 games so qualification requires two.
        games = [(g[0], f'2026-01-01 10:{i:02d}:00', *g[2:]) for i, g in enumerate(games)]
        history = {'games': [dict(zip(keys, g)) for g in games]}
        old = standings(games, calculate_ratings(games, score_aware=False), 2)
        published = dict(display_year='2026', minimum_games=2,
                         stats=[dict(name=r['player'], rating=r['rating'], wins=r['wins'], losses=r['losses'])
                                for r in old])
        result = compare(history, '2026', published)
        self.assertTrue(result['published_baseline_verified'])
        self.assertNotIn('Late', [r['player'] for r in result['all_qualified']])
        self.assertEqual(game_tuple(history['games'][0]), games[0])
        published['stats'][0]['rating'] += 1
        with self.assertRaisesRegex(ValueError, 'does not match'):
            compare(history, '2026', published)


if __name__ == '__main__':
    unittest.main()
