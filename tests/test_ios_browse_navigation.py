"""Check native browsing metadata and division filtering without app startup."""
import ast
from datetime import date
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import unittest
from unittest.mock import patch
from flask import Flask, jsonify
from doubles_division import active_doubles_division
from stats_location_filter import filter_stats_connection


class IOSBrowseNavigationTests(unittest.TestCase):
    def test_default_year_metadata_uses_shared_website_policy(self):
        source = Path(__file__).resolve().parents[1] / 'ios_api.py'
        tree = ast.parse(source.read_text())
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'api_other_game_types')
        app = Flask(__name__)
        def default_year(name=None, kind='other'):
            return '2023' if name == 'Matterhorn' else 'All years'
        namespace = {'app': app, 'jsonify': jsonify, '_S': lambda: SimpleNamespace(browse_game_year=default_year)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        with patch('other_functions.other_year_games', return_value=[]), \
             patch('other_functions.other_game_names', return_value=['Matterhorn', 'Gin Rummy']), \
             patch('other_functions.other_game_types', return_value=['Board games']), \
             patch('other_functions.other_game_type_for_name', return_value='Board games'):
            response = app.test_client().get('/api/other/game-types')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['default_years'], {'Matterhorn': '2023', 'Gin Rummy': 'All years'})
        self.assertEqual(response.json['vollis_default_year'], 'All years')
        self.assertIn('game_names', response.json)

    def test_empty_division_does_not_claim_an_empty_previous_season(self):
        source = Path(__file__).resolve().parents[1] / 'ios_api.py'
        node = next(n for n in ast.walk(ast.parse(source.read_text()))
                    if isinstance(n, ast.FunctionDef) and n.name == 'api_doubles_stats')
        current = str(date.today().year)
        previous = str(date.today().year - 1)
        app = Flask(__name__)
        namespace = {
            'app': app, 'date': date, 'jsonify': jsonify,
            '_year_arg': lambda default: default, '_ranking': lambda *a, **k: {},
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        with ExitStack() as stack:
            for name in ['year_games', 'stats_per_year', 'rare_stats_per_year', 'todays_stats', 'todays_games']:
                stack.enter_context(patch('stat_functions.' + name, return_value=[]))
            stack.enter_context(patch('stat_functions.grab_all_years', return_value=[current, previous, 'All years']))
            response = app.test_client().get('/api/doubles/stats?division=women')
        self.assertEqual(response.json['display_year'], current)
        self.assertFalse(response.json['showing_previous_year'])

    def test_native_doubles_reads_filter_both_divisions(self):
        app = Flask(__name__)
        app.secret_key = 'test'
        for endpoint in ['api_doubles_stats', 'api_doubles_player', 'api_doubles_list', 'api_network']:
            app.add_url_rule('/' + endpoint, endpoint=endpoint, view_func=lambda: '')
            for division, expected in [('open', 1), ('women', 2)]:
                with app.test_request_context('/' + endpoint + '?division=' + division):
                    self.assertEqual(active_doubles_division(), division)
                    with sqlite3.connect(':memory:') as conn:
                        conn.execute('CREATE TABLE games (id, division)')
                        conn.executemany('INSERT INTO games VALUES (?, ?)', [(1, 'open'), (2, 'women')])
                        filter_stats_connection(conn, 'games')
                        self.assertEqual(conn.execute('SELECT id FROM games').fetchall(), [(expected,)])
                        self.assertEqual(conn.execute('SELECT count(*) FROM main.games').fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()
