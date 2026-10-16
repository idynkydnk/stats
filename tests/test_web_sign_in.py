import ast
import re
import sqlite3
import time
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from flask import session
from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader

from tests import test_private_accounts
from private_accounts import account_for_user
from web_sign_in import init_email_sign_in, safe_login_next


class WebSignInTests(unittest.TestCase):
    def setUp(self):
        test_private_accounts.PrivateAccountTests.setUp(self)
        from flask_mail import Mail
        self.app.config['MAIL_DEFAULT_SENDER'] = 'stats@example.com'
        Mail(self.app)
        self.service.mail = Mock()
        self.service.log_activity = Mock()
        self.service.verify_password = lambda name, password: name.lower() == 'kyle' and password == 'valid-password'
        self.app.jinja_loader = ChoiceLoader([
            DictLoader({'test_base.html': '{% block extra_css %}{% endblock %}{% block content %}{% endblock %}{% block extra_js %}{% endblock %}', 'partials/page_header_actions.html': ''}),
            FileSystemLoader(str(Path(__file__).resolve().parents[1] / 'templates')),
        ])
        self.app.context_processor(lambda: {'base_template': 'test_base.html'})
        namespace = {'app': self.app}
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'stats.py').read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'login']
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'stats.py', 'exec'), namespace)
        self.app.add_url_rule('/', 'index', lambda: 'stats')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET login_email='kyle@example.com' WHERE username='Kyle'")

    def page(self, client=None, query=''):
        client = client or self.a
        response = client.get('/login' + query, base_url='https://localhost')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        html = response.get_data(as_text=True)
        self.assertNotIn('Continue with Apple', html)
        self.assertNotIn('Continue with Google', html)
        self.assertNotIn('accounts.google.com', html)
        return re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    def post(self, csrf, client=None, **data):
        return (client or self.a).post('/login', data={'csrf': csrf, **data}, base_url='https://localhost')

    def send(self, email='kyle@example.com', client=None, remember=True, query=''):
        csrf = self.page(client, query)
        response = self.post(csrf, client, action='send', email=email, remember_me='on' if remember else '')
        self.assertEqual(response.status_code, 303, response.get_data(as_text=True))
        message = self.service.mail.send.call_args.args[0]
        self.assertEqual(message.recipients, [email.strip().lower()])
        self.assertFalse(message.cc)
        self.assertFalse(message.bcc)
        code = re.search(r'\b\d{4}\b', message.body).group()
        return csrf, code

    def signed_in_username(self, client=None):
        with (client or self.a).session_transaction(base_url='https://localhost') as saved:
            return saved.get('username')

    def test_existing_account_reuses_identity_permissions_and_remember_cookie(self):
        csrf, code = self.send(' Kyle@Example.COM ', query='?next=/stats/2026')
        response = self.post(csrf, action='verify', code=code)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.location, '/stats/2026')
        self.assertEqual(self.signed_in_username(), 'Kyle')
        self.assertEqual(self.a.get('/admin', base_url='https://localhost').status_code, 200)
        self.assertIsNone(account_for_user(self.path, 'Kyle'))
        cookie = next(value for value in response.headers.getlist('Set-Cookie') if value.startswith('remember_token='))
        for flag in ('Secure', 'HttpOnly', 'SameSite=Lax', 'Max-Age=7776000'):
            self.assertIn(flag, cookie)

    def test_new_account_created_only_after_verification_and_is_private(self):
        csrf, code = self.send('new@example.com', remember=False)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM site_users').fetchone()[0], 1)
        response = self.post(csrf, action='verify', code=code)
        self.assertEqual(response.status_code, 303)
        self.assertIsNone(self.signed_in_username())
        response = self.post(csrf, action='signup', first_name='alex', last_name='PLAYER')
        self.assertEqual(response.status_code, 303)
        self.assertIn('remember_token=; Expires=', response.headers.getlist('Set-Cookie')[0])
        username = self.signed_in_username()
        self.assertIsNotNone(account_for_user(self.path, username))
        self.assertFalse(self.service.adminfx.get_site_user(username)['is_admin'])
        user = self.service.adminfx.get_site_user(username)
        self.assertEqual((user['first_name'], user['last_name'], user['display_name']), ('Alex', 'Player', 'Alex Player'))
        self.assertEqual(self.a.get('/admin', base_url='https://localhost').status_code, 403)
        self.assertEqual(self.a.get('/api/games', headers={'X-Stats-Owned': '1'}, base_url='https://localhost').json['rows'], [])
        # Another browser receives a new code for the exact same account.
        with patch('web_sign_in.time', return_value=time.time() + 61):
            csrf, code = self.send('new@example.com', client=self.b)
            self.assertEqual(self.post(csrf, self.b, action='verify', code=code).status_code, 303)
        self.assertEqual(self.signed_in_username(self.b), username)

    def remove_email(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET login_email=NULL WHERE username='Kyle'")

    def enroll(self):
        self.remove_email()
        csrf = self.page(query='?next=/admin')
        response = self.post(csrf, action='password', username='Kyle', password='valid-password', remember_me='on')
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.location, '/login')
        page = self.a.get('/login', base_url='https://localhost')
        self.assertIn('Add your email', page.get_data(as_text=True))
        return self.send('added@example.com')

    def test_missing_email_prompt_keeps_existing_account_and_verifies_before_saving(self):
        csrf, code = self.enroll()
        self.assertIsNone(self.service.adminfx.get_site_user('Kyle')['login_email'])
        response = self.post(csrf, action='verify', code=code)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.location, '/admin')
        self.assertEqual(self.signed_in_username(), 'Kyle')
        self.assertEqual(self.service.adminfx.get_site_user('Kyle')['login_email'], 'added@example.com')
        self.assertTrue(self.service.adminfx.get_site_user('Kyle')['is_admin'])
        self.assertIsNone(account_for_user(self.path, 'Kyle'))
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM site_users').fetchone()[0], 1)
        # The same account now works without a password in another browser.
        with patch('web_sign_in.time', return_value=time.time() + 61):
            csrf, code = self.send('added@example.com', client=self.b)
            self.assertEqual(self.post(csrf, self.b, action='verify', code=code).status_code, 303)
        self.assertEqual(self.signed_in_username(self.b), 'Kyle')

    def test_remembered_sessions_prompt_without_interrupting_api_requests(self):
        self.remove_email()
        self.app.add_url_rule('/remember-test', view_func=lambda: self.app.response_class(
            'remembered', headers={'Set-Cookie': 'remember_token=shared-token; Path=/; Secure; HttpOnly; SameSite=Lax'}))
        self.a.get('/remember-test', base_url='https://localhost')
        response = self.a.get('/admin', headers={'Accept': 'text/html'}, base_url='https://localhost')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/login')
        response = self.a.get('/login', base_url='https://localhost')
        self.assertIn('Add your email', response.get_data(as_text=True))
        self.assertEqual(self.a.get('/api/me', headers={'Accept': 'text/html'}, base_url='https://localhost').status_code, 200)

    def test_enrollment_cannot_claim_another_accounts_email(self):
        csrf, code = self.enroll()
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO site_users (username, login_email) VALUES ('Other', 'added@example.com')")
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 409)
        self.assertIsNone(self.service.adminfx.get_site_user('Kyle')['login_email'])
        self.assertEqual(self.service.adminfx.get_site_user('Other')['login_email'], 'added@example.com')

    def test_enrollment_code_requires_the_original_authenticated_account(self):
        csrf, code = self.enroll()
        with self.a.session_transaction(base_url='https://localhost') as saved:
            saved.pop('logged_in')
            saved.pop('username')
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 403)
        self.assertIsNone(self.service.adminfx.get_site_user('Kyle')['login_email'])
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM site_users').fetchone()[0], 1)

    def test_enrollment_does_not_overwrite_an_email_set_while_code_is_pending(self):
        csrf, code = self.enroll()
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET login_email='admin-set@example.com' WHERE username='Kyle'")
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 403)
        self.assertEqual(self.service.adminfx.get_site_user('Kyle')['login_email'], 'admin-set@example.com')

    def test_signup_requires_verified_email_and_both_names(self):
        csrf, code = self.send('new@example.com')
        names = {'first_name': 'jane', 'last_name': "o'NEILL"}
        self.assertEqual(self.post(csrf, action='signup', **names).status_code, 400)
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 303)
        html = self.a.get('/login', base_url='https://localhost').get_data(as_text=True)
        for text in ('First name', 'Last name', 'autocomplete="given-name"', 'autocomplete="family-name"'):
            self.assertIn(text, html)
        for first, last in [('', 'Smith'), ('Jane', ''), ('Jane', '<script>'), ('123', 'Smith')]:
            self.assertEqual(self.post(csrf, action='signup', first_name=first, last_name=last).status_code, 400)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM site_users').fetchone()[0], 1)
        self.assertEqual(self.post(csrf, action='signup', **names).status_code, 303)
        user = self.service.adminfx.get_site_user(self.signed_in_username())
        self.assertEqual(user['display_name'], "Jane O'Neill")
        self.assertEqual(self.post(csrf, action='signup', **names).status_code, 403)

    def test_signup_proof_expires_and_code_cannot_be_verified_twice(self):
        csrf, code = self.send('new@example.com')
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 303)
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 400)
        with patch('web_sign_in.time', return_value=time.time() + 601):
            response = self.post(csrf, action='signup', first_name='New', last_name='Player')
        self.assertEqual(response.status_code, 400)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM site_users').fetchone()[0], 1)
        self.assertIn('Email me a code', response.get_data(as_text=True))

    def test_signup_offers_existing_account_path_instead_of_guessing_by_name(self):
        csrf, code = self.send('new@example.com')
        self.post(csrf, action='verify', code=code)
        response = self.post(csrf, action='change', password_start='1')
        self.assertEqual(response.location, '/login?password=1')
        page = self.a.get(response.location, base_url='https://localhost').get_data(as_text=True)
        self.assertIn('class="sr-login-fallback" open', page)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM site_users').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM web_email_codes').fetchone()[0], 0)

    def test_four_digit_code_supports_leading_zero_and_expiry(self):
        with patch('web_sign_in.secrets.randbelow', return_value=7):
            csrf, code = self.send()
        self.assertEqual(code, '0007')
        self.assertIn('5 minutes', self.service.mail.send.call_args.args[0].body)
        self.assertEqual(self.post(csrf, action='verify', code='000007').status_code, 400)
        self.assertEqual(self.post(csrf, action='verify', code='0 0 0 7').status_code, 303)

    def test_wrong_code_limit_applies_across_resends_and_browsers(self):
        csrf, code = self.send()
        wrong = '9999' if code != '9999' else '1111'
        for _ in range(3):
            self.assertEqual(self.post(csrf, action='verify', code=wrong).status_code, 400)
        with patch('web_sign_in.time', return_value=time.time() + 61):
            csrf_b, code_b = self.send(client=self.b)
            wrong_b = '9999' if code_b != '9999' else '1111'
            for _ in range(3):
                self.assertEqual(self.post(csrf_b, self.b, action='verify', code=wrong_b).status_code, 400)
        with patch('web_sign_in.time', return_value=time.time() + 122):
            self.assertEqual(self.post(csrf_b, self.b, action='resend').status_code, 303)
            new_code = re.search(r'\b\d{4}\b', self.service.mail.send.call_args.args[0].body).group()
            self.assertEqual(self.post(csrf_b, self.b, action='verify', code=new_code).status_code, 429)

    def test_name_capitalization_preserves_mixed_case_and_unicode(self):
        from account_names import clean_signup_name
        for raw, expected in [('  jane  ', 'Jane'), ('SMITH', 'Smith'), ('anne-marie', 'Anne-Marie'),
                              ("o’NEILL", 'O’Neill'), ('McDonald', 'McDonald'), ('deVries', 'deVries'),
                              ('élodie', 'Élodie'), ('李', '李')]:
            self.assertEqual(clean_signup_name(raw), expected)

    def test_private_existing_user_keeps_games(self):
        from private_accounts import create_account
        create_account(self.path, 'existing', password='old-password')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET login_email='existing@example.com' WHERE username='existing'")
        account = account_for_user(self.path, 'existing')
        from private_accounts import provision_database
        database = provision_database(self.path, account['id'])
        with sqlite3.connect(database) as conn:
            conn.execute("INSERT INTO games VALUES (2, 'Existing private game')")
        csrf, code = self.send('existing@example.com')
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 303)
        self.assertEqual(self.signed_in_username(), 'existing')
        self.assertEqual(self.a.get('/api/games', headers={'X-Stats-Owned': '1'}, base_url='https://localhost').json['rows'], [[2, 'Existing private game']])

    def test_code_page_accessibility_and_no_code_in_cookie_or_database(self):
        csrf, code = self.send()
        html = self.a.get('/login', base_url='https://localhost').get_data(as_text=True)
        for text in ('Check your email', 'autocomplete="one-time-code"', 'inputmode="numeric"', 'Send a new code', 'Use a different email', 'role="alert"'):
            if text != 'role="alert"':
                self.assertIn(text, html)
        with self.a.session_transaction(base_url='https://localhost') as saved:
            self.assertNotIn(code, str(dict(saved)))
        with sqlite3.connect(self.path) as conn:
            row = conn.execute('SELECT code_hash FROM web_email_codes').fetchone()
            self.assertNotEqual(row[0], code)
            self.assertEqual(len(row[0]), 64)

    def test_csrf_browser_binding_and_replay(self):
        csrf, code = self.send()
        self.assertEqual(self.post(csrf, self.b, action='verify', code=code).status_code, 403)
        self.assertEqual(self.post('☃', action='verify', code=code).status_code, 403)
        with self.a.session_transaction(base_url='https://localhost') as saved:
            old = dict(saved)
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 303)
        with self.a.session_transaction(base_url='https://localhost') as saved:
            saved.clear()
            saved.update(old)
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 400)
        self.assertIsNone(self.signed_in_username())

    def test_expiry_attempt_limit_and_correct_code_cannot_bypass_lockout(self):
        csrf, code = self.send()
        wrong = '9999' if code != '9999' else '1111'
        for _ in range(3):
            self.assertEqual(self.post(csrf, action='verify', code=wrong).status_code, 400)
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 429)
        with sqlite3.connect(self.path) as conn:
            conn.execute('UPDATE web_email_codes SET attempts=0, expires_at=0')
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 400)
        self.assertIsNone(self.signed_in_username())

    def test_resend_throttle_replacement_and_change_email(self):
        csrf, original = self.send()
        self.assertEqual(self.post(csrf, action='resend').status_code, 429)
        self.assertEqual(self.service.mail.send.call_count, 1)
        with patch('web_sign_in.time', return_value=time.time() + 61), patch('web_sign_in.secrets.randbelow', return_value=1234 if original != '1234' else 6543):
            self.assertEqual(self.post(csrf, action='resend').status_code, 303)
            self.assertEqual(self.post(csrf, action='verify', code=original).status_code, 400)
        self.assertEqual(self.post(csrf, action='change').status_code, 303)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM web_email_codes').fetchone()[0], 0)
        self.assertIn('Email me a code', self.a.get('/login', base_url='https://localhost').get_data(as_text=True))

    def test_email_and_ip_limits_survive_new_browser(self):
        csrf, code = self.send()
        other_csrf = self.page(self.b)
        self.assertEqual(self.post(other_csrf, self.b, action='send', email='KYLE@example.com').status_code, 429)
        for i in range(1, 5):
            with patch('web_sign_in.time', return_value=time.time() + i * 61):
                self.assertEqual(self.post(csrf, action='resend').status_code, 303)
        with patch('web_sign_in.time', return_value=time.time() + 305):
            self.assertEqual(self.post(csrf, action='resend').status_code, 429)
        self.assertEqual(self.service.mail.send.call_count, 5)

    def test_ip_send_and_verify_limits_cover_multiple_addresses(self):
        csrf = self.page()
        for i in range(20):
            self.assertEqual(self.post(csrf, action='send', email=f'user{i}@example.com').status_code, 303)
        self.assertEqual(self.post(csrf, action='send', email='blocked@example.com').status_code, 429)
        # A fresh client cannot bypass the shared limit.
        csrf_b = self.page(self.b)
        self.assertEqual(self.post(csrf_b, self.b, action='send', email='another@example.com').status_code, 429)
        import hashlib
        import hmac
        key_hash = hmac.new(self.app.secret_key.encode(), b'verify:127.0.0.1', hashlib.sha256).hexdigest()
        with sqlite3.connect(self.path) as conn:
            conn.executemany('INSERT INTO web_login_events VALUES (?, ?, ?)',
                             [('verify', key_hash, int(time.time()))] * 30)
        self.assertEqual(self.post(csrf, action='verify', code='0000').status_code, 429)

    def test_untrusted_requests_never_send_email(self):
        self.assertEqual(self.post('', action='send', email='new@example.com').status_code, 403)
        self.service.mail.send.assert_not_called()

    def test_invalid_email_and_delivery_failure_do_not_create_account(self):
        csrf = self.page()
        for email in ('bad', 'a@example.com\r\nBcc: evil@example.com', 'a b@example.com', '@example.com'):
            self.assertEqual(self.post(csrf, action='send', email=email).status_code, 400)
        self.service.mail.send.assert_not_called()
        self.service.mail.send.side_effect = RuntimeError('SMTP unavailable')
        self.assertEqual(self.post(csrf, action='send', email='new@example.com').status_code, 503)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM web_email_codes').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM site_users').fetchone()[0], 1)

    def test_inactive_and_ambiguous_emails_cannot_sign_in_or_create_replacement(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET active=0 WHERE username='Kyle'")
        csrf, code = self.send()
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 403)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET active=1 WHERE username='Kyle'")
            conn.execute("INSERT INTO site_users (username, login_email) VALUES ('Duplicate', 'kyle@example.com')")
        with patch('web_sign_in.time', return_value=time.time() + 61):
            csrf, code = self.send()
            self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 403)
        self.assertIsNone(self.signed_in_username())

    def test_safe_redirects_and_password_fallback(self):
        for value in ('https://attacker.example', '//attacker.example', '/\\attacker.example', '/%2fattacker.example', '/%5cattacker.example', '/\n/attacker.example', None):
            self.assertEqual(safe_login_next(value), '/')
        for destination, expected in [('https://localhost/stats/2026', '/stats/2026'), ('https://attacker.example', '/')]:
            csrf = self.page(query='?next=' + destination)
            response = self.post(csrf, action='password', username='Kyle', password='wrong')
            self.assertEqual(response.status_code, 401)
            self.assertIn('role="alert"', response.get_data(as_text=True))
            response = self.post(csrf, action='password', username='Kyle', password='valid-password')
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.location, expected)
            with self.a.session_transaction(base_url='https://localhost') as saved:
                saved.clear()

    def test_admin_email_changes_require_admin_and_csrf(self):
        data = {'username': 'Kyle', 'email': 'updated@example.com', 'csrf': 'admin-csrf'}
        self.assertEqual(self.a.post('/admin/users/email', data=data).status_code, 403)
        with self.a.session_transaction() as saved:
            saved.update(logged_in=True, username='Kyle', login_email_admin_csrf='admin-csrf')
        self.assertEqual(self.a.post('/admin/users/email', data={**data, 'csrf': 'wrong'}).status_code, 403)
        self.assertEqual(self.a.post('/admin/users/email', data=data).status_code, 303)
        self.assertEqual(self.service.adminfx.get_site_user('Kyle')['login_email'], 'updated@example.com')
        self.service.log_activity.assert_called_once()
        with self.a.session_transaction() as saved:
            saved.update(logged_in=True, username='not-admin')
        self.assertEqual(self.a.post('/admin/users/email', data=data).status_code, 403)

    def test_admin_email_change_rejects_conflicts_and_revokes_pending_codes(self):
        from web_sign_in import set_login_email
        csrf, code = self.send()
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO site_users (username, login_email) VALUES ('Other', 'other@example.com')")
        with self.assertRaises(ValueError):
            set_login_email(self.path, 'Kyle', 'other@example.com')
        with self.assertRaises(ValueError):
            set_login_email(self.path, 'Kyle', 'invalid')
        set_login_email(self.path, 'Kyle', 'updated@example.com')
        self.assertEqual(self.post(csrf, action='verify', code=code).status_code, 400)
        self.assertEqual(self.service.adminfx.get_site_user('Kyle')['login_email'], 'updated@example.com')
        set_login_email(self.path, 'Kyle', '')
        self.assertIsNone(self.service.adminfx.get_site_user('Kyle')['login_email'])

    def test_old_web_provider_endpoints_removed(self):
        for provider in ('google', 'apple'):
            self.assertEqual(self.a.post('/auth/' + provider, json={}).status_code, 404)

    def test_migration_uses_only_explicit_player_links_and_does_not_follow_later_edits(self):
        # Separate pre-migration database; migration must also work with legacy schema.
        path = str(Path(self.directory.name) / 'legacy.db')
        with sqlite3.connect(path) as conn:
            conn.executescript('''
                CREATE TABLE site_users (username TEXT, player_name TEXT);
                CREATE TABLE players (full_name TEXT, email TEXT);
                INSERT INTO site_users VALUES ('owner', 'Owner Person'), ('unlinked', NULL);
                INSERT INTO players VALUES ('Owner Person', ' Owner@Example.com '), ('Unlinked Person', 'unlinked@example.com');
            ''')
        init_email_sign_in(path)
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute('SELECT login_email FROM site_users ORDER BY username').fetchall(), [('owner@example.com',), (None,)])
            conn.execute("UPDATE players SET email='changed@example.com'")
        init_email_sign_in(path)
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute("SELECT login_email FROM site_users WHERE username='owner'").fetchone()[0], 'owner@example.com')


if __name__ == '__main__':
    unittest.main()
