import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from bs4 import BeautifulSoup
from jinja2 import ChoiceLoader, DictLoader


ROOT = Path(__file__).resolve().parents[1]


class AISummaryNavigationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'))
        self.app.secret_key = 'test'
        self.app.add_url_rule('/', endpoint='index', view_func=lambda: 'Stats')
        self.app.add_url_rule('/ai_summary/', endpoint='ai_summary', view_func=lambda: 'Select games')
        self.app.add_url_rule('/select_ai_prompt/', endpoint='select_ai_prompt', view_func=lambda: 'Select players')
        self.app.jinja_loader = ChoiceLoader([
            DictLoader({'test_base.html': '{% block content %}{% endblock %}{% block extra_js %}{% endblock %}',
                        'partials/page_header_actions.html': ''}),
            self.app.jinja_loader,
        ])
        self.jobs = SimpleNamespace(
            enqueue_job=Mock(return_value=42), daemon_is_alive=lambda: True,
            get_job=Mock(return_value=dict(id=42, username='Sam', status='pending')),
        )
        self.ns = dict(
            app=self.app, request=request, session=session, redirect=redirect,
            url_for=url_for, flash=flash, ai_jobs=self.jobs,
            login_required=lambda f: f, log_activity=Mock(),
            _normalize_image_mode=lambda mode: mode or 'none',
            render_template=render_template,
            _can_access_job=lambda job: job['username'] == session.get('username'),
        )
        tree = ast.parse((ROOT / 'stats.py').read_text())
        names = {'preview_ai_summary_with_prompt', 'inject_ai_summary_progress', '_render_select_ai_prompt'}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'stats.py', 'exec'), self.ns)
        service = SimpleNamespace(ai_jobs=self.jobs, log_activity=Mock(),
                                  _normalize_image_mode=self.ns['_normalize_image_mode'])
        self.ns.update(_S=lambda: service, jsonify=jsonify, api_login_required=lambda f: f)
        api = ast.parse((ROOT / 'ios_api.py').read_text())
        nodes = [node for node in ast.walk(api) if isinstance(node, ast.FunctionDef)
                 and node.name == 'api_ai_summary_json']
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'ios_api.py', 'exec'), self.ns)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(username='Sam', logged_in=True)
        self.app.context_processor(lambda: {'base_template': 'test_base.html'})

    def test_single_prompt_form_submits_blank_and_combined_requests_to_worker(self):
        for prompt in ('', 'Keep it funny. For the picture, use a green Martha’s net.'):
            with self.subTest(prompt=prompt), self.app.test_request_context('/'):
                page = self.ns['_render_select_ai_prompt']([1, 2], 'doubles', custom_prompt=prompt)
                soup = BeautifulSoup(page, 'html.parser')
                form = soup.select_one('#generate-form')
                areas = form.select('textarea')
                self.assertEqual(len(areas), 1)
                self.assertEqual(areas[0]['name'], 'custom_prompt')
                self.assertEqual(areas[0].text, prompt)
                self.assertIn('For the picture', areas[0]['placeholder'])
                self.assertFalse(areas[0].has_attr('required'))
                self.assertFalse(any(button.has_attr('disabled') for button in form.select('button[type="submit"]')))
                data = {'game_ids': ['1', '2'], 'game_type': 'doubles', 'image_mode': 'image',
                        'prompt_style': form.select_one('[name="prompt_style"]')['value'],
                        'custom_prompt': areas[0].text}
                response = self.client.post(form['action'], data=data)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(self.jobs.enqueue_job.call_args.args[3:5], ('combined', prompt))
                self.assertEqual(self.jobs.enqueue_job.call_args.kwargs['image_details'], '')

    def test_recoverable_error_preserves_and_escapes_prompt_and_legacy_picture_details(self):
        with self.app.test_request_context('/'):
            page = self.ns['_render_select_ai_prompt'](
                [1], 'doubles', prompt_style='custom', custom_prompt='Funny </textarea><script>bad()</script>',
                image_details='A green net.', error='Try again.',
            )
        soup = BeautifulSoup(page, 'html.parser')
        area = soup.select_one('#custom-prompt-text')
        self.assertEqual(area.text, 'Funny </textarea><script>bad()</script>\n\nFor the picture: A green net.')
        self.assertEqual(len(soup.select('textarea')), 1)
        self.assertNotIn('<script>bad()</script>', page)

    def test_native_and_website_queue_the_same_combined_prompt(self):
        for prompt in ('', 'Keep it funny. For the picture, use a green net.'):
            for mode in ('none', 'image'):
                data = {'game_ids': ['1', '2'], 'game_type': 'doubles',
                        'prompt_style': 'combined', 'custom_prompt': prompt, 'image_mode': mode}
                self.client.post('/preview_ai_summary_with_prompt/', data=data)
                website_call = self.jobs.enqueue_job.call_args
                response = self.client.post('/api/ai/summary', json=data)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.jobs.enqueue_job.call_args, website_call)

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
