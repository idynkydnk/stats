"""Real web routes and account middleware; external AI work is stubbed."""
import ast
from functools import wraps
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import abort, flash, jsonify, redirect, request, session, url_for

from private_accounts import connect_data, private_database
from tests import test_private_accounts as account_fixtures
from tests import test_ai_summary_games as game_fixtures


class PersonalRecapCreationTests(unittest.TestCase):
    register = account_fixtures.PrivateAccountTests.register

    def setUp(self):
        account_fixtures.PrivateAccountTests.setUp(self)
        # Use real game schemas so the picker runs its actual ownership queries.
        schema = game_fixtures.AISummaryGamesTests()
        schema.setUp()
        self.addCleanup(schema.tearDown)
        with sqlite3.connect(self.path) as conn:
            conn.execute('DROP TABLE games')
            for table in ('games', 'vollis_games', 'other_games'):
                ddl = schema.conn.execute('SELECT sql FROM sqlite_master WHERE name=?', (table,)).fetchone()[0]
                conn.execute(ddl)
                kind = {'games': 'doubles', 'vollis_games': 'vollis', 'other_games': 'other'}[table]
                game_fixtures.AISummaryGamesTests.insert(SimpleNamespace(conn=conn), kind, 'Kyle', '2026-10-06')
                game_fixtures.AISummaryGamesTests.insert(SimpleNamespace(conn=conn), kind, 'dan', '2026-10-06')
        self.jobs = SimpleNamespace(daemon_is_alive=Mock(return_value=True),
                                    enqueue_job=Mock(return_value=42), get_job=Mock())
        self.published = Mock(return_value='new-recap')

        def login_required(func):
            @wraps(func)
            def guarded(*args, **kwargs):
                if not session.get('logged_in'):
                    return jsonify(error='Sign in'), 401
                return func(*args, **kwargs)
            return guarded

        def own_players(ids, kind):
            with connect_data(self.path) as conn:
                return [row[0] for row in conn.execute('SELECT winner1 FROM games WHERE id=?', (ids[0],))]

        def payload(ids, **kwargs):
            return {'players': own_players(ids, 'doubles'), 'database': private_database()}

        namespace = dict(
            app=self.app, sqlite3=sqlite3, session=session, request=request, jsonify=jsonify,
            flash=flash, redirect=redirect, url_for=url_for, abort=abort,
            login_required=login_required, api_login_required=login_required,
            _stats_db_path=lambda: self.path,
            is_admin=lambda: self.service.is_admin(session.get('username')),
            render_template=lambda template, **context: jsonify(context), ai_jobs=self.jobs,
            _roster_players_for_games=own_players, build_ai_recap_roster_cards=lambda names: names,
            _normalize_image_mode=lambda value: value or 'none',
            _normalize_prompt_style=lambda value: value,
            log_activity=Mock(), _save_ai_prompt_log=Mock(), _ai_image_log_note=lambda value: '',
            build_doubles_email_payload=payload, build_vollis_email_payload=payload,
            build_other_email_payload=payload, _publish_ai_recap=self.published,
        )
        names = {'ai_summary', 'select_ai_prompt', 'select_ai_style', 'preview_ai_summary_with_prompt',
                 '_render_select_ai_prompt', 'ai_summary_job_status', 'api_ai_summary_job_status',
                 'api_generate_and_send_ai_summary', '_can_access_job', '_is_owner_or_admin'}
        tree = ast.parse(Path('stats.py').read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'stats.py', 'exec'), namespace)
        self.app.add_url_rule('/', 'index', lambda: 'Stats')
        self.app.add_url_rule('/recap/<share_id>/', 'view_ai_recap', lambda share_id: share_id)
        filtering = patch('email_content.filter_illustratable_players', side_effect=lambda names: names)
        filtering.start()
        self.addCleanup(filtering.stop)

    def add_personal_games(self, client, username):
        self.register(client, username)
        with client.session_transaction() as state:
            self.assertEqual(state['username'], username)
        from private_accounts import account_for_user, provision_database
        account = account_for_user(self.path, username)
        path = provision_database(self.path, account['id'])
        with sqlite3.connect(path) as conn:
            for kind in ('doubles', 'vollis', 'other'):
                game_fixtures.AISummaryGamesTests.insert(SimpleNamespace(conn=conn), kind, username, '2026-10-05')
            conn.execute('UPDATE games SET winner1=?', (username + ' player',))
        return path

    def test_all_personal_users_can_pick_own_games_and_queue_web_recap(self):
        for username in ('dan', 'jen', 'newperson'):
            with self.subTest(username=username):
                client = self.app.test_client()
                self.add_personal_games(client, username)
                page = client.get('/ai_summary/')
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page.json['doubles_games'][0][2], username + ' player')
                self.assertEqual(len(page.json['doubles_games']), 1)
                self.assertEqual(page.json['select_all_ids'], {kind: ['1'] for kind in ('doubles', 'vollis', 'other')})
                self.assertFalse(page.json['showing_all'])
                self.assertIn('no-store', page.headers['Cache-Control'])
                form = {'game_ids': '1', 'game_type': 'doubles', 'prompt_style': 'default'}
                roster = client.post('/select_ai_prompt/', data=form)
                self.assertEqual(roster.status_code, 200)
                self.assertEqual(roster.json['player_cards'], [username + ' player'])
                self.assertEqual(client.post('/select_ai_style/', data=form).status_code, 200)
                self.assertEqual(client.post('/preview_ai_summary_with_prompt/', data=form).status_code, 302)
                self.assertEqual(self.jobs.enqueue_job.call_args.args[:3], (username, ['1'], 'doubles'))
                with client.session_transaction() as state:
                    self.assertEqual(state['ai_summary_job_id'], 42)
                self.assertEqual(client.post('/api/generate_and_send_ai_summary/', data=form).status_code, 200)
                self.assertEqual(client.get('/admin').status_code, 403)

    def test_synchronous_fallback_uses_own_database(self):
        path = self.add_personal_games(self.a, 'dan')
        self.jobs.daemon_is_alive.return_value = False
        response = self.a.post('/preview_ai_summary_with_prompt/', data={'game_ids': '1', 'game_type': 'doubles'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.published.call_args.args[0], {'players': ['dan player'], 'database': path})

    def test_job_pages_and_polling_still_enforce_ownership(self):
        self.add_personal_games(self.a, 'dan')
        for owner, expected in [('dan', 200), ('someoneelse', 403)]:
            self.jobs.get_job.return_value = {'id': 42, 'username': owner, 'status': 'running'}
            self.assertEqual(self.a.get('/ai_summary/job/42/').status_code, expected)
            self.assertEqual(self.a.get('/api/ai_summary_job/42/').status_code, expected)
        self.jobs.get_job.return_value = {'id': 42, 'username': 'dan', 'status': 'completed', 'share_id': 'new-recap'}
        self.assertEqual(self.a.get('/ai_summary/job/42/').status_code, 302)
        self.assertIn('/recap/new-recap/', self.a.get('/api/ai_summary_job/42/').json['recap_url'])

    def test_guests_still_need_to_sign_in_and_kyle_keeps_existing_picker(self):
        self.assertEqual(self.a.get('/ai_summary/').status_code, 401)
        self.assertEqual(self.a.post('/preview_ai_summary_with_prompt/', data={'game_ids': '1'}).status_code, 401)
        response = self.a.get('/ai_summary/', headers={'Authorization': 'Bearer shared-token'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['showing_all'])
        self.assertEqual(len(response.json['doubles_games']), 2)


if __name__ == '__main__':
    unittest.main()
