"""Real software-authenticator signatures exercise the WebAuthn verifier."""
import hashlib
import json
import secrets
import sqlite3
import time
import unittest
from unittest.mock import patch

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes

from tests import test_web_sign_in


class PasskeyTests(unittest.TestCase):
    def setUp(self):
        test_web_sign_in.WebSignInTests.setUp(self)
        self.app.config['PASSKEY_ORIGIN'] = 'https://localhost'
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(32)

    def owner(self, client=None, username='Kyle', recent=True):
        client = client or self.a
        with client.session_transaction(base_url='https://localhost') as saved:
            saved['username'] = username
            saved['logged_in'] = True
            saved['authenticated_at'] = int(time.time()) if recent else 0
        response = client.get('/account/passkeys', base_url='https://localhost')
        self.assertEqual(response.status_code, 200)
        return client

    def post(self, path, body=None, client=None, **kwargs):
        client = client or self.a
        with client.session_transaction(base_url='https://localhost') as saved:
            csrf = saved.get('passkey_csrf', '')
        headers = {'Origin': 'https://localhost', 'X-CSRF-Token': csrf}
        headers.update(kwargs.pop('headers', {}))
        return client.post('/auth/passkeys/' + path, json={} if body is None else body,
                           headers=headers, base_url='https://localhost', **kwargs)

    def client_data(self, options, kind, origin='https://localhost'):
        return json.dumps({'type': 'webauthn.' + kind, 'challenge': options['challenge'],
                           'origin': origin, 'crossOrigin': False}).encode()

    def registration(self, options, flags=0x45, origin='https://localhost'):
        public = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: public.x.to_bytes(32, 'big'), -3: public.y.to_bytes(32, 'big')})
        auth = hashlib.sha256(b'localhost').digest() + bytes([flags]) + bytes(4)
        auth += bytes(16) + len(self.credential_id).to_bytes(2, 'big') + self.credential_id + cose
        return {'id': bytes_to_base64url(self.credential_id), 'rawId': bytes_to_base64url(self.credential_id),
                'type': 'public-key', 'response': {
                    'clientDataJSON': bytes_to_base64url(self.client_data(options, 'create', origin)),
                    'attestationObject': bytes_to_base64url(cbor2.dumps({'fmt': 'none', 'authData': auth, 'attStmt': {}}))}}

    def register(self, client=None):
        client = self.owner(client)
        options = self.post('register/options', client=client)
        self.assertEqual(options.status_code, 200, options.text)
        self.assertEqual(options.json['authenticatorSelection']['residentKey'], 'required')
        self.handle = options.json['user']['id']
        self.assertEqual(self.post('register/verify', {'credential': self.registration(options.json), 'label': 'iPhone'}, client).status_code, 200)
        return options.json

    def start_login(self, remember=True):
        self.b.get('/login?next=/stats/2026', base_url='https://localhost')
        options = self.post('login/options', {'remember': remember}, self.b)
        self.assertEqual(options.status_code, 200, options.text)
        return options.json

    def assertion(self, options, count=1, flags=5, origin='https://localhost', handle=None):
        client_data = self.client_data(options, 'get', origin)
        auth = hashlib.sha256(b'localhost').digest() + bytes([flags]) + count.to_bytes(4, 'big')
        signature = self.key.sign(auth + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {'id': bytes_to_base64url(self.credential_id), 'rawId': bytes_to_base64url(self.credential_id),
                'type': 'public-key', 'response': {'clientDataJSON': bytes_to_base64url(client_data),
                'authenticatorData': bytes_to_base64url(auth), 'signature': bytes_to_base64url(signature),
                'userHandle': handle or self.handle}}

    def test_registration_login_and_remember_permissions(self):
        self.register()
        options = self.start_login()
        result = self.post('login/verify', {'credential': self.assertion(options)}, self.b)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json['redirect'], '/stats/2026')
        with self.b.session_transaction(base_url='https://localhost') as saved:
            self.assertEqual(saved['username'], 'Kyle')
            self.assertGreater(saved['authenticated_at'], 0)
        self.assertEqual(self.b.get('/admin', base_url='https://localhost').status_code, 200)
        self.assertIn('remember_token=', str(result.headers.getlist('Set-Cookie')))
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT sign_count FROM passkey_credentials').fetchone()[0], 1)

    def test_requires_session_recent_login_csrf_and_origin(self):
        self.a.get('/login', base_url='https://localhost')
        self.assertEqual(self.post('register/options').status_code, 401)
        self.owner(recent=False)
        self.assertEqual(self.post('register/options').status_code, 403)
        page = self.a.get('/login?reauth=1&next=/account/passkeys', base_url='https://localhost')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Email me a code', page.text)
        self.owner()
        self.assertEqual(self.post('register/options', headers={'X-CSRF-Token': 'bad'}).status_code, 403)
        self.assertEqual(self.post('register/options', headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.post('register/options', []).status_code, 400)

    def test_wrong_origin_missing_verification_and_handle_rejected(self):
        self.register()
        for kwargs in ({'origin': 'https://evil.example'}, {'flags': 1}, {'handle': bytes_to_base64url(b'wrong-user')}):
            options = self.start_login()
            response = self.post('login/verify', {'credential': self.assertion(options, **kwargs)}, self.b)
            self.assertEqual(response.status_code, 400, response.text)
            with self.b.session_transaction(base_url='https://localhost') as saved:
                self.assertFalse(saved.get('logged_in'))

    def test_registration_wrong_origin_and_missing_verification(self):
        self.owner()
        for kwargs in ({'origin': 'https://evil.example'}, {'flags': 0x41}):
            options = self.post('register/options').json
            response = self.post('register/verify', {'credential': self.registration(options, **kwargs)})
            self.assertEqual(response.status_code, 400, response.text)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM passkey_credentials').fetchone()[0], 0)

    def test_bad_signature_and_single_use_even_if_cookie_is_replayed(self):
        self.register()
        options = self.start_login()
        cookie = self.b.get_cookie('session').value
        credential = self.assertion(options)
        credential['response']['signature'] = bytes_to_base64url(b'not-a-signature')
        self.assertEqual(self.post('login/verify', {'credential': credential}, self.b).status_code, 400)
        self.b.set_cookie('session', cookie)
        self.assertEqual(self.post('login/verify', {'credential': self.assertion(options)}, self.b).status_code, 400)

    def test_expired_and_cross_browser_challenges(self):
        self.register()
        options = self.start_login()
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE passkey_challenges SET expires_at=0 WHERE kind='login'")
        self.assertEqual(self.post('login/verify', {'credential': self.assertion(options)}, self.b).status_code, 400)
        options = self.start_login()
        self.assertEqual(self.post('login/verify', {'credential': self.assertion(options)}, self.a).status_code, 400)
        self.assertEqual(self.post('login/verify', {'credential': self.assertion(options)}, self.b).status_code, 200)

    def test_remove_is_owner_scoped_and_revokes_signin(self):
        self.register()
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO site_users(username,password_hash) VALUES ('Other','unused')")
        self.owner(self.b, 'Other')
        self.assertEqual(self.post('remove', {'id': bytes_to_base64url(self.credential_id)}, self.b).status_code, 200)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM passkey_credentials').fetchone()[0], 1)
        self.assertEqual(self.post('remove', {'id': bytes_to_base64url(self.credential_id)}).status_code, 200)
        self.b = self.app.test_client()
        options = self.start_login()
        self.assertEqual(self.post('login/verify', {'credential': self.assertion(options)}, self.b).status_code, 400)

    def test_deactivated_and_deleted_users_lose_credentials(self):
        for sql in ("UPDATE site_users SET active=0 WHERE username='Kyle'", "DELETE FROM site_users WHERE username='Kyle'"):
            with self.subTest(sql=sql):
                self.setUp()
                self.register()
                options = self.start_login()
                with sqlite3.connect(self.path) as conn:
                    conn.execute(sql)
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM passkey_credentials').fetchone()[0], 0)
                self.assertEqual(self.post('login/verify', {'credential': self.assertion(options)}, self.b).status_code, 400)

    def test_duplicate_registration_and_malformed_responses(self):
        self.register()
        options = self.post('register/options').json
        self.assertEqual(options['excludeCredentials'][0]['id'], bytes_to_base64url(self.credential_id))
        self.assertEqual(self.post('register/verify', {'credential': self.registration(options)}).status_code, 400)
        for credential in (None, {}, {'id': []}, {'id': '%%%'}):
            self.start_login()
            self.assertEqual(self.post('login/verify', {'credential': credential}, self.b).status_code, 400)

    def test_restored_session_cannot_bypass_recent_signin_via_email_api(self):
        self.owner(recent=False)
        result = self.a.get('/api/auth/email', base_url='https://localhost')
        self.assertEqual(result.status_code, 200)
        self.a.get('/account/passkeys', base_url='https://localhost')
        self.assertEqual(self.post('register/options').status_code, 403)

    def test_missing_dependency_preserves_email_login(self):
        with patch('passkey_sign_in.PASSKEYS_AVAILABLE', False):
            page = self.a.get('/login', base_url='https://localhost')
            self.assertEqual(page.status_code, 200)
            self.assertIn('Email me a code', page.text)
            self.assertNotIn('data-passkey-action', page.text)
            self.assertEqual(self.post('login/options').status_code, 503)

    def test_rate_limit(self):
        self.b.get('/login', base_url='https://localhost')
        for _ in range(30):
            self.assertEqual(self.post('login/options', client=self.b).status_code, 200)
        self.assertEqual(self.post('login/options', client=self.b).status_code, 429)

    def test_private_account_can_manage_and_use_passkeys(self):
        from private_accounts import create_account
        create_account(self.path, 'player', 'password')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET login_email='player@example.com' WHERE username='player'")
        self.owner(username='player')
        options = self.post('register/options').json
        self.handle = options['user']['id']
        self.assertEqual(self.post('register/verify', {'credential': self.registration(options)}).status_code, 200)
        options = self.start_login(remember=False)
        result = self.post('login/verify', {'credential': self.assertion(options)}, self.b)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn('remember_token=;', str(result.headers.getlist('Set-Cookie')))
        with self.b.session_transaction(base_url='https://localhost') as saved:
            self.assertEqual(saved['username'], 'player')
        self.assertEqual(self.b.get('/admin', base_url='https://localhost').status_code, 403)


if __name__ == '__main__':
    unittest.main()
