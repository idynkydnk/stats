import ast
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from bs4 import BeautifulSoup
from jinja2 import ChoiceLoader, DictLoader
from tests import test_ai_summary_games as game_fixtures
import content_safety


ROOT = Path(__file__).resolve().parents[1]


class AISummaryNavigationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'))
        self.app.secret_key = 'test'
        self.app.testing = True
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = str(Path(temporary.name) / 'stats.db')
        fixtures = game_fixtures.AISummaryGamesTests()
        fixtures.setUp()
        self.addCleanup(fixtures.tearDown)
        fixtures.insert('doubles', 'Sam', '2026-10-29', count=3)
        fixtures.conn.execute("UPDATE games SET comments='Parents visiting from Florida' WHERE id=1")
        fixtures.conn.commit()
        with sqlite3.connect(self.path) as conn:
            fixtures.conn.backup(conn)
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
            app=self.app, request=request, session=session, redirect=redirect, abort=abort,
            sqlite3=sqlite3, json=json, _stats_db_path=lambda: self.path,
            url_for=url_for, flash=flash, ai_jobs=self.jobs,
            login_required=lambda f: f, log_activity=Mock(),
            _normalize_image_mode=lambda mode: mode or 'none',
            render_template=render_template,
            _can_access_job=lambda job: job['username'] == session.get('username'),
        )
        tree = ast.parse((ROOT / 'stats.py').read_text())
        names = {'preview_ai_summary_with_prompt', 'inject_ai_summary_progress', '_render_select_ai_prompt',
                 'select_ai_style', '_ai_recap_edit_url', 'edit_ai_summary_job', 'ai_summary_job_status',
                 'api_ai_summary_job_status'}
        self.ns['api_login_required'] = lambda f: f
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

    def register_safety(self):
        content_safety.register_content_safety(self.app, SimpleNamespace(
            _stats_db_path=lambda: self.path, is_admin=lambda: False,
            _render_select_ai_prompt=self.ns['_render_select_ai_prompt'],
        ))

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

    def test_sharing_disabled_restores_long_prompt_and_selection_without_queuing(self):
        self.register_safety()
        prompt = 'Beuks and Kyle won. Lynch was offended.\n' * 250 + '</textarea><script>bad()</script>'
        form = {'game_ids': ['1', '2'], 'game_type': 'doubles', 'prompt_style': 'combined',
                'custom_prompt': prompt, 'image_mode': 'image'}
        with patch.object(content_safety, 'consent_state', return_value={'granted': False}):
            blocked = self.client.post('/preview_ai_summary_with_prompt/', data=form)
        self.assertEqual(blocked.status_code, 403)
        self.assertIn('no-store', blocked.headers['Cache-Control'])
        soup = BeautifulSoup(blocked.data, 'html.parser')
        self.assertEqual(soup.select_one('#custom-prompt-text').text, prompt)
        self.assertEqual([x['value'] for x in soup.select('#generate-form [name="game_ids"]')], ['1', '2'])
        self.assertEqual(soup.select_one('#image-mode')['value'], 'image')
        self.assertIn('AI sharing is turned off', soup.select_one('[role="alert"]').text)
        self.assertEqual(len(soup.select('.sr-review-game')), 2)
        self.assertNotIn(b'<script>bad()</script>', blocked.data)
        self.jobs.enqueue_job.assert_not_called()
        # Restoring sharing lets the original draft go through unchanged.
        retried = self.client.post('/preview_ai_summary_with_prompt/', data=form)
        self.assertEqual(retried.status_code, 302)
        self.assertEqual(self.jobs.enqueue_job.call_args.args[4], form['custom_prompt'])

    def test_reported_prompt_queues_unchanged_on_web_and_native_without_moderation(self):
        self.register_safety()
        prompt = (
            'Dom was late. he came with his wife and little baby girl in a stroller.\n\n'
            'kyle beat down mert and easton in 1v1 games before dom showed up.\n\n'
            'easton kept saying kyle was a wizard because of his shots.\n\n'
            'easton riding a bike down the strand with a giant boombox blasting music.\n\n'
            'kyle made sure the get easton a win at the end, even though they started down 7-1.'
        )
        data = {'game_ids': ['1', '2'], 'game_type': 'doubles', 'custom_prompt': prompt, 'image_mode': 'image'}
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}), patch('requests.post') as post:
            response = self.client.post('/preview_ai_summary_with_prompt/', data=data)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.jobs.enqueue_job.call_args.args[4], prompt)
            website_call = self.jobs.enqueue_job.call_args
            response = self.client.post('/api/ai/summary', json=data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.jobs.enqueue_job.call_args, website_call)
        self.assertEqual(self.jobs.enqueue_job.call_count, 2)
        post.assert_not_called()

    def test_block_during_generation_restores_draft(self):
        self.jobs.daemon_is_alive = lambda: False
        self.ns['build_doubles_email_payload'] = Mock(side_effect=content_safety.ContentSafetyError('Blocked output.'))
        response = self.client.post('/preview_ai_summary_with_prompt/', data={
            'game_ids': ['1', '2'], 'custom_prompt': 'My original prompt.', 'image_mode': 'image',
        })
        soup = BeautifulSoup(response.data, 'html.parser')
        self.assertEqual(soup.select_one('textarea').text, 'My original prompt.')
        self.assertIn('Blocked output.', soup.select_one('[role="alert"]').text)
        self.assertEqual(len(soup.select('.sr-review-game')), 2)

    def test_prompt_page_shows_selected_stats_games_and_comments_below_form(self):
        response = self.client.post('/select_ai_style/', data={'game_ids': ['1', '2'], 'game_type': 'doubles'})
        soup = BeautifulSoup(response.data, 'html.parser')
        self.assertEqual({x['data-game-id'] for x in soup.select('.sr-review-game')}, {'1', '2'})
        self.assertIn('Parents visiting from Florida', soup.select_one('.sr-review-comment').text)
        alex = next(row for row in soup.select('.sr-review-stats tbody tr') if 'Alex' in row.text)
        self.assertEqual([cell.text for cell in alex.select('td')][:3], ['2', '0', '100.0%'])
        self.assertLess(response.data.index(b'id="generate-form"'), response.data.index(b'id="selected-stats-title"'))

    def test_failed_background_job_reopens_original_draft_and_is_owner_only(self):
        self.jobs.get_job.return_value = dict(id=42, username='Sam', status='failed',
            game_type='doubles', game_ids_json='["1", "2"]', custom_prompt='Original background draft.',
            image_details='Green net.', image_mode='image', error='Content was blocked.')
        status = self.client.get('/api/ai_summary_job/42/')
        edit_url = status.json['edit_url']
        self.assertEqual(self.client.get('/ai_summary/job/42/').location, edit_url)
        with self.client.session_transaction() as state:
            state['ai_summary_job_id'] = 42
        response = self.client.get(edit_url)
        soup = BeautifulSoup(response.data, 'html.parser')
        self.assertEqual(soup.select_one('textarea').text, 'Original background draft.\n\nFor the picture: Green net.')
        self.assertEqual(len(soup.select('.sr-review-game')), 2)
        self.jobs.enqueue_job.assert_not_called()
        with self.client.session_transaction() as state:
            self.assertNotIn('ai_summary_job_id', state)
        with self.client.session_transaction() as state:
            state['username'] = 'Alex'
        self.assertEqual(self.client.get(edit_url).status_code, 403)
        self.jobs.get_job.return_value = None
        self.assertEqual(self.client.get(edit_url).status_code, 404)

    def test_prompt_review_renders_other_sports_and_ties(self):
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            fixtures = SimpleNamespace(conn=conn)
            game_fixtures.AISummaryGamesTests.insert(fixtures, 'vollis', 'Sam', '2026-10-29')
            game_fixtures.AISummaryGamesTests.insert(fixtures, 'other', 'Sam', '2026-10-29')
            conn.execute('ALTER TABLE other_games ADD COLUMN is_tie INTEGER DEFAULT 0')
            conn.execute('UPDATE other_games SET is_tie=1, winner_score=10, loser_score=10')
        for kind in ('vollis', 'other'):
            response = self.client.post('/select_ai_style/', data={'game_ids': '1', 'game_type': kind})
            soup = BeautifulSoup(response.data, 'html.parser')
            self.assertEqual(len(soup.select('.sr-review-game')), 1)
            self.assertIn('Alex', soup.select_one('.sr-review-game').text)
            if kind == 'other':
                self.assertIn('Tie', soup.select_one('.sr-review-game').text)
                self.assertFalse(soup.select('.sr-review-team.winner'))

    def test_selection_load_error_does_not_erase_prompt(self):
        for error in (sqlite3.OperationalError('Offline'), TypeError('Incomplete game scores')):
            with patch('ai_summary_games.load_ai_summary_selection', side_effect=error):
                with self.app.test_request_context('/'), self.assertLogs(self.app.logger, level='ERROR'):
                    page = self.ns['_render_select_ai_prompt'](['1'], 'doubles', custom_prompt='Keep this draft.')
            self.assertIn('Keep this draft.', page)
            self.assertIn('could not be loaded', page)

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

    def test_failed_draft_stays_reachable_and_template_can_poll_all_states(self):
        for status in ('pending', 'completed', 'failed'):
            with self.subTest(status=status), self.app.test_request_context('/'):
                session.update(username='Sam', logged_in=True, ai_summary_job_id=42)
                self.jobs.get_job.return_value.update(status=status, share_id='recap-42')
                context = self.ns['inject_ai_summary_progress']()
                html = self.app.jinja_env.get_template('partials/ai_summary_progress.html').render(**context)
                self.assertIn('Generating your recap', html)
                self.assertIn('Open recap', html)
                if status == 'failed':
                    self.assertEqual(context['ai_summary_progress_job']['edit_url'], '/ai_summary/job/42/edit/')
                    self.assertIn('Edit prompt and try again', html)
                self.assertEqual('ai_summary_job_id' in session, status != 'completed')


if __name__ == '__main__':
    unittest.main()
