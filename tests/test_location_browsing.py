import sqlite3
import unittest
from location_functions import backfill_2011, location_games, assign_locations


class LocationBrowsingTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        for table in ('games', 'vollis_games', 'other_games'):
            self.conn.execute(f'''CREATE TABLE {table} (
                id INTEGER PRIMARY KEY, game_date TEXT, location TEXT,
                updated_at TEXT, updated_by TEXT, winner1 TEXT, loser1 TEXT)''')
            self.conn.executemany(f'INSERT INTO {table} (id,game_date,location,winner1,loser1) VALUES (?,?,?,?,?)', [
                (1, '2011-01-01 12:00:00', None, 'A', 'B'),
                (2, '2011-12-31 12:00:00', 'Old place', 'A', 'B'),
                (3, '2012-01-01 12:00:00', None, 'A', 'B')])
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_backfill_all_types_only_2011_and_runs_once(self):
        self.assertEqual(backfill_2011(self.conn), 6)
        self.assertEqual(len(location_games(self.conn, '2011', 'New Jersey')), 6)
        self.assertEqual(len(location_games(self.conn, '2012', missing=True)), 3)
        assign_locations(self.conn, ['doubles:1'], 'Updated place', 'tester')
        self.assertEqual(backfill_2011(self.conn), 0)
        self.assertEqual(len(location_games(self.conn, '2011', 'Updated place')), 1)

    def test_edit_selection_preserves_scores_and_unselected_rows(self):
        count, rows = assign_locations(self.conn, ['doubles:1', 'vollis:2'], 'Beach', 'tester')
        self.assertEqual(count, 2)
        self.assertEqual(rows[0]['winner1'], 'A')
        self.assertEqual(rows[0]['updated_by'], 'tester')
        self.assertEqual(len(location_games(self.conn, 'All years', 'beach')), 2)
        self.assertEqual(len(location_games(self.conn, '2012', missing=True)), 3)
        assign_locations(self.conn, ['doubles:1'], '', 'tester')
        self.assertEqual(len(location_games(self.conn, 'All years', 'Beach')), 1)

    def test_invalid_selection_does_not_write(self):
        for keys in ([], ['games:1'], ['doubles:1', 'other:999']):
            with self.assertRaises(ValueError):
                assign_locations(self.conn, keys, 'Beach', 'tester')
            self.assertEqual(len(location_games(self.conn, 'All years', 'Beach')), 0)


if __name__ == '__main__':
    unittest.main()
