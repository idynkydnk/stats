import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from flask import Flask
import stat_functions as stats
from migrations.add_jen_player import migrate


class WomensDoublesPlayersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'stats.db')
        self.app = Flask(__name__)
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                CREATE TABLE games (id INTEGER PRIMARY KEY, winner1 TEXT, winner2 TEXT,
                    loser1 TEXT, loser2 TEXT, game_date TEXT, updated_by TEXT, division TEXT);
                CREATE TABLE players (full_name TEXT, created_at TEXT, updated_at TEXT);
                CREATE TABLE site_users (username TEXT, player_name TEXT);
                INSERT INTO site_users VALUES ('Jen', NULL);
                INSERT INTO players (full_name) VALUES ('Kyle Thompson');
                INSERT INTO games VALUES (1, 'Kyle Thompson', 'Mert Kurt', 'Chris Goshow', 'Tyler Weston', '2026-09-19', 'kyle', 'open');
            ''')
            migrate(conn)
        self.patcher = patch.object(stats, 'set_cur', side_effect=lambda: sqlite3.connect(self.path).cursor())
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_empty_womens_games_only_suggest_jen(self):
        with self.app.test_request_context('/add_game/?division=women'):
            self.assertEqual(stats.all_players_ordered_for_doubles('Jen'), ['Jen Weston'])
            self.assertEqual(stats.all_players_ordered_for_doubles('Kyle'), ['Jen Weston'])
        with self.app.test_request_context('/api/doubles_players'):
            self.assertEqual(stats.all_players_ordered_for_doubles('Jen'), ['Jen Weston'])

    def test_only_womens_participants_are_added_without_duplicates(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO games VALUES (2, 'Jen Weston', 'Alice', 'Beth', 'Cara', '2026-09-19', 'Jen', 'women')")
            conn.execute("INSERT INTO players (full_name) VALUES ('Unplayed Player')")
        with self.app.test_request_context('/api/doubles_players?division=women'):
            self.assertEqual(stats.all_players_ordered_for_doubles('Kyle'), ['Jen Weston', 'Alice', 'Beth', 'Cara'])

    def test_migration_links_account_once_without_duplicate_players(self):
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT player_name FROM site_users').fetchone()[0], 'Jen Weston')
            migrate(conn)
            self.assertEqual(conn.execute("SELECT count(*) FROM players WHERE full_name='Jen Weston'").fetchone()[0], 1)
            conn.execute("UPDATE site_users SET player_name='Updated Profile'")
            migrate(conn)
            self.assertEqual(conn.execute('SELECT player_name FROM site_users').fetchone()[0], 'Updated Profile')

    def test_mens_selection_does_not_use_womens_roster(self):
        with self.app.test_request_context('/add_game/?division=open'), patch.object(stats, 'get_players_ordered_from_cache', return_value=['Kyle Thompson']), patch('player_functions.merge_roster_into_player_names', side_effect=lambda names: names):
            self.assertEqual(stats.all_players_ordered_for_doubles(), ['Kyle Thompson'])
