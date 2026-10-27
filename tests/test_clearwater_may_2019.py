import json
import sqlite3
import unittest

from migrations.clearwater_may_2019 import NAME, TABLES, correct_database


class ClearwaterMay2019Tests(unittest.TestCase):
    def test_inclusive_dates_only_fill_gaps_and_preserve_later_edits(self):
        with sqlite3.connect(':memory:') as conn:
            for table in TABLES:
                conn.execute(f'''CREATE TABLE {table} (
                    id INTEGER PRIMARY KEY, game_date TEXT, location TEXT,
                    updated_at TEXT, winner_score INTEGER, entered_by TEXT)''')
                conn.executemany(f'INSERT INTO {table} VALUES (?,?,?,?,?,?)', [
                    (1, '2019-05-26 23:59:59', '', 'original', 21, 'kyle'),
                    (2, '2019-05-27 00:00:00', None, 'original', 21, 'kyle'),
                    (3, '2019-06-01 23:59:59', '  ', 'original', 25, 'aaron'),
                    (4, '2019-06-02 00:00:00', '', 'original', 21, 'kyle'),
                    (5, '2019-05-29 12:00:00', 'Clearwater Beach', 'original', 21, 'kyle'),
                    (6, '2019-05-29 12:00:00', 'Existing location', 'original', 21, 'kyle'),
                ])
            conn.commit()
            before = {table: conn.execute(f'SELECT * FROM {table} ORDER BY id').fetchall() for table in TABLES}
            self.assertEqual(correct_database(conn), 6)
            for table in TABLES:
                after = [tuple(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY id')]
                for old, new in zip(before[table], after):
                    if old[0] in (2, 3):
                        self.assertEqual(new[2], 'Clearwater Beach')
                        self.assertEqual(new[:2] + new[4:], old[:2] + old[4:])
                    else:
                        self.assertEqual(new, old)
                audit = conn.execute('SELECT before_json FROM location_migration_audit WHERE migration=? AND game_key=?',
                                     (NAME, f'{table}:2')).fetchone()
                self.assertIsNone(json.loads(audit[0])['location'])
            conn.execute("UPDATE games SET location='Later correction' WHERE id=2")
            conn.commit()
            self.assertEqual(correct_database(conn), 0)
            self.assertEqual(conn.execute('SELECT location FROM games WHERE id=2').fetchone()[0], 'Later correction')


if __name__ == '__main__':
    unittest.main()
