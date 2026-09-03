import sqlite3
import unittest

from migrations.normalize_player_name_whitespace import normalize_player_names
from player_identity import canonical_player_name, unique_player_names
from create_games_database import create_game


class PlayerIdentityTests(unittest.TestCase):
    def test_search_names_ignore_surrounding_whitespace(self):
        self.assertEqual(canonical_player_name('  Dhruva Jagasia  '), 'Dhruva Jagasia')
        self.assertEqual(
            unique_player_names(['Dhruva Jagasia ', 'Dhruva Jagasia']),
            ['Dhruva Jagasia'],
        )

    def test_search_names_dedupe_invisible_unicode_and_case_variants(self):
        self.assertEqual(
            unique_player_names([
                'Dhruva Jagasia',
                'dhruva  jagasia',
                'Dhruva\u00a0Jagasia',
                'Ｄｈｒｕｖａ Jagasia',
            ]),
            ['Dhruva Jagasia'],
        )

    def test_migration_preserves_games_and_combines_last_played_identity(self):
        conn = sqlite3.connect(':memory:')
        conn.executescript('''
            CREATE TABLE games (
                id INTEGER PRIMARY KEY,
                game_date TEXT NOT NULL,
                winner1 TEXT NOT NULL,
                winner2 TEXT NOT NULL,
                winner_score INTEGER NOT NULL,
                loser1 TEXT NOT NULL,
                loser2 TEXT NOT NULL,
                loser_score INTEGER NOT NULL
            );
            CREATE TABLE doubles_player_last_played (
                player_name TEXT PRIMARY KEY,
                last_game_date TEXT NOT NULL
            );
        ''')
        conn.executemany(
            'INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            [
                (1, '2021-09-06 00:00:00', 'Dhruva Jagasia ', 'A', 21, 'B', 'C', 18),
                (2, '2025-02-01 19:13:56', 'D', 'E', 21, 'Dhruva Jagasia', 'F', 19),
            ],
        )
        conn.executemany(
            'INSERT INTO doubles_player_last_played VALUES (?, ?)',
            [
                ('Dhruva Jagasia ', '2021-09-06 00:00:00'),
                ('Dhruva Jagasia', '2025-02-01 19:13:56'),
            ],
        )

        changed = normalize_player_names(conn)

        self.assertEqual(changed['games'], [1])
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM games').fetchone()[0], 2)
        self.assertEqual(
            conn.execute(
                "SELECT COUNT(*) FROM games WHERE TRIM(winner1) = ? OR TRIM(loser1) = ?",
                ('Dhruva Jagasia', 'Dhruva Jagasia'),
            ).fetchone()[0],
            2,
        )
        self.assertEqual(
            conn.execute(
                'SELECT player_name, last_game_date FROM doubles_player_last_played '
                'WHERE player_name = ?',
                ('Dhruva Jagasia',),
            ).fetchone(),
            ('Dhruva Jagasia', '2025-02-01 19:13:56'),
        )
        conn.close()

    def test_doubles_writer_canonicalizes_names_at_database_boundary(self):
        conn = sqlite3.connect(':memory:')
        conn.execute('''
            CREATE TABLE games (
                id INTEGER PRIMARY KEY,
                game_date TEXT NOT NULL,
                winner1 TEXT NOT NULL,
                winner2 TEXT NOT NULL,
                winner_score INTEGER NOT NULL,
                loser1 TEXT NOT NULL,
                loser2 TEXT NOT NULL,
                loser_score INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                comments TEXT
            )
        ''')
        create_game(conn, (
            '2026-09-03 10:00:00', ' Dhruva Jagasia ', 'A ', 21,
            ' B', ' C ', 18, '2026-09-03 10:00:00', '',
        ))

        self.assertEqual(
            conn.execute(
                'SELECT winner1, winner2, loser1, loser2 FROM games'
            ).fetchone(),
            ('Dhruva Jagasia', 'A', 'B', 'C'),
        )
        conn.close()


if __name__ == '__main__':
    unittest.main()
