import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from flask import Flask, flash, redirect, request, session, url_for


ROOT = Path(__file__).resolve().parents[1]


class AISummaryNavigationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'))
        self.app.secret_key = 'test'
        self.app.add_url_rule('/', endpoint='index', view_func=lambda: 'Stats')
        self.app.add_url_rule('/ai_summary/', endpoint='ai_summary', view_func=lambda: 'Select games')
        self.jobs = SimpleNamespace(
            enqueue_job=Mock(return_value=42), daemon_is_alive=lambda: True,
            get_job=Mock(return_value=dict(id=42, username='Sam', status='pending')),
        )
        self.ns = dict(
            app=self.app, request=request, session=session, redirect=redirect,
            url_for=url_for, flash=flash, ai_jobs=self.jobs,
            login_required=lambda f: f, log_activity=Mock(),
            _normalize_image_mode=lambda mode: mode or 'none',
            _can_access_job=lambda job: job['username'] == session.get('username'),
        )
        tree = ast.parse((ROOT / 'stats.py').read_text())
        names = {'preview_ai_summary_with_prompt', 'inject_ai_summary_progress'}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'stats.py', 'exec'), self.ns)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(username='Sam', logged_in=True)

    def test_each_summary_mode_returns_home_with_pending_job(self):
        for mode in ('none', 'image', 'animation'):
            with self.subTest(mode=mode):
                response = self.client.post('/preview_ai_summary_with_prompt/', data={
                    'game_ids': ['1', '2'], 'image_mode': mode,
                    'animation_player': 'Sam', 'animation_details': 'Wave',
                })
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, '/')
                with self.client.session_transaction() as state:
                    self.assertEqual(state['ai_summary_job_id'], 42)
                self.assertEqual(self.jobs.enqueue_job.call_args.kwargs['image_mode'], mode)

    def test_invalid_selection_does_not_queue_or_return_home(self):
        response = self.client.post('/preview_ai_summary_with_prompt/', data={})
        self.assertEqual(response.location, '/ai_summary/')
        self.jobs.enqueue_job.assert_not_called()

    def test_status_only_shown_for_accessible_jobs(self):
        with self.app.test_request_context('/'):
            session.update(username='Alex', logged_in=True, ai_summary_job_id=42)
            self.assertEqual(self.ns['inject_ai_summary_progress'](), {})
            self.assertNotIn('ai_summary_job_id', session)
        with self.app.test_request_context('/'):
            session.update(username='Sam', logged_in=True, ai_summary_job_id=42)
            context = self.ns['inject_ai_summary_progress']()
            self.assertEqual(context['ai_summary_progress_job']['id'], 42)
            self.assertNotIn('username', context['ai_summary_progress_job'])
            self.assertEqual(session['ai_summary_job_id'], 42)

    def test_finished_job_shown_once_and_template_can_poll_all_states(self):
        for status in ('pending', 'completed', 'failed'):
            with self.subTest(status=status), self.app.test_request_context('/'):
                session.update(username='Sam', logged_in=True, ai_summary_job_id=42)
                self.jobs.get_job.return_value.update(status=status, share_id='recap-42')
                context = self.ns['inject_ai_summary_progress']()
                html = self.app.jinja_env.get_template('partials/ai_summary_progress.html').render(**context)
                self.assertIn('Generating your recap', html)
                self.assertIn('Open recap', html)
                self.assertEqual('ai_summary_job_id' in session, status == 'pending')


if __name__ == '__main__':
    unittest.main()
