"""Safety state and external-provider boundaries, using disposable storage only."""
import base64
from io import BytesIO
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask, g, jsonify, session

import content_safety as safety


class ContentSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'identity.db')
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='test')
        self.service = SimpleNamespace(_stats_db_path=lambda: self.path,
                                       is_admin=lambda: session.get('username') == 'admin')
        self.saved = []

        @self.app.post('/generate', endpoint='api_ai_summary_json')
        def generate():
            self.saved.append('generated')
            return jsonify(ok=True)

        @self.app.post('/api/upload', endpoint='api_upload_player_photo')
        def upload():
            self.saved.append('uploaded')
            return jsonify(ok=True)

        @self.app.get('/recap/<share_id>/', endpoint='view_ai_recap')
        def recap(share_id):
            return 'Visible recap'

        @self.app.delete('/account', endpoint='private_delete_account')
        def delete():
            return jsonify(ok=True)

        @self.app.put('/api/ai-library/<kind>/<share_id>', endpoint='api_edit_ai_library_item')
        def edit(kind, share_id):
            self.saved.append('edited')
            return jsonify(ok=True)

        safety.register_content_safety(self.app, self.service)
        self.client = self.app.test_client()
        self.sign_in()

    def sign_in(self, username='alice'):
        with self.client.session_transaction() as state:
            state.clear()
            if username:
                state.update(username=username, logged_in=True)

    def consent(self, granted=True, version=safety.CONSENT_VERSION):
        return self.client.put('/api/privacy/ai-consent', json=dict(granted=granted, version=version))

    def moderation_response(self, flagged=False):
        response = Mock()
        response.json.return_value = {'results': [{'flagged': flagged}]}
        return response

    def test_sharing_defaults_on_and_explicit_choices_are_scoped_and_persistent(self):
        self.assertTrue(self.client.get('/api/privacy/ai-consent').json['granted'])
        self.assertEqual(self.client.post('/generate', json={}).status_code, 200)
        self.assertEqual(self.consent(version='old').status_code, 400)
        self.assertFalse(self.consent(False).json['granted'])
        safety.init_safety(self.path)
        self.assertFalse(self.client.get('/api/privacy/ai-consent').json['granted'])
        self.sign_in('bob')
        self.assertTrue(self.client.get('/api/privacy/ai-consent').json['granted'])
        self.sign_in()
        self.saved.clear()
        self.assertEqual(self.client.post('/generate', json={}).status_code, 403)
        self.assertEqual(self.saved, [])
        self.assertTrue(self.consent().json['granted'])
        self.assertEqual(self.client.post('/generate', json={}).status_code, 200)

    def test_legacy_schema_and_old_opt_ins_use_new_default(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute('DROP TABLE ai_data_consent')
            conn.execute('CREATE TABLE ai_data_consent (username TEXT PRIMARY KEY COLLATE NOCASE, '
                         'version TEXT NOT NULL, granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
            conn.execute("INSERT INTO ai_data_consent(username,version) VALUES ('alice','old')")
        safety.init_safety(self.path)
        self.assertTrue(self.client.get('/api/privacy/ai-consent').json['granted'])
        self.assertFalse(self.consent(False).json['granted'])
        self.sign_in('bob')
        self.assertTrue(self.client.get('/api/privacy/ai-consent').json['granted'])

    def test_default_does_not_allow_unauthenticated_generation(self):
        self.sign_in(None)
        response = self.client.post('/generate', json={})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json['code'], 'authentication_required')
        self.assertEqual(self.saved, [])

    def test_no_upload_or_provider_transfer_when_sharing_is_off(self):
        self.consent(False)
        with patch('requests.post') as post:
            response = self.client.post('/api/upload', data={'photo': (BytesIO(b'photo'), 'face.jpg')},
                                        headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 403)
        post.assert_not_called()
        self.assertEqual(self.saved, [])

    def test_cross_origin_and_form_mutations_cannot_change_consent(self):
        self.consent(False)
        response = self.client.put('/api/privacy/ai-consent', json=dict(granted=True, version=safety.CONSENT_VERSION),
                                   headers={'Origin': 'https://attacker.example'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.put('/api/privacy/ai-consent', data={'granted': 'true'}).status_code, 415)
        self.assertEqual(self.client.put('/api/privacy/ai-consent', json=[]).status_code, 400)
        self.assertFalse(self.client.get('/api/privacy/ai-consent').json['granted'])

    def test_flagged_and_unavailable_moderation_never_save(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), patch('requests.post', return_value=self.moderation_response(True)):
            self.assertEqual(self.client.post('/generate', json={'custom_prompt': 'A story'}).status_code, 400)
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}):
            self.assertEqual(self.client.post('/generate', json={'custom_prompt': 'A story'}).status_code, 503)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), patch('requests.post', return_value=Mock(json=lambda: {})):
            self.assertEqual(self.client.post('/generate', json={'custom_prompt': 'A story'}).status_code, 503)
        self.assertEqual(self.saved, [])

    def test_allowed_content_uses_named_moderation_service(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), patch('requests.post', return_value=self.moderation_response()) as post:
            response = self.client.post('/generate', json={'custom_prompt': 'Friendly volleyball recap'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_args.args[0], 'https://api.openai.com/v1/moderations')
        self.assertEqual(post.call_args.kwargs['json']['input'][0]['text'], 'Friendly volleyball recap')

    def test_animated_upload_cannot_bypass_image_checks_with_safe_first_frame(self):
        from PIL import Image
        raw = BytesIO()
        Image.new('RGB', (2, 2), 'white').save(raw, format='GIF', save_all=True,
                                            append_images=[Image.new('RGB', (2, 2), 'black')])
        self.consent()
        with patch('requests.post') as post:
            response = self.client.post('/api/upload', data={'photo': (BytesIO(raw.getvalue()), 'animation.gif')})
        self.assertEqual(response.status_code, 400)
        self.assertIn('still image', response.json['error'])
        post.assert_not_called()
        self.assertEqual(self.saved, [])

    def test_reports_resolve_author_from_server_and_do_not_hide_automatically(self):
        with patch.object(safety, '_load_content', return_value={'username': 'bob', 'share_id': 'r1'}):
            self.sign_in(None)
            response = self.client.post('/api/content/report', json={'kind': 'recap', 'id': 'r1',
                                                                     'reason': 'Threatening text', 'author': 'victim'})
        self.assertEqual(response.status_code, 200)
        with self.app.test_request_context():
            row = safety.list_reports()[0]
            self.assertEqual(row['author'], 'bob')
            self.assertTrue(safety.content_visible('recap', {'username': 'bob', 'share_id': 'r1'}))

    def test_blocking_is_personal_and_filters_public_detail(self):
        self.assertEqual(self.client.post('/api/content/blocked-users', json={'username': 'bob'}).status_code, 200)
        with patch.object(safety, '_load_content', return_value={'username': 'bob', 'share_id': 'r1'}):
            self.assertEqual(self.client.get('/recap/r1/').status_code, 404)
            self.sign_in('carol')
            self.assertEqual(self.client.get('/recap/r1/').status_code, 200)
        self.sign_in()
        self.assertEqual(self.client.delete('/api/content/blocked-users', json={'username': 'bob'}).status_code, 200)

    def test_admin_remove_and_suspend_hides_content_but_allows_account_deletion(self):
        with patch.object(safety, '_load_content', return_value={'username': 'bob', 'share_id': 'r1'}):
            self.client.post('/api/content/report', json={'kind': 'recap', 'id': 'r1', 'reason': 'Threatening text'})
        self.assertEqual(self.client.post('/api/admin/content-reports/1', json={'action': 'suspend'}).status_code, 403)
        self.sign_in('admin')
        with patch('admin_functions.delete_ai_recap_page', return_value=True) as remove, \
                patch('admin_functions.get_ai_recap_page', return_value={'share_id': 'r1'}), \
                patch('admin_functions.list_ai_recap_pages', return_value=([], 0)), \
                patch('flyer_functions.list_flyer_pages', return_value=([], 0)):
            self.assertEqual(self.client.post('/api/admin/content-reports/1', json={'action': 'suspend'}).status_code, 200)
            remove.assert_called_once_with('r1')
        self.sign_in('bob')
        self.assertEqual(self.client.post('/generate', json={}).status_code, 403)
        self.assertEqual(self.client.delete('/account').status_code, 200)
        self.assertEqual(self.consent(False).status_code, 200)
        with self.app.test_request_context():
            self.assertEqual(safety.filter_content('recap', [{'username': 'bob', 'share_id': 'r2'}]), [])
            g.account_deletion_cleanup = True
            self.assertEqual(len(safety.filter_content('recap', [{'username': 'bob', 'share_id': 'r2'}])), 1)

    def test_cleanup_removes_consent_blocks_and_report_personal_data(self):
        self.consent()
        self.client.post('/api/content/blocked-users', json={'username': 'bob'})
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO content_reports(reporter,kind,content_id,author,reason) VALUES ('bob','recap','r1','alice','personal details')")
            safety.delete_account_safety_data(conn, 'alice')
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM ai_data_consent WHERE username=?',
                                          ('alice',)).fetchone()[0], 0)
        self.assertEqual(self.client.get('/api/content/blocked-users').json['users'], [])
        with self.app.test_request_context():
            report = safety.list_reports()[0]
            self.assertEqual(report['author'], '')
            self.assertNotIn('personal details', report['reason'])

    def test_failed_file_removal_keeps_report_open_and_content_hidden(self):
        with patch.object(safety, '_load_content', return_value={'username': 'bob', 'share_id': 'r1'}):
            self.client.post('/api/content/report', json={'kind': 'recap', 'id': 'r1', 'reason': 'Threatening text'})
        self.sign_in('admin')
        with patch('admin_functions.get_ai_recap_page', return_value={'share_id': 'r1'}), \
                patch('admin_functions.delete_ai_recap_page', return_value=False):
            response = self.client.post('/api/admin/content-reports/1', json={'action': 'hide'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['code'], 'content_removal_pending')
        with self.app.test_request_context():
            self.assertEqual(safety.list_reports()[0]['status'], 'open')
            self.assertFalse(safety.content_visible('recap', {'username': 'bob', 'share_id': 'r1'}))

    def test_admin_cannot_substitute_own_consent_for_content_owner(self):
        self.sign_in('bob')
        self.consent(False)
        self.sign_in('admin')
        self.consent()
        with patch.object(safety, '_load_content', return_value={'username': 'bob', 'share_id': 'r1'}), patch('requests.post') as post:
            response = self.client.put('/api/ai-library/recap/r1', json={'summary': 'A game story'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json['code'], 'content_owner_consent_required')
        post.assert_not_called()
        self.assertEqual(self.saved, [])

    def test_active_author_operation_defers_removal_without_false_success(self):
        from account_lifecycle import account_lock
        with patch.object(safety, '_load_content', return_value={'username': 'bob', 'share_id': 'r1'}):
            self.client.post('/api/content/report', json={'kind': 'recap', 'id': 'r1', 'reason': 'Threatening text'})
        self.sign_in('admin')
        with account_lock(self.path, 'bob'), patch.object(safety, '_remove_reported_content') as remove:
            response = self.client.post('/api/admin/content-reports/1', json={'action': 'hide'})
        self.assertEqual(response.status_code, 409)
        remove.assert_not_called()
        with self.app.test_request_context():
            self.assertEqual(safety.list_reports()[0]['status'], 'open')

    def test_failed_static_image_unlink_can_retry_after_page_was_removed(self):
        content = {'username': 'bob', 'share_id': 'r1', 'hero_image_url': '/static/email_images/unsafe.png'}
        with patch.object(safety, '_load_content', return_value=content):
            self.client.post('/api/content/report', json={'kind': 'recap', 'id': 'r1', 'reason': 'Harmful image'})
        self.sign_in('admin')
        image = Path(self.temp.name) / 'unsafe.png'
        image.write_bytes(b'image')
        with patch('admin_functions.get_ai_recap_page', return_value=content), \
                patch('admin_functions.delete_ai_recap_page', return_value=True), \
                patch('admin_functions.email_images_dir', return_value=self.temp.name), \
                patch('ai_library.live_image_filenames', return_value=set()), \
                patch.object(Path, 'unlink', side_effect=OSError('temporary filesystem failure')):
            self.assertEqual(self.client.post('/api/admin/content-reports/1', json={'action': 'hide'}).status_code, 409)
        self.assertTrue(image.exists())
        with patch('admin_functions.get_ai_recap_page', return_value=None), \
                patch('admin_functions.email_images_dir', return_value=self.temp.name), \
                patch('ai_library.live_image_filenames', return_value=set()):
            self.assertEqual(self.client.post('/api/admin/content-reports/1', json={'action': 'hide'}).status_code, 200)
        self.assertFalse(image.exists())
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM content_removal_work').fetchone()[0], 0)

    def test_provider_call_rechecks_withdrawal_in_worker_context(self):
        import email_content
        self.consent()
        self.consent(False)
        with self.app.test_request_context():
            session['username'] = 'alice'
            with patch.object(email_content, '_generate_ai_text_openai') as generate:
                with self.assertRaises(safety.ContentSafetyError):
                    email_content.generate_ai_text('A game story')
                generate.assert_not_called()

    def test_google_fallback_is_disabled_and_openai_output_is_checked(self):
        import email_content
        self.consent()
        with self.app.test_request_context():
            session['username'] = 'alice'
            with patch.object(safety, 'moderate_content') as moderate, patch.object(email_content, 'active_ai_provider', return_value='gemini'), \
                    patch.object(email_content, 'require_ai_api_key', return_value='test'), \
                    patch.object(email_content, '_generate_ai_text_gemini', return_value='A friendly recap') as generate:
                with self.assertRaises(safety.ContentSafetyError):
                    email_content.generate_ai_text('A game story')
                generate.assert_not_called()
                moderate.assert_not_called()
            with patch.object(safety, 'moderate_content') as moderate, patch.object(email_content, 'active_ai_provider', return_value='openai'), \
                    patch.object(email_content, 'require_ai_api_key', return_value='test'), \
                    patch.object(email_content, '_generate_ai_text_openai', return_value='A friendly recap'):
                self.assertEqual(email_content.generate_ai_text('A game story'), 'A friendly recap')
                self.assertEqual(moderate.call_args.args[0], 'A friendly recap')


if __name__ == '__main__':
    unittest.main()
