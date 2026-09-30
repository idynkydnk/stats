"""Check removal authorization and existing-session invalidation without startup jobs."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
from flask import Flask, flash, redirect, request, session, url_for


class UserRemovalTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.secret_key = 'test'
        self.users = Mock()
        self.users.delete_site_user.return_value = True
        self.users.get_site_user.side_effect = lambda name: {'active': True} if name in ('admin', 'user') else None
        namespace = dict(app=app, adminfx=self.users, flash=flash, redirect=redirect,
                         request=request, session=session, url_for=url_for,
                         log_activity=Mock(), is_admin=lambda: session.get('username') == 'admin')
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'stats.py').read_text())
        for name in ('reject_removed_user_session', 'admin_required', 'admin_delete_user'):
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            exec(compile(ast.Module(body=[node], type_ignores=[]), 'stats.py', 'exec'), namespace)
        for name in ('login', 'index', 'admin_dashboard'):
            app.add_url_rule('/' + name, name, lambda: 'OK')
        self.client = app.test_client()

    def login(self, name):
        with self.client.session_transaction() as state:
            state.update(logged_in=True, username=name)

    def test_admin_can_remove_user(self):
        self.login('admin')
        self.assertEqual(self.client.post('/admin/users/delete', data={'username': ' user '}).status_code, 302)
        self.users.delete_site_user.assert_called_once_with('user')

    def test_self_removal_is_blocked(self):
        self.login('admin')
        self.client.post('/admin/users/delete', data={'username': 'ADMIN'})
        self.users.delete_site_user.assert_not_called()

    def test_non_admin_cannot_remove_user(self):
        self.login('user')
        self.client.post('/admin/users/delete', data={'username': 'someone'})
        self.users.delete_site_user.assert_not_called()

    def test_removed_user_session_is_cleared(self):
        self.login('removed')
        self.client.get('/index')
        with self.client.session_transaction() as state:
            self.assertNotIn('logged_in', state)

    def test_deactivated_user_session_is_cleared(self):
        self.users.get_site_user.side_effect = None
        self.users.get_site_user.return_value = {'active': False}
        self.login('user')
        self.client.get('/index')
        with self.client.session_transaction() as state:
            self.assertNotIn('logged_in', state)
