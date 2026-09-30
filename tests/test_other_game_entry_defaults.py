import sqlite3
import unittest
from unittest.mock import patch

from other_functions import (other_game_entry_info, other_game_entry_defaults,
                             get_other_game_entry_info, other_year_games)


class OtherGameEntryDefaultsTests(unittest.TestCase):
    def test_sequence_defaults_follow_latest_saved_player_count(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE other_games (
            id INTEGER PRIMARY KEY, game_name, game_date, game_type,
            winner1, winner1_score, loser1, loser2, loser3)''')
        # Even when timestamps match, each newly saved result replaces the
        # previous player count, including when unused loser slots are blank.
        for loser_count in (2, 1, 3, 1):
            conn.execute('INSERT INTO other_games VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)',
                         ('Sequence', '2026-09-30 10:00:00', 'Board game',
                          'A', 2, 'B', 'C' if loser_count >= 2 else '',
                          'D' if loser_count >= 3 else None))
            for year in ('All years', '2026'):
                with self.subTest(loser_count=loser_count, year=year), \
                     patch('other_functions.set_cur', return_value=conn.cursor()), \
                     patch('time_display.format_game_time', return_value='09/30/26 10:00 AM'):
                    defaults = other_game_entry_defaults(other_year_games(year))['sequence']
                self.assertEqual(defaults['winner_count'], 1)
                self.assertEqual(defaults['loser_count'], loser_count)
                self.assertEqual(defaults['score_type'], 'individual')

    def test_team_individual_none_and_new_game(self):
        row = dict(game_type='Volleyball', winner_score=21, winner1='A',
                   winner2='B', loser1='C', loser2='D')
        self.assertEqual(other_game_entry_info(row), dict(
            game_type='Volleyball', score_type='team', winner_count=2, loser_count=2))
        self.assertEqual(other_game_entry_info(dict(row, winner1_score=0))['score_type'], 'individual')
        self.assertEqual(other_game_entry_info(dict(row, winner_score=None))['score_type'], 'none')
        self.assertEqual(other_game_entry_info(None)['score_type'], 'individual')

    def test_preloaded_defaults_keep_latest_and_normalize_names(self):
        games = [dict(game_name='No jump', game_type='Volleyball', winner_score=21),
                 dict(game_name=' no JUMP ', game_type='Old type', winner1_score=10)]
        self.assertEqual(list(other_game_entry_defaults(games)), ['no jump'])
        self.assertEqual(other_game_entry_defaults(games)['no jump']['score_type'], 'team')

    def test_fallback_reads_latest_matching_row_without_formatting_history(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE other_games (id, game_name, game_date, game_type, winner_score, winner1_score)')
        conn.executemany('INSERT INTO other_games VALUES (?, ?, ?, ?, ?, ?)', [
            (1, 'No jump', '2026-01-01', 'Old type', None, 10),
            (2, 'No jump', '2026-09-28', 'Volleyball', 21, None),
            (3, 'Different', '2026-09-29', 'Cards', None, 50)])
        with patch('other_functions.set_cur', return_value=conn.cursor()), \
             patch('other_functions.readable_games_data', side_effect=AssertionError('Must not format history')):
            info = get_other_game_entry_info(' no JUMP ')
        self.assertEqual(info['game_type'], 'Volleyball')
        self.assertEqual(info['score_type'], 'team')
