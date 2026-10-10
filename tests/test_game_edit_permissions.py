"""Entry ownership controls game links and both edit request methods."""
import ast
from datetime import date, datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask, abort, flash, jsonify, redirect, request, session, url_for
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

from game_entry_ownership import editable_game_ids

ROOT = Path(__file__).resolve().parents[1]


class GameEditPermissionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = str(Path(self.directory.name) / 'stats.db')
        with sqlite3.connect(self.database) as conn:
            for table in ('games', 'vollis_games', 'other_games'):
                conn.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, entered_by, updated_by)')
                conn.executemany(f'INSERT INTO {table} VALUES (?, ?, ?)',
                                 [(1, 'Alice', 'Bob'), (2, 'Bob', 'Alice'), (3, None, 'Alice')])
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.writes = Mock()
        self.namespace = dict(app=self.app, login_required=lambda f: f,
            api_login_required=lambda f: f, session=session, request=request,
            abort=abort, jsonify=jsonify, flash=flash, redirect=redirect, url_for=url_for,
            sqlite3=sqlite3, date=date, datetime=datetime,
            _stats_db_path=lambda: self.database,
            is_admin=lambda: session.get('username') == 'Admin',
            find_game=lambda id: [(id, '2026-10-05 10:00:00', 'A', 'B', 21, 'C', 'D', 15, '2026-10-05 10:00:00', '')],
            find_vollis_game=lambda id: [(id, '2026-10-05 10:00:00', 'A', 21, 'B', 15, '2026-10-05 10:00:00')],
            find_other_game=lambda id: [dict(id=id, game_date='2026-10-05 10:00:00')],
            winners_scores=lambda: [], losers_scores=lambda: [], year_games=lambda year: [],
            all_players=lambda games: [], vollis_year_games=lambda year: [],
            all_vollis_players=lambda games: [], other_year_games=lambda year: [],
            all_other_players=lambda games: [], other_game_names=lambda games: [],
            other_game_types=lambda games: [], render_template=lambda *a, **kw: 'editor',
            update_game=self.writes, edit_vollis_game=self.writes,
            clear_stats_cache=Mock(), update_kobs=Mock(), log_user_action=Mock(), log_activity=Mock(),
            get_user_now=lambda: '2026-10-05 11:00:00',
            adminfx=SimpleNamespace(snapshot_row=Mock(return_value=None)))
        self.namespace.update(remove_game=self.writes, remove_vollis_game=self.writes, remove_other_game=self.writes)
        wanted = {'delete_game', 'delete_vollis_game', 'delete_other_game', '_editable_game_ids', 'update', 'update_vollis_game', 'update_other_game', 'api_doubles_update'}
        nodes = [n for n in ast.parse((ROOT / 'stats.py').read_text()).body
                 if isinstance(n, ast.FunctionDef) and n.name in wanted]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'stats.py', 'exec'), self.namespace)
        for endpoint in ('games', 'vollis_games', 'other_games', 'edit_games', 'edit_vollis_games', 'edit_other_games'):
            self.app.add_url_rule('/' + endpoint + '/<year>/', endpoint, lambda year: '')
        self.client = self.app.test_client()

    def login(self, username):
        with self.client.session_transaction() as state:
            state['username'] = username
            state['logged_in'] = bool(username)

    def test_only_entrant_or_admin_including_unattributed_games(self):
        with sqlite3.connect(self.database) as conn:
            for table in ('games', 'vollis_games', 'other_games'):
                self.assertEqual(editable_game_ids(conn, table, [1, 2, 3], ' alice '), {1})
                self.assertEqual(editable_game_ids(conn, table, [1, 2, 3], 'Admin', admin=True), {1, 2, 3})
                self.assertEqual(editable_game_ids(conn, table, [1, 2, 3], ''), set())
            conn.execute('UPDATE games SET updated_by="Admin" WHERE id=1')
            self.assertEqual(editable_game_ids(conn, 'games', [1], 'Alice'), {1})

    def test_html_edit_routes_enforce_ownership_on_get_and_post(self):
        for endpoint in ('edit', 'edit_vollis_game', 'edit_other_game'):
            self.login('Alice')
            self.assertEqual(self.client.get(f'/{endpoint}/1/').status_code, 200)
            for method in ('get', 'post'):
                self.assertEqual(getattr(self.client, method)(f'/{endpoint}/2/').status_code, 403)
                self.assertEqual(getattr(self.client, method)(f'/{endpoint}/3/').status_code, 403)
            self.login('Admin')
            self.assertEqual(self.client.get(f'/{endpoint}/2/').status_code, 200)
            self.assertEqual(self.client.get(f'/{endpoint}/3/').status_code, 200)
        self.writes.assert_not_called()

    def test_delete_requires_ownership_for_confirmation_and_submission(self):
        for endpoint in ('delete', 'delete_vollis_game', 'delete_other_game'):
            self.login('Alice')
            self.assertEqual(self.client.get(f'/{endpoint}/1/').status_code, 200)
            for method in ('get', 'post'):
                for game_id in (2, 3):
                    self.assertEqual(getattr(self.client, method)(f'/{endpoint}/{game_id}/').status_code, 403)
            self.login('Admin')
            self.assertEqual(self.client.get(f'/{endpoint}/2/').status_code, 200)
        self.writes.assert_not_called()

    def test_delete_returns_to_browse_year_and_cancel_returns_to_editor(self):
        cases = [('delete', 'games', 'update'),
                 ('delete_vollis_game', 'vollis_games', 'update_vollis_game'),
                 ('delete_other_game', 'other_games', 'update_other_game')]
        # Deletion reads raw column positions, while the edit fixture uses named fields.
        self.namespace['find_other_game'] = lambda id: [(id, '2026-10-05', 'Cards', 'Rummy', 'A', '', '', '', '', '', 21, 'B')]
        render = Mock(return_value='confirmation')
        self.namespace['render_template'] = render
        for username, game_id in [('Alice', 1), ('Admin', 2)]:
            self.login(username)
            for endpoint, browse, editor in cases:
                response = self.client.get(f'/{endpoint}/{game_id}/', query_string=dict(
                    games_year='All years', from_edit='true'))
                self.assertEqual(response.status_code, 200)
                context = render.call_args.kwargs
                with self.app.test_request_context():
                    self.assertEqual(context['cancel_url'], url_for(editor, id=game_id, games_year='All years'))
                self.assertEqual(context['return_url'], '/'+browse+'/All%20years/')
                self.writes.assert_not_called()
                response = self.client.post(f'/{endpoint}/{game_id}/', data={'games_year': 'All years'})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, '/'+browse+'/All%20years/')
                self.writes.assert_called_once_with(game_id)
                self.writes.reset_mock()

    def test_doubles_api_cannot_bypass_ownership(self):
        self.login('Alice')
        response = self.client.put('/api/doubles/games/2', json={'loser_score': 16})
        self.assertEqual(response.status_code, 403)
        self.writes.assert_not_called()

    def test_other_and_vollis_api_updates_cannot_bypass_ownership(self):
        tree = ast.parse((ROOT / 'ios_api.py').read_text())
        register = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'register_ios_api')
        nodes = [n for n in register.body if isinstance(n, ast.FunctionDef)
                 and n.name in {'api_vollis_update', 'api_other_update'}]
        api_namespace = dict(app=self.app, api_login_required=lambda f: f,
                             _S=lambda: SimpleNamespace(**self.namespace), request=request, jsonify=jsonify)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'ios_api.py', 'exec'), api_namespace)
        self.login('Alice')
        with patch('vollis_functions.find_vollis_game', self.namespace['find_vollis_game']), \
             patch('other_functions.find_other_game', self.namespace['find_other_game']):
            for kind in ('vollis', 'other'):
                self.assertEqual(self.client.put(f'/api/{kind}/games/2', json={}).status_code, 403)
        self.writes.assert_not_called()

    def test_save_returns_to_browse_year_for_owner_and_admin(self):
        for username, game_id in [('Alice', 1), ('Admin', 2)]:
            self.login(username)
            response = self.client.post(f'/edit/{game_id}/', data=dict(
                game_date='2026-10-05', game_time='10:00', winner1='A', winner2='B',
                loser1='C', loser2='D', winner_score='21', loser_score='16', games_year='All years'))
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, '/games/All%20years/')

    def test_browse_templates_show_one_edit_link_per_permitted_game(self):
        env = Environment(loader=ChoiceLoader([DictLoader({
            'base': '{% block content %}{% endblock %}',
            'partials/page_header_actions.html': '', 'partials/section_tabs.html': '',
        }), FileSystemLoader(ROOT / 'templates')]))
        env.globals['url_for'] = lambda endpoint, **kw: '/' + endpoint + '/' + str(kw.get('id', ''))
        doubles = [[id, '10/05/2026 10:00 AM', 'A', 'B', 21, 'C', 'D', 15] for id in (1, 2)]
        vollis = [[id, '10/05/26 10:00 AM', 'A', 21, 'B', 15] for id in (1, 2)]
        other = [dict(game_id=id, game_name='No jump', game_date_only='10/05/26', game_time='10:00 AM',
                      winners=[dict(name='A', score=None), dict(name='B', score=None)],
                      losers=[dict(name='C', score=None)], winner_score=21, loser_score=15) for id in (1, 2)]
        for template, games in [('games.html', doubles), ('vollis_games.html', vollis), ('other_games.html', other)]:
            for allowed in (set(), {1}, {1, 2}):
                html = env.get_template(template).render(base_template='base', games=games,
                    editable_game_ids=allowed, year='2026', total_games=2, page=1, per_page=50,
                    page_end=2, total_pages=1, day_groups=[dict(label='Today', games=games)])
                self.assertEqual(html.count('aria-label="Edit game"'), len(allowed))


if __name__ == '__main__':
    unittest.main()
