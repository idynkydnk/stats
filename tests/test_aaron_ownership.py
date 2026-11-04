import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from migrations.restore_aaron_ownership import migrate


class AaronOwnershipTest(unittest.TestCase):
    def test_move_repeat_and_collision_rollback(self):
        records = json.loads(Path('migrations/restore_aaron_ownership.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'private_data').mkdir()
            site = root / 'stats.db'
            personal = root / 'private_data' / 'aaron.db'
            schema = 'CREATE TABLE games (id INTEGER PRIMARY KEY,winner1, winner2, loser1, loser2, entered_by, updated_by, updated_at, comments)'
            with sqlite3.connect(site) as conn:
                conn.execute(schema)
                conn.execute('CREATE TABLE private_accounts(id,username)')
                conn.execute("INSERT INTO private_accounts VALUES ('aaron','aaron')")
                for row in records:
                    conn.execute('INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?)', [row['id'], *row['players'], 'kyle','kyle','2026-09-30','preserve'])
            with sqlite3.connect(personal) as conn:
                conn.execute(schema)
                conn.execute('INSERT INTO games(id) VALUES (?)', (records[-1]['id'],))
            with self.assertRaises(sqlite3.IntegrityError):
                migrate(site)
            with sqlite3.connect(site) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM games').fetchone()[0], 5)
            with sqlite3.connect(personal) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM games').fetchone()[0], 1)
                conn.execute('DELETE FROM games')
            migrate(site)
            migrate(site)
            with sqlite3.connect(site) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM games').fetchone()[0], 0)
                self.assertEqual(conn.execute('SELECT count(*) FROM deleted_records').fetchone()[0], 5)
            with sqlite3.connect(personal) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM games WHERE entered_by='aaron' AND updated_by='kyle' AND comments='preserve'").fetchone()[0], 5)
