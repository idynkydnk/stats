import json
import sqlite3
import unittest

from migrations.correct_john_russian_max import correct_database


class JohnMaxCorrectionTests(unittest.TestCase):
    def database(self):
        conn = sqlite3.connect(':memory:')
        conn.execute('''CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
            winner1 TEXT, winner2 TEXT, loser1 TEXT, loser2 TEXT,
            winner_score INTEGER, loser_score INTEGER, entered_by TEXT, updated_at TEXT)''')
        conn.execute('CREATE TABLE doubles_player_last_played(player_name TEXT PRIMARY KEY,last_game_date TEXT)')
        for row_id, day, owner, player in (
            (1, '2026-10-09', 'john', 'Russian Max'),
            (2, '2026-10-08', 'john', 'Russian Max'),
            (3, '2026-10-09', 'kyle', 'Russian Max'),
            (4, '2026-10-09', 'john', 'Max States'),
        ):
            conn.execute('INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (row_id, day + ' 09:00:00', player, 'John Moran', 'A', 'B', 21, 18, owner, 'old'))
        conn.commit()
        self.addCleanup(conn.close)
        return conn

    def test_scoped_correction_audit_and_repeat(self):
        conn = self.database()
        changes = correct_database(conn, {'john'})
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['before']['winner1'], 'Russian Max')
        self.assertEqual(changes[0]['after']['winner1'], 'Max Chicherin')
        self.assertEqual([r[0] for r in conn.execute('SELECT winner1 FROM games ORDER BY id')],
                         ['Max Chicherin', 'Russian Max', 'Russian Max', 'Max States'])
        self.assertEqual(changes, correct_database(conn, {'john'}))
        self.assertEqual(conn.execute('SELECT count(*) FROM player_correction_audit').fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT last_game_date FROM doubles_player_last_played WHERE player_name='Max Chicherin'").fetchone()[0], '2026-10-09 09:00:00')

    def test_personal_database_and_all_game_types(self):
        conn = self.database()
        conn.execute('CREATE TABLE vollis_games(id INTEGER PRIMARY KEY, game_date TEXT, winner TEXT, loser TEXT)')
        conn.execute("INSERT INTO vollis_games VALUES (1,'2026-10-09 10:00:00','John Moran','russian max')")
        conn.execute('CREATE TABLE other_games(id INTEGER PRIMARY KEY, game_date TEXT, winner1 TEXT, loser6 TEXT)')
        conn.execute("INSERT INTO other_games VALUES (1,'2026-10-09 11:00:00',' Russian Max ','Other')")
        conn.commit()
        self.assertEqual(len(correct_database(conn, {'john'}, personal=True)), 4)
        self.assertEqual(conn.execute('SELECT loser FROM vollis_games').fetchone()[0], 'Max Chicherin')
        self.assertEqual(conn.execute('SELECT winner1 FROM other_games').fetchone()[0], 'Max Chicherin')

    def test_duplicate_player_rolls_back(self):
        conn = self.database()
        conn.execute("UPDATE games SET loser1='Max Chicherin' WHERE id=3")
        conn.commit()
        with self.assertRaises(ValueError):
            correct_database(conn, {'john'}, personal=True)
        self.assertEqual(conn.execute('SELECT winner1 FROM games WHERE id=1').fetchone()[0], 'Russian Max')


if __name__ == '__main__':
    unittest.main()
