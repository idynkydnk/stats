import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives import serialization

import account_lifecycle
import apple_account_tokens as apple
from private_accounts import account_for_user, ai_account_context
from tests import test_private_accounts as private_account_tests


class AccountLifecycleTests(unittest.TestCase):
    setUp = private_account_tests.PrivateAccountTests.setUp
    register = private_account_tests.PrivateAccountTests.register

    def test_public_policy_pages_ignore_expired_credentials_and_stale_sessions(self):
        for path, endpoint in (('/privacy', 'privacy_policy'), ('/support', 'support_page'),
                               ('/community-guidelines', 'community_guidelines')):
            self.app.add_url_rule(path, endpoint, lambda: 'Public information')
        with self.a.session_transaction() as state:
            state.update(logged_in=True, username='deleted-account')
        for path in ('/privacy', '/support', '/community-guidelines'):
            for headers in ({}, {'Authorization': 'Bearer expired'}, {'Authorization': 'invalid'},
                            {'X-Stats-Account-Required':'1', 'X-Stats-Preview':'1'}):
                self.assertEqual(self.a.get(path, headers=headers).status_code, 200)
        self.assertEqual(self.a.get('/api/games', headers={'Authorization':'Bearer expired'}).status_code, 401)

    def test_delete_erases_identity_media_jobs_and_only_owned_data(self):
        import admin_functions as admin
        import flyer_functions as flyers
        import ai_auto_send_jobs
        ai_auto_send_jobs.init_ai_auto_send_jobs_db()
        a = self.register(self.a, 'alice')
        b = self.register(self.b, 'bob')
        self.a.post('/api/games', headers=a, json={'name': 'Alice private'})
        self.b.post('/api/games', headers=b, json={'name': 'Bob private'})
        alice = account_for_user(self.path, 'alice')
        bob = account_for_user(self.path, 'bob')
        media = self.account_media_path
        alice_photo = media / 'photos' / (alice['id'] + '_1.jpg')
        bob_photo = media / 'photos' / (bob['id'] + '_1.jpg')
        alice_photo.write_bytes(b'alice portrait')
        bob_photo.write_bytes(b'bob portrait')
        shared_image = media / 'images' / ('a' * 32 + '.png')
        private_image = media / 'images' / ('b' * 32 + '.png')
        shared_image.write_bytes(b'image used by two published pages')
        private_image.write_bytes(b'image used only by Alice')
        for user in ('alice', 'bob'):
            html = '<p>private story</p>'
            if user == 'alice':
                html += '<img src="/static/email_images/' + private_image.name + '">'
            admin.insert_ai_recap_page(user + '-recap', user, 'doubles', html,
                                      hero_image_url='/static/email_images/' + shared_image.name)
            flyers.insert_flyer_page(user + '-flyer', user, ['Player'], 'doubles', '2026-10-21', '', '')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET login_email='alice@example.com',display_name='Alice Smith',first_name='Alice',last_name='Smith' WHERE username='alice'")
            conn.executescript('''
                CREATE TABLE ai_prompt_log(username TEXT, prompt_text TEXT);
                CREATE TABLE activity_log(username TEXT, summary TEXT);
                CREATE TABLE ai_recap_subscriptions(email TEXT);
                INSERT INTO ai_prompt_log VALUES ('alice','private names'), ('bob','keep');
                INSERT INTO activity_log VALUES ('alice','private names'), ('bob','keep');
                INSERT INTO ai_recap_subscriptions VALUES ('alice@example.com'), ('bob@example.com');
            ''')
            conn.execute("INSERT INTO auth_tokens VALUES ('alice','secret')")
            conn.execute("INSERT INTO ai_auto_send_jobs(username,game_type,game_ids_json,prompt_style,payload_json) VALUES ('alice','doubles','[]','','private payload')")
        snapshot_dir = Path(self.directory.name) / 'cache' / 'snapshots'
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / 'cached.db').write_bytes(b'cached player data')
        response = self.a.delete('/api/account', headers=a)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIsNone(account_for_user(self.path, 'alice'))
        self.assertIsNone(self.service.adminfx.get_site_user('alice'))
        self.assertFalse(alice_photo.exists())
        self.assertTrue(bob_photo.exists())
        self.assertTrue(shared_image.exists())
        self.assertFalse(private_image.exists())
        self.assertIsNone(admin.get_ai_recap_page('alice-recap'))
        self.assertIsNotNone(admin.get_ai_recap_page('bob-recap'))
        self.assertIsNone(flyers.get_flyer_page('alice-flyer'))
        self.assertIsNotNone(flyers.get_flyer_page('bob-flyer'))
        self.assertFalse((snapshot_dir / 'cached.db').exists())
        self.assertEqual(self.b.get('/api/games', headers=b).json['rows'], [[2, 'Bob private']])
        with sqlite3.connect(self.path) as conn:
            for table in ('ai_auto_send_jobs', 'ai_prompt_log', 'activity_log', 'auth_tokens'):
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table} WHERE username=?', ('alice',)).fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT email FROM ai_recap_subscriptions').fetchall(), [('bob@example.com',)])
            self.assertEqual(conn.execute('SELECT username_hash FROM private_deleted_accounts').fetchall(),
                             [(account_lifecycle.username_digest('alice'),)])
        self.assertEqual(self.a.post('/api/auth/register', json={'username':'alice','password':'a strong password'}).status_code, 409)
        self.assertEqual(self.a.get('/api/games', headers=a).status_code, 401)
        with self.assertRaises(PermissionError):
            with ai_account_context(self.app, self.path, 'alice'):
                self.fail('Deleted account must never fall back to the public database')

    def test_deletion_waits_for_existing_worker_and_stale_workers_cannot_write(self):
        a = self.register(self.a, 'alice')
        entered = threading.Event()
        release = threading.Event()
        def worker():
            with ai_account_context(self.app, self.path, 'alice'):
                entered.set()
                release.wait(10)
        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaises(account_lifecycle.AccountBusy):
                with account_lifecycle.account_lock(self.path, 'alice', exclusive=True, timeout=0.05):
                    self.fail('An active worker must protect its writes')
            self.assertIsNotNone(account_for_user(self.path, 'alice'))
        finally:
            release.set()
            thread.join(2)
        self.assertEqual(self.a.delete('/api/account', headers=a).status_code, 200)

    def test_apple_missing_token_still_deletes_and_returns_manual_revocation_instructions(self):
        a = self.register(self.a, 'alice')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE private_accounts SET apple_subject='apple-subject' WHERE username='alice'")
        self.apple_revoke.stop()
        response = self.a.delete('/api/account', headers=a)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['apple_manual_revocation_required'])
        self.assertEqual(response.json['apple_manual_revocation_url'], 'https://support.apple.com/en-us/102571')
        self.assertIsNone(account_for_user(self.path, 'alice'))
        self.assertIsNone(self.service.adminfx.get_site_user('alice'))
        self.assertEqual(self.a.get('/api/games', headers=a).status_code, 401)

    def test_apple_unreadable_token_still_deletes_without_claiming_revocation(self):
        a = self.register(self.a, 'alice')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE private_accounts SET apple_subject='apple-subject' WHERE username='alice'")
        # A valid ciphertext whose original encryption key is unavailable.
        old_token = Fernet(Fernet.generate_key()).encrypt(b'old-token').decode()
        apple.save_token(self.path, 'alice', old_token)
        self.apple_revoke.stop()
        with patch.dict(os.environ, {'APPLE_TOKEN_ENCRYPTION_KEY': Fernet.generate_key().decode()}), \
                patch('requests.post') as provider:
            response = self.a.delete('/api/account', headers=a)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['apple_manual_revocation_required'])
        provider.assert_not_called()
        self.assertIsNone(account_for_user(self.path, 'alice'))
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT * FROM apple_account_tokens').fetchall(), [])

    def test_apple_provider_failure_keeps_account_retryable(self):
        a = self.register(self.a, 'alice')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE private_accounts SET apple_subject='apple-subject' WHERE username='alice'")
        for failure in ('Apple could not be reached. Please try again.',
                        'Apple sign-in is temporarily unavailable. Please try again later.'):
            with patch.object(apple, 'revoke_account_token', side_effect=apple.AppleAccountError(failure)):
                response = self.a.delete('/api/account', headers=a)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('apple_manual_revocation_required', response.json)
        self.assertIsNotNone(account_for_user(self.path, 'alice'))
        self.assertEqual(self.a.get('/api/games', headers=a).status_code, 200)
        response = self.a.delete('/api/account', headers=a)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json['apple_manual_revocation_required'])
        self.assertNotIn('apple_manual_revocation_url', response.json)

    def test_filesystem_failure_does_not_remove_identity_before_retry(self):
        a = self.register(self.a, 'alice')
        with patch.object(account_lifecycle, 'delete_owned_media', side_effect=OSError('disk unavailable')):
            response = self.a.delete('/api/account', headers=a)
        self.assertEqual(response.status_code, 503)
        self.assertIsNotNone(account_for_user(self.path, 'alice'))
        self.assertEqual(self.a.delete('/api/account', headers=a).status_code, 200)

    def test_hidden_media_and_failed_image_cleanup_are_finished_on_retry(self):
        import admin_functions as admin
        import content_safety
        a = self.register(self.a, 'alice')
        content_safety.init_safety(self.path)
        self.app.config['CONTENT_SAFETY_DB'] = self.path
        filename = 'a' * 32 + '.png'
        picture = self.account_media_path / 'images' / filename
        picture.write_bytes(b'private generated photo')
        admin.insert_ai_recap_page('hidden-recap', 'alice', 'doubles', '<p>Story</p>',
                                  hero_image_url='/static/email_images/' + filename)
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO content_hidden(kind,content_id,reason) VALUES ('recap','hidden-recap','removed')")
        original_unlink = Path.unlink
        def fail_picture(path, *args, **kwargs):
            if path == picture:
                raise OSError('file temporarily locked')
            return original_unlink(path, *args, **kwargs)
        with patch('ai_library.cleanup_images'), patch.object(Path, 'unlink', fail_picture):
            self.assertEqual(self.a.delete('/api/account', headers=a).status_code, 503)
        self.assertIsNone(admin.get_ai_recap_page('hidden-recap'))
        self.assertTrue(picture.exists())
        self.assertIsNotNone(account_for_user(self.path, 'alice'))
        self.assertEqual(self.a.delete('/api/account', headers=a).status_code, 200)
        self.assertFalse(picture.exists())
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT * FROM account_deletion_work').fetchall(), [])

    def test_deletion_finishes_pending_moderation_image_cleanup(self):
        import content_safety
        a = self.register(self.a, 'alice')
        content_safety.init_safety(self.path)
        filename = 'c' * 32 + '.png'
        picture = self.account_media_path / 'images' / filename
        picture.write_bytes(b'image left after a failed moderation unlink')
        with sqlite3.connect(self.path) as conn:
            conn.execute('INSERT INTO content_removal_work VALUES (?,?,?,?)',
                         ('recap', 'already-removed', 'Alice', json.dumps([filename])))
        self.assertEqual(self.a.delete('/api/account', headers=a).status_code, 200)
        self.assertFalse(picture.exists())
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT * FROM content_removal_work').fetchall(), [])


class AppleTokenTests(unittest.TestCase):
    def setUp(self):
        self.signing = ec.generate_private_key(ec.SECP256R1())
        pem = self.signing.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()).decode()
        self.fernet_key = Fernet.generate_key()
        self.env = patch.dict(os.environ, {'APPLE_TEAM_ID': 'TESTTEAM01', 'APPLE_KEY_ID': 'TESTKEY001',
                                         'APPLE_PRIVATE_KEY': pem, 'APPLE_IOS_CLIENT_ID': 'com.kt.stats',
                                         'APPLE_TOKEN_ENCRYPTION_KEY': self.fernet_key.decode()})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.apple_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def identity(self, **overrides):
        claims = {'sub':'person', 'nonce':'expected-nonce', 'aud':'com.kt.stats',
                  'iss':'https://appleid.apple.com', 'iat':int(time.time()), 'exp':int(time.time())+300}
        claims.update(overrides)
        return jwt.encode(claims, self.apple_key, algorithm='RS256')

    def test_exchange_binds_identity_encrypts_and_revokes_with_apple(self):
        body = {'id_token': self.identity(), 'refresh_token': 'sensitive-refresh-token'}
        response = SimpleNamespace(status_code=200, json=lambda:body)
        with patch('requests.post', return_value=response) as post, \
                patch('jwt.PyJWKClient.get_signing_key_from_jwt', return_value=SimpleNamespace(key=self.apple_key.public_key())):
            encrypted = apple.exchange_code('one-use-code', 'person', 'expected-nonce')
        self.assertNotIn('sensitive-refresh-token', encrypted)
        self.assertEqual(Fernet(self.fernet_key).decrypt(encrypted.encode()), b'sensitive-refresh-token')
        args = post.call_args.kwargs
        self.assertFalse(args['allow_redirects'])
        self.assertEqual(args['data']['grant_type'], 'authorization_code')
        secret = jwt.decode(args['data']['client_secret'], self.signing.public_key(), algorithms=['ES256'], audience='https://appleid.apple.com')
        self.assertEqual(secret['sub'], 'com.kt.stats')
        self.assertEqual(secret['iss'], 'TESTTEAM01')
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp)/'tokens.db')
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE apple_account_tokens(username TEXT PRIMARY KEY, encrypted_refresh_token TEXT)')
            apple.save_token(path, 'person', encrypted)
            with patch('requests.post', return_value=SimpleNamespace(status_code=200)) as revoke:
                self.assertTrue(apple.revoke_account_token(path, 'person'))
            self.assertEqual(revoke.call_args.args[0], 'https://appleid.apple.com/auth/revoke')
            self.assertEqual(revoke.call_args.kwargs['data']['token_type_hint'], 'refresh_token')
            self.assertEqual(revoke.call_args.kwargs['data']['token'], 'sensitive-refresh-token')

    def test_wrong_subject_nonce_audience_or_failed_provider_is_rejected(self):
        with patch('jwt.PyJWKClient.get_signing_key_from_jwt', return_value=SimpleNamespace(key=self.apple_key.public_key())):
            for overrides in ({'sub':'someone-else'}, {'nonce':'wrong'}, {'aud':'wrong-app'}, {'exp':1}):
                response = SimpleNamespace(status_code=200, json=lambda:{'id_token':self.identity(**overrides), 'refresh_token':'secret'})
                with patch('requests.post', return_value=response), self.assertRaises(apple.AppleAccountError):
                    apple.exchange_code('code', 'person', 'expected-nonce')
        with patch('requests.post', return_value=SimpleNamespace(status_code=400)), self.assertRaises(apple.AppleAccountError):
            apple.exchange_code('expired-code', 'person', 'expected-nonce')

    def test_invalid_server_encryption_configuration_remains_retryable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / 'tokens.db')
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE apple_account_tokens(username TEXT PRIMARY KEY, encrypted_refresh_token TEXT)')
            apple.save_token(path, 'person', Fernet(self.fernet_key).encrypt(b'valid-token').decode())
            for environment in ({}, {'APPLE_TOKEN_ENCRYPTION_KEY': 'invalid-key'}):
                with patch.dict(os.environ, environment, clear=True), patch('requests.post') as provider:
                    with self.assertRaises(apple.AppleAccountError):
                        apple.revoke_account_token(path, 'person')
                    provider.assert_not_called()


if __name__ == '__main__':
    unittest.main()
