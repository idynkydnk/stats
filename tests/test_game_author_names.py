"""Game bylines resolve account names without changing ownership identifiers."""
import ast
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

import admin_functions as adminfx


class GameAuthorNameTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = str(Path(directory.name) / 'stats.db')
        patcher = patch.object(adminfx, 'stats_db_path', return_value=self.database)
        patcher.start()
        self.addCleanup(patcher.stop)
        adminfx.init_users_db()
        self.username = 'google_' + 'a' * 32
        adminfx.create_site_user(self.username, 'hash')
        with sqlite3.connect(self.database) as conn:
            conn.execute('UPDATE site_users SET display_name=? WHERE username=?',
                         ('José McDonald', self.username))
        players = patch.object(adminfx, 'list_players_for_site_updates', return_value=[])
        players.start()
        self.addCleanup(players.stop)
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'stats.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == '_api_game_row_to_dict')
        namespace = {'adminfx': adminfx}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'stats.py', 'exec'), namespace)
        self.serialize = namespace['_api_game_row_to_dict']
        self.app = Flask(__name__)

    def test_names_for_list_and_player_rows_preserve_identity(self):
        row = dict(id=1, updated_by=self.username, entered_by=self.username)
        tuple_row = (1, '2026-10-07', 'A', 'B', 21, 'C', 'D', 10, None, '', None, self.username)
        with self.app.test_request_context(), patch.object(
                adminfx, 'site_user_display_name', wraps=adminfx.site_user_display_name) as resolve:
            for game in (row, tuple_row, dict(row, updated_by=self.username.upper())):
                result = self.serialize(game)
                self.assertEqual(result['updated_by_display_name'], 'José McDonald')
                self.assertEqual(result['updated_by'].casefold(), self.username)
            self.assertEqual(self.serialize(row)['entered_by'], self.username)
            self.assertEqual(resolve.call_count, 1)
            self.assertEqual(self.serialize({'id': 2})['updated_by_display_name'], '')
        # A new request must pick up a corrected or linked name.
        adminfx.set_site_user_player(self.username, 'José Smith')
        with self.app.test_request_context():
            self.assertEqual(self.serialize(row)['updated_by_display_name'], 'José Smith')

    def test_missing_social_name_has_readable_fallback(self):
        with self.app.test_request_context():
            result = self.serialize({'updated_by': 'apple_' + 'b' * 32})
            self.assertEqual(result['updated_by_display_name'], 'Apple account')


if __name__ == '__main__':
    unittest.main()
