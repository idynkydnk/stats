"""Mixed recap IDs stay distinct across game tables and retain source details."""
import sqlite3
import unittest

from ai_summary_games import load_mixed_recap_rows


class MixedRecapRowsTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        for table in ('games', 'vollis_games', 'other_games'):
            self.conn.execute(f'''CREATE TABLE {table} (
                id INTEGER, game_date TEXT, entered_by TEXT, winner1 TEXT,
                winner2 TEXT, loser1 TEXT, loser2 TEXT, winner TEXT, loser TEXT,
                winner_score INTEGER, loser_score INTEGER, comments TEXT,
                comment TEXT, game_name TEXT, game_type TEXT, location TEXT)''')
            self.conn.execute(f'''INSERT INTO {table} VALUES
                (1, '2026-11-03 08:00:00', 'Kyle', 'Alex', 'Pat', 'Sam', 'Jo',
                 'Alex', 'Sam', 21, 19, 'Long rally', 'Warm-up', 'No jump', 'Volleyball', 'Beach')''')
            self.conn.execute(f"INSERT INTO {table} (id, entered_by) VALUES (2, 'dan')")
        self.conn.execute("UPDATE other_games SET game_date='2026-11-03 07:00:00' WHERE id=1")

    def test_colliding_ids_deduplicate_within_type_and_keep_details(self):
        rows = load_mixed_recap_rows(self.conn, ['doubles:1', 'other:1', 'doubles:1'], 'Kyle')
        self.assertEqual([row['id'] for row in rows], ['doubles:1', 'other:1'])
        self.assertEqual([row['game_name'] for row in rows], ['Doubles', 'No jump'])
        self.assertEqual([row['comment'] for row in rows], ['Long rally', 'Warm-up'])
        self.assertEqual(rows[0]['winner2'], 'Pat')
        self.assertEqual(rows[1]['location'], 'Beach')

    def test_vollis_normalizes_player_names(self):
        row = load_mixed_recap_rows(self.conn, ['vollis:1'], 'Kyle')[0]
        self.assertEqual((row['game_name'], row['winner1'], row['loser1']), ('Vollis', 'Alex', 'Sam'))

    def test_owner_scope_applies_to_each_table(self):
        ids = ['doubles:1', 'other:1', 'other:2']
        self.assertEqual([r['id'] for r in load_mixed_recap_rows(self.conn, ids, 'dan')], ['other:2'])
        self.assertEqual(load_mixed_recap_rows(self.conn, ids, ''), [])
        self.assertEqual(len(load_mixed_recap_rows(self.conn, ids, 'kyle')), 3)

    def test_invalid_types_and_ids_are_rejected(self):
        for value in ('games:1', 'other:1 OR 1=1', '1', 'doubles:-1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                load_mixed_recap_rows(self.conn, [value], 'Kyle')


if __name__ == '__main__':
    unittest.main()
