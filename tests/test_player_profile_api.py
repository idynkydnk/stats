"""Single-profile reads avoid roster/history work and preserve source boundaries."""
import ast
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import jsonify, request, url_for
from ios_api import _abs
from player_functions import get_player_profile_by_name
from private_accounts import account_for_user, connect_data, provision_database
from tests import test_private_accounts as fixtures

ROOT = Path(__file__).resolve().parents[1]


class PlayerProfileTests(unittest.TestCase):
    register = fixtures.PrivateAccountTests.register

    def setUp(self):
        fixtures.PrivateAccountTests.setUp(self)
        with sqlite3.connect(self.path) as conn:
            for column in ('email', 'date_of_birth', 'height', 'notes', 'created_at', 'updated_at',
                           'photo_path', 'full_body_photo_path', 'nickname', 'full_body_photo_paths',
                           'ai_image_traits', 'face_photo_focus', 'full_body_photo_crops', 'ai_image_path'):
                conn.execute(f'ALTER TABLE players ADD COLUMN {column} TEXT')
            conn.execute("UPDATE players SET nickname='Shared', email='shared@example.test'")
        source = ast.parse((ROOT / 'stats.py').read_text())
        card_node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'build_player_list_cards')
        ns = dict(url_for=url_for, _cache_busted_static_url=lambda path: '/static/' + path if path else None)
        exec(compile(ast.Module(body=[card_node], type_ignores=[]), 'stats.py', 'exec'), ns)
        service = SimpleNamespace(build_player_list_cards=ns['build_player_list_cards'], EMAIL_SITE_BASE_URL='https://stats.example')
        tree = ast.parse((ROOT / 'ios_api.py').read_text())
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'api_player_profile')
        api_ns = dict(app=self.app, request=request, jsonify=jsonify, _abs=_abs, _S=lambda: service)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'ios_api.py', 'exec'), api_ns)
        for patcher in (
            patch('player_functions.set_cur', side_effect=lambda: connect_data(self.path).cursor()),
            patch('player_functions._players_db_connection', side_effect=lambda: connect_data(self.path)),
            patch('player_functions.get_all_players', side_effect=AssertionError('Loaded entire roster')),
            patch('ios_api._S', return_value=service),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def profile(self, client, name, headers=None):
        return client.get('/api/player-profile', query_string={'name': name}, headers=headers)

    def test_profile_fields_without_history_and_missing_names(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("""UPDATE players SET full_name='José Example', photo_path='uploads/face.jpg',
                ai_image_path='uploads/ai.png', date_of_birth='1990-04-01', height='180',
                ai_image_traits='["glasses"]', face_photo_focus='25,40,2'""")
        response = self.profile(self.a, '  jose example  ', {'Authorization': 'Bearer shared-token'})
        self.assertEqual(response.status_code, 200)
        p = response.json['player']
        self.assertEqual((p['name'], p['nickname'], p['email']), ('José Example', 'Shared', 'shared@example.test'))
        self.assertEqual((p['dateOfBirth'], p['height']), ('1990-04-01', '180'))
        self.assertEqual(p['aiImageTraits'], ['glasses'])
        self.assertEqual(p['faceFocus'], {'x': 25.0, 'y': 40.0, 'z': 2.0})
        self.assertTrue(p['photoUrl'].startswith('https://'))
        self.assertTrue(p['aiImageUrl'].endswith('/static/uploads/ai.png'))
        self.assertNotIn('games', p)
        self.assertNotIn('firstGame', p)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.profile(self.a, 'Nobody').json, {'player': None})
        self.assertEqual(self.profile(self.a, ' ').status_code, 400)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM players').fetchone()[0], 1)

    def test_exact_match_precedes_accent_fallback_and_closes_connection(self):
        with sqlite3.connect(self.path) as conn:
            conn.executemany('INSERT INTO players (full_name) VALUES (?)', [('José',), ('Jose',)])
        conn = sqlite3.connect(self.path)
        with patch('player_functions.set_cur', return_value=conn.cursor()):
            self.assertEqual(get_player_profile_by_name('Jose')[1], 'Jose')
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute('SELECT 1')

    def test_owned_combined_and_disabled_sources(self):
        own = self.register(self.a, 'alice')
        bob_headers = self.register(self.b, 'bob')
        alice = account_for_user(self.path, 'alice')
        bob = account_for_user(self.path, 'bob')
        with sqlite3.connect(provision_database(self.path, alice['id'])) as conn:
            conn.execute("INSERT INTO players (full_name, nickname) VALUES ('Alice player', 'Only Alice')")
        with sqlite3.connect(provision_database(self.path, bob['id'])) as conn:
            conn.execute("INSERT INTO players (full_name) VALUES ('Bob private')")
        combined = {**own, 'X-Stats-Combined': '1'}
        self.assertIsNone(self.profile(self.a, 'Shared player', own).json['player'])
        self.assertEqual(self.profile(self.a, 'Shared player', combined).json['player']['nickname'], 'Shared')
        self.assertEqual(self.profile(self.a, 'Alice player', own).json['player']['nickname'], 'Only Alice')
        self.assertIsNone(self.profile(self.b, 'Alice player', bob_headers).json['player'])
        self.assertIsNone(self.profile(self.a, 'Bob private', combined).json['player'])
        self.a.put('/api/account/stats-sources', headers=own, json={'owner': 'kyle', 'enabled': False})
        self.assertIsNone(self.profile(self.a, 'Shared player', combined).json['player'])
        bad = self.profile(self.app.test_client(), 'Shared player', {'Authorization': 'Bearer invalid', 'X-Stats-Account-Required': '1'})
        self.assertIn(bad.status_code, (401, 403))
        preview = self.profile(self.app.test_client(), 'Shared player', {'X-Stats-Preview': '1'})
        self.assertEqual(preview.status_code, 403)
