"""Native JSON transport exercises the exact same flow as the website."""
import re
import sqlite3
import time
import unittest
from unittest.mock import patch

from tests import test_web_sign_in


class EmailAppSignInTests(unittest.TestCase):
    def setUp(self):
        test_web_sign_in.WebSignInTests.setUp(self)

    def start(self, client=None, token=None):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        result = (client or self.a).get('/api/auth/email', headers=headers, base_url='https://localhost')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        self.assertEqual(result.json['step'], 'email')
        return result.json['csrf']

    def post(self, csrf, client=None, **fields):
        return (client or self.a).post('/api/auth/email', json={'csrf': csrf, **fields}, base_url='https://localhost')

    def send(self, csrf, email, client=None):
        result = self.post(csrf, client, action='send', email=email)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json['step'], 'code')
        self.assertEqual(result.json['email'], email)
        self.assertNotIn('token', result.json)
        code = re.search(r'\b\d{4}\b', self.service.mail.send.call_args.args[0].body).group()
        return code

    def test_existing_account_returns_bearer_token_with_original_permissions(self):
        csrf = self.start()
        code = self.send(csrf, 'kyle@example.com')
        result = self.post(csrf, action='verify', code=code)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['step'], 'complete')
        self.assertEqual(self.service.validate_auth_token(result.json['token']), 'Kyle')
        self.assertNotIn('remember_token', str(result.headers.getlist('Set-Cookie')))
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 403)

    def test_signup_requires_names_and_reuses_same_account_on_website(self):
        csrf = self.start()
        code = self.send(csrf, 'new@example.com')
        self.assertEqual(self.post(csrf, action='signup', first_name='alex', last_name='SMITH').status_code, 400)
        result = self.post(csrf, action='verify', code=code)
        self.assertEqual(result.json['step'], 'signup')
        self.assertNotIn('token', result.json)
        self.assertEqual(self.post(csrf, action='signup', first_name='alex', last_name='').status_code, 400)
        result = self.post(csrf, action='signup', first_name='alex', last_name='SMITH')
        self.assertEqual(result.json['step'], 'complete')
        username = self.service.validate_auth_token(result.json['token'])
        user = self.service.adminfx.get_site_user(username)
        self.assertEqual(user['display_name'], 'Alex Smith')
        self.assertFalse(user['is_admin'])
        self.assertEqual(self.b.get('/api/games', headers={'Authorization': 'Bearer ' + result.json['token'], 'X-Stats-Owned': '1'}).json['rows'], [])
        # The browser signs into that same identity using its own challenge.
        self.b = self.app.test_client()
        with patch('web_sign_in.time', return_value=time.time() + 61):
            page = self.b.get('/login', base_url='https://localhost').get_data(as_text=True)
            web_csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
            self.b.post('/login', data={'csrf': web_csrf, 'action': 'send', 'email': 'new@example.com'}, base_url='https://localhost')
            web_code = re.search(r'\b\d{4}\b', self.service.mail.send.call_args.args[0].body).group()
            self.assertEqual(self.b.post('/login', data={'csrf': web_csrf, 'action': 'verify', 'code': web_code}, base_url='https://localhost').status_code, 303)
        with self.b.session_transaction(base_url='https://localhost') as saved:
            self.assertEqual(saved['username'], username)

    def test_password_and_saved_bearer_sessions_can_enroll_email(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET login_email=NULL WHERE username='Kyle'")
        csrf = self.start()
        result = self.post(csrf, action='password', username='Kyle', password='valid-password')
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json['enrolling'])
        self.assertNotIn('token', result.json)
        # A separate restored app session can enroll without re-entering password.
        csrf_b = self.start(self.b, token='shared-token')
        code = self.send(csrf_b, 'added@example.com', self.b)
        result = self.post(csrf_b, self.b, action='verify', code=code)
        self.assertEqual(result.json['step'], 'complete')
        self.assertEqual(self.service.validate_auth_token(result.json['token']), 'Kyle')
        self.assertEqual(self.service.adminfx.get_site_user('Kyle')['login_email'], 'added@example.com')

    def test_invalid_bearer_csrf_payload_and_cross_session_rejected(self):
        self.assertEqual(self.a.get('/api/auth/email', headers={'Authorization': 'Bearer invalid'}).status_code, 401)
        csrf = self.start()
        code = self.send(csrf, 'kyle@example.com')
        self.assertEqual(self.post(csrf, self.b, action='verify', code=code).status_code, 403)
        self.assertEqual(self.post('wrong', action='verify', code=code).status_code, 403)
        for body in ([], None, {'csrf': csrf, 'code': 1234}):
            self.assertEqual(self.a.post('/api/auth/email', json=body, base_url='https://localhost').status_code, 400)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET active=0 WHERE username='Kyle'")
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 403)

    def test_me_reports_whether_the_app_should_prompt_for_email(self):
        import ast
        from pathlib import Path
        from flask import g, jsonify, session
        from private_accounts import private_database
        tree = ast.parse(Path('ios_api.py').read_text())
        registration = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'register_ios_api')
        node = next(node for node in registration.body if isinstance(node, ast.FunctionDef) and node.name == 'api_me')
        node.decorator_list = []
        self.service.adminfx.site_user_display_name = lambda username: username
        namespace = dict(_S=lambda: self.service, session=session, jsonify=jsonify, g=g, private_database=private_database)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'ios_api.py', 'exec'), namespace)
        self.app.view_functions['api_me'] = namespace['api_me']
        headers = {'Authorization': 'Bearer shared-token'}
        self.assertFalse(self.a.get('/api/me', headers=headers).json['needs_login_email'])
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET login_email=NULL WHERE username='Kyle'")
        self.assertTrue(self.a.get('/api/me', headers=headers).json['needs_login_email'])

    def test_resend_change_and_shared_web_rate_limits(self):
        csrf = self.start()
        code = self.send(csrf, 'kyle@example.com')
        self.assertEqual(self.post(csrf, action='resend').status_code, 429)
        with patch('web_sign_in.time', return_value=time.time() + 61):
            result = self.post(csrf, action='resend')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json['step'], 'code')
        result = self.post(csrf, action='change')
        self.assertEqual(result.json['step'], 'email')
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 400)

    def test_completed_session_can_recover_if_final_response_is_lost(self):
        csrf = self.start()
        code = self.send(csrf, 'kyle@example.com')
        self.post(csrf, action='verify', code=code)
        result = self.a.get('/api/auth/email', base_url='https://localhost')
        self.assertEqual(result.json['step'], 'complete')
        self.assertEqual(self.service.validate_auth_token(result.json['token']), 'Kyle')


if __name__ == '__main__':
    unittest.main()
