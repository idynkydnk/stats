"""Custom app formats survive saving, browsing, and account source selection."""
from contextlib import closing
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import one_on_one as singles
from ios_api import register_ios_api
from tests import test_one_on_one as singles_tests


class CustomOneOnOneTests(unittest.TestCase):
    add_other = singles_tests.OneOnOneTests.add_other

    def setUp(self):
        singles_tests.OneOnOneTests.setUp(self)
        with sqlite3.connect(self.path) as conn:
            conn.execute('ALTER TABLE other_games ADD COLUMN entered_by TEXT')
        self.service = SimpleNamespace(
            note_user_presence=Mock(), _new_game_location=lambda value: value,
            browse_game_year=lambda *args, **kwargs: 'All years',
            _remember_game_location=Mock(), clear_stats_cache=Mock(), log_activity=Mock(),
            adminfx=SimpleNamespace(snapshot_last_row=lambda _: {'id': self.last_id()}),
        )
        for patcher in (
            patch('ios_api._S', return_value=self.service),
            patch('ios_api._ensure_deleted_table'),
            patch('other_functions.create_connection', side_effect=lambda _: sqlite3.connect(self.path)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app.secret_key = 'test'
        self.app.testing = True
        register_ios_api(self.app)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(logged_in=True, username='Kyle')
        self.fields = dict(game_name='Back line lefty', game_type='Volleyball',
                           winners=['A'], losers=['B'], score_type='team',
                           winner_score=21, loser_score=15,
                           game_date='2026-10-20 10:00:00', one_on_one=True)

    def last_id(self):
        with sqlite3.connect(self.path) as conn:
            return conn.execute('SELECT max(id) FROM other_games').fetchone()[0]

    def test_create_then_browse_and_reuse_custom_format(self):
        response = self.client.post('/api/other/games', json=self.fields)
        self.assertEqual(response.status_code, 201, response.json)
        catalog = self.client.get('/api/other/game-types').json
        self.assertIn('Back line lefty', catalog['one_on_one_formats'])
        self.assertEqual(catalog['entry_defaults']['back line lefty']['winner_count'], 1)
        with self.app.test_request_context('/stats?format=Back+line+lefty'):
            self.assertEqual(singles.selected_format(), 'Back line lefty')
            rows = singles.games('All years', singles.selected_format())
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]['winner'], rows[0]['loser_score']), ('A', 15))
            self.assertIn('Back line lefty', singles.formats_by_total_games())
            self.assertEqual(singles.ratings(rows)['rated_games'], 1)
        response = self.client.post('/api/other/games', json=dict(self.fields, game_name='  BACK LINE lefty '))
        self.assertEqual(response.status_code, 201, response.json)
        with self.app.test_request_context('/stats'):
            self.assertEqual(singles.formats_by_total_games().count('Back line lefty'), 1)
            self.assertEqual(len(singles.games('All years', 'Back line lefty')), 2)

    def test_invalid_sides_types_and_existing_other_names_do_not_register(self):
        for changes in ({'winners': ['A', 'C']}, {'losers': ['a']},
                        {'game_type': 'Cards'}, {'game_name': 'No jump'}, {'game_name': ' '}):
            response = self.client.post('/api/other/games', json=dict(self.fields, **changes))
            self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(self.last_id(), 9)
        self.assertEqual(singles.custom_formats(), {})

    def test_ordinary_other_entry_does_not_become_a_singles_format(self):
        response = self.client.post('/api/other/games', json=dict(self.fields, one_on_one=False))
        self.assertEqual(response.status_code, 201, response.json)
        self.assertIsNone(singles.canonical_format('Back line lefty'))
        self.assertEqual(len(singles.games()), 4)

    def test_failed_save_rolls_back_new_format(self):
        with patch('other_functions.create_other_game', side_effect=ValueError('save failed')):
            response = self.client.post('/api/other/games', json=self.fields)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(singles.custom_formats(), {})
        self.assertEqual(self.last_id(), 9)

    def test_custom_formats_follow_selected_account_sources(self):
        from account_stats_views import build_stats_view
        own = str(Path(self.tmp.name) / 'own.db')
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(own)) as target:
            source.backup(target)
        self.client.post('/api/other/games', json=self.fields)
        with patch('account_stats_views._database_path', return_value=self.path):
            for enabled in (False, True):
                snapshot = build_stats_view(self.path, own, [dict(enabled=enabled, number=1)])
                try:
                    with closing(sqlite3.connect(snapshot)) as conn:
                        self.assertEqual('back line lefty' in singles._custom_formats(conn), enabled)
                finally:
                    Path(snapshot).unlink()
        with closing(sqlite3.connect(own)) as conn:
            self.assertEqual(singles._custom_formats(conn), {})


if __name__ == '__main__':
    unittest.main()
