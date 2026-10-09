"""Standings preserve results and ordering while avoiding player-by-game scans."""
import random
import unittest
from unittest.mock import patch

from flask import Flask, g
import stat_functions as doubles
import vollis_functions as vollis
import other_functions as other


def reference(games, sides, minimum, rare=False, ratings=None):
    """Independent per-player reference, including legacy duplicate-name rules."""
    pairs = [sides(game) for game in games]
    names = list(dict.fromkeys(p for winners, losers in pairs for p in winners + losers))
    rows = []
    for name in names:
        wins = sum(name in winners for winners, _ in pairs)
        losses = sum(name not in winners and name in losers for winners, losers in pairs)
        if ((wins + losses < minimum) if rare else (wins + losses >= minimum)):
            row = [name, wins, losses, wins / (wins + losses)]
            if ratings is not None:
                row.append(ratings.get(name, 0))
            rows.append(row)
    rows.sort(key=(lambda row: (row[1] == 0, -row[4])) if ratings is not None else
              (lambda row: -row[3]))
    return rows


class StandingsTests(unittest.TestCase):
    def setUp(self):
        doubles.clear_stats_cache()
        self.addCleanup(doubles.clear_stats_cache)
        rng = random.Random(7)
        self.games = [(i, '2026-01-01', *rng.choices(['Alice', 'Bob', 'Cara', 'Dan', '?'], k=2),
                       21, *rng.choices(['Alice', 'Bob', 'Cara', 'Dan', '?'], k=2), 10)
                      for i in range(75)]

    def test_doubles_matches_reference_including_ties_duplicates_and_rare_players(self):
        ratings = dict(Alice=12, Bob=12, Cara=9, Dan=0)
        rank_rows = [dict(player=p, rating=r) for p, r in ratings.items()]
        sides = lambda game: ([p for p in game[2:4] if '?' not in p],
                              [p for p in game[5:7] if '?' not in p])
        for games in ([], self.games, [(1, '', 'Alice', 'Bob', 21, 'Cara', 'Dan', 10)]):
            doubles.clear_stats_cache()
            with patch.object(doubles, 'all_games', return_value=games), \
                 patch.object(doubles, 'calculate_trueskill_rankings', return_value=rank_rows) as rate:
                for minimum in (1, 40, 100):
                    self.assertEqual(doubles.stats_per_year('All years', minimum),
                                     reference(games, sides, minimum, ratings=ratings))
                    self.assertEqual(doubles.rare_stats_per_year('All years', minimum),
                                     reference(games, sides, minimum, rare=True, ratings=ratings))
                self.assertEqual(rate.call_count, 1)

    def test_private_calculations_are_reused_only_inside_the_request(self):
        app = Flask(__name__)
        with patch.object(doubles, 'all_games', return_value=self.games), \
             patch.object(doubles, 'calculate_trueskill_rankings', return_value=[]) as rate:
            for account in ('alice', 'bob', 'alice'):
                with app.test_request_context('/'):
                    g.private_database = account + '.db'
                    doubles.stats_per_year('All years', 30)
                    doubles.rare_stats_per_year('All years', 30)
            self.assertEqual(rate.call_count, 3)

    def test_vollis_matches_reference(self):
        games = [(g[0], g[1], g[2], 21, g[5], 10) for g in self.games]
        with patch.object(vollis, 'vollis_year_games', return_value=games):
            for minimum in (0, 20, 100):
                self.assertEqual(vollis.vollis_stats_per_year('All years', minimum),
                                 reference(games, lambda game: ([game[2]], [game[4]]), minimum))

    def test_other_cards_and_thresholds_match_reference_with_invalid_slots(self):
        games = [dict(winner1=g[2], winner2=g[3], loser1=g[5], loser2=g[6],
                      winner3='21', loser3='2026-01-01', winner4=None, loser4='  ')
                 for g in self.games]
        sides = lambda game: ([game['winner1'], game['winner2']], [game['loser1'], game['loser2']])
        expected = reference(games, sides, 0)
        self.assertEqual(other.total_game_name_stats(games), [row + [row[1] + row[2]] for row in expected])
        with patch.object(other, 'other_year_games', return_value=games):
            for minimum in (1, 40, 100):
                self.assertEqual(other.other_stats_per_year('All years', minimum), reference(games, sides, minimum))
                self.assertEqual(other.rare_other_stats_per_year('All years', minimum),
                                 reference(games, sides, minimum, rare=True))


if __name__ == '__main__':
    unittest.main()
