"""Selected seasons constrain flyer previews, queued images, and saved remakes."""
import ast
from pathlib import Path
import secrets
import sqlite3
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from flask import render_template
from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader

import email_content as content
import flyer_functions as flyers
from private_accounts import account_for_user, ai_account_context, provision_database
from tests import test_personal_flyer_access as flyer_fixtures

ROOT = Path(__file__).resolve().parents[1]


class FlyerSeasonTests(unittest.TestCase):
    register = flyer_fixtures.PersonalFlyerAccessTests.register

    def setUp(self):
        flyer_fixtures.PersonalFlyerAccessTests.setUp(self)
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''DROP TABLE games;
                CREATE TABLE games(id INTEGER PRIMARY KEY, game_date TEXT, winner1 TEXT, winner2 TEXT,
                    winner_score INTEGER, loser1 TEXT, loser2 TEXT, loser_score INTEGER,
                    entered_by TEXT, division TEXT DEFAULT 'open');
                CREATE TABLE vollis_games(id INTEGER PRIMARY KEY, game_date TEXT, winner TEXT,
                    winner_score INTEGER, loser TEXT, loser_score INTEGER, entered_by TEXT);
                CREATE TABLE other_games(id INTEGER PRIMARY KEY, game_date TEXT, game_name TEXT,
                    game_type TEXT, winner1 TEXT, loser1 TEXT, winner_score INTEGER, loser_score INTEGER,
                    entered_by TEXT, is_tie INTEGER DEFAULT 0);''')
        self.headers = self.register(self.a, 'alice')
        self.bob_headers = self.register(self.b, 'bob')
        self.own_path = provision_database(self.path, account_for_user(self.path, 'alice')['id'])
        self.defaults = dict(name='Winter league', start_date='2025-12-31', end_date='2026-01-02',
                             minimum_mode='fixed', minimum_games=10)
        self.payload = dict(players=['Alex', 'New Player'], game_type='doubles',
                            event_date='2026-10-12', event_time='17:00', location='Beach')
        self.game(1, '2025-12-30')
        self.game(2, '2025-12-31 00:00:00')
        self.game(3, '2026-01-02 23:59:59', winner='Cam', loser='Alex')
        self.game(4, '2026-01-03')
        self.game(5, '2026-01-01', owner='bob')
        self.game(1, '2026-01-01', path=self.path)
        self.season = self.create_season()

    def game(self, ident, day, winner='Alex', loser='Cam', owner='alice', path=None, division='open'):
        with sqlite3.connect(path or self.own_path) as conn:
            conn.execute('INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (ident, day, winner, 'Bea', 21, loser, 'Dee', 15, owner, division))

    def create_season(self, client=None, headers=None, **changes):
        response = (client or self.a).post('/api/seasons', headers=headers or self.headers,
                                          json=dict(self.defaults, **changes))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json['season']

    def preview(self, **changes):
        payload = dict(self.payload, season_id=self.season['id'], **changes)
        with patch('email_content._clean_player_lines_block',
                   return_value=('Alex and New Player', 2, payload['players'])):
            return self.a.post('/api/flyer_prompts/', headers=self.headers, json=payload)

    def test_preview_uses_only_season_dates_owner_and_fresh_ratings(self):
        from stat_functions import _calculate_trueskill_from_games
        with sqlite3.connect(self.own_path) as conn:
            rows = conn.execute('SELECT * FROM games WHERE id IN (2,3) ORDER BY game_date').fetchall()
        rating = next(row['rating'] for row in _calculate_trueskill_from_games(rows) if row['player'] == 'Alex')
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.json)
        prompt = response.json['scene_prompt']
        self.assertIn('Winter league STATS · 2025-12-31 – 2026-01-02', prompt)
        self.assertIn(f'Alex (display name: Alex):\nRating: {rating:.1f}\nWins: 1\nLosses: 1\nWin %: 50%', prompt)
        self.assertIn('New Player (display name: New Player):\nRating: —\nWins: 0\nLosses: 0\nWin %: —', prompt)
        self.assertNotIn('[CURRENT-YEAR DOUBLES STATS]', prompt)

    def test_choices_preserved_through_forms_queue_and_native_api(self):
        private = self.create_season(self.b, self.bob_headers, name='Bob private')
        shared = self.create_season(self.b, self.bob_headers, name='Bob shared')
        self.b.post('/api/seasons/' + shared['id'] + '/share', headers=self.bob_headers)
        choices = self.a.get('/create_flyer/').json['seasons']
        self.assertEqual({s['id'] for s in choices}, {self.season['id'], shared['id']})
        payload = dict(self.payload, season_id=self.season['id'])
        response = self.a.post('/create_flyer/roster/', data=payload)
        self.assertEqual(response.json['flyer']['season_id'], self.season['id'])
        response = self.a.post('/create_flyer/', data=payload)
        self.assertEqual(response.json['season_id'], self.season['id'])
        for path, kwargs, expected in (
            ('/create_flyer/generate/', dict(data=payload), 302),
            ('/api/flyers', dict(json=payload, headers=self.headers), 201),
        ):
            response = self.a.post(path, **kwargs)
            self.assertEqual(response.status_code, expected, response.text)
            self.assertEqual(self.service.ai_jobs.enqueue_flyer_job.call_args.args[1]['season_id'], self.season['id'])
        for invalid in (private['id'], 'deleted-season', ['bad-id']):
            response = self.a.post('/api/flyers', headers=self.headers, json=dict(payload, season_id=invalid))
            self.assertEqual(response.status_code, 400, response.text)
        with patch('email_content._clean_player_lines_block', return_value=('Alex', 1, ['Alex'])):
            response = self.a.post('/api/flyer_prompts/', json=dict(payload, season_id=shared['id']))
            self.assertEqual(response.status_code, 200, response.text)
            self.b.delete('/api/seasons/' + shared['id'] + '/share', headers=self.bob_headers)
            response = self.a.post('/api/flyer_prompts/', json=dict(payload, season_id=shared['id']))
            self.assertEqual(response.status_code, 400, response.text)

    def test_real_form_renders_selected_and_unavailable_seasons_without_defaulting(self):
        self.app.jinja_loader = ChoiceLoader([
            DictLoader({'test-base.html': '{% block content %}{% endblock %}{% block extra_js %}{% endblock %}',
                        'partials/page_header_actions.html': '', 'partials/ai_generate_loading.html': '',
                        'partials/player_photo_modal.html': ''}),
            FileSystemLoader(str(ROOT / 'templates')),
        ])
        self.namespace['render_template'] = lambda name, **kw: render_template(name, base_template='test-base.html', **kw)
        self.namespace['build_ai_recap_roster_cards'] = lambda names: [dict(name=name) for name in names]
        payload = dict(self.payload, season_id=self.season['id'])
        response = self.a.post('/create_flyer/', data=payload)
        soup = BeautifulSoup(response.data, 'html.parser')
        self.assertEqual(soup.select_one('#season_id option[selected]')['value'], self.season['id'])
        response = self.a.post('/create_flyer/roster/', data=payload)
        soup = BeautifulSoup(response.data, 'html.parser')
        self.assertEqual(soup.select_one('input[name=season_id]')['value'], self.season['id'])
        self.a.delete('/api/seasons/' + self.season['id'], headers=self.headers)
        response = self.a.post('/create_flyer/generate/', data=payload)
        soup = BeautifulSoup(response.data, 'html.parser')
        self.assertEqual(soup.select_one('#season_id option[selected]')['value'], self.season['id'])
        self.service.ai_jobs.enqueue_flyer_job.assert_not_called()

    def test_worker_refreshes_stale_custom_prompt_and_persists_season(self):
        tree = ast.parse((ROOT / 'stats.py').read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {'_generate_and_publish_flyer', '_publish_flyer_page'}]
        self.namespace['secrets'] = secrets
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'stats.py', 'exec'), self.namespace)
        payload = dict(self.payload, season_id=self.season['id'], scene_prompt=(
            'Sunny beach poster.\n[CURRENT-YEAR DOUBLES STATS]Old year stats[/CURRENT-YEAR DOUBLES STATS]\n'
            '[SEASON STATS]Old season stats[/SEASON STATS]'))
        with patch('email_content.require_ai_api_key', return_value='test-key'), \
             patch('email_content._image_labels_for_players', return_value={}), \
             patch('email_content._reference_parts_from_uploaded_photos', return_value=([], ['Alex'])), \
             patch('email_content._generate_image_bytes', return_value=(b'image', 'image/png')) as generate, \
             patch('email_content._normalize_image_bytes_to_aspect', return_value=(b'image', 'image/png')), \
             patch('email_content._save_email_image', return_value=('/image.png', '/tmp/image.png')), \
             patch('ai_library.after_publish'):
            result = self.run_job('alice', payload)
        self.assertTrue(result['success'], result)
        prompt = generate.call_args.args[0]
        self.assertIn('Sunny beach poster.', prompt)
        self.assertIn('Wins: 1\nLosses: 1\nWin %: 50%', prompt)
        self.assertNotIn('Old year stats', prompt)
        self.assertNotIn('Old season stats', prompt)
        self.assertNotIn('[CURRENT-YEAR DOUBLES STATS]', prompt)
        self.assertEqual(prompt.count('[SEASON STATS]'), 1)
        saved = flyers.get_flyer_page(result['share_id'])
        self.assertEqual(saved['season_id'], self.season['id'])

    def test_unavailable_season_never_falls_back_during_worker_generation(self):
        self.a.delete('/api/seasons/' + self.season['id'], headers=self.headers)
        with ai_account_context(self.app, self.path, 'alice'), \
             patch('email_content._flyer_current_year_stats_block') as yearly:
            with self.assertRaisesRegex(ValueError, 'no longer available'):
                content._refresh_flyer_stats('Sunny beach', ['Alex'], 'doubles', season_id=self.season['id'])
        yearly.assert_not_called()

    def test_empty_season_and_other_formats_do_not_read_yearly_stats(self):
        with sqlite3.connect(self.own_path) as conn:
            conn.execute("INSERT INTO vollis_games VALUES (1,'2026-01-01','Alex',21,'Cam',15,'alice')")
            conn.execute("INSERT INTO other_games VALUES (1,'2026-01-01','Sequence','Board games','Alex','Cam',0,0,'alice',1)")
        with patch('email_content._flyer_current_year_stats_block') as yearly:
            vollis = self.preview(game_type='vollis').json['scene_prompt']
            self.assertIn('Game format: Vollis', vollis)
            self.assertIn('Wins: 1\nLosses: 0\nWin %: 100%', vollis)
            other = self.preview(game_type='other', game_name='Sequence').json['scene_prompt']
            self.assertIn('Rating: —\nWins: 0\nLosses: 0\nTies: 1\nWin %: 0%', other)
            self.assertNotIn('Game format: Doubles', other)
            self.a.put('/api/seasons/' + self.season['id'], headers=self.headers,
                       json=dict(self.defaults, start_date='2027-01-01', end_date='2027-01-02'))
            empty = self.preview().json['scene_prompt']
            self.assertIn('Rating: —\nWins: 0\nLosses: 0\nWin %: —', empty)
        yearly.assert_not_called()


if __name__ == '__main__':
    unittest.main()
