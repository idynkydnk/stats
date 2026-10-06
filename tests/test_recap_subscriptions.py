"""Public recap access and email subscriptions without app startup jobs."""
import ast
import json
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import Mock, patch

from flask import Flask, abort, flash, redirect, request, session, url_for
from jinja2 import ChoiceLoader, DictLoader
import admin_functions as adminfx
import recap_subscriptions
from email_content import plain_text_fallback_from_html

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
                       plain_text_fallback_from_html=plain_text_fallback_from_html,
                       serialize_recap_list_entry=lambda row, base: dict(row),
                       _stats_db_path=adminfx.stats_db_path,
                       _is_owner_or_admin=lambda owner: session.get('username') == owner)
        tree = ast.parse((ROOT / 'stats.py').read_text())
        names = {'my_ai_recaps', 'inject_recap_subscription_token', 'subscribe_ai_recaps',
                 'send_ai_summary_messages', '_apply_ai_email_opt_out',
                 '_email_published_recap', '_publish_ai_recap', '_absolute_site_url'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'stats.py', 'exec'), self.ns)
        self.client = self.app.test_client()

    def test_public_directory_and_owner_controls(self):
        self.assertEqual(self.client.get('/ai-recaps/?page=bad').status_code, 200)
        self.admin.list_ai_recap_pages.assert_called_with(page=1, per_page=25, usernames=None)
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

    def test_manual_send_does_not_email_subscribers_again(self):
        recap_subscriptions.subscribe('fan@example.com')
        build = Mock(side_effect=lambda *args, **kwargs: args[3])
        send = Mock(return_value=(1, []))
        self.ns.update(_filter_ai_email_opt_outs=lambda values: values,
                       _ai_email_public_recipients=list, extend_ai_email_recipients=list,
                       build_ai_summary_message=build, send_messages_with_retry=send,
                       _ai_email_public_sent_count=lambda values, errors: len(values))
        self.assertEqual(self.ns['send_ai_summary_messages']('Recap', 'html', 'text', ['player@example.com']), (1, []))
        send.assert_called_once_with(['player@example.com'])
        cur = Mock()
        cur.fetchone.return_value = None
        self.ns['set_cur'] = lambda: cur
        self.ns['_apply_ai_email_opt_out']('FAN@example.com')
        self.assertEqual(recap_subscriptions.recipients([]), [])

    def publish(self, sender=None, payload=None):
        self.admin.get_ai_recap_page.return_value = None
        self.ns.update(json=json, EMAIL_PLACEHOLDER='{{EMAIL_PLACEHOLDER}}',
                       _refresh_instagram_slides=Mock(), log_activity=Mock(),
                       build_ai_summary_message=Mock(side_effect=lambda *args, **kwargs: args),
                       send_messages_with_retry=sender or Mock(return_value=(1, [])))
        with self.app.app_context():
            return self.ns['_publish_ai_recap'](
                payload or {'subject': 'A & B recap'}, 'fun', '', [1], username='creator')

    def test_publishing_notifies_subscribers_without_a_request_or_manual_send(self):
        recap_subscriptions.subscribe('fan@example.com')
        sender = Mock(return_value=(1, []))
        share_id = self.publish(sender)
        self.admin.insert_ai_recap_page.assert_called_once()
        sender.assert_called_once()
        subject, html, plain, recipient = sender.call_args.args[0][0]
        self.assertEqual(recipient, 'fan@example.com')
        self.assertIn('A &amp; B recap', html)
        self.assertIn(f'https://example.com/recap/{share_id}/', html)
        self.assertIn(f'https://example.com/recap/{share_id}/', plain)
        self.assertIn('/opt_out_ai_emails?email={{EMAIL_PLACEHOLDER}}', html)
        self.ns['log_activity'].assert_called_once()
        self.assertEqual(self.ns['log_activity'].call_args.args[0], 'Sent AI recap to subscribers')

    def test_subscriber_email_contains_full_recap_and_embedded_image_inputs(self):
        recap_subscriptions.subscribe('fan@example.com')
        html = ('<html><head><style>p {color: blue}</style></head><body>'
                '<h1>A &amp; B recap</h1><img src="https://example.com/hero.png">'
                '<p>Alex and Jesse won the final.</p><table><tr><td>21–18</td></tr></table>'
                '</body></html>')
        plain = 'A & B recap\n\nAlex and Jesse won the final.\n21–18'
        self.publish(payload=dict(subject='A & B recap', html_body=html,
                                  plain_text_body=plain,
                                  hero_image_url='https://example.com/hero.png',
                                  hero_image_path='/tmp/hero.png'))
        args = self.ns['build_ai_summary_message'].call_args
        self.assertIn(html.split('</body>')[0], args.args[1])
        self.assertTrue(args.args[2].startswith(plain))
        self.assertLess(args.args[1].index('View the recap online'), args.args[1].index('</body>'))
        self.assertNotIn('A new AI recap is ready', args.args[1])
        self.assertEqual(args.kwargs, dict(hero_image_url='https://example.com/hero.png',
                                          hero_image_path='/tmp/hero.png'))

    def test_html_only_recap_has_full_plain_text_alternative(self):
        recap_subscriptions.subscribe('fan@example.com')
        self.publish(payload=dict(subject='Recap', html_body='<p>Alex won 21–18.</p>'))
        args = self.ns['build_ai_summary_message'].call_args.args
        self.assertIn('Alex won 21–18.', args[2])
        self.assertIn('Unsubscribe:', args[2])

    def test_plain_text_only_recap_is_visible_and_escaped_in_html(self):
        recap_subscriptions.subscribe('fan@example.com')
        self.publish(payload=dict(subject='Recap', plain_text_body='Alex & Jesse won.\n21–18'))
        args = self.ns['build_ai_summary_message'].call_args.args
        self.assertIn('Alex &amp; Jesse won.<br>21–18', args[1])
        self.assertIn('Alex & Jesse won.\n21–18', args[2])

    def test_publishing_without_subscribers_does_not_send(self):
        sender = Mock()
        self.publish(sender)
        sender.assert_not_called()

    def test_email_failure_preserves_published_page_and_records_failure(self):
        recap_subscriptions.subscribe('fan@example.com')
        for sender in (Mock(side_effect=RuntimeError('SMTP unavailable')),
                       Mock(return_value=(0, ['fan@example.com: refused']))):
            self.assertTrue(self.publish(sender))
            self.assertEqual(self.ns['log_activity'].call_args.args[0],
                             'AI recap subscriber email failed')
            self.admin.insert_ai_recap_page.reset_mock()

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
