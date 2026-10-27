import ast
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, jsonify, request
from other_functions import get_one_on_one_common_scores


class OneOnOneScoreTests(unittest.TestCase):
    def score_history(self, name):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE other_games (id, game_date, game_name, game_type,
            winner1, loser1, winner2, winner_score, loser_score, winner1_score, loser1_score)''')
        rows = [
            (1, '2025-01-01', 'Italian short court', 'Volleyball', 'A', 'B', None, None, None, 11, 0),
            (2, '2026-01-01', ' italian SHORT court ', 'Volleyball', 'A', 'B', None, 11, 9, 11, 9),
            (3, '2026-02-01', 'Italian short court', 'Volleyball', 'A', 'B', None, 15, 13, None, None),
            (4, '2026-03-01', 'Half court long ways', 'Volleyball', 'A', 'B', None, 21, 19, None, None),
            (5, '2026-04-01', 'Italian short court', 'Volleyball', 'A', 'B', 'C', 50, 48, None, None),
            (6, '2026-05-01', 'Italian short court', 'Cards', 'A', 'B', None, 60, 58, None, None),
            (7, '2026-06-01', 'Italian short court', 'Volleyball', 'A', 'A', None, 70, 68, None, None),
        ]
        conn.executemany('INSERT INTO other_games VALUES (' + ','.join(['?'] * 11) + ')', rows)
        with patch('other_functions.set_cur', return_value=conn.cursor()):
            return get_one_on_one_common_scores(name)

    def test_counts_both_storage_types_once_and_keeps_formats_separate(self):
        scores = self.score_history(' ITALIAN short COURT ')
        self.assertEqual(scores['winner_scores'], [11, 15])
        self.assertEqual(scores['loser_scores'], [13, 9, 0])
        self.assertEqual(scores['winner_individual_scores'], [11, 15])
        self.assertEqual(self.score_history('Half court long ways')['winner_scores'], [21])

    def test_new_format_has_no_invented_scores(self):
        self.assertEqual(self.score_history('New format')['winner_scores'], [])

    def test_api_uses_one_on_one_history_only_when_requested(self):
        app = Flask(__name__)
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'stats.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'get_other_game_common_scores')
        namespace = dict(app=app, request=request, jsonify=jsonify)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'stats.py', 'exec'), namespace)
        with patch('other_functions.get_one_on_one_common_scores', return_value={'winner_scores': [11]}) as singles, \
             patch('other_functions.get_common_scores_for_game', return_value={'winner_scores': [8]}) as other:
            client = app.test_client()
            self.assertEqual(client.get('/api/other_game_common_scores/Italian%20short%20court?one_on_one=1').json['winner_scores'], [11])
            self.assertEqual(client.get('/api/other_game_common_scores/Sequence').json['winner_scores'], [8])
            singles.assert_called_once_with('Italian short court')
            other.assert_called_once_with('Sequence')
