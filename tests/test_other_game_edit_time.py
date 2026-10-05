"""Other-game time corrections persist without moving ordinary score edits."""
import ast
from datetime import date, datetime
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from flask import Flask, flash, redirect, render_template, request, session, url_for
from jinja2 import ChoiceLoader, DictLoader
from create_other_database import BASE_UPDATE_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


class OtherGameEditTimeTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        columns = ', '.join(f'{column} TEXT' for column in BASE_UPDATE_COLUMNS)
        self.conn.execute(f'CREATE TABLE other_games (id INTEGER PRIMARY KEY, {columns})')
        self.original = '2026-10-05 15:31:42.123456'
        self.conn.execute('''INSERT INTO other_games
            (id, game_date, game_name, game_type, winner1, loser1, winner_score, loser_score)
            VALUES (921, ?, 'No jump', 'Volleyball', 'A', 'B', 21, 15)''', (self.original,))
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'))
        self.app.secret_key = 'test'
        self.app.jinja_loader = ChoiceLoader([DictLoader({
            'test_base.html': '{% block extra_css %}{% endblock %}{% block content %}{% endblock %}',
            'partials/page_header_actions.html': '',
        }), self.app.jinja_loader])
        self.app.context_processor(lambda: {'base_template': 'test_base.html'})
        self.app.add_url_rule('/other/<year>', 'edit_other_games', lambda year: '')
        namespace = dict(app=self.app, login_required=lambda f: f, request=request,
                         session=session, date=date, datetime=datetime, flash=flash,
                         redirect=redirect, url_for=url_for, render_template=render_template,
                         find_other_game=lambda game_id: self.conn.execute(
                             'SELECT * FROM other_games WHERE id=?', (game_id,)).fetchall(),
                         other_year_games=lambda year: [], all_other_players=lambda games: [],
                         other_game_names=lambda games: [], other_game_types=lambda games: [],
                         get_user_now=lambda: '2026-10-05 16:00:00',
                         adminfx=SimpleNamespace(snapshot_row=Mock(return_value=None)),
                         log_user_action=Mock(), log_activity=Mock())
        node = next(n for n in ast.parse((ROOT / 'stats.py').read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'update_other_game')
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'stats.py', 'exec'), namespace)
        self.client = self.app.test_client()
        self.form = dict(game_name='No jump', game_type='Volleyball', score_type='team',
                         winner1='A', loser1='B', winner_score='21', loser_score='16')

    def submit(self, **fields):
        with patch('database_functions.create_connection', return_value=self.conn), \
             patch('other_functions.game_name_requires_scores', return_value=True):
            return self.client.post('/edit_other_game/921/', data={**self.form, **fields})

    def row(self):
        return self.conn.execute('SELECT * FROM other_games WHERE id=921').fetchone()

    def test_editor_shows_saved_date_and_time(self):
        response = self.client.get('/edit_other_game/921/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'value="2026-10-05"', response.data)
        self.assertIn(b'value="15:31"', response.data)
        self.assertIn(b'name="game_time"', response.data)

    def test_correct_time_and_date(self):
        response = self.submit(game_date='2026-10-04', game_time='06:30')
        self.assertEqual(response.status_code, 302)
        row = self.row()
        self.assertEqual(row['game_date'], '2026-10-04 06:30:00')
        self.assertEqual(row['updated_at'], '2026-10-05 16:00:00')
        self.assertEqual(row['loser_score'], '16')

    def test_unchanged_or_omitted_controls_preserve_full_timestamp(self):
        for fields in ({}, dict(game_date='2026-10-05', game_time='15:31')):
            with self.subTest(fields=fields):
                self.assertEqual(self.submit(**fields).status_code, 302)
                self.assertEqual(self.row()['game_date'], self.original)

    def test_invalid_or_incomplete_date_time_does_not_save(self):
        for fields in (dict(game_date='2026-02-30', game_time='06:30'),
                       dict(game_date='2026-10-05', game_time='25:00'),
                       dict(game_date='2026-10-05'), dict(game_time='06:30'),
                       dict(game_date='', game_time='')):
            with self.subTest(fields=fields):
                response = self.submit(**fields)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.row()['game_date'], self.original)
                self.assertEqual(self.row()['loser_score'], '15')
        self.assertIn(b'value="06:30"', self.submit(game_date='bad', game_time='06:30').data)


if __name__ == '__main__':
    unittest.main()
