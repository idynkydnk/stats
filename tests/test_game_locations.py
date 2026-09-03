import sqlite3
import unittest

from create_games_database import create_game
from create_other_database import BASE_INSERT_COLUMNS, create_other_game
from create_vollis_database import create_vollis_game
from email_content import (
    _append_location_context,
    _summary_location_from_rows,
    build_scene_image_prompt,
)


class GameLocationTests(unittest.TestCase):
    def test_doubles_insert_adds_and_saves_location_column(self):
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
                comments TEXT,
                entered_timezone TEXT,
                updated_by TEXT
            )
        ''')
        game = (
            '2026-09-03 10:00:00', 'A', 'B', 21, 'C', 'D', 15,
            '2026-09-03 10:00:00', '', 'America/Los_Angeles', 'mila',
            'Mission Beach',
        )

        create_game(conn, game)

        self.assertEqual(
            conn.execute('SELECT location FROM games').fetchone()[0],
            'Mission Beach',
        )
        conn.close()

    def test_vollis_insert_adds_and_saves_location_column(self):
        conn = sqlite3.connect(':memory:')
        conn.execute('''
            CREATE TABLE vollis_games (
                id INTEGER PRIMARY KEY,
                game_date TEXT NOT NULL,
                winner TEXT NOT NULL,
                winner_score INTEGER NOT NULL,
                loser TEXT NOT NULL,
                loser_score INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                entered_timezone TEXT
            )
        ''')

        create_vollis_game(conn, (
            '2026-09-03 10:00:00', 'A', 11, 'B', 8,
            '2026-09-03 10:00:00', 'America/Los_Angeles', 'Mission Beach',
        ))

        self.assertEqual(
            conn.execute('SELECT location FROM vollis_games').fetchone()[0],
            'Mission Beach',
        )
        conn.close()

    def test_other_insert_adds_and_saves_location_column(self):
        conn = sqlite3.connect(':memory:')
        legacy_columns = [name for name in BASE_INSERT_COLUMNS if name != 'location']
        conn.execute(
            'CREATE TABLE other_games (id INTEGER PRIMARY KEY, '
            + ', '.join(f'{name} TEXT' for name in legacy_columns)
            + ')'
        )
        values = {name: None for name in BASE_INSERT_COLUMNS}
        values.update({
            'game_date': '2026-09-03 10:00:00',
            'game_type': 'Cards',
            'game_name': 'Gin Rummy',
            'winner1': 'A',
            'loser1': 'B',
            'updated_at': '2026-09-03 10:00:00',
            'location': 'Mission Beach',
        })

        create_other_game(conn, tuple(values[name] for name in BASE_INSERT_COLUMNS))

        self.assertEqual(
            conn.execute('SELECT location FROM other_games').fetchone()[0],
            'Mission Beach',
        )
        conn.close()

    def test_location_is_in_default_and_custom_image_prompts(self):
        prompt = build_scene_image_prompt(
            'doubles', [], location='Mission Beach',
        )
        custom = _append_location_context(
            'Create a dramatic sunset scene.', 'Mission Beach',
        )

        for value in (prompt, custom):
            self.assertIn('LOCATION CONTEXT', value)
            self.assertIn('Mission Beach', value)

    def test_selected_locations_are_deduplicated(self):
        rows = [
            (1, 'Mission Beach'),
            (2, 'mission beach'),
            (3, 'La Jolla Shores'),
        ]

        self.assertEqual(
            _summary_location_from_rows(rows, ['id', 'location']),
            'Mission Beach, La Jolla Shores',
        )


if __name__ == '__main__':
    unittest.main()
