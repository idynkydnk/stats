import ast
import sqlite3
import types
import unittest
from pathlib import Path
from unittest.mock import Mock
from migrations.tyler_locations_20260916 import backfill_tyler_locations


class TylerLocationTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        for table in ('games', 'vollis_games', 'other_games'):
            self.conn.execute(f'''CREATE TABLE {table} (id INTEGER PRIMARY KEY,
                game_date TEXT, winner1 TEXT, loser1 TEXT, location TEXT,
                winner_score INTEGER DEFAULT 21, updated_at TEXT DEFAULT 'original')''')

    def add(self, ident, day, opponent, location=None, player='Tyler Weston', table='games'):
        self.conn.execute(f'INSERT INTO {table} (id,game_date,winner1,loser1,location) VALUES (?,?,?,?,?)',
                          (ident, day, player, opponent, location))
        self.conn.commit()

    def test_live_rows_day_propagation_and_undo(self):
        self.add(9001, '2026-09-14', 'Christian Vincent', 'Clearwater, Florida')
        self.add(9002, '2026-09-14', 'Shared Player')
        self.add(9003, '2026-09-12', 'Ryan McCoy', table='other_games')
        self.add(9004, '2026-09-14', 'Christian Vincent', player='Another Player')
        self.assertEqual(backfill_tyler_locations(self.conn), 3)
        self.assertEqual([tuple(r) for r in self.conn.execute('SELECT location,winner_score FROM games ORDER BY id')],
                         [('The Oasis',21), ('The Oasis',21), (None,21)])
        self.assertEqual(self.conn.execute('SELECT location FROM other_games').fetchone()[0], 'Clearwater Beach')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM location_migration_audit').fetchone()[0],3)
        # A subsequent manual edit or newly entered game must survive restarts.
        self.conn.execute("UPDATE games SET location='Manual correction' WHERE id=9001")
        self.conn.commit()
        self.add(9005, '2026-09-14', 'Eddie Molina')
        self.assertEqual(backfill_tyler_locations(self.conn), 0)
        self.assertEqual(self.conn.execute('SELECT location FROM games WHERE id=9001').fetchone()[0], 'Manual correction')
        self.assertIsNone(self.conn.execute('SELECT location FROM games WHERE id=9005').fetchone()[0])

    def test_conflicts_unknown_specific_locations_and_future_are_preserved(self):
        self.add(1,'2026-09-01','Christian Vincent')
        self.add(2,'2026-09-01','Ryan McCoy')
        self.add(3,'2026-09-02','Shared Player')
        self.add(4,'2026-09-03','Ian Hall','Different venue')
        self.add(5,'2026-09-17','Eddie Molina')
        before=[tuple(r) for r in self.conn.execute('SELECT * FROM games')]
        self.assertEqual(backfill_tyler_locations(self.conn),0)
        self.assertEqual([tuple(r) for r in self.conn.execute('SELECT * FROM games')],before)

    def test_form_default_for_tyler_and_other_users(self):
        tree=ast.parse(Path('stats.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_game_location_form_context')
        admin=types.SimpleNamespace(get_site_user=Mock(return_value={}),get_user_last_location=Mock(return_value='Beach'))
        namespace=dict(session={'username':'Tyler'},adminfx=admin,saved_game_locations=lambda:['Beach','The Oasis'])
        exec(compile(ast.Module(body=[node],type_ignores=[]),'stats.py','exec'),namespace)
        self.assertEqual(namespace['_game_location_form_context'](),{'last_location':'The Oasis','locations':['The Oasis','Beach']})
        namespace['session']['username']='someone'
        self.assertEqual(namespace['_game_location_form_context']()['last_location'],'Beach')
        admin.get_site_user.return_value={'player_name':'Tyler Weston'}
        self.assertEqual(namespace['_game_location_form_context']()['last_location'],'The Oasis')


if __name__ == '__main__':
    unittest.main()
