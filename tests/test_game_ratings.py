import copy
import math
import unittest
from game_ratings import rate_matches, match_teams, summarize_games
from ios_api import _card_stats


def game(id, winners=('A',), losers=('B',), name='No jump', category='Volleyball', date='2026-01-01'):
    return dict(id=id, game_date=date, game_name=name, game_type=category,
                **{f'winner{i}': p for i, p in enumerate(winners, 1)},
                **{f'loser{i}': p for i, p in enumerate(losers, 1)})


class GameRatingTests(unittest.TestCase):
    def test_reference_decisive_head_to_head(self):
        ratings = rate_matches([(['A'], ['B'])])
        self.assertAlmostEqual(ratings['A']['mu'], 29.2054731068, places=6)
        self.assertAlmostEqual(ratings['A']['sigma'], 7.1948165515, places=6)
        self.assertAlmostEqual(ratings['B']['mu'], 20.7945268932, places=6)
        self.assertTrue(ratings['A']['provisional'])
        self.assertEqual(ratings['A']['rating'], round(ratings['A']['mu']-3*ratings['A']['sigma'], 2))

    def test_no_inferred_losing_teams(self):
        self.assertIsNone(match_teams(game(1, losers=('B','C'), name='Backgammon', category='Board games')))
        self.assertIsNone(match_teams(game(1, ('A','B'), ('C','D'), name='Scrabble', category='Board games')))
        self.assertIsNotNone(match_teams(game(1, ('A','B'), ('C','D'), name='Euchre', category='Card games')))
        self.assertIsNotNone(match_teams(game(1, ('A','B'), ('C','D'))))

    def test_supported_multiplayer_games_and_ambiguous_winners(self):
        for name in ['Gin Rummy', 'Scrabble', 'Sequence', 'Catan', 'Spot it!', 'Sushi go!', 'Otrio']:
            summary = summarize_games([game(1, losers=('B', 'C'), name=name, category='Other')])
            self.assertEqual(set(summary['ratings']), {'A', 'B', 'C'})
            self.assertEqual((summary['rated_games'], summary['unrated_games']), (1, 0))
            self.assertIsNone(match_teams(game(2, ('A', 'B'), ('C',), name=name, category='Other')))
        for name in ['Backgammon', 'Euchre', 'Ping pong', 'Tic-tac-toe', 'Unknown']:
            self.assertIsNone(match_teams(game(1, losers=('B', 'C'), name=name, category='Other')))
        for losers in [('B', '?'), ('B', 'B'), ('B', 'A')]:
            self.assertIsNone(match_teams(game(1, losers=losers, name='Gin Rummy', category='Card games')))

    def test_multiplayer_order_symmetry_and_one_game_per_player(self):
        first = game(1, losers=('B', 'C', 'D'), name='Gin Rummy', category='Card games')
        reverse = game(1, losers=('D', 'C', 'B'), name='Gin Rummy', category='Card games')
        ratings = summarize_games([first])['ratings']
        self.assertEqual(ratings, summarize_games([reverse])['ratings'])
        self.assertEqual(ratings['B'], ratings['C'])
        self.assertGreater(ratings['A']['mu'], 25)
        self.assertLess(ratings['B']['mu'], 25)
        self.assertEqual(ratings['A']['opponents'], 3)
        self.assertEqual(ratings['B']['opponents'], 1)
        self.assertTrue(all(r['rated_games'] == 1 for r in ratings.values()))

    def test_large_field_does_not_multiply_winner_adjustment(self):
        head_to_head = rate_matches([(['A'], ['B'])])
        multiplayer = rate_matches([(['A'], ['B', 'C', 'D', 'E'])])
        self.assertAlmostEqual(multiplayer['A']['mu'], head_to_head['A']['mu'])
        self.assertAlmostEqual(multiplayer['A']['sigma'], head_to_head['A']['sigma'])
        self.assertAlmostEqual(25 - multiplayer['B']['mu'], (25 - head_to_head['B']['mu']) / 4)

    def test_multiplayer_uses_opponent_strength_and_replays_stably(self):
        history = [(['Strong'], ['Weak'])] * 30
        upset = rate_matches(history + [(['New'], ['Strong', 'Other'])])
        expected = rate_matches(history + [(['New'], ['Weak', 'Other'])])
        self.assertGreater(upset['New']['mu'], expected['New']['mu'])
        matches = [(['A'], ['B', 'C']), (['C'], ['B', 'A']), (['B'], ['A', 'C'])] * 200
        ratings = rate_matches(matches)
        self.assertTrue(all(math.isfinite(r['rating']) and r['sigma'] > 0 for r in ratings.values()))
        self.assertTrue(all(r['rated_games'] == 600 for r in ratings.values()))

    def test_rotating_and_luck_heavy_games_not_rated(self):
        for name in ['Kings', 'Vollis kings', 'Coed kings/queens', 'One Dollar Wednesdays', 'Uno', 'Ono 99']:
            category = 'Card games' if name in ['Uno','Ono 99'] else 'Volleyball'
            self.assertIsNone(match_teams(game(1, name=name, category=category)))

    def test_incomplete_or_repeated_players_skip_whole_match(self):
        for w,l in [(('A','?'),('B','C')), (('A','A'),('B','C')), (('A',),('A',)), ((),('B',))]:
            self.assertIsNone(match_teams(game(1,w,l)))

    def test_chronological_replay_and_no_mutation(self):
        games=[game(3,date='2026-03-01'),game(1,date='2026-01-01'),game(2,('B',),('A',),date='2026-02-01')]
        original=copy.deepcopy(games)
        self.assertEqual(summarize_games(games),summarize_games(list(reversed(games))))
        self.assertEqual(games,original)
        self.assertNotEqual(summarize_games(games)['ratings'],summarize_games(games[:-1])['ratings'])

    def test_opponent_variety_required_even_after_many_games(self):
        r=rate_matches([(['A'],['B'])]*40)
        self.assertTrue(r['A']['provisional'])
        r=rate_matches([(['A'],[p]) for p in ['B','C','D']]*20)
        self.assertFalse(r['A']['provisional'])
        self.assertTrue(all(math.isfinite(v['rating']) and v['sigma']>0 for v in r.values()))

    def test_coverage_and_api_do_not_mistake_game_count_for_rating(self):
        summary=summarize_games([game(1),game(2,losers=('B','C'))])
        self.assertEqual((summary['rated_games'],summary['unrated_games']),(1,1))
        card=dict(game_name='No jump',stats=[['A',2,0,1,2],['C',0,1,0,1]],**summary)
        payload=_card_stats(card)
        self.assertEqual(payload['stats'][0]['rating'],summary['ratings']['A']['rating'])
        self.assertTrue(payload['stats'][0]['provisional'])
        self.assertNotIn('rating',payload['stats'][1])
        self.assertNotIn('rating',_card_stats({'stats':[['A',10,0,1,10]]})['stats'][0])

class RatingScopeTests(unittest.TestCase):
    def test_game_year_location_and_changed_results_are_isolated(self):
        import os
        import sqlite3
        import tempfile
        from unittest.mock import patch
        from flask import Flask
        import other_functions
        from game_ratings import attach_other_ratings
        from stats_location_filter import filter_stats_connection
        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE other_games (id INTEGER PRIMARY KEY, game_date, game_name, game_type, winner1, loser1, location)')
                conn.executemany('INSERT INTO other_games VALUES (?,?,?,?,?,?,?)',[
                    (1,'2026-01-01','No jump','Volleyball','A','B','Beach'),
                    (2,'2026-01-02','No jump','Volleyball','B','A','Park'),
                    (3,'2025-01-01','No jump','Volleyball','X','Y','Beach'),
                    (4,'2026-01-01','Coed','Volleyball','Z','Q','Beach')])
            app=Flask(__name__)
            app.add_url_rule('/other_stats/<year>/',endpoint='other_stats',view_func=lambda year:'')
            def cursor():
                conn=sqlite3.connect(path)
                conn.row_factory=sqlite3.Row
                filter_stats_connection(conn,'other_games')
                return conn.cursor()
            with patch.object(other_functions,'set_cur',side_effect=cursor):
                with app.test_request_context('/other_stats/2026/?location=Beach'):
                    first=attach_other_ratings({'game_name':'No jump'},'2026')
                    self.assertEqual(first['rated_games'],1)
                    self.assertEqual(set(first['ratings']),{'A','B'})
                with app.test_request_context('/other_stats/2026/'):
                    self.assertEqual(attach_other_ratings({'game_name':'No jump'},'2026')['rated_games'],2)
                with sqlite3.connect(path) as conn:
                    conn.execute("UPDATE other_games SET winner1='B',loser1='A' WHERE id=1")
                with app.test_request_context('/other_stats/2026/?location=Beach'):
                    changed=attach_other_ratings({'game_name':'No jump'},'2026')
                    self.assertGreater(changed['ratings']['B']['rating'],changed['ratings']['A']['rating'])
                    self.assertNotEqual(first['ratings'],changed['ratings'])
        finally:
            os.unlink(path)

class YearSelectionTests(unittest.TestCase):
    def test_explicit_all_years_is_not_the_default_season(self):
        from flask import Flask
        from ios_api import _year_arg
        app = Flask(__name__)
        for query, expected in [('', '2026'), ('?year=All%20years', 'All years'), ('?year=all', 'All years'), ('?year=2024', '2024')]:
            with app.test_request_context('/api/other/stats' + query):
                self.assertEqual(_year_arg('2026'), expected)
