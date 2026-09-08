"""Exercise location routes against a temporary database, without app startup jobs."""
import ast
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import Mock

from flask import Flask, flash, redirect, render_template, request, session, url_for
from jinja2 import ChoiceLoader, DictLoader
from location_functions import assign_locations, location_games, location_players

ROOT = Path(__file__).resolve().parents[1]


class AdminLocationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = str(Path(self.directory.name) / 'stats.db')
        with sqlite3.connect(self.database) as conn:
            for table in ('games', 'vollis_games', 'other_games'):
                conn.execute(f'''CREATE TABLE {table} (id INTEGER PRIMARY KEY,
                    game_date TEXT, location TEXT, updated_at TEXT, updated_by TEXT,
                    winner1 TEXT, loser1 TEXT, winner_score INTEGER, loser_score INTEGER)''')
            conn.executemany("INSERT INTO games VALUES (?, '2026-09-01', NULL, NULL, NULL, 'Alice', 'Bob', 21, 15)",
                             [(i,) for i in range(1, 106)])
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'))
        self.app.secret_key = 'test-only'
        self.app.testing = True
        self.app.jinja_loader = ChoiceLoader([DictLoader({
            'test_base.html': '{% block extra_css %}{% endblock %}{% block content %}{% endblock %}{% block extra_js %}{% endblock %}',
            'partials/page_header_actions.html': '',
        }), self.app.jinja_loader])
        self.app.context_processor(lambda: dict(base_template='test_base.html', navigation_locations=['Beach']))
        for endpoint in ('login', 'index', 'admin_dashboard'):
            self.app.add_url_rule('/' + endpoint, endpoint, lambda: 'OK')
        namespace = dict(app=self.app, sqlite3=sqlite3, request=request, session=session,
                         redirect=redirect, url_for=url_for, flash=flash,
                         render_template=render_template, location_games=location_games,
                         location_players=location_players, assign_locations=assign_locations,
                         is_admin=lambda: session.get('is_admin'),
                         adminfx=types.SimpleNamespace(stats_db_path=lambda: self.database),
                         clear_stats_cache=Mock(), log_activity=Mock())
        tree = ast.parse((ROOT / 'stats.py').read_text())
        for name in ('admin_required', 'locations_page', 'admin_game_locations'):
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(ROOT / 'stats.py'), 'exec'), namespace)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(logged_in=True, is_admin=True, username='tester')

    def test_admin_access(self):
        with self.client.session_transaction() as state:
            state['is_admin'] = False
        self.assertEqual(self.client.get('/admin/game-locations/').status_code, 302)
        self.assertEqual(self.client.post('/admin/game-locations/', data={'games': 'doubles:1', 'location': 'Beach'}).status_code, 302)
        with sqlite3.connect(self.database) as conn:
            self.assertIsNone(conn.execute('SELECT location FROM games WHERE id=1').fetchone()[0])

    def test_all_pages_uses_reviewed_snapshot(self):
        import re
        html = self.client.get('/admin/game-locations/?player=Alice&missing=1').get_data(as_text=True)
        self.assertIn('Select all 105 matching games', html)
        token = re.search(r'name="selection_token" value="([^"]+)"', html).group(1)
        with sqlite3.connect(self.database) as conn:
            conn.execute("INSERT INTO games VALUES (106, '2026-09-01', NULL, NULL, NULL, 'Alice', 'Bob', 21, 15)")
        response = self.client.post('/admin/game-locations/?player=Alice&missing=1', data={
            'selection_scope': 'all', 'selection_token': token, 'location': 'Beach'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('player=Alice', response.location)
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM games WHERE location='Beach'").fetchone()[0], 105)
            self.assertIsNone(conn.execute('SELECT location FROM games WHERE id=106').fetchone()[0])
        with self.client.session_transaction() as state:
            self.assertEqual(state['_flashes'], [('success', 'Updated locations for 105 games.')])

    def test_invalid_bulk_token_and_manual_selection(self):
        self.client.post('/admin/game-locations/', data={'selection_scope': 'all', 'selection_token': 'invalid', 'location': 'Beach'})
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM games WHERE location IS NOT NULL').fetchone()[0], 0)
        self.client.post('/admin/game-locations/', data={'games': ['doubles:1', 'doubles:3'], 'location': 'Beach'})
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM games WHERE location='Beach'").fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()
