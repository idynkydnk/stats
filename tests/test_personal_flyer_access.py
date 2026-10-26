"""Personal flyer routes and background generation retain account ownership."""
import ast
import os
import sqlite3
import sys
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import abort, flash, g, jsonify, redirect, request, session, url_for

import flyer_functions as flyers
from private_accounts import ai_account_context, connect_data, private_database
from player_identity import unique_player_names
from tests import test_private_accounts as fixtures

ROOT = Path(__file__).resolve().parents[1]


class PersonalFlyerAccessTests(unittest.TestCase):
    register = fixtures.PrivateAccountTests.register

    def setUp(self):
        fixtures.PrivateAccountTests.setUp(self)
        storage = Path(self.directory.name) / 'flyers'
        storage.mkdir()
        for replacement in (
            patch.object(flyers, '_flyer_storage_dir', return_value=str(storage)),
            patch.dict(sys.modules, {'ai_auto_send_jobs': SimpleNamespace(list_jobs_with_share_ids=lambda **kw: [])}),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)
        self.picture = storage / 'picture.jpg'
        self.picture.write_bytes(b'test flyer image')
        for owner in ['alice', 'bob', 'Kyle']:
            flyers.insert_flyer_page(owner + '-own', owner, ['Player'], 'doubles',
                                     '2026-10-07', '17:00', 'Beach', flyer_image_url='/picture.jpg')
        self.service.app = self.app
        self.service.EMAIL_SITE_BASE_URL = 'https://example.com'
        self.app.extensions['image_preview_url'] = lambda image: image
        self.service.note_user_presence = lambda username: None
        self.service.log_activity = lambda *args, **kwargs: None
        self.service.ai_jobs = SimpleNamespace(
            enqueue_flyer_job=Mock(return_value=42),
            daemon_is_alive=Mock(return_value=True), get_job=Mock(),
        )
        self.generate = Mock(return_value='new-flyer')

        def login_required(func):
            @wraps(func)
            def guarded(*args, **kwargs):
                if not session.get('logged_in'):
                    return jsonify(error='Sign in'), 401
                return func(*args, **kwargs)
            return guarded

        def own_players():
            with connect_data(self.path) as conn:
                return conn.execute('SELECT * FROM players').fetchall()

        players_patch = patch('player_functions.get_all_players', side_effect=own_players)
        players_patch.start()
        self.addCleanup(players_patch.stop)
        namespace = dict(
            app=self.app, request=request, session=session, jsonify=jsonify,
            abort=abort, os=os, wraps=wraps, _S=lambda: self.service,
            flash=flash, redirect=redirect, url_for=url_for, date=date,
            login_required=login_required, api_login_required=login_required,
            render_template=lambda template, **context: jsonify(context),
            ai_jobs=self.service.ai_jobs, unique_player_names=unique_player_names,
            build_ai_recap_roster_cards=lambda names: names,
            EMAIL_SITE_BASE_URL=self.service.EMAIL_SITE_BASE_URL,
            adminfx=SimpleNamespace(absolutize_hero_image_url=lambda image, base: base + image),
            _format_utc_str=lambda value: value,
            _stats_db_path=lambda: self.path,
            is_admin=lambda: self.service.is_admin(session.get('username')),
            _generate_and_publish_flyer=self.generate,
            _absolute_site_url=lambda path: 'https://example.com' + path,
            log_activity=self.service.log_activity,
        )
        for filename, names in [
            ('stats.py', {'_browse_username_filter', '_is_owner_or_admin',
                          '_validate_flyer_payload', '_flyer_sport_label',
                          'run_flyer_job', 'download_flyer', 'my_ai_flyers',
                          'my_ai_flyers_delete', 'create_flyer', 'create_flyer_roster',
                          'create_flyer_generate', 'flyer_job_status', 'api_flyer_prompts',
                          '_parse_flyer_form', '_flyer_form_template_kwargs',
                          '_flyer_player_names', '_can_access_job', 'serialize_flyer_list_entry'}),
            ('ios_api.py', {'api_login_required', 'api_my_flyers',
                            'api_create_flyer', 'api_delete_flyer', 'api_pin_ai_library_item'}),
        ]:
            tree = ast.parse((ROOT / filename).read_text())
            nodes = [node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef) and node.name in names]
            exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, 'exec'), namespace)
        for name in ['_browse_username_filter', '_is_owner_or_admin',
                     '_validate_flyer_payload', '_flyer_sport_label']:
            setattr(self.service, name, namespace[name])
        self.run_job = namespace['run_flyer_job']
        self.namespace = namespace
        self.service.serialize_flyer_list_entry = namespace['serialize_flyer_list_entry']
        self.app.add_url_rule('/flyer/<share_id>/', 'view_flyer', lambda share_id: share_id)

    def test_web_browse_and_delete_keep_personal_ownership(self):
        self.register(self.a, 'alice')
        response = self.a.get('/flyers/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['share_id'] for row in response.json['entries']}, {'alice-own', 'bob-own', 'Kyle-own'})
        self.assertEqual({row['share_id'] for row in response.json['entries'] if row['can_manage']}, {'alice-own'})
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertTrue(response.json['showing_all'])
        response = self.a.post('/flyers/delete', data={'share_id': 'bob-own'})
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(flyers.get_flyer_page('bob-own'))
        response = self.a.post('/flyers/delete', data={'share_id': 'alice-own'}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['share_id'] for row in response.json['entries']}, {'bob-own', 'Kyle-own'})
        self.assertIsNone(flyers.get_flyer_page('alice-own'))

    def test_web_creation_and_progress_use_personal_account(self):
        self.register(self.a, 'alice')
        with ai_account_context(self.app, self.path, 'alice'):
            with connect_data(self.path) as conn:
                conn.execute("INSERT INTO players VALUES (1, 'Alice character')")
        response = self.a.get('/create_flyer/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['players'], ['Alice character'])
        payload = dict(players=['Alice character'], event_date='2026-10-12',
                       event_time='17:00', location='Beach', scene_prompt='Sunset')
        with patch('email_content.build_flyer_scene_prompt', return_value='Sunset') as prompt:
            response = self.a.post('/api/flyer_prompts/', json=payload)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['scene_prompt'], 'Sunset')
            self.assertEqual(prompt.call_args.args[0], ['Alice character'])
        response = self.a.post('/create_flyer/roster/', data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['player_cards'], ['Alice character'])
        response = self.a.post('/create_flyer/', data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['selected_players'], ['Alice character'])
        response = self.a.post('/create_flyer/generate/', data={**payload, 'username': 'bob'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/create_flyer/job/42/'))
        username, queued = self.service.ai_jobs.enqueue_flyer_job.call_args.args
        self.assertEqual(username, 'alice')
        self.assertEqual(queued['players'], ['Alice character'])
        for owner, expected in [('alice', 200), ('bob', 403)]:
            self.service.ai_jobs.get_job.return_value = dict(username=owner, status='pending')
            self.assertEqual(self.a.get(response.location).status_code, expected)
        self.service.ai_jobs.get_job.return_value = dict(
            username='alice', status='completed', share_id='alice-own')
        self.assertTrue(self.a.get(response.location).location.endswith('/flyer/alice-own/'))
        self.service.ai_jobs.daemon_is_alive.return_value = False
        response = self.a.post('/create_flyer/generate/', data=payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.generate.call_args.args[0], 'alice')

    def test_web_flyer_flow_still_requires_sign_in(self):
        for path, method in [('/create_flyer/', 'get'),
                             ('/flyers/delete', 'post'), ('/create_flyer/roster/', 'post'),
                             ('/create_flyer/generate/', 'post'), ('/api/flyer_prompts/', 'post'),
                             ('/create_flyer/job/42/', 'get')]:
            with self.subTest(path=path):
                self.assertEqual(getattr(self.a, method)(path).status_code, 401)

    def test_public_flyer_browsing_redacts_creator_fields_and_checks_permissions(self):
        flyers.update_flyer_page('alice-own', scene_prompt='Private creation instructions', image_details='Private notes')
        for path, key in (('/flyers/', 'entries'), ('/api/flyers', 'flyers')):
            for query in ('', '?page=invalid'):
                response = self.app.test_client().get(path + query)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json[key]), 3)
                self.assertFalse(any(row['can_manage'] for row in response.json[key]))
                self.assertNotIn('Private creation instructions', response.text)
                self.assertNotIn('Private notes', response.text)
                self.assertTrue(all(row['download_url'] for row in response.json[key]))
            with patch('content_safety.filter_content', side_effect=lambda kind, entries: [e for e in entries if e['username'] != 'alice']):
                response = self.app.test_client().get(path)
                self.assertEqual({e['share_id'] for e in response.json[key]}, {'bob-own', 'Kyle-own'})
        self.register(self.a, 'alice')
        response = self.a.get('/api/flyers')
        own = next(row for row in response.json['flyers'] if row['share_id'] == 'alice-own')
        self.assertTrue(own['can_manage'])
        self.assertEqual(own['scene_prompt'], 'Private creation instructions')

    def test_flyer_page_controls_follow_login_and_item_ownership(self):
        from bs4 import BeautifulSoup
        from flask import render_template
        from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader
        self.app.jinja_loader = ChoiceLoader([
            DictLoader({'test_base.html': '{% block content %}{% endblock %}',
                        'partials/page_header_actions.html': ''}),
            FileSystemLoader(str(ROOT / 'templates')),
        ])
        self.app.add_url_rule('/pin/<kind>/<share_id>', 'pin_ai_library_item', lambda kind, share_id: '')
        self.app.context_processor(lambda: dict(base_template='test_base.html',
                                               ai_library_limits={'flyer': 25}, recap_subscription_token=lambda: 'test'))
        self.namespace['render_template'] = render_template
        visitor = self.app.test_client()
        page = BeautifulSoup(visitor.get('/flyers/').data, 'html.parser')
        self.assertFalse(page.select('form'))
        self.assertNotIn('Create flyer', page.get_text())
        self.assertEqual(len(page.select('.adm-flyer-card')), 3)
        self.register(self.a, 'alice')
        page = BeautifulSoup(self.a.get('/flyers/').data, 'html.parser')
        self.assertIn('Create flyer', page.get_text())
        self.assertEqual(len(page.select('form[action="/flyers/delete"]')), 1)
        self.assertEqual(page.select_one('form[action="/flyers/delete"] input[name="share_id"]')['value'], 'alice-own')

    def test_browse_delete_and_download_personal_flyers(self):
        headers = self.register(self.a, 'alice')
        self.register(self.b, 'bob')
        response = self.a.get('/api/flyers', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['share_id'] for row in response.json['flyers']}, {'alice-own', 'bob-own', 'Kyle-own'})
        self.assertEqual({row['share_id'] for row in response.json['flyers'] if row['can_manage']}, {'alice-own'})
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.a.delete('/api/flyers/bob-own', headers=headers).status_code, 403)
        self.assertIsNotNone(flyers.get_flyer_page('bob-own'))
        with patch('email_content._email_image_path_from_url', return_value=str(self.picture)):
            response = self.a.get('/flyer/alice-own/download.jpg', headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b'test flyer image')
            response.close()
        self.assertEqual(self.a.delete('/api/flyers/alice-own', headers=headers).status_code, 200)
        self.assertEqual({row['share_id'] for row in self.a.get('/api/flyers', headers=headers).json['flyers']}, {'bob-own', 'Kyle-own'})
        admin = self.app.test_client().get('/api/flyers', headers={'Authorization': 'Bearer shared-token'})
        self.assertEqual(admin.json['total'], 2)
        self.assertTrue(all(row['can_manage'] for row in admin.json['flyers']))

    def test_favorites_require_owner_or_admin_and_boolean_setting(self):
        headers = self.register(self.a, 'alice')
        self.register(self.b, 'bob')
        path = '/api/ai-library/flyer/alice-own/pin'
        self.assertEqual(self.app.test_client().post(path, json={'pinned': True}).status_code, 401)
        self.assertEqual(self.a.post(path, headers=headers, json={'pinned': 'true'}).status_code, 400)
        self.assertEqual(self.a.post(path, headers=headers, json=['pinned']).status_code, 400)
        self.assertEqual(self.a.post('/api/ai-library/flyer/bob-own/pin', headers=headers, json={'pinned': True}).status_code, 403)
        self.assertEqual(self.a.post(path, headers=headers, json={'pinned': True}).status_code, 200)
        self.assertTrue(next(row for row in self.a.get('/api/flyers', headers=headers).json['flyers'] if row['share_id'] == 'alice-own')['pinned'])
        self.assertEqual(self.app.test_client().post(path, headers={'Authorization': 'Bearer shared-token'}, json={'pinned': False}).status_code, 200)
        self.assertFalse(flyers.get_flyer_page('alice-own')['pinned'])
        self.assertEqual(self.a.post('/api/ai-library/flyer/missing/pin', headers=headers, json={'pinned': True}).status_code, 404)

    def test_create_requires_login_and_queues_for_current_account(self):
        self.assertEqual(self.a.get('/api/flyers').status_code, 200)
        self.assertEqual(self.a.post('/api/flyers', json={}).status_code, 401)
        headers = self.register(self.a, 'alice')
        self.assertEqual(self.a.post('/api/flyers', headers=headers, json={}).status_code, 400)
        payload = dict(players=['Alice'], event_date='2026-10-07', event_time='17:00', location='Beach')
        response = self.a.post('/api/flyers', headers=headers, json={**payload, 'username': 'bob'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json['job_id'], 42)
        username, queued = self.service.ai_jobs.enqueue_flyer_job.call_args.args
        self.assertEqual(username, 'alice')
        self.assertEqual(queued['players'], ['Alice'])
        self.assertEqual(self.a.get('/admin', headers=headers).status_code, 403)

    def test_worker_generates_with_creator_players(self):
        self.register(self.a, 'alice')
        self.register(self.b, 'bob')
        with ai_account_context(self.app, self.path, 'alice'):
            with connect_data(self.path) as conn:
                conn.execute("INSERT INTO players VALUES (1, 'Alice character')")

        def generate(username, payload):
            self.assertEqual(session['username'], username)
            with connect_data(self.path) as conn:
                expected = {'alice': [(1, 'Alice character')], 'bob': [], 'Kyle': [(1, 'Shared player')]}
                self.assertEqual(conn.execute('SELECT * FROM players').fetchall(), expected[username])
            self.assertEqual(bool(private_database()), username != 'Kyle')
            return 'new-flyer'

        self.generate.side_effect = generate
        for username in ['alice', 'bob', 'Kyle']:
            self.assertTrue(self.run_job(username, {'players': ['Player']})['success'])

    def prepare_flyer_stats(self):
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                DROP TABLE games;
                CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
                    winner1 TEXT, winner2 TEXT, winner_score INTEGER,
                    loser1 TEXT, loser2 TEXT, loser_score INTEGER);
                CREATE TABLE trueskill_rankings (year, player, mu, sigma, rating,
                    games_played, wins, losses, updated_at);
                INSERT INTO games VALUES
                    (1, '2026-01-01', 'Alex', 'Bea', 21, 'Cam', 'Dee', 10);
            ''')
        headers = self.register(self.a, 'alice')
        self.register(self.b, 'bob')
        with ai_account_context(self.app, self.path, 'alice'):
            with connect_data(self.path) as conn:
                conn.execute("INSERT INTO games VALUES (1, '2026-02-01', 'Cam', 'Dee', 21, 'Alex', 'Bea', 10)")
            # Prime the owner's rating cache; combined ratings must include KT too.
            from stat_functions import calculate_trueskill_rankings
            own_rating = next(r['rating'] for r in calculate_trueskill_rankings(2026) if r['player'] == 'Alex')
        with ai_account_context(self.app, self.path, 'bob'):
            with connect_data(self.path) as conn:
                conn.execute("INSERT INTO games VALUES (1, '2026-03-01', 'Alex', 'Bea', 21, 'Cam', 'Dee', 10)")
        with sqlite3.connect(self.path) as conn:
            # An unavailable source must stay excluded even with an enabled preference.
            conn.execute("INSERT OR REPLACE INTO account_stats_sources VALUES ('alice', 'bob', 1)")
        clock = patch('email_content.datetime')
        clock.start().now.return_value = datetime(2026, 10, 14)
        self.addCleanup(clock.stop)
        from stat_functions import _calculate_trueskill_from_games
        combined = [(1, '2026-01-01', 'Alex', 'Bea', 21, 'Cam', 'Dee', 10),
                    (1, '2026-02-01', 'Cam', 'Dee', 21, 'Alex', 'Bea', 10)]
        combined_rating = next(r['rating'] for r in _calculate_trueskill_from_games(combined) if r['player'] == 'Alex')
        return headers, own_rating, combined_rating

    def test_flyer_preview_honors_selected_sources_for_counts_and_rating(self):
        headers, own_rating, combined_rating = self.prepare_flyer_stats()
        for enabled, rating, wins, percent in [(True, combined_rating, 1, 50), (False, own_rating, 0, 0)]:
            with self.subTest(kt_enabled=enabled):
                response = self.a.put('/api/account/stats-sources', headers=headers,
                                      json={'owner': 'kyle', 'enabled': enabled})
                self.assertEqual(response.status_code, 200, response.json)
                with patch('email_content._clean_player_lines_block', return_value=('Alex', 1, ['Alex'])):
                    response = self.a.post('/api/flyer_prompts/', headers=headers, json={'players': ['Alex']})
                self.assertEqual(response.status_code, 200, response.json)
                self.assertIn(f'Rating: {rating:.1f}\nWins: {wins}\nLosses: 1\nWin %: {percent}%', response.json['scene_prompt'])

    def test_flyer_uses_other_selected_sources_and_respects_revoked_sharing(self):
        import email_content as content
        self.prepare_flyer_stats()
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO stats_source_group VALUES ('alice')")
            conn.execute("UPDATE private_accounts SET share_stats=1 WHERE username='bob'")
        for kt_enabled, bob_enabled, shared, wins in [
            (True, True, True, 2),
            (False, True, True, 1),
            (True, False, True, 1),
            (False, True, False, 0),
        ]:
            with self.subTest(kt=kt_enabled, bob=bob_enabled, shared=shared):
                with sqlite3.connect(self.path) as conn:
                    conn.executemany('INSERT OR REPLACE INTO account_stats_sources VALUES (?, ?, ?)',
                                     [('alice', 'kyle', kt_enabled), ('alice', 'bob', bob_enabled)])
                    conn.execute("UPDATE private_accounts SET share_stats=? WHERE username='bob'", (shared,))
                with ai_account_context(self.app, self.path, 'alice'):
                    prompt = content._flyer_current_year_stats_block(['Alex'])
                    self.assertIn(f'Wins: {wins}\nLosses: 1\nWin %: {100 * wins / (wins + 1):.0f}%', prompt)

    def test_worker_refreshes_custom_flyer_with_selected_stats_and_keeps_owner_assets(self):
        import email_content as content
        from account_stats_views import selected_stats_context
        _, _, combined_rating = self.prepare_flyer_stats()

        def generate(username, payload):
            def references(*args, **kwargs):
                self.assertNotIn('stats_view_database', g)
                with connect_data(self.path) as conn:
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM games').fetchone()[0], 1)
                return [], ['Alex']

            with patch('email_content._image_labels_for_players', return_value={}), \
                 patch('email_content._reference_parts_from_uploaded_photos', side_effect=references), \
                 patch('email_content._generate_image_bytes', return_value=(b'image', 'image/png')) as image, \
                 patch('email_content._normalize_image_bytes_to_aspect', return_value=(b'image', 'image/png')), \
                 patch('email_content._save_email_image', return_value=('/image.png', '/tmp/image.png')):
                content.generate_flyer_image('key', ['Alex'], 'doubles', custom_scene_prompt=(
                    'Sunny beach.\n[CURRENT-YEAR DOUBLES STATS]\nOld stats\n[/CURRENT-YEAR DOUBLES STATS]'))
            prompt = image.call_args.args[0]
            self.assertIn(f'Rating: {combined_rating:.1f}\nWins: 1\nLosses: 1\nWin %: 50%', prompt)
            self.assertIn('Sunny beach.', prompt)
            self.assertNotIn('Old stats', prompt)
            self.assertNotIn('stats_view_database', g)
            # Failed reads also restore owner storage and remove the temporary data.
            with self.assertRaisesRegex(ValueError, 'failed read'):
                with selected_stats_context():
                    snapshot = g.stats_view_database
                    raise ValueError('failed read')
            self.assertFalse(Path(snapshot).exists())
            self.assertNotIn('stats_view_database', g)
            return 'new-flyer'

        self.generate.side_effect = generate
        result = self.run_job('alice', {'players': ['Alex']})
        self.assertTrue(result['success'], result)


if __name__ == '__main__':
    unittest.main()
