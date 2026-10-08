"""Personal flyer routes and background generation retain account ownership."""
import ast
import os
import sys
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import abort, jsonify, request, session

import flyer_functions as flyers
from private_accounts import ai_account_context, connect_data, private_database
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
        self.service.serialize_flyer_list_entry = lambda row, base: dict(row)
        self.service.note_user_presence = lambda username: None
        self.service.log_activity = lambda *args, **kwargs: None
        self.service.ai_jobs = SimpleNamespace(enqueue_flyer_job=Mock(return_value=42))
        self.generate = Mock(return_value='new-flyer')
        namespace = dict(
            app=self.app, request=request, session=session, jsonify=jsonify,
            abort=abort, os=os, wraps=wraps, _S=lambda: self.service,
            _stats_db_path=lambda: self.path,
            is_admin=lambda: self.service.is_admin(session.get('username')),
            _generate_and_publish_flyer=self.generate,
            _absolute_site_url=lambda path: 'https://example.com' + path,
            log_activity=self.service.log_activity,
        )
        for filename, names in [
            ('stats.py', {'_browse_username_filter', '_is_owner_or_admin',
                          '_validate_flyer_payload', '_flyer_sport_label',
                          'run_flyer_job', 'download_flyer'}),
            ('ios_api.py', {'api_login_required', 'api_my_flyers',
                            'api_create_flyer', 'api_delete_flyer'}),
        ]:
            tree = ast.parse((ROOT / filename).read_text())
            nodes = [node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef) and node.name in names]
            exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, 'exec'), namespace)
        for name in ['_browse_username_filter', '_is_owner_or_admin',
                     '_validate_flyer_payload', '_flyer_sport_label']:
            setattr(self.service, name, namespace[name])
        self.run_job = namespace['run_flyer_job']

    def test_browse_delete_and_download_personal_flyers(self):
        headers = self.register(self.a, 'alice')
        self.register(self.b, 'bob')
        response = self.a.get('/api/flyers', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['share_id'] for row in response.json['flyers']], ['alice-own'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.a.delete('/api/flyers/bob-own', headers=headers).status_code, 403)
        self.assertIsNotNone(flyers.get_flyer_page('bob-own'))
        with patch('email_content._email_image_path_from_url', return_value=str(self.picture)):
            response = self.a.get('/flyer/alice-own/download.jpg', headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b'test flyer image')
            response.close()
        self.assertEqual(self.a.delete('/api/flyers/alice-own', headers=headers).status_code, 200)
        self.assertEqual(self.a.get('/api/flyers', headers=headers).json['flyers'], [])
        admin = self.app.test_client().get('/api/flyers', headers={'Authorization': 'Bearer shared-token'})
        self.assertEqual(admin.json['total'], 2)

    def test_create_requires_login_and_queues_for_current_account(self):
        self.assertEqual(self.a.get('/api/flyers').status_code, 401)
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


if __name__ == '__main__':
    unittest.main()
