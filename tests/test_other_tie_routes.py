"""Tie entry survives web/API save and edit without inventing wins or losses."""
from datetime import datetime
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask
import ios_api
from create_other_database import BASE_INSERT_COLUMNS
import test_other_game_edit_time as edit_tests
import test_saved_game_popup as popup_tests


class OtherTieAPITests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        columns = ', '.join(f'{name}' for name in BASE_INSERT_COLUMNS)
        self.conn.execute(f'CREATE TABLE other_games (id INTEGER PRIMARY KEY, {columns})')
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.app.testing = True
        with patch('ios_api._ensure_deleted_table'):
            ios_api.register_ios_api(self.app)
        self.server = SimpleNamespace(
            note_user_presence=Mock(), _new_game_location=lambda location: location,
            _remember_game_location=Mock(), clear_stats_cache=Mock(),
            _editable_game_ids=lambda table, ids: set(ids), log_activity=Mock(),
            get_user_now=lambda: '2026-10-21 14:00:00',
            player_avatar_context=lambda name: {},
            adminfx=SimpleNamespace(snapshot_last_row=lambda kind: self.row(),
                                    snapshot_row=lambda kind, id: self.row()))
        for item in (
            patch('ios_api._S', return_value=self.server),
            patch('other_functions.create_connection', return_value=self.conn),
            patch('database_functions.create_connection', return_value=self.conn),
            patch('other_functions.set_cur', side_effect=self.conn.cursor),
        ):
            item.start()
            self.addCleanup(item.stop)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(logged_in=True, username='tester')
        self.payload = dict(game_name='Sequence', game_type='Board games',
                            game_date='2026-10-21 13:00:00', score_type='team',
                            winners=['A', 'B'], losers=['C', 'D'],
                            winner_score=1, loser_score=1, is_tie=True)

    def row(self):
        row = self.conn.execute('SELECT * FROM other_games ORDER BY id DESC LIMIT 1').fetchone()
        return dict(row) if row else None

    def test_sequence_one_one_round_trip_and_player_stats(self):
        response = self.client.post('/api/other/games', json=self.payload)
        self.assertEqual(response.status_code, 201, response.data)
        game_id = response.get_json()['id']
        game = self.client.get(f'/api/other/games/{game_id}').get_json()
        self.assertIs(game['is_tie'], True)
        self.assertEqual((game['winner_score'], game['loser_score']), (1, 1))
        for name in ['A', 'B', 'C', 'D']:
            stats = self.client.get(f'/api/other/players/{name}').get_json()
            self.assertEqual({k: stats['stats'][k] for k in ('wins', 'losses', 'ties', 'games')},
                             dict(wins=0, losses=0, ties=1, games=1))
            self.assertTrue(all(opponent['ties'] == 1 for opponent in stats['opponents']))
        # An older client editing a comment must retain the explicit outcome.
        payload = dict(self.payload, comment='Finished level')
        del payload['is_tie']
        self.assertEqual(self.client.put(f'/api/other/games/{game_id}', json=payload).status_code, 200)
        self.assertEqual(self.row()['is_tie'], 1)
        self.assertEqual(self.row()['comment'], 'Finished level')
        response = self.client.put(f'/api/other/games/{game_id}', json=dict(self.payload, is_tie=False, winner_score=2))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.row()['is_tie'], 0)

    def test_volleyball_and_contradictory_tie_scores_rejected_without_write(self):
        for fields in [dict(game_type='Volleyball'), dict(game_type=' VOLLEYBALL '),
                       dict(winner_score=2), dict(is_tie='banana')]:
            with self.subTest(fields=fields):
                response = self.client.post('/api/other/games', json=dict(self.payload, **fields))
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIsNone(self.row())

    def test_edit_cannot_convert_saved_tie_into_volleyball(self):
        self.assertEqual(self.client.post('/api/other/games', json=self.payload).status_code, 201)
        response = self.client.put('/api/other/games/1', json=dict(self.payload, game_type='Volleyball'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.row()['game_type'], 'Board games')

    def test_zero_zero_and_no_scores_ties(self):
        for fields in [dict(winner_score=0, loser_score=0), dict(score_type='none')]:
            response = self.client.post('/api/other/games', json=dict(self.payload, **fields))
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(self.row()['is_tie'], 1)

    def test_card_ties_count_as_games_and_not_a_rating(self):
        row = ['A', 1, 2, .25, 4, 1]
        stats = ios_api._card_stats(dict(stats=[row]))['stats'][0]
        self.assertEqual(stats['ties'], 1)
        self.assertEqual(stats['games'], 4)
        self.assertNotIn('rating', stats)
        today = ios_api._other_ranking(['A', 0, 0, 0, 0, 1], today=True)
        self.assertEqual((today['games'], today['ties'], today['plus_minus']), (1, 1, 0))


class OtherTieWebEditTests(edit_tests.OtherGameEditTimeTests):
    def test_edit_sequence_tie_and_return_to_win_loss(self):
        response = self.submit(game_type='Board games', game_name='Sequence', is_tie='1',
                               winner_score='1', loser_score='1')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.row()['is_tie'], 1)
        response = self.client.get('/edit_other_game/921/')
        self.assertIn(b'value="1" selected', response.data)
        response = self.submit(game_type='Board games', game_name='Sequence', is_tie='0',
                               winner_score='2', loser_score='1')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.row()['is_tie'], 0)

    def test_volleyball_tie_and_unequal_tie_rejected(self):
        for fields in [dict(game_type='Volleyball', winner_score='1', loser_score='1'),
                       dict(game_type='Board games', winner_score='2', loser_score='1')]:
            response = self.submit(is_tie='1', **fields)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.row()['loser_score'], '15')


class OtherTieWebAddTests(popup_tests.SavedGamePopupTests):
    def test_receipt_shows_tie_and_writes_explicit_outcome(self):
        response = self.client.post('/add_other_game/', data=dict(self.fields,
            game_type='Board games', winner_score='1', loser_score='1', is_tie='1'))
        self.assertEqual(response.status_code, 302)
        self.assertIs(self.write.call_args.kwargs['is_tie'], True)
        html = self.client.get(response.location).get_data(as_text=True)
        self.assertIn('Tie', html)

    def test_volleyball_tie_rejected_before_write(self):
        response = self.client.post('/add_other_game/', data=dict(self.fields,
            game_type='Volleyball', winner_score='1', loser_score='1', is_tie='1'))
        self.assertEqual(response.status_code, 302)
        self.write.assert_not_called()


class OtherTieRecapTests(unittest.TestCase):
    def test_text_and_html_describe_zero_zero_tie_neutrally(self):
        from email_content import create_other_email_plain_text, create_other_email_html
        game = dict(game_date='10/21/2026', is_tie=True, winners=[dict(name='A')],
                    losers=[dict(name='B')], winner_score=0, loser_score=0)
        stats = [['A', 0, 0, 0, 0, 1], ['B', 0, 0, 0, 0, 1]]
        plain = create_other_email_plain_text('', stats, [game], datetime(2026, 10, 21), 'Sequence')
        self.assertIn('A tied with B (0-0)', plain)
        self.assertIn('1 tie', plain)
        html = create_other_email_html('', stats, [game], datetime(2026, 10, 21), 'Sequence')
        self.assertIn('<br>Tie', html)
        self.assertNotIn('class="team-cell winner-team"', html)
        self.assertNotIn('class="score-loser"', html)


if __name__ == '__main__':
    unittest.main()
