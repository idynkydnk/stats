"""Exercise real recap lists through personal-account middleware and preferences."""
import ast
import json
import os
import secrets
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import abort, flash, jsonify, redirect, request, session, url_for
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

import admin_functions as admin
from tests import test_private_accounts as account_fixtures

ROOT = Path(__file__).resolve().parents[1]


class PersonalRecapAccessTests(unittest.TestCase):
    register = account_fixtures.PrivateAccountTests.register

    def setUp(self):
        account_fixtures.PrivateAccountTests.setUp(self)
        storage = Path(self.directory.name) / 'recaps'
        storage.mkdir()
        for replacement in (
            patch.object(admin, 'stats_db_path', return_value=self.path),
            patch.object(admin, '_recap_storage_dir', return_value=str(storage)),
            patch.object(admin, '_legacy_recap_dir', return_value=str(storage / 'legacy')),
            patch.dict(sys.modules, {'ai_auto_send_jobs': SimpleNamespace(list_jobs_with_share_ids=lambda **kw: [])}),
            patch('email_content.cleanup_expired_solo_images'),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)
        admin.init_ai_recap_pages_db()
        for i in range(30):
            admin.insert_ai_recap_page(f'kyle-{i:02}', 'Kyle', 'doubles', '<p>Kyle recap</p>')
        admin.insert_ai_recap_page('alice-own', 'alice', 'doubles', '<p>Alice recap</p>')
        admin.insert_ai_recap_page('bob-own', 'bob', 'doubles', '<p>Bob recap</p>')
        self.service.app = self.app
        self.service.adminfx = admin
        self.service.EMAIL_SITE_BASE_URL = 'https://example.com'
        self.service.serialize_recap_list_entry = lambda row, base: dict(row)
        self.generate = Mock(return_value={'html_body': '<p>Updated recap</p>',
                                          'plain_text_body': 'Updated recap', 'subject': 'Updated'})
        self.generate_image = Mock()
        namespace = dict(
            app=self.app, request=request, session=session, jsonify=jsonify,
            abort=abort, flash=flash, redirect=redirect, url_for=url_for, json=json, adminfx=admin, secrets=secrets,
            _stats_db_path=lambda: self.path, _S=lambda: self.service,
            EMAIL_SITE_BASE_URL=self.service.EMAIL_SITE_BASE_URL,
            serialize_recap_list_entry=self.service.serialize_recap_list_entry,
            is_admin=lambda: self.service.is_admin(session.get('username')),
            log_activity=lambda *args, **kwargs: None, os=os,
            note_user_presence=lambda username: None, validate_auth_token=lambda token: None,
            _build_ai_summary_payload=self.generate,
            _try_generate_email_hero_image=self.generate_image,
            _load_games_and_players_for_recap=Mock(return_value=([{}], ['Alice'], None, '')),
            replace_recap_hero_image=lambda html, url: html + '<img src="' + url + '">',
            _refresh_instagram_slides=Mock(return_value=[]),
            render_template=lambda template, **context: jsonify(context),
            recap_html_for_page=lambda html: html,
        )
        for filename, names in [
            ('stats.py', {'my_ai_recaps', 'view_ai_recap', 'recap_og_image',
                          '_is_owner_or_admin', 'my_ai_recaps_delete', 'login_required',
                          'remake_ai_recap_summary', 'remake_ai_recap_image',
                          'upload_ai_recap_image', '_require_recap_creator',
                          'rebuild_ai_recap_instagram', 'pin_ai_library_item'}),
            ('ios_api.py', {'api_my_recaps'}),
        ]:
            tree = ast.parse((ROOT / filename).read_text())
            nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
            exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, 'exec'), namespace)
        self.app.add_url_rule('/login/', 'login', lambda: 'Sign in')

    def test_web_favorite_requires_owner_and_form_token(self):
        self.register(self.a, 'alice')
        with self.a.session_transaction() as state:
            state['recap_subscription_token'] = 'test-token'
        path = '/ai-library/recap/alice-own/pin'
        self.assertEqual(self.a.post(path, data={'pinned': '1'}).status_code, 400)
        data = {'pinned': '1', 'subscription_token': 'test-token'}
        self.assertEqual(self.a.post('/ai-library/recap/bob-own/pin', data=data).status_code, 403)
        self.assertEqual(self.a.post(path, data=data).status_code, 302)
        self.assertTrue(admin.get_ai_recap_page('alice-own')['pinned'])
        self.assertEqual(self.a.post(path, data={**data, 'pinned': '0'}).status_code, 302)
        self.assertFalse(admin.get_ai_recap_page('alice-own')['pinned'])

    def test_web_and_api_filter_before_pagination_and_follow_kt_preferences(self):
        headers = self.register(self.a, 'alice')
        self.register(self.b, 'bob')
        # Sharing another user's stats must not add their recaps to this directory.
        self.b.put('/api/account/stats-sharing', json={'share_stats': True})
        self.a.put('/api/account/stats-sources', json={'owner': 'bob', 'enabled': True})
        for enabled in [True, False, True]:
            response = self.a.put('/api/account/stats-sources', json={'owner': 'kyle', 'enabled': enabled})
            self.assertEqual(response.status_code, 200)
            for path, key, total_key, auth in [
                ('/ai-recaps/', 'entries', 'total_entries', {}),
                ('/api/ai/recaps', 'recaps', 'total', headers),
            ]:
                entries = []
                for page in [1, 2]:
                    response = self.a.get(f'{path}?page={page}', headers=auth)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json[total_key], 31 if enabled else 1)
                    self.assertFalse(response.json['showing_all'])
                    entries.extend(response.json[key])
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                ids = {entry['share_id'] for entry in entries}
                expected = {'alice-own'} | ({f'kyle-{i:02}' for i in range(30)} if enabled else set())
                self.assertEqual(ids, expected)
                if key == 'entries':
                    self.assertEqual({entry['share_id'] for entry in entries if entry['can_manage']}, {'alice-own'})

    def test_legacy_starter_preference_and_explicit_selection(self):
        self.register(self.a, 'alice')
        self.a.put('/api/account/starter-stats', json={'show_starter_stats': False})
        with sqlite3.connect(self.path) as conn:
            conn.execute('DELETE FROM account_stats_sources WHERE viewer=?', ('alice',))
        self.assertEqual(self.a.get('/ai-recaps/').json['total_entries'], 1)
        # Web choices can override the older starter-stats field.
        with sqlite3.connect(self.path) as conn:
            conn.execute('INSERT INTO account_stats_sources VALUES (?, ?, 1)', ('alice', 'kyle'))
        self.assertEqual(self.a.get('/api/ai/recaps').json['total'], 31)

    def test_personal_user_can_open_published_recaps(self):
        self.register(self.a, 'alice')
        for share_id in ['alice-own', 'kyle-00']:
            response = self.a.get(f'/recap/{share_id}/')
            self.assertEqual(response.status_code, 200)
            self.assertIn('recap</p>', response.json['recap_html'])
        self.assertEqual(self.a.get('/recap/missing/').status_code, 404)
        self.assertEqual(self.a.get('/admin').status_code, 403)

    def test_public_directory_and_single_creator_filter_are_preserved(self):
        self.assertEqual(self.app.test_client().get('/ai-recaps/').json['total_entries'], 32)
        self.assertEqual(admin.list_ai_recap_pages(username='alice')[1], 1)
        self.assertEqual(admin.list_ai_recap_pages(usernames=set()), ([], 0))

    def test_personal_delete_controls_only_allow_owned_recaps(self):
        self.register(self.a, 'alice')
        for share_id in ['bob-own', 'kyle-00']:
            self.assertEqual(self.a.post('/ai-recaps/delete', data={'share_id': share_id}).status_code, 302)
            self.assertIsNotNone(admin.get_ai_recap_page(share_id))
        self.assertEqual(self.a.post('/ai-recaps/delete', data={'share_id': 'alice-own'}).status_code, 302)
        self.assertIsNone(admin.get_ai_recap_page('alice-own'))

    def test_management_controls_on_public_and_creator_views(self):
        self.register(self.a, 'alice')
        with patch('email_content.list_instagram_slide_paths', return_value=[]):
            for suffix in ['', '?published=1']:
                for share_id, allowed in [('alice-own', True), ('bob-own', False)]:
                    response = self.a.get(f'/recap/{share_id}/{suffix}')
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json['can_manage'], allowed)
                    self.assertEqual(response.json['can_remake'], allowed and bool(suffix))
                public = self.app.test_client().get(f'/recap/alice-own/{suffix}')
                self.assertFalse(public.json['can_manage'])
                self.assertFalse(public.json['can_remake'])

    def test_remake_summary_uses_owner_games_and_restores_admin_identity(self):
        from private_accounts import private_database, account_for_user, provision_database
        self.register(self.a, 'alice')
        account = account_for_user(self.path, 'alice')
        owner_path = provision_database(self.path, account['id'])
        admin.update_ai_recap_page('alice-own', game_ids_json='[1]')

        def generate(*args, **kwargs):
            self.assertEqual(private_database(), owner_path)
            self.assertEqual(session['username'], 'alice')
            return {'html_body': '<p>Updated recap</p>', 'subject': 'Updated'}

        self.generate.side_effect = generate
        for username in ['alice', 'Kyle', 'moderator']:
            self.service.is_admin = lambda name=None: (name or '').casefold() in {'kyle', 'moderator'}
            with self.a.session_transaction() as state:
                state.update(username=username, logged_in=True)
            response = self.a.post('/recap/alice-own/remake-summary/', data={'custom_prompt': 'Fun'})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(admin.get_ai_recap_page('alice-own')['subject'], 'Updated')
            with self.a.session_transaction() as state:
                self.assertEqual(state['username'], username)
        self.assertEqual(self.generate.call_count, 3)

    def test_mutation_routes_reject_other_users_and_require_login(self):
        self.register(self.a, 'alice')
        for action in ['remake-summary', 'remake-image', 'upload-image', 'instagram/rebuild']:
            url = f'/recap/bob-own/{action}/'
            # Requests reach the ownership check, not the personal-account block.
            self.assertEqual(self.a.post(url).status_code, 302)
            response = self.app.test_client().post(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login/', response.location)
        self.generate.assert_not_called()
        self.assertEqual(admin.get_ai_recap_page('bob-own')['html_body'], '<p>Bob recap</p>')
        response = self.app.test_client().post('/ai-recaps/delete', data={'share_id': 'bob-own'})
        self.assertIn('/login/', response.location)
        self.assertIsNotNone(admin.get_ai_recap_page('bob-own'))

    def test_admins_can_manage_and_delete_any_recap(self):
        self.register(self.b, 'moderator')
        for username, share_id in [('Kyle', 'alice-own'), ('moderator', 'bob-own')]:
            self.service.is_admin = lambda name=None: (name or '').casefold() in {'kyle', 'moderator'}
            with self.a.session_transaction() as state:
                state.update(username=username, logged_in=True)
            response = self.a.get('/ai-recaps/')
            self.assertTrue(response.json['showing_all'])
            self.assertGreater(response.json['total_entries'], 25)
            self.assertTrue(all(entry['can_manage'] for entry in response.json['entries']))
            self.assertTrue(self.a.get(f'/recap/{share_id}/').json['can_manage'])
            response = self.a.post('/ai-recaps/delete', data={'share_id': share_id, 'page': 'invalid'})
            self.assertEqual(response.status_code, 302)
            self.assertIsNone(admin.get_ai_recap_page(share_id))

    def test_owner_name_matching_ignores_case(self):
        self.register(self.a, 'alice')
        admin.update_ai_recap_page('alice-own', username='Alice')
        self.assertTrue(self.a.get('/recap/alice-own/').json['can_manage'])
        self.assertEqual(self.a.post('/ai-recaps/delete', data={'share_id': 'alice-own'}).status_code, 302)
        self.assertIsNone(admin.get_ai_recap_page('alice-own'))

    def test_personal_owner_can_reach_picture_and_instagram_actions(self):
        self.register(self.a, 'alice')
        with patch('email_content.require_ai_api_key', return_value='test'), \
             patch('email_content.save_uploaded_email_image', side_effect=ValueError('Choose a picture')) as upload, \
             patch('email_content.delete_instagram_slides') as clear_slides:
            for action in ['remake-image', 'upload-image', 'instagram/rebuild']:
                response = self.a.post(f'/recap/alice-own/{action}/')
                self.assertEqual(response.status_code, 302)
                self.assertIn('published=1', response.location)
            upload.assert_called_once()
            clear_slides.assert_called_once_with('alice-own')

    def test_admin_picture_remake_uses_recap_owner_context(self):
        from private_accounts import private_database, account_for_user, provision_database
        self.register(self.a, 'alice')
        account = account_for_user(self.path, 'alice')
        owner_path = provision_database(self.path, account['id'])
        admin.update_ai_recap_page('alice-own', game_ids_json='[1]')
        with self.a.session_transaction() as state:
            state.update(username='Kyle', logged_in=True)

        def generate_image(*args, **kwargs):
            self.assertEqual(private_database(), owner_path)
            self.assertEqual(session['username'], 'alice')
            return '/new-picture.png', '', '', '', {}

        self.generate_image.side_effect = generate_image
        with patch('email_content.require_ai_api_key', return_value='test'), \
             patch('email_content.session_stats_for_illustration', return_value={}), \
             patch('email_content.ensure_recap_og_image'):
            response = self.a.post('/recap/alice-own/remake-image/', data={'scene_prompt': 'At the beach'})
        self.assertEqual(response.status_code, 302)
        self.generate_image.assert_called_once()
        self.assertEqual(admin.get_ai_recap_page('alice-own')['hero_image_url'], '/new-picture.png')
        with self.a.session_transaction() as state:
            self.assertEqual(state['username'], 'Kyle')

    def test_templates_render_edit_and_delete_only_for_managers(self):
        environment = Environment(loader=ChoiceLoader([
            DictLoader({'base.html': '{% block content %}{% endblock %}',
                        'partials/recap_subscription.html': '',
                        'partials/page_header_actions.html': '',
                        'partials/menu_sidebar.html': ''}),
            FileSystemLoader(ROOT / 'templates'),
        ]))
        environment.globals.update(url_for=lambda endpoint, **kw: '/' + endpoint,
                                   get_flashed_messages=lambda **kw: [],
                                   request=SimpleNamespace(args={}),
                                   recap_subscription_token=lambda: 'token',
                                   ai_library_limits={'recap': 100, 'flyer': 50})
        for allowed in [False, True]:
            entry = dict(share_id='recap', can_manage=allowed, subject='Recap')
            context = dict(base_template='base.html', entries=[entry], page=1, total_pages=1,
                           session={'logged_in': True}, share_id='recap', can_manage=allowed,
                           recap_html='<p>Recap</p>', show_creator_view=False)
            for template in ['ai_recaps.html', 'recap.html']:
                html = environment.get_template(template).render(**context)
                self.assertEqual('> Edit' in html, allowed)
                self.assertEqual('/my_ai_recaps_delete' in html, allowed)


if __name__ == '__main__':
    unittest.main()
