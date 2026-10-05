"""Edits from native forms omit game_date and retain chronological ordering."""
import ast
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from flask import Flask, jsonify, request, session
from create_games_database import database_update_game

ROOT = Path(__file__).resolve().parents[1]


class GameEditTimeTests(unittest.TestCase):
    def test_score_edit_keeps_original_time_and_order_but_updates_sync_time(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / 'stats.db')
            original = '2026-09-23 09:12:34.123456'
            edited = '2026-09-23 10:14:00'
            with closing(sqlite3.connect(database)) as conn, conn:
                conn.execute('''CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
                    winner1 TEXT, winner2 TEXT, winner_score INTEGER, loser1 TEXT,
                    loser2 TEXT, loser_score INTEGER, updated_at TEXT, comments TEXT,
                    entered_timezone TEXT, updated_by TEXT, location TEXT)''')
                for game_id, stamp in [(1, original), (2, '2026-09-23 09:48:00')]:
                    conn.execute('INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                 (game_id, stamp, 'A', 'B', 21, 'C', 'D', 15, stamp, '',
                                  'America/Los_Angeles', 'tester', 'Beach'))

            def find_game(game_id):
                with closing(sqlite3.connect(database)) as conn, conn:
                    return conn.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchall()

            def update_game(*args, updated_by=None):
                with closing(sqlite3.connect(database)) as conn, conn:
                    database_update_game(conn, (*args[:-1], updated_by, args[-1]))

            app = Flask(__name__)
            app.secret_key = 'test'
            namespace = dict(app=app, api_login_required=lambda f: f, request=request,
                             session=session, jsonify=jsonify, sqlite3=sqlite3, datetime=datetime,
                             find_game=find_game, update_game=update_game,
                             _editable_game_ids=lambda table, ids: set(ids),
                             get_user_now=lambda: edited, _api_get_db=lambda: database,
                             adminfx=SimpleNamespace(snapshot_row=Mock(return_value=None)),
                             _remember_game_location=Mock(), clear_stats_cache=Mock(),
                             update_kobs=Mock(), log_activity=Mock(),
                             _api_game_row_to_dict=lambda row: {'id': row[0], 'game_date': row[1]})
            node = next(n for n in ast.parse((ROOT / 'stats.py').read_text()).body
                        if isinstance(n, ast.FunctionDef) and n.name == 'api_doubles_update')
            exec(compile(ast.Module(body=[node], type_ignores=[]), 'stats.py', 'exec'), namespace)
            response = app.test_client().put('/api/doubles/games/1', json={'loser_score': 16})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['game_date'], original)
            row = find_game(1)[0]
            self.assertEqual(row[7], 16)
            self.assertEqual(row[8], edited)
            with closing(sqlite3.connect(database)) as conn, conn:
                self.assertEqual(conn.execute('SELECT id FROM games ORDER BY game_date DESC').fetchall(),
                                 [(2,), (1,)])


if __name__ == '__main__':
    unittest.main()
