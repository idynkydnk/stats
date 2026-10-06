"""Exercise real recap lists through personal-account middleware and preferences."""
import ast
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import abort, flash, jsonify, redirect, request, session, url_for

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
        namespace = dict(
            app=self.app, request=request, session=session, jsonify=jsonify,
            abort=abort, flash=flash, redirect=redirect, url_for=url_for, json=json, adminfx=admin,
            _stats_db_path=lambda: self.path, _S=lambda: self.service,
            EMAIL_SITE_BASE_URL=self.service.EMAIL_SITE_BASE_URL,
            serialize_recap_list_entry=self.service.serialize_recap_list_entry,
            is_admin=lambda: self.service.is_admin(session.get('username')),
            login_required=lambda func: func, log_activity=lambda *args, **kwargs: None,
            render_template=lambda template, **context: jsonify(context),
            recap_html_for_page=lambda html: html,
        )
        for filename, names in [
            ('stats.py', {'my_ai_recaps', 'view_ai_recap', 'recap_og_image',
                          '_is_owner_or_admin', 'my_ai_recaps_delete'}),
            ('ios_api.py', {'api_my_recaps'}),
        ]:
            tree = ast.parse((ROOT / filename).read_text())
            nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
            exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, 'exec'), namespace)

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


if __name__ == '__main__':
    unittest.main()
