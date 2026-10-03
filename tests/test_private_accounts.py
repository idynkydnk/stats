import os
import hashlib
import time
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask, jsonify, session
from werkzeug.security import check_password_hash

from private_accounts import (
    account_for_user, connect_data, create_account, private_database,
    register_private_accounts,
)


class PrivateAccountTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / 'stats.db')
        self.env = patch.dict(os.environ, {'STATS_PRIVATE_DATA_DIR': str(Path(self.directory.name) / 'personal')})
        self.env.start()
        self.addCleanup(self.env.stop)
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                CREATE TABLE site_users (username TEXT PRIMARY KEY, password_hash TEXT,
                    is_admin INTEGER DEFAULT 0, active INTEGER DEFAULT 1);
                CREATE TABLE auth_tokens (username TEXT, token_hash TEXT);
                CREATE TABLE games (id INTEGER PRIMARY KEY, winner1 TEXT);
                CREATE TABLE players (id INTEGER PRIMARY KEY, full_name TEXT);
                CREATE TABLE deleted_records (id INTEGER PRIMARY KEY, record_id INTEGER);
                INSERT INTO games VALUES (1, 'Shared player');
                INSERT INTO players VALUES (1, 'Shared player');
                INSERT INTO site_users VALUES ('Kyle', 'existing', 1, 1);
            ''')
        self.tokens = {'shared-token': 'Kyle'}
        def user(name):
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute('SELECT * FROM site_users WHERE lower(username)=lower(?)', (name,)).fetchone()
                return dict(row) if row else None
        def establish(name, login=False):
            session['username'] = name
            session['logged_in'] = True
            return name
        def token(name):
            value = name + '-token'
            self.tokens[value] = name
            return value
        self.service = SimpleNamespace(
            _stats_db_path=lambda: self.path,
            adminfx=SimpleNamespace(get_site_user=user),
            validate_auth_token=self.tokens.get,
            establish_user_session=establish,
            create_auth_token=token,
            login_rate_limited=lambda ip: False,
            record_login_failure=lambda ip: None,
            clear_login_failures=lambda ip: None,
            _client_ip=lambda: '127.0.0.1',
        )
        self.app = Flask(__name__)
        self.app.secret_key = 'test-only'
        self.app.testing = True
        register_private_accounts(self.app, self.service)

        @self.app.route('/api/games', endpoint='api_doubles_list', methods=['GET', 'POST', 'PUT', 'DELETE'])
        def games():
            from flask import request
            with connect_data(self.path) as conn:
                if request.method == 'POST':
                    conn.execute('INSERT INTO games VALUES (2, ?)', (request.json['name'],))
                if request.method == 'DELETE':
                    conn.execute('DELETE FROM games WHERE id=2')
                if request.method == 'PUT':
                    conn.execute('UPDATE games SET winner1=? WHERE id=?',
                                 (request.json['name'], request.json['id']))
                return jsonify(rows=conn.execute('SELECT * FROM games ORDER BY id').fetchall())

        @self.app.route('/api/ai/roster', endpoint='api_ai_roster', methods=['POST'])
        def ai_roster():
            with connect_data(self.path) as conn:
                return jsonify(players=conn.execute('SELECT * FROM players').fetchall())

        @self.app.route('/api/me', endpoint='api_me')
        def me():
            return jsonify(private=bool(private_database()))

        @self.app.route('/admin', endpoint='admin_dashboard')
        def admin():
            return 'shared admin'

        self.a = self.app.test_client()
        self.b = self.app.test_client()

    def register(self, client, name):
        response = client.post('/api/auth/register', json={'username': name, 'password': 'a strong password'})
        self.assertEqual(response.status_code, 201, response.json)
        return {'Authorization': 'Bearer ' + response.json['token'], 'X-Stats-Account-Required': '1'}

    def test_private_read_write_delete_and_public_isolation(self):
        a = self.register(self.a, 'alice')
        b = self.register(self.b, 'bob')
        self.assertEqual(self.a.get('/api/games', headers=a).json['rows'], [])
        self.a.post('/api/games', headers=a, json={'name': 'Alice private'})
        self.assertEqual(self.b.get('/api/games', headers=b).json['rows'], [])
        self.b.post('/api/games', headers=b, json={'name': 'Bob private'})
        self.a.delete('/api/games', headers=a)
        self.assertEqual(self.b.get('/api/games', headers=b).json['rows'], [[2, 'Bob private']])
        public = self.app.test_client().get('/api/games')
        self.assertEqual(public.json['rows'], [[1, 'Shared player']])
        self.assertEqual(self.a.get('/api/games', headers=a).headers['Cache-Control'], 'no-store')

    def test_personal_ai_access_uses_only_own_players(self):
        a = self.register(self.a, 'alice')
        b = self.register(self.b, 'bob')
        from private_accounts import ai_account_context
        with ai_account_context(self.app, self.path, 'alice'):
            with connect_data(self.path) as conn:
                conn.execute("INSERT INTO players VALUES (1, 'Alice character')")
        self.assertEqual(self.a.post('/api/ai/roster', headers=a).json['players'], [[1, 'Alice character']])
        self.assertEqual(self.b.post('/api/ai/roster', headers=b).json['players'], [])
        self.assertEqual(self.a.post('/api/ai/roster', headers={**a, 'X-Stats-Preview': '1'}).status_code, 403)

    def test_ai_worker_context_keeps_accounts_and_public_storage_separate(self):
        from private_accounts import ai_account_context
        self.register(self.a, 'alice')
        self.register(self.b, 'bob')
        with ai_account_context(self.app, self.path, 'alice'):
            with connect_data(self.path) as conn:
                conn.execute("INSERT INTO players VALUES (1, 'Alice character')")
        with ai_account_context(self.app, self.path, 'bob'):
            with connect_data(self.path) as conn:
                self.assertEqual(conn.execute('SELECT * FROM players').fetchall(), [])
        with ai_account_context(self.app, self.path, 'Kyle'):
            self.assertIsNone(private_database())
            with connect_data(self.path) as conn:
                self.assertEqual(conn.execute('SELECT * FROM players').fetchall(), [(1, 'Shared player')])

    def test_storage_has_no_shared_rows_or_auth_tables(self):
        a = self.register(self.a, 'alice')
        self.a.get('/api/games', headers=a)
        account = account_for_user(self.path, 'alice')
        path = Path(self.directory.name) / 'personal' / (account['id'] + '.db')
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute('SELECT * FROM players').fetchall(), [])
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='site_users'").fetchone())

    def test_starter_preview_is_public_read_only_and_separate_from_personal_games(self):
        preview = {'X-Stats-Preview': '1', 'X-Stats-Account-Required': '1'}
        guest = self.app.test_client()
        self.assertEqual(guest.get('/api/games', headers=preview).json['rows'], [[1, 'Shared player']])
        self.assertEqual(guest.post('/api/games', headers=preview, json={'name': 'Never saved'}).status_code, 403)
        self.assertEqual(guest.get('/admin', headers=preview).status_code, 403)
        a = self.register(self.a, 'alice')
        self.a.post('/api/games', headers=a, json={'name': 'Private player'})
        self.assertEqual(self.a.get('/api/games', headers={**a, **preview}).json['rows'], [[1, 'Shared player']])
        self.assertEqual(self.a.delete('/api/games', headers={**a, **preview}).status_code, 403)
        self.assertEqual(self.a.get('/api/games', headers=a).json['rows'], [[2, 'Private player']])

    def test_hiding_starter_stats_is_account_preference_and_never_deletes_games(self):
        a = self.register(self.a, 'alice')
        self.register(self.b, 'bob')
        self.a.post('/api/games', headers=a, json={'name': 'Private player'})
        self.assertEqual(account_for_user(self.path, 'alice')['show_starter_stats'], 1)
        for visible in [False, True]:
            result = self.a.put('/api/account/starter-stats', headers=a, json={'show_starter_stats': visible})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(bool(account_for_user(self.path, 'alice')['show_starter_stats']), visible)
            self.assertEqual(account_for_user(self.path, 'bob')['show_starter_stats'], 1)
            self.assertEqual(self.a.get('/api/games', headers=a).json['rows'], [[2, 'Private player']])
            self.assertEqual(self.app.test_client().get('/api/games').json['rows'], [[1, 'Shared player']])
        self.assertEqual(self.a.put('/api/account/starter-stats', headers=a, json={'show_starter_stats': 'false'}).status_code, 400)
        self.assertEqual(self.app.test_client().put('/api/account/starter-stats', json={'show_starter_stats': False}).status_code, 403)

    def test_personal_accounts_cannot_mutate_shared_stats_with_or_without_preview_flag(self):
        auth = self.register(self.a, 'alice')
        self.a.post('/api/games', headers=auth, json={'name': 'Personal game'})
        preview = {**auth, 'X-Stats-Preview': '1'}
        for method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            result = self.a.open('/api/games', method=method, headers=preview,
                                 json={'id': 1, 'name': 'Changed shared player'})
            self.assertEqual(result.status_code, 403, method)
        # Removing or falsifying the preview flag never selects the shared DB.
        for preview_value in [None, '0', 'false']:
            headers = dict(auth)
            if preview_value is not None:
                headers['X-Stats-Preview'] = preview_value
            response = self.a.put('/api/games', headers=headers,
                                  json={'id': 1, 'name': 'Changed shared player'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['rows'], [[2, 'Personal game']])
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT * FROM games').fetchall(), [(1, 'Shared player')])

    def test_preview_rejects_player_and_administrative_mutations(self):
        auth = self.register(self.a, 'alice')
        preview = {**auth, 'X-Stats-Preview': '1'}
        attempts = [
            ('POST', '/api/update_player_info'), ('POST', '/api/rename_player'),
            ('POST', '/api/delete_player'), ('POST', '/api/player_photo/Shared/'),
            ('POST', '/api/admin/undo/1'), ('POST', '/api/admin/users'),
            ('DELETE', '/api/account'), ('PUT', '/api/account/starter-stats'),
        ]
        for method, path in attempts:
            with self.subTest(method=method, path=path):
                response = self.a.open(path, method=method, headers=preview, json={})
                self.assertEqual(response.status_code, 403)
        self.assertTrue(self.service.adminfx.get_site_user('alice')['active'])

    def test_client_cannot_select_another_account_or_fall_back_from_invalid_token(self):
        a = self.register(self.a, 'alice')
        b = self.register(self.b, 'bob')
        self.a.post('/api/games', headers=a, json={'name': 'Private'})
        self.assertEqual(self.b.get('/api/games?username=alice&account_id=alice', headers=b).json['rows'], [])
        self.assertEqual(self.a.get('/api/games', headers={'Authorization': 'Bearer invalid'}).status_code, 401)
        self.assertEqual(self.a.get('/api/games', headers={'X-Stats-Account-Required': '1'}).status_code, 401)

    def test_shared_tools_blocked_for_personal_cookie_and_bearer(self):
        a = self.register(self.a, 'alice')
        self.assertEqual(self.a.get('/admin', headers=a).status_code, 403)
        self.assertEqual(self.a.get('/admin').status_code, 403)
        self.assertEqual(self.a.get('/admin', headers={'Authorization': 'Bearer shared-token'}).status_code, 200)

    def test_registration_validates_and_cannot_claim_existing_user(self):
        for name, password in [('a/b', 'a strong password'), ('alice', 'short')]:
            self.assertEqual(self.a.post('/api/auth/register', json={'username': name, 'password': password}).status_code, 400)
        self.assertEqual(self.a.post('/api/auth/register', json=[]).status_code, 400)
        self.assertEqual(self.a.post('/api/auth/register', json={'username': 'kyle', 'password': 'a strong password'}).status_code, 409)
        self.register(self.a, 'alice')
        user = self.service.adminfx.get_site_user('alice')
        self.assertFalse(user['is_admin'])
        self.assertTrue(check_password_hash(user['password_hash'], 'a strong password'))

    def test_deactivated_account_and_deleted_account_are_denied(self):
        a = self.register(self.a, 'alice')
        self.a.post('/api/games', headers=a, json={'name': 'Private'})
        self.assertEqual(self.a.delete('/api/account', headers=a).status_code, 200)
        self.assertEqual(self.a.get('/api/games', headers=a).status_code, 401)
        account = account_for_user(self.path, 'alice')
        with sqlite3.connect(Path(self.directory.name) / 'personal' / (account['id'] + '.db')) as conn:
            self.assertEqual(conn.execute('SELECT * FROM games').fetchall(), [])

    def test_google_requires_configuration_and_verified_identity(self):
        with patch.dict(os.environ, {'GOOGLE_IOS_CLIENT_ID': ''}):
            self.assertEqual(self.a.post('/api/auth/google', json={'id_token': 'bad'}).status_code, 503)
        with patch.dict(os.environ, {'GOOGLE_IOS_CLIENT_ID': 'expected-client'}), \
             patch('google.oauth2.id_token.verify_oauth2_token', return_value={'sub': 'google-user', 'email_verified': True}) as verify:
            first = self.a.post('/api/auth/google', json={'id_token': 'verified-by-library'})
            second = self.b.post('/api/auth/google', json={'id_token': 'verified-by-library'})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json['username'], second.json['username'])
            self.assertEqual(verify.call_args.args[2], 'expected-client')
            self.assertTrue(account_for_user(self.path, first.json['username']))
        with patch.dict(os.environ, {'GOOGLE_IOS_CLIENT_ID': 'expected-client'}), \
             patch('google.oauth2.id_token.verify_oauth2_token', side_effect=ValueError('bad token')):
            self.assertEqual(self.a.post('/api/auth/google', json={'id_token': 'bad'}).status_code, 401)

    def test_social_signup_after_deletion_uses_new_empty_account(self):
        for provider in ('apple', 'google'):
            for legacy_link in (False, True):
                with self.subTest(provider=provider, legacy_link=legacy_link):
                    subject = f'{provider}-deleted-{legacy_link}'
                    def sign_in():
                        if provider == 'apple':
                            nonce = self.a.post('/api/auth/apple/challenge').json['nonce']
                            nonce_hash = hashlib.sha256(nonce.encode()).hexdigest()
                            with patch('jwt.PyJWKClient.get_signing_key_from_jwt', return_value=SimpleNamespace(key='test')), \
                                 patch('jwt.decode', return_value={'sub': subject, 'nonce': nonce_hash}):
                                return self.a.post('/api/auth/apple', json={'id_token': 'verified', 'nonce': nonce})
                        with patch('google.oauth2.id_token.verify_oauth2_token', return_value={'sub': subject, 'email_verified': True}):
                            return self.a.post('/api/auth/google', json={'id_token': 'verified'})

                    first = sign_in()
                    self.assertEqual(first.status_code, 200, first.json)
                    old_name = first.json['username']
                    old_account = account_for_user(self.path, old_name)
                    old_headers = {'Authorization': 'Bearer ' + first.json['token']}
                    self.a.post('/api/games', headers=old_headers, json={'name': 'Deleted private game'})
                    with sqlite3.connect(self.path) as conn:
                        conn.execute('INSERT INTO auth_tokens VALUES (?, ?)', (old_name, 'old-hash'))
                    self.assertEqual(self.a.delete('/api/account', headers=old_headers).status_code, 200)
                    self.assertIsNone(account_for_user(self.path, old_name)[provider + '_subject'])
                    if legacy_link:
                        # Reproduce accounts deleted before identities were released.
                        with sqlite3.connect(self.path) as conn:
                            conn.execute(f'UPDATE private_accounts SET {provider}_subject=? WHERE username=?',
                                         (subject, old_name))

                    fresh = sign_in()
                    self.assertEqual(fresh.status_code, 200, fresh.json)
                    self.assertNotEqual(fresh.json['username'], old_name)
                    new_account = account_for_user(self.path, fresh.json['username'])
                    self.assertNotEqual(new_account['id'], old_account['id'])
                    self.assertEqual(new_account[provider + '_subject'], subject)
                    fresh_headers = {'Authorization': 'Bearer ' + fresh.json['token']}
                    self.assertEqual(self.a.get('/api/games', headers=fresh_headers).json['rows'], [])
                    self.assertEqual(sign_in().json['username'], fresh.json['username'])
                    self.assertEqual(self.a.get('/api/games', headers=old_headers).status_code, 401)
                    self.assertFalse(self.service.adminfx.get_site_user(old_name)['active'])
                    with sqlite3.connect(self.path) as conn:
                        self.assertEqual(conn.execute('SELECT * FROM auth_tokens WHERE username=?', (old_name,)).fetchall(), [])
                        self.assertEqual(conn.execute('SELECT * FROM games').fetchall(), [(1, 'Shared player')])

    def test_stats_cache_is_not_shared_with_private_requests(self):
        from stat_functions import cached, clear_stats_cache
        from flask import g
        clear_stats_cache()
        @cached()
        def account_stat():
            return private_database() or 'shared'
        with self.app.test_request_context('/'):
            self.assertEqual(account_stat(), 'shared')
            g.private_database = 'alice'
            self.assertEqual(account_stat(), 'alice')
            g.private_database = 'bob'
            self.assertEqual(account_stat(), 'bob')
            del g.private_database
            self.assertEqual(account_stat(), 'shared')

    def test_apple_signature_audience_nonce_and_replay(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        def challenge():
            return self.a.post('/api/auth/apple/challenge').json['nonce']
        def apple_token(raw_nonce, **overrides):
            claims = {'iss': 'https://appleid.apple.com', 'aud': 'com.kt.stats',
                      'sub': 'apple-person', 'iat': int(time.time()), 'exp': int(time.time()) + 300,
                      'nonce': hashlib.sha256(raw_nonce.encode()).hexdigest()}
            claims.update(overrides)
            return jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'test'})
        with patch('jwt.PyJWKClient.get_signing_key_from_jwt', return_value=SimpleNamespace(key=key.public_key())):
            nonce = challenge()
            payload = {'nonce': nonce, 'id_token': apple_token(nonce)}
            response = self.a.post('/api/auth/apple', json=payload)
            self.assertEqual(response.status_code, 200, response.json)
            self.assertTrue(response.json['is_private'])
            self.assertEqual(self.a.post('/api/auth/apple', json=payload).status_code, 401)
            for overrides in [{'aud': 'wrong-app'}, {'iss': 'wrong-issuer'}, {'exp': 1}, {'nonce': 'wrong'}]:
                nonce = challenge()
                response = self.a.post('/api/auth/apple', json={'nonce': nonce, 'id_token': apple_token(nonce, **overrides)})
                self.assertEqual(response.status_code, 401, overrides)


if __name__ == '__main__':
    unittest.main()
