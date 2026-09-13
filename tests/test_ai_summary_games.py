import sqlite3
import unittest

from ai_summary_games import load_ai_summary_games
from game_entry_ownership import ensure_game_entry_owner
from create_games_database import create_game, database_update_game
from create_vollis_database import create_vollis_game
from create_other_database import BASE_INSERT_COLUMNS


class AISummaryGamesTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('''CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
            winner1 TEXT, winner2 TEXT, winner_score INTEGER, loser1 TEXT, loser2 TEXT,
            loser_score INTEGER, updated_at TEXT, comments TEXT, entered_timezone TEXT,
            updated_by TEXT, location TEXT)''')
        self.conn.execute('''CREATE TABLE vollis_games (id INTEGER PRIMARY KEY, game_date TEXT,
            winner TEXT, winner_score INTEGER, loser TEXT, loser_score INTEGER,
            updated_at TEXT, entered_timezone TEXT, location TEXT)''')
        self.conn.execute('CREATE TABLE other_games (id INTEGER PRIMARY KEY, ' +
                          ', '.join(f'{col} TEXT' for col in BASE_INSERT_COLUMNS) + ')')
        for table in ('games', 'vollis_games'):
            ensure_game_entry_owner(self.conn, table)

    def tearDown(self):
        self.conn.close()

    def insert(self, kind, owner, day, count=1):
        table = {'doubles': 'games', 'vollis': 'vollis_games', 'other': 'other_games'}[kind]
        values = {'game_date': day + ' 12:00:00', 'entered_by': owner,
                  'updated_at': '2026-09-13 12:00:00', 'winner_score': 21, 'loser_score': 10}
        if kind == 'vollis':
            values.update(winner='Alex', loser='Sam')
        else:
            values.update(winner1='Alex', loser1='Sam')
        if kind == 'doubles':
            values.update(winner2='Pat', loser2='Jo')
        if kind == 'other':
            values.update(game_name='Gin rummy')
        ids = []
        for _ in range(count):
            cur = self.conn.execute(f"INSERT INTO {table} ({', '.join(values)}) VALUES ({','.join('?' for _ in values)})", list(values.values()))
            ids.append(cur.lastrowid)
        return ids

    def ids(self, kind, username='mila', **kwargs):
        rows = load_ai_summary_games(self.conn, kind, username, **kwargs)
        return [r['game_id'] if kind == 'other' else r[0] for r in rows]

    def test_filters_owner_before_limit_and_keeps_entire_latest_day(self):
        for kind in ('doubles', 'vollis', 'other'):
            with self.subTest(kind=kind):
                self.insert(kind, 'kyle', '2026-09-13', 60)
                mine = self.insert(kind, 'Mila', '2026-09-12', 65)
                self.insert(kind, 'mila', '2026-09-11')
                self.insert(kind, None, '2026-09-14')
                self.assertEqual(self.ids(kind), list(reversed(mine)))
                self.assertEqual(self.ids(kind, 'nobody'), [])
                self.assertEqual(self.ids(kind, ''), [])

    def test_search_only_returns_my_entries_including_older_days(self):
        for kind in ('doubles', 'vollis', 'other'):
            with self.subTest(kind=kind):
                mine = self.insert(kind, 'mila', '2020-01-01')
                self.insert(kind, 'kyle', '2026-09-13')
                self.assertEqual(self.ids(kind, query='Alex Sam'), mine)
                self.assertEqual(self.ids(kind, query='2020'), mine)
                self.assertEqual(self.ids(kind, "mila' OR 1=1 --", query='Alex'), [])

    def test_editing_doubles_does_not_transfer_entry_owner(self):
        date = '2026-09-12 12:00:00'
        game_id = create_game(self.conn, (date, 'Alex', 'Pat', 21, 'Sam', 'Jo', 10,
                                         date, '', None, 'mila', 'Beach'))
        database_update_game(self.conn, (game_id, date, 'Alex', 'Pat', 21, 'Sam', 'Jo', 12,
                                        date, 'Fixed score', 'kyle', game_id))
        self.assertEqual(self.ids('doubles'), [game_id])
        self.assertEqual(self.ids('doubles', 'kyle'), [])

    def test_vollis_creation_records_owner(self):
        date = '2026-09-12 12:00:00'
        create_vollis_game(self.conn, (date, 'Alex', 21, 'Sam', 10, date, None, 'Beach', 'mila'))
        self.assertEqual(len(self.ids('vollis')), 1)
        self.assertEqual(self.ids('vollis', 'kyle'), [])

    def test_legacy_attribution_is_preserved_only_once(self):
        with sqlite3.connect(':memory:') as conn:
            conn.execute('CREATE TABLE games (updated_by TEXT)')
            conn.execute("INSERT INTO games VALUES ('mila')")
            ensure_game_entry_owner(conn, 'games')
            conn.execute("UPDATE games SET updated_by = 'kyle'")
            ensure_game_entry_owner(conn, 'games')
            self.assertEqual(conn.execute('SELECT entered_by FROM games').fetchone()[0], 'mila')


if __name__ == '__main__':
    unittest.main()
