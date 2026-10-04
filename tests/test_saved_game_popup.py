"""A receipt must describe this save, appear once, and never announce rejected input."""
import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask, flash, redirect, render_template, request, session, url_for

ROOT = Path(__file__).resolve().parents[1]


class SavedGamePopupTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'))
        self.app.secret_key = 'test'
        self.app.testing = True
        self.render = Mock(side_effect=lambda template, **values: render_template(
            'partials/saved_game_popup.html', saved_game=values.get('saved_game')))
        self.write = Mock()
        namespace = dict(app=self.app, date=date, request=request, session=session,
                         flash=flash, redirect=redirect, url_for=url_for,
                         render_template=self.render, login_required=lambda fn: fn,
                         parse_client_datetime_for_game=lambda *args: '2026-10-02 10:00:00',
                         _remember_game_location=Mock(), clear_stats_cache=Mock(),
                         log_user_action=Mock(), log_activity=Mock(), update_kobs=Mock(),
                         adminfx=SimpleNamespace(snapshot_last_row=lambda _: None),
                         _game_location_form_context=lambda: {},
                         add_game_stats=self.write, add_vollis_stats=self.write,
                         add_other_stats=self.write)
        for name in ('all_players_ordered_for_doubles', 'todays_games', 'todays_stats',
                     'vollis_year_games', 'all_vollis_players', 'todays_vollis_games',
                     'todays_vollis_stats', 'other_year_games', 'other_game_names',
                     'other_game_types', 'todays_other_games', 'todays_other_stats'):
            namespace[name] = Mock(return_value=[])
        tree = ast.parse((ROOT / 'stats.py').read_text())
        for name in ('_add_doubles_game_view', 'add_game',
                     'add_vollis_game', 'add_other_game'):
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            exec(compile(ast.Module(body=[node], type_ignores=[]), 'stats.py', 'exec'), namespace)
        self.client = self.app.test_client()
        self.patches = [
            patch('player_functions.get_player_by_name', return_value=True),
            patch('player_functions.merge_roster_into_player_names', return_value=[]),
            patch('other_functions.all_combined_players', return_value=[]),
            patch('other_functions.game_name_requires_scores', return_value=False),
            patch('other_functions.other_game_entry_defaults', return_value={}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.fields = dict(winner1='Alice', winner2='Bob', loser1='Chris', loser2='Dan',
                           winner='Alice', loser='Chris', winner_score='21', loser_score='15',
                           game_type='Cards', game_name='Sequence', score_type='team',
                           comments='<script>comment</script>', comment='<script>comment</script>',
                           location='Beach')

    def test_each_form_shows_exact_result_once_after_save(self):
        for path in ('add_game', 'add_vollis_game', 'add_other_game'):
            with self.subTest(path=path):
                response = self.client.post('/' + path + '/', data=self.fields)
                self.assertEqual(response.status_code, 302)
                html = self.client.get(response.location).get_data(as_text=True)
                self.assertIn('Game added', html)
                for text in ('Alice', 'Chris', '21', '15', 'Beach', 'Add another game', 'Done'):
                    self.assertIn(text, html)
                self.assertNotIn('<script>comment</script>', html)
                self.assertNotIn('saved-game-popup', self.client.get(response.location).get_data(as_text=True))
        self.assertEqual(self.write.call_count, 3)

    def test_rejected_input_never_shows_success(self):
        for path in ('add_game', 'add_vollis_game', 'add_other_game'):
            with self.subTest(path=path):
                response = self.client.post('/' + path + '/', data=dict(self.fields, winner1='', winner='', game_name=''))
                self.assertNotIn('saved-game-popup', self.client.get(response.location).get_data(as_text=True))
        self.write.assert_not_called()

    def test_individual_scores_and_no_scores(self):
        for scoring in ('individual', 'none'):
            response = self.client.post('/add_other_game/', data=dict(self.fields,
                score_type=scoring, winner1_score='8', loser1_score='3',
                winner2='', loser2=''))
            self.client.get(response.location)
            receipt = self.render.call_args.kwargs['saved_game']
            self.assertEqual(receipt['winners'], 'Alice (8)' if scoring == 'individual' else 'Alice')
            self.assertEqual(receipt['losers'], 'Chris (3)' if scoring == 'individual' else 'Chris')
            self.assertIsNone(receipt['winner_score'])


if __name__ == '__main__':
    unittest.main()
