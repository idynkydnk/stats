"""Verify the app's Google-to-Stats handoff without relying on browser cookies."""
import ast
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import secrets
import sqlite3
import time
import unittest
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from private_accounts import GOOGLE_IOS_CLIENT_ID
from tests import test_private_accounts


class GoogleAppSignInTests(unittest.TestCase):
    def setUp(self):
        test_private_accounts.PrivateAccountTests.setUp(self)
        # Use production token creation/validation, not the fixture's token map.
        with sqlite3.connect(self.path) as conn:
            conn.execute('ALTER TABLE auth_tokens ADD COLUMN expires_at TEXT')
        self.service.adminfx.canonical_username = lambda name: name
        namespace = dict(sqlite3=sqlite3, hashlib=hashlib, secrets=secrets,
                         datetime=datetime, timedelta=timedelta,
                         adminfx=self.service.adminfx, _stats_db_path=lambda: self.path)
        names = {'generate_auth_token', 'hash_token', 'create_auth_token', 'validate_auth_token'}
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'stats.py').read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'stats.py', 'exec'), namespace)
        self.service.create_auth_token = namespace['create_auth_token']
        self.service.validate_auth_token = namespace['validate_auth_token']
        self.client = self.app.test_client(use_cookies=False)
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        certs = patch('google.oauth2.id_token._fetch_certs', return_value={'test-google': public_key})
        certs.start()
        self.addCleanup(certs.stop)
        config = patch.dict('os.environ', {'GOOGLE_IOS_CLIENT_ID': GOOGLE_IOS_CLIENT_ID})
        config.start()
        self.addCleanup(config.stop)

    def sign_in(self, **overrides):
        now = int(time.time())
        claims = dict(sub='google-test-person', iss='https://accounts.google.com',
                      aud=GOOGLE_IOS_CLIENT_ID, iat=now, exp=now + 3600,
                      email_verified=True, name='Test Player')
        claims.update(overrides)
        token = jwt.encode(claims, self.key, algorithm='RS256', headers={'kid': 'test-google'})
        return self.client.post('/api/auth/google', json={'id_token': token},
                                headers={'X-Stats-Account-Required': '1'})

    def assert_app_session(self, response):
        self.assertEqual(response.status_code, 200, response.json)
        me = self.client.get('/api/me', headers={
            'Authorization': 'Bearer ' + response.json['token'],
            'X-Stats-Account-Required': '1',
        })
        self.assertEqual(me.status_code, 200, me.json)
        self.assertTrue(me.json['private'])

    def test_google_handoff_works_without_cookies(self):
        self.assert_app_session(self.sign_in())

    def test_fresh_google_token_tolerates_small_server_clock_difference(self):
        self.assert_app_session(self.sign_in(iat=int(time.time()) + 5))

    def test_invalid_identity_and_tokens_outside_clock_tolerance_are_rejected(self):
        now = int(time.time())
        for claims in ({'aud': 'another-app'}, {'email_verified': False},
                       {'iat': now + 120}, {'iat': now - 3600, 'exp': now - 120}):
            with self.subTest(claims=claims):
                self.assertEqual(self.sign_in(**claims).status_code, 401)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM auth_tokens').fetchone()[0], 0)
