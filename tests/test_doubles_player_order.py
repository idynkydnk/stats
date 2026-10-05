import sqlite3
import unittest
from unittest.mock import patch

import stat_functions


class DoublesPlayerOrderTests(unittest.TestCase):
    def test_username_capitalization_does_not_split_player_history(self):
        with sqlite3.connect(':memory:') as conn:
            conn.execute('''CREATE TABLE games (
                id INTEGER PRIMARY KEY, game_date TEXT, winner1 TEXT, winner2 TEXT,
                winner_score INTEGER, loser1 TEXT, loser2 TEXT, updated_by TEXT
            )''')
            conn.executemany('INSERT INTO games VALUES (?, ?, ?, ?, 21, ?, ?, ?)', [
                (1, '2026-09-16', 'Brian', 'Tyler', 'Eddie', 'Kevin', 'tyler'),
                (2, '2026-09-28', 'Tyler', 'Brad', 'Ian', 'Tommy', 'Tyler'),
                (3, '2026-09-29', 'Dan', 'Fernando', 'Hendrik', 'Cherry', 'dan'),
            ])
            global_order = ['Dan', 'Fernando', 'Hendrik', 'Cherry', 'Tyler',
                            'Brad', 'Ian', 'Tommy', 'Brian', 'Eddie', 'Kevin']
            with patch('doubles_division.entry_division', return_value='open'), \
                    patch.object(stat_functions, 'set_cur', side_effect=conn.cursor), \
                    patch.object(stat_functions, 'get_players_ordered_from_cache', return_value=global_order), \
                    patch('player_functions.merge_roster_into_player_names', side_effect=lambda names: names):
                for username in ('tyler', 'Tyler', 'TYLER', ' tyler '):
                    with self.subTest(username=username):
                        self.assertEqual(
                            stat_functions.all_players_ordered_for_doubles(username),
                            ['Tyler', 'Brad', 'Ian', 'Tommy', 'Brian', 'Eddie', 'Kevin',
                             'Dan', 'Fernando', 'Hendrik', 'Cherry'],
                        )
                self.assertEqual(stat_functions.all_players_ordered_for_doubles('new-user'), global_order)


if __name__ == '__main__':
    unittest.main()
