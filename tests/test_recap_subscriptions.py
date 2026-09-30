"""Public recap access and email subscriptions without app startup jobs."""
import ast
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import Mock, patch

from flask import Flask, abort, flash, redirect, request, session, url_for
from jinja2 import ChoiceLoader, DictLoader
import admin_functions as adminfx
import recap_subscriptions

ROOT = Path(__file__).resolve().parents[1]


class RecapSubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = patch.object(adminfx, 'stats_db_path', return_value=str(Path(self.tmp.name) / 'stats.db'))
        self.db.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.db.stop)
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'))
        self.app.secret_key = 'test'
        self.render = Mock(return_value='recaps')
        self.admin = Mock()
        self.admin.list_ai_recap_pages.return_value = ([{'share_id': 'abc', 'username': 'owner'}], 1)
        self.ns = dict(app=self.app, request=request, session=session, abort=abort,
                       flash=flash, redirect=redirect, url_for=url_for, secrets=secrets,
                       recap_subscriptions=recap_subscriptions, adminfx=self.admin,
                       EMAIL_SITE_BASE_URL='https://example.com', render_template=self.render,
                       serialize_recap_list_entry=lambda row, base: dict(row),
                       _is_owner_or_admin=lambda owner: session.get('username') == owner)
        tree = ast.parse((ROOT / 'stats.py').read_text())
        names = {'my_ai_recaps', 'inject_recap_subscription_token', 'subscribe_ai_recaps',
                 'send_ai_summary_messages', '_apply_ai_email_opt_out'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'stats.py', 'exec'), self.ns)
        self.client = self.app.test_client()

    def test_public_directory_and_owner_controls(self):
        self.assertEqual(self.client.get('/ai-recaps/?page=bad').status_code, 200)
        self.admin.list_ai_recap_pages.assert_called_with(page=1, per_page=25, username=None)
        self.assertFalse(self.render.call_args.kwargs['entries'][0]['can_manage'])
        with self.client.session_transaction() as sess:
            sess.update(logged_in=True, username='owner')
        self.client.get('/ai-recaps/')
        self.assertTrue(self.render.call_args.kwargs['entries'][0]['can_manage'])
        with self.client.session_transaction() as sess:
            sess['username'] = 'other'
        self.client.get('/ai-recaps/')
        self.assertFalse(self.render.call_args.kwargs['entries'][0]['can_manage'])

    def test_anonymous_subscribe_validation_and_deduplication(self):
        self.assertEqual(self.client.post('/ai-recaps/subscribe', data={'email': 'a@example.com'}).status_code, 400)
        with self.client.session_transaction() as sess:
            sess['recap_subscription_token'] = 'token'
        for email in ['bad', 'A@example.com', ' a@example.com ']:
            response = self.client.post('/ai-recaps/subscribe', data={'email': email, 'subscription_token': 'token'})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(recap_subscriptions.recipients([]), ['a@example.com'])
        self.assertEqual(recap_subscriptions.recipients(['A@example.com']), ['A@example.com'])

    def test_delivery_includes_subscribers_and_unsubscribe_removes_them(self):
        recap_subscriptions.subscribe('fan@example.com')
        build = Mock(side_effect=lambda *args, **kwargs: args[3])
        send = Mock(return_value=(2, []))
        self.ns.update(_filter_ai_email_opt_outs=lambda values: values,
                       _ai_email_public_recipients=list, extend_ai_email_recipients=list,
                       build_ai_summary_message=build, send_messages_with_retry=send,
                       _ai_email_public_sent_count=lambda values, errors: len(values))
        self.assertEqual(self.ns['send_ai_summary_messages']('Recap', 'html', 'text', ['player@example.com']), (2, []))
        send.assert_called_once_with(['player@example.com', 'fan@example.com'])
        cur = Mock()
        cur.fetchone.return_value = None
        self.ns['set_cur'] = lambda: cur
        self.ns['_apply_ai_email_opt_out']('FAN@example.com')
        self.assertEqual(recap_subscriptions.recipients([]), [])

    def test_public_menu_and_subscription_templates(self):
        with self.app.test_request_context('/'):
            self.app.jinja_env.globals.update(url_for=lambda endpoint, **kw: '/' + endpoint,
                                             recap_subscription_token=lambda: 'token')
            menu = self.app.jinja_env.get_template('partials/menu_sidebar.html').render(session={})
            self.assertIn('/my_ai_recaps', menu)
            self.assertNotIn('/ai_summary', menu)
            self.app.jinja_env.loader = ChoiceLoader([
                DictLoader({'test_base.html': '{% block content %}{% endblock %}'}),
                self.app.jinja_env.loader,
            ])
            template = self.app.jinja_env.get_template('ai_recaps.html')
            for manageable in (False, True):
                html = template.render(base_template='test_base.html', session={'logged_in': manageable},
                                       entries=[dict(share_id='abc', subject='Recap', can_manage=manageable)],
                                       page=1, total_pages=1)
                self.assertEqual('Creator view' in html, manageable)
                self.assertEqual('> Delete' in html, manageable)
            self.app.jinja_env.get_template('recap.html')
            form = self.app.jinja_env.get_template('partials/recap_subscription.html').render()
            self.assertIn('type="email"', form)
            self.assertIn('/subscribe_ai_recaps', form)


if __name__ == '__main__':
    unittest.main()
