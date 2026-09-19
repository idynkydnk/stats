import sqlite3
import unittest

from create_other_database import (BASE_INSERT_COLUMNS, BASE_UPDATE_COLUMNS,
                                   create_other_game, database_update_other_game)
from migrations.normalize_other_game_categories import normalize_other_game_categories
from other_game_categories import canonical_other_category


class OtherGameCategoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.execute('CREATE TABLE other_games (id INTEGER PRIMARY KEY, ' +
                          ', '.join(BASE_INSERT_COLUMNS) + ')')

    def tearDown(self):
        self.conn.close()

    def test_merge_preserves_every_other_field_and_is_repeatable(self):
        labels = ['Card game', 'Card games', 'Board game', 'Board games', 'Volleyball']
        for index, label in enumerate(labels):
            values = [f'value-{index}-{col}' for col in BASE_INSERT_COLUMNS]
            values[1] = label
            self.conn.execute('INSERT INTO other_games (' + ','.join(BASE_INSERT_COLUMNS) +
                              ') VALUES (' + ','.join('?' for _ in values) + ')', values)
        self.conn.commit()
        before = self.conn.execute('SELECT * FROM other_games ORDER BY id').fetchall()
        self.assertEqual(normalize_other_game_categories(self.conn), 2)
        after = self.conn.execute('SELECT * FROM other_games ORDER BY id').fetchall()
        expected = [row[:2] + (canonical_other_category(row[2]),) + row[3:] for row in before]
        self.assertEqual(after, expected)
        self.assertEqual(self.conn.execute('SELECT game_id, original_category FROM other_category_migration_audit ORDER BY game_id').fetchall(), [(1, 'Card game'), (3, 'Board game')])
        self.assertEqual(normalize_other_game_categories(self.conn), 0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM other_category_migration_audit').fetchone()[0], 2)

    def test_insert_and_edit_prevent_aliases_from_returning(self):
        values = [None] * len(BASE_INSERT_COLUMNS)
        values[1] = ' CARD GAME '
        create_other_game(self.conn, values)
        self.assertEqual(self.conn.execute('SELECT game_type FROM other_games').fetchone()[0], 'Card games')
        updated = [None] * len(BASE_UPDATE_COLUMNS)
        updated[1] = 'board game'
        database_update_other_game(self.conn, updated + [1])
        self.assertEqual(self.conn.execute('SELECT game_type FROM other_games').fetchone()[0], 'Board games')

    def test_unexpected_changes_roll_back(self):
        self.conn.execute("INSERT INTO other_games (id, game_type, comment) VALUES (1, 'Card game', 'keep')")
        self.conn.execute("CREATE TRIGGER bad_update AFTER UPDATE ON other_games BEGIN UPDATE other_games SET comment='changed' WHERE id=NEW.id; END")
        self.conn.commit()
        with self.assertRaises(RuntimeError):
            normalize_other_game_categories(self.conn)
        self.assertEqual(self.conn.execute('SELECT game_type, comment FROM other_games').fetchone(), ('Card game', 'keep'))
