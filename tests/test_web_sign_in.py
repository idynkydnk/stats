import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import flash, make_response, redirect, render_template, request, session, url_for
from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader

from tests import test_private_accounts
from private_accounts import account_for_user, GOOGLE_IOS_CLIENT_ID
from web_sign_in import safe_login_next


class WebSignInTests(unittest.TestCase):
    def setUp(self):
        test_private_accounts.PrivateAccountTests.setUp(self)
        self.config = patch.dict(os.environ, {
            'GOOGLE_WEB_CLIENT_ID': 'google-web-client',
            'APPLE_WEB_CLIENT_ID': 'apple-web-service',
            'APPLE_WEB_REDIRECT_URI': 'https://localhost/login',
        })
        self.config.start()
        self.addCleanup(self.config.stop)
        self.app.jinja_loader = ChoiceLoader([
            DictLoader({
                'test_base.html': '{% block extra_css %}{% endblock %}{% block content %}{% endblock %}{% block extra_js %}{% endblock %}',
                'partials/page_header_actions.html': '',
            }),
            FileSystemLoader(str(Path(__file__).resolve().parents[1] / 'templates')),
        ])

        self.app.context_processor(lambda: {'base_template': 'test_base.html'})
        # Exercise the actual password route without importing the production DB.
        namespace = dict(
            app=self.app, request=request, session=session, flash=flash, redirect=redirect,
            render_template=render_template, make_response=make_response, url_for=url_for,
            verify_password=lambda name, password: name == 'Kyle' and password == 'valid-password',
            log_activity=Mock(),
            **{name: getattr(self.service, name) for name in (
                'validate_auth_token', 'establish_user_session', 'create_auth_token',
                '_client_ip', 'login_rate_limited', 'record_login_failure', 'clear_login_failures')},
        )
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'stats.py').read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'login']
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'stats.py', 'exec'), namespace)

        @self.app.get('/', endpoint='index')
        def index():
            return 'stats'

        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        for mock in [
            patch('google.oauth2.id_token._fetch_certs', return_value={'web-key': self.public_key}),
            patch('jwt.PyJWKClient.get_signing_key_from_jwt', return_value=SimpleNamespace(key=self.key.public_key())),
        ]:
            mock.start()
            self.addCleanup(mock.stop)

    def login_page(self, client=None, query=''):
        response = (client or self.a).get('/login' + query, base_url='https://localhost')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn('same-origin-allow-popups', response.headers['Cross-Origin-Opener-Policy'])
        html = response.get_data(as_text=True)
        self.assertIn('Continue with Apple', html)
        self.assertIn('Continue with Google', html)
        self.assertIn('autocomplete="current-password"', html)
        return json.loads(re.search(r'id="sr-sign-in-config">(.*?)</script>', html).group(1))

    def token(self, provider, challenge_nonce, **overrides):
        claims = {
            'sub': provider + '-person',
            'iss': 'https://accounts.google.com' if provider == 'google' else 'https://appleid.apple.com',
            'aud': 'google-web-client' if provider == 'google' else 'apple-web-service',
            'iat': int(time.time()), 'exp': int(time.time()) + 300,
            'nonce': challenge_nonce, 'email_verified': True, 'name': 'Alex Player',
        }
        claims.update(overrides)
        return jwt.encode(claims, self.key, algorithm='RS256', headers={'kid': 'web-key'})

    def sign_in(self, provider, config, client=None, **payload):
        body = {'id_token': self.token(provider, config['nonce']),
                'state': config['csrf'], 'remember_me': True, 'next': '/stats/2026'}
        body.update(payload)
        return (client or self.a).post('/auth/' + provider, json=body,
                                      headers={'X-CSRF-Token': config['csrf']},
                                      base_url='https://localhost')

    def test_web_and_app_reuse_the_same_account_for_both_providers(self):
        for provider in ('google', 'apple'):
            with self.subTest(provider=provider):
                if provider == 'google':
                    ios_token = self.token(provider, 'unused', aud=GOOGLE_IOS_CLIENT_ID)
                    payload = {'id_token': ios_token}
                else:
                    nonce = self.b.post('/api/auth/apple/challenge').json['nonce']
                    ios_token = self.token(provider, hashlib.sha256(nonce.encode()).hexdigest(), aud='com.kt.stats')
                    payload = {'id_token': ios_token, 'nonce': nonce, 'full_name': 'Alex Player'}
                app_response = self.b.post('/api/auth/' + provider, json=payload)
                self.assertEqual(app_response.status_code, 200, app_response.json)
                username = app_response.json['username']
                account = account_for_user(self.path, username)
                # A private game created through the app must remain visible on web.
                headers = {'Authorization': 'Bearer ' + app_response.json['token'], 'X-Stats-Owned': '1'}
                self.b.post('/api/games', json={'name': provider + ' private'}, headers=headers)
                config = self.login_page()
                response = self.sign_in(provider, config)
                self.assertEqual(response.status_code, 200, response.json)
                self.assertNotIn('token', response.json)
                self.assertEqual(response.json['next'], '/stats/2026')
                cookie = next(value for value in response.headers.getlist('Set-Cookie') if value.startswith('remember_token='))
                for flag in ('Secure', 'HttpOnly', 'SameSite=Lax', 'Max-Age=7776000'):
                    self.assertIn(flag, cookie)
                with self.a.session_transaction(base_url='https://localhost') as session:
                    self.assertEqual(session['username'], username)
                    self.assertNotIn('web_sign_in', session)
                self.assertEqual(account_for_user(self.path, username)['id'], account['id'])
                games = self.a.get('/api/games', headers={'X-Stats-Owned': '1'}, base_url='https://localhost')
                self.assertEqual(games.json['rows'], [[2, provider + ' private']])
                self.assertEqual(self.a.get('/admin', base_url='https://localhost').status_code, 403)

    def test_new_social_account_and_remember_cookie_opt_out(self):
        response = self.sign_in('apple', self.login_page(), remember_me=False, full_name='Alex New')
        self.assertEqual(response.status_code, 200)
        self.assertIn('remember_token=; Expires=', response.headers.getlist('Set-Cookie')[0])
        with self.a.session_transaction(base_url='https://localhost') as session:
            user = self.service.adminfx.get_site_user(session['username'])
            self.assertEqual(user['display_name'], 'Alex New')
            self.assertFalse(user['is_admin'])

    def test_browser_binding_csrf_and_expiry(self):
        config = self.login_page()
        self.assertEqual(self.sign_in('google', config, client=self.b).status_code, 403)
        response = self.a.post('/auth/google', json={'id_token': 'anything'}, base_url='https://localhost')
        self.assertEqual(response.status_code, 403)
        with self.a.session_transaction(base_url='https://localhost') as session:
            session['web_sign_in'] = dict(session['web_sign_in'], expires=int(time.time()) - 1)
        self.assertEqual(self.sign_in('google', config).status_code, 403)

    def test_signed_tokens_reject_wrong_audience_issuer_nonce_expiry_and_email(self):
        for provider in ('google', 'apple'):
            overrides = [{'aud': 'unrelated-client'}, {'iss': 'https://attacker.example'},
                         {'nonce': 'wrong'}, {'exp': int(time.time()) - 60}, {'sub': ''}]
            if provider == 'google':
                overrides.append({'email_verified': False})
            for override in overrides:
                with self.subTest(provider=provider, override=override):
                    config = self.login_page()
                    response = self.sign_in(provider, config, id_token=self.token(provider, config['nonce'], **override))
                    self.assertEqual(response.status_code, 401, response.json)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM private_accounts').fetchone()[0], 0)

    def test_invalid_signature_and_apple_state_are_rejected(self):
        for provider in ('google', 'apple'):
            config = self.login_page()
            token = self.token(provider, config['nonce'])
            prefix, signature = token.rsplit('.', 1)
            forged = prefix + '.' + ('A' if signature[0] != 'A' else 'B') + signature[1:]
            self.assertEqual(self.sign_in(provider, config, id_token=forged).status_code, 401)
        self.assertEqual(self.sign_in('apple', self.login_page(), state='wrong').status_code, 401)

    def test_consumed_or_expired_database_challenge_cannot_be_reused(self):
        config = self.login_page()
        with self.a.session_transaction(base_url='https://localhost') as session:
            original = dict(session['web_sign_in'])
        self.assertEqual(self.sign_in('google', config).status_code, 200)
        # Even replaying the old signed session cookie cannot reuse the nonce.
        with self.a.session_transaction(base_url='https://localhost') as session:
            session['web_sign_in'] = original
        self.assertEqual(self.sign_in('google', config).status_code, 401)
        config = self.login_page()
        with sqlite3.connect(self.path) as conn:
            conn.execute('UPDATE private_auth_challenges SET expires_at=0')
        self.assertEqual(self.sign_in('apple', config).status_code, 401)

    def test_missing_configuration_and_provider_outage(self):
        with patch.dict(os.environ, {'GOOGLE_WEB_CLIENT_ID': '', 'APPLE_WEB_CLIENT_ID': ''}):
            config = self.login_page()
            for provider in ('google', 'apple'):
                self.assertEqual(self.sign_in(provider, config).status_code, 503)
        with patch('google.oauth2.id_token.verify_oauth2_token', side_effect=RuntimeError('offline')):
            self.assertEqual(self.sign_in('google', self.login_page()).status_code, 503)

    def test_rate_limit_and_invalid_payload(self):
        config = self.login_page()
        with patch.object(self.service, 'login_rate_limited', return_value=True):
            self.assertEqual(self.sign_in('google', config).status_code, 429)
        self.assertEqual(self.sign_in('google', config, id_token=None).status_code, 400)

    def test_external_redirects_are_rejected(self):
        for value in ('https://attacker.example', '//attacker.example', '/\\attacker.example',
                      '/%2fattacker.example', '/%5cattacker.example', '/\n/attacker.example', None):
            self.assertEqual(safe_login_next(value), '/')
        self.assertEqual(safe_login_next('/stats/2026?game=cards'), '/stats/2026?game=cards')
        with self.app.test_request_context(base_url='https://localhost'):
            self.assertEqual(safe_login_next('https://localhost/stats/2026?game=cards'), '/stats/2026?game=cards')
        config = self.login_page(query='?next=https://attacker.example')
        self.assertEqual(config['next'], '/')
        self.assertEqual(self.sign_in('google', config, next='//attacker.example').json['next'], '/')

    def test_password_login_still_works_and_failed_attempt_keeps_social_buttons(self):
        response = self.a.post('/login', data={'username': 'Kyle', 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Continue with Apple', response.get_data(as_text=True))
        for destination, expected in [('https://localhost/stats/2026', '/stats/2026'),
                                      ('https://attacker.example', '/')]:
            response = self.a.post('/login', base_url='https://localhost', data={
                'username': 'Kyle', 'password': 'valid-password', 'remember_me': 'on', 'next': destination,
            })
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers['Location'], expected)
            with self.a.session_transaction(base_url='https://localhost') as saved:
                self.assertEqual(saved['username'], 'Kyle')


if __name__ == '__main__':
    unittest.main()
