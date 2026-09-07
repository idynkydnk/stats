import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from flask import Flask
import stat_functions as doubles
import vollis_functions as vollis
import other_functions as other
from stats_location_filter import filter_stats_connection


class StatsLocationFilterTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.add_url_rule('/stats/<year>/', endpoint='stats', view_func=lambda year: '')
        self.app.add_url_rule('/edit/', endpoint='update', view_func=lambda: '', methods=['GET', 'POST'])
        fd, self.path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        with sqlite3.connect(self.path) as conn:
            conn.execute('''CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
                winner1 TEXT, winner2 TEXT, winner_score INTEGER, loser1 TEXT, loser2 TEXT,
                loser_score INTEGER, updated_at TEXT, comments TEXT, entered_timezone TEXT,
                updated_by TEXT, location TEXT)''')
            conn.executemany('INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', [
                (1, '2011-01-01 12:00:00', 'A', 'B', 21, 'C', 'D', 10, '2012-03-01 12:00:00', '', None, None, 'New Jersey'),
                (2, '2011-02-01 12:00:00', 'C', 'D', 21, 'A', 'B', 10, '2012-03-01 12:00:00', '', None, None, 'California'),
                (3, '2012-01-01 12:00:00', 'A', 'B', 21, 'C', 'D', 10, '2012-03-01 12:00:00', '', None, None, 'New Jersey'),
                (4, '2012-02-01 12:00:00', 'A', 'B', 21, 'C', 'D', 10, '2012-03-01 12:00:00', '', None, None, None),
            ])
            conn.execute('CREATE TABLE vollis_games AS SELECT id, game_date, winner1 AS winner, winner_score, loser1 AS loser, loser_score, updated_at, entered_timezone, location FROM games')
            conn.execute('CREATE TABLE other_games AS SELECT * FROM games')
        self.patches = [patch.object(module, 'create_connection', side_effect=lambda *args: sqlite3.connect(self.path)) for module in (doubles, vollis, other)]
        for item in self.patches:
            item.start()
        doubles.clear_stats_cache()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        doubles.clear_stats_cache()
        os.unlink(self.path)

    def test_year_location_intersection_and_cached_results(self):
        for location, expected in [('New Jersey', (1, 0)), ('California', (0, 1)), ('', (1, 1)), ('New Jersey', (1, 0))]:
            with self.app.test_request_context('/stats/2011/', query_string={'location': location}):
                counts = doubles.get_player_wins_losses('2011')['A']
                self.assertEqual((counts['wins'], counts['losses']), expected)
                self.assertEqual(doubles.year_games_count('2011'), sum(expected))
        with self.app.test_request_context('/stats/All years/?location=New+Jersey'):
            self.assertEqual(doubles.year_games_count('All years'), 2)
            self.assertEqual(len(doubles.year_games_paginated_search('All years', 'A')), 2)

    def test_all_game_types_and_missing_location(self):
        with self.app.test_request_context('/stats/2011/?location=California'):
            self.assertEqual(vollis.vollis_stats_per_year('2011', 0)[0][:3], ['C', 1, 0])
            cur = other.set_cur()
            self.assertEqual(cur.execute('SELECT COUNT(*) FROM other_games').fetchone()[0], 1)
        with self.app.test_request_context('/stats/2012/?missing=1'):
            self.assertEqual(doubles.year_games_count('2012'), 1)
        with self.app.test_request_context('/stats/2011/?location=Unknown'):
            self.assertEqual(doubles.stats_per_year('2011', 1), [])
            self.assertIn('2012', doubles.grab_all_years())

    def test_rankings_bypass_shared_database_cache(self):
        with self.app.test_request_context('/stats/2011/?location=New+Jersey'), patch('database_functions.get_trueskill_from_db') as read, patch('database_functions.save_trueskill_to_db') as save:
            rankings = doubles.calculate_trueskill_rankings('2011')
            self.assertEqual({r['player'] for r in rankings}, {'A', 'B', 'C', 'D'})
            read.assert_not_called()
            save.assert_not_called()

    def test_no_filter_outside_stats_and_safe_location_quotes(self):
        with self.app.test_request_context('/edit/?location=New+Jersey'):
            self.assertEqual(doubles.year_games_count('2011'), 2)
        with self.app.test_request_context('/stats/2011/', query_string={'location': "x' OR 1=1 --"}):
            self.assertEqual(doubles.year_games_count('2011'), 0)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM games').fetchone()[0], 4)


if __name__ == '__main__':
    unittest.main()
