"""Public review links stay usable and browser account controls stay gated."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask, abort, redirect, session

from policy_pages import register_policy_pages, safe_return_path

ROOT = Path(__file__).resolve().parents[1]


class PolicyPagesTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'),
                         static_folder=str(ROOT / 'static'))
        self.app.secret_key = 'test-only'
        self.app.testing = True

        def require_login(fn):
            def wrapped(*args, **kwargs):
                if not session.get('logged_in'):
                    return redirect('/login/')
                return fn(*args, **kwargs)
            wrapped.__name__ = fn.__name__
            return wrapped

        def require_admin(fn):
            def wrapped(*args, **kwargs):
                if session.get('username') != 'Kyle':
                    abort(403)
                return fn(*args, **kwargs)
            wrapped.__name__ = fn.__name__
            return wrapped

        register_policy_pages(self.app, SimpleNamespace(
            login_required=require_login, admin_required=require_admin,
            is_admin=lambda: session.get('username') == 'Kyle'))
        self.client = self.app.test_client()

    def login(self, name='alice'):
        with self.client.session_transaction() as state:
            state.update(username=name, logged_in=True)

    def test_required_public_links_work_without_login_or_stats_database(self):
        for path, heading in [('/privacy', 'Privacy policy'), ('/support', 'Support'),
                              ('/community-guidelines', 'Community guidelines')]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(heading, response.text)
            self.assertIn('idynkydnk@gmail.com', response.text)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_settings_and_moderation_require_correct_account_access(self):
        self.assertEqual(self.client.get('/privacy-settings').status_code, 302)
        self.assertEqual(self.client.get('/admin/content-reports').status_code, 403)
        self.login()
        response = self.client.get('/privacy-settings?next=https://evil.example')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('evil.example', response.text)
        self.assertIn('data-consent-grant disabled', response.text)
        self.assertEqual(self.client.get('/admin/content-reports').status_code, 403)
        self.login('Kyle')
        self.assertEqual(self.client.get('/admin/content-reports').status_code, 200)

    def test_reporting_is_public_but_requires_visible_content_and_escapes_identifiers(self):
        self.assertEqual(self.client.get('/report-content?kind=unknown&id=1').status_code, 400)
        with patch('content_safety.content_for_report', return_value={'username': '<bad>'}) as load:
            response = self.client.get('/report-content?kind=recap&id=sample')
            self.assertEqual(response.status_code, 200)
            load.assert_called_once_with('recap', 'sample')
            self.assertIn('You can report without signing in', response.text)
            self.login()
            response = self.client.get('/report-content?kind=recap&id=sample')
            self.assertIn('data-block-author="&lt;bad&gt;"', response.text)
            self.assertNotIn('data-block-author="<bad>"', response.text)

    def test_return_link_never_leaves_site(self):
        for value in ['https://evil.example', '//evil.example', '/\\evil.example',
                      '/path\nheader', 'http://[', 'javascript:alert(1)']:
            self.assertEqual(safe_return_path(value), '/')
        self.assertEqual(safe_return_path('/ai_summary/?year=2026'), '/ai_summary/?year=2026')


if __name__ == '__main__':
    unittest.main()
