import ast
from contextlib import ExitStack
from datetime import date
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask, jsonify

import stat_functions


class PlayerGameHistoryOrderTests(unittest.TestCase):
    def test_app_response_is_newest_first_without_reversing_form_or_streak(self):
        source = Path(__file__).resolve().parents[1] / 'ios_api.py'
        node = next(n for n in ast.walk(ast.parse(source.read_text()))
                    if isinstance(n, ast.FunctionDef) and n.name == 'api_doubles_player')
        app = Flask(__name__)
        namespace = {
            'app': app, 'date': date, 'jsonify': jsonify,
            '_S': lambda: SimpleNamespace(player_avatar_context=lambda name: {}),
            '_year_arg': lambda default: '2026', '_abs': lambda value: value,
            '_doubles_game_dict': lambda game: {'id': game[0]},
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        games = [
            [4, '09/28/2026 09:17 AM', 'A', 'B', 21, 'Evan Murray', 'D', 18],
            [2, '10/07/2026 08:29 AM', 'Evan Murray', 'B', 21, 'C', 'D', 18],
            [1, '10/07/2026 08:30 AM', 'Evan Murray', 'B', 21, 'C', 'D', 18],
        ]
        with ExitStack() as stack:
            for name in ('all_years_player', 'total_stats', 'partner_stats_by_year',
                         'opponent_stats_by_year', 'calculate_trueskill_rankings'):
                stack.enter_context(patch.object(stat_functions, name, return_value=[]))
            history = stack.enter_context(patch.object(stat_functions, 'games_from_player_by_year', return_value=games))
            response = app.test_client().get('/api/doubles/players/Evan%20Murray')
            self.assertEqual(response.status_code, 200)
            self.assertEqual([game['id'] for game in response.json['games']], [1, 2, 4])
            self.assertEqual(response.json['recent_form'], ['L', 'W', 'W'])
            self.assertEqual(response.json['current_streak'], {'type': 'W', 'length': 2})
            history.return_value = []
            response = app.test_client().get('/api/doubles/players/Evan%20Murray')
            self.assertEqual(response.json['games'], [])
            self.assertIsNone(response.json['current_streak'])

    def test_history_uses_game_time_instead_of_entry_order(self):
        with sqlite3.connect(':memory:') as conn:
            conn.execute('''CREATE TABLE games (
                id INTEGER PRIMARY KEY, game_date TEXT, winner1 TEXT, winner2 TEXT,
                winner_score INTEGER, loser1 TEXT, loser2 TEXT, loser_score INTEGER
            )''')
            conn.executemany('INSERT INTO games VALUES (?, ?, ?, ?, 21, ?, ?, 18)', [
                (1, '2026-10-07 08:30:00', 'A', 'B', 'Evan Murray', 'D'),
                (2, '2026-10-07 08:29:45', 'Evan Murray', 'B', 'C', 'D'),
                (3, '2026-10-07 08:29:15', 'A', ' Evan Murray ', 'C', 'D'),
                (4, '2026-09-28 09:17:00', 'A', 'B', 'C', 'Evan Murray'),
                (5, '2025-12-31 12:00:00', 'Evan Murray', 'B', 'C', 'D'),
                (6, '2026-10-07 08:30:00', 'Evan Murray', 'B', 'C', 'D'),
                (7, '2026-10-08 10:00:00', 'A', 'B', 'C', 'D'),
            ])
            with patch.object(stat_functions, 'set_cur', side_effect=conn.cursor):
                for year, newest_first in [
                    ('2026', [6, 1, 2, 3, 4]),
                    ('All years', [6, 1, 2, 3, 4, 5]),
                ]:
                    with self.subTest(year=year):
                        games = stat_functions.games_from_player_by_year(year, ' Evan Murray ')
                        # The page reverses the chronological list for display;
                        # recent form and streaks also rely on its newest end.
                        self.assertEqual([game[0] for game in reversed(games)], newest_first)


if __name__ == '__main__':
    unittest.main()
