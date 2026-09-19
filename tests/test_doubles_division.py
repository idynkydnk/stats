import sqlite3
import unittest
from unittest.mock import patch
from flask import Flask, session
from doubles_division import entry_division, ensure_division_column, active_doubles_division
from stats_location_filter import filter_stats_connection
from create_games_database import create_game
import stat_functions as doubles


class DoublesDivisionTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        for endpoint in ('stats', 'add_game', 'api_doubles_create'):
            self.app.add_url_rule('/' + endpoint, endpoint=endpoint, view_func=lambda: '', methods=['GET', 'POST'])
        self.conn = sqlite3.connect(':memory:')
        self.conn.execute('''CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
            winner1 TEXT, winner2 TEXT, winner_score INTEGER, loser1 TEXT, loser2 TEXT,
            loser_score INTEGER, updated_at TEXT, comments TEXT, entered_timezone TEXT,
            updated_by TEXT, location TEXT)''')
        doubles.clear_stats_cache()

    def tearDown(self):
        self.conn.close()
        doubles.clear_stats_cache()

    def test_migration_preserves_existing_games_and_is_repeatable(self):
        self.conn.execute('INSERT INTO games (id) VALUES (1)')
        ensure_division_column(self.conn)
        ensure_division_column(self.conn)
        self.assertEqual(self.conn.execute('SELECT division FROM games').fetchone()[0], 'open')

    def test_jen_default_and_explicit_override_for_web_and_api(self):
        for endpoint, body, expected in [
            ('add_game', {}, 'women'), ('add_game', {'division': 'open'}, 'open'),
            ('api_doubles_create', {}, 'women'), ('api_doubles_create', {'division': 'open'}, 'open'),
        ]:
            kwargs = {'json': body} if endpoint.startswith('api') else {'data': body}
            with self.app.test_request_context('/' + endpoint, method='POST', **kwargs):
                with patch('create_games_database._update_player_last_played'):
                    row_id = create_game(self.conn, ('2026-09-19', 'A', 'B', 21, 'C', 'D', 15, '2026-09-19', '', None, 'Jen', 'Beach'))
                self.assertEqual(self.conn.execute('SELECT division FROM games WHERE id=?', (row_id,)).fetchone()[0], expected)
        with self.app.test_request_context('/add_game'):
            self.assertEqual(entry_division('Kyle'), 'open')
            self.assertEqual(entry_division(' JEN '), 'women')

    def test_sections_and_location_intersect_without_changing_stored_games(self):
        ensure_division_column(self.conn)
        self.conn.executemany('INSERT INTO games (id, division, location) VALUES (?, ?, ?)',
                              [(1, 'open', 'Beach'), (2, 'women', 'Beach'), (3, 'women', 'Park')])
        with self.app.test_request_context('/stats?division=women&location=Beach'):
            filter_stats_connection(self.conn, 'games')
            self.assertEqual(self.conn.execute('SELECT id FROM games').fetchall(), [(2,)])
            self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM main.games').fetchone()[0], 3)
        self.conn.execute('DROP VIEW temp.games')
        with self.app.test_request_context('/stats'):
            filter_stats_connection(self.conn, 'games')
            self.assertEqual(self.conn.execute('SELECT id FROM games').fetchall(), [(1,)])

    def test_jen_provisioning_is_once_only_and_preserves_existing_users(self):
        from migrations.create_jen_user import migrate
        self.conn.execute("CREATE TABLE site_users (username TEXT, password_hash TEXT, is_admin INTEGER, active INTEGER DEFAULT 1)")
        migrate(self.conn)
        self.assertEqual(self.conn.execute('SELECT username, is_admin, active FROM site_users').fetchall(), [('Jen', 0, 1)])
        self.conn.execute("UPDATE site_users SET password_hash='changed', active=0")
        migrate(self.conn)
        self.assertEqual(self.conn.execute('SELECT password_hash, active FROM site_users').fetchone(), ('changed', 0))
        self.conn.execute('DELETE FROM site_users')
        migrate(self.conn)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM site_users').fetchone()[0], 0)
        self.conn.execute('DELETE FROM site_account_migrations')
        self.conn.execute("INSERT INTO site_users VALUES ('jen', 'existing', 0, 0)")
        migrate(self.conn)
        self.assertEqual(self.conn.execute('SELECT password_hash, active FROM site_users').fetchall(), [('existing', 0)])

    def test_stats_default_depends_on_user_and_allows_switching(self):
        for username, expected in [('Jen', 'women'), ('JEN', 'women'), ('Kyle', 'open'), ('Aaron', 'open'), ('', 'open')]:
            with self.app.test_request_context('/stats'):
                session['username'] = username
                self.assertEqual(active_doubles_division(), expected)
            for explicit in ('open', 'women'):
                with self.app.test_request_context('/stats?division=' + explicit):
                    session['username'] = username
                    self.assertEqual(active_doubles_division(), explicit)
            with self.app.test_request_context('/stats?division=invalid'):
                session['username'] = username
                self.assertEqual(active_doubles_division(), expected)

    def test_cache_separates_divisions(self):
        calls = []
        @doubles.cached()
        def sample():
            calls.append(True)
            return len(calls)
        for division, expected in [('open', 1), ('women', 2), ('open', 1)]:
            with self.app.test_request_context('/stats?division=' + division):
                self.assertEqual(sample(), expected)


if __name__ == '__main__':
    unittest.main()
