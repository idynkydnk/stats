import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import g
from account_stats_views import build_stats_view, sources_for_user, SOURCE_ID_STRIDE
from private_accounts import account_for_user, connect_data, provision_database
from migrations.separate_existing_accounts import migrate, ownership_report
from tests import test_private_accounts as account_fixtures


class StatsSourceAPITests(unittest.TestCase):
    setUp = account_fixtures.PrivateAccountTests.setUp
    register = account_fixtures.PrivateAccountTests.register

    def test_default_combined_view_and_owned_writes(self):
        a = self.register(self.a, 'alice')
        combined = {**a, 'X-Stats-Combined': '1'}
        self.a.post('/api/games', headers=combined, json={'name': 'Alice game'})
        rows = self.a.get('/api/games', headers=combined).json['rows']
        self.assertEqual(rows, [[2, 'Alice game'], [SOURCE_ID_STRIDE + 1, 'Shared player']])
        self.assertEqual(self.app.test_client().get('/api/games').json['rows'], [[1, 'Shared player']])
        self.a.put('/api/account/stats-sources', headers=a, json={'owner': 'kyle', 'enabled': False})
        self.assertEqual(self.a.get('/api/games', headers=combined).json['rows'], [[2, 'Alice game']])
        # Repeated toggles never copy foreign rows into the owned file.
        for _ in range(2):
            self.a.put('/api/account/stats-sources', headers=a, json={'owner': 'kyle', 'enabled': True})
            self.assertEqual(len(self.a.get('/api/games', headers=combined).json['rows']), 2)
        own = account_for_user(self.path, 'alice')
        with sqlite3.connect(provision_database(self.path, own['id'])) as conn:
            self.assertEqual(conn.execute('SELECT * FROM games').fetchall(), [(2, 'Alice game')])

    def test_sharing_authorization_revocation_and_no_cross_account_edit(self):
        a = self.register(self.a, 'alice')
        b = self.register(self.b, 'bob')
        self.a.post('/api/games', headers=a, json={'name': 'Alice'})
        self.b.post('/api/games', headers=b, json={'name': 'Bob'})
        self.assertEqual(self.b.put('/api/account/stats-sources', headers=b, json={'owner': 'alice', 'enabled': True}).status_code, 403)
        self.assertEqual(self.a.put('/api/account/stats-sharing', headers=a, json={'share_stats': True}).status_code, 200)
        self.assertEqual(self.b.put('/api/account/stats-sources', headers=b, json={'owner': 'alice', 'enabled': True}).status_code, 200)
        rows = self.b.get('/api/games', headers={**b, 'X-Stats-Combined': '1'}).json['rows']
        foreign = next(r[0] for r in rows if r[1] == 'Alice')
        self.assertGreater(foreign, SOURCE_ID_STRIDE)
        # Even if a caller submits a foreign ID, the owned DB contains no matching row.
        self.b.put('/api/games', headers=b, json={'id': foreign, 'name': 'Tampered'})
        self.assertEqual(self.a.get('/api/games', headers=a).json['rows'], [[2, 'Alice']])
        self.a.put('/api/account/stats-sharing', headers=a, json={'share_stats': False})
        rows = self.b.get('/api/games', headers={**b, 'X-Stats-Combined': '1'}).json['rows']
        self.assertNotIn('Alice', [r[1] for r in rows])
        self.assertEqual(self.b.put('/api/account/stats-sources', headers=b, json={'owner': '/tmp/anything', 'enabled': True}).status_code, 403)

    def test_admin_can_include_unshared_source_and_preferences_are_independent(self):
        a = self.register(self.a, 'alice')
        self.a.post('/api/games', headers=a, json={'name': 'Alice'})
        admin = {'Authorization': 'Bearer shared-token'}
        self.assertEqual(self.app.test_client().put('/api/account/stats-sources', headers=admin,
                         json={'owner': 'alice', 'enabled': True}).status_code, 200)
        rows = self.app.test_client().get('/api/games', headers={**admin, 'X-Stats-Combined': '1'}).json['rows']
        self.assertEqual({r[1] for r in rows}, {'Alice', 'Shared player'})
        self.assertFalse(account_for_user(self.path, 'alice')['share_stats'])
        self.assertTrue(account_for_user(self.path, 'alice')['show_starter_stats'])
        self.assertEqual(self.app.test_client().get('/api/account/stats-sources').status_code, 401)

    def test_snapshot_cleanup_and_no_identity_tables(self):
        self.register(self.a, 'alice')
        own = account_for_user(self.path, 'alice')
        snapshot = build_stats_view(self.path, provision_database(self.path, own['id']), sources_for_user(self.path, 'alice'))
        self.addCleanup(lambda: os.path.exists(snapshot) and os.unlink(snapshot))
        with sqlite3.connect(snapshot) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn('site_users', tables)
            self.assertNotIn('auth_tokens', tables)
        self.assertEqual(os.stat(snapshot).st_mode & 0o777, 0o600)


class ExistingAccountMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'stats.db'
        env = patch.dict(os.environ, {'STATS_PRIVATE_DATA_DIR': str(self.path.parent / 'private_data')})
        env.start()
        self.addCleanup(env.stop)
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                CREATE TABLE site_users (username TEXT PRIMARY KEY, password_hash TEXT, is_admin INTEGER DEFAULT 0, active INTEGER DEFAULT 1);
                INSERT INTO site_users VALUES ('kyle','k',1,1),('tyler','t',0,1),('dan','d',0,1),('arbel','a',0,1);
                CREATE TABLE games (id INTEGER PRIMARY KEY AUTOINCREMENT, winner1 TEXT, loser1 TEXT, entered_by TEXT, updated_by TEXT, comments TEXT);
                INSERT INTO games VALUES (1,'Kyle','A','kyle','dan','keep'),(2,'Tyler','Kyle','Tyler','kyle','move'),(3,'Dan','Kyle','dan','dan','move'),(4,'Unknown','Kyle',NULL,'tyler','keep');
                CREATE TABLE vollis_games (id INTEGER PRIMARY KEY, winner TEXT, loser TEXT, entered_by TEXT);
                INSERT INTO vollis_games VALUES (1,'Tyler','Kyle','tyler');
                CREATE TABLE other_games (id INTEGER PRIMARY KEY, winner1 TEXT, loser1 TEXT, entered_by TEXT);
                INSERT INTO other_games VALUES (1,'Dan','Kyle','dan');
                CREATE TABLE players (id INTEGER PRIMARY KEY, full_name TEXT, nickname TEXT);
                INSERT INTO players VALUES (1,'Kyle','K'),(2,'Tyler','T'),(3,'Dan','D'),(4,'Unused','U');
                CREATE TABLE tournaments (id INTEGER PRIMARY KEY);
                INSERT INTO tournaments VALUES (1);
                CREATE TABLE trueskill_rankings (id INTEGER PRIMARY KEY);
                INSERT INTO trueskill_rankings VALUES (1);
            ''')

    def test_backup_move_identity_integrity_and_repeatability(self):
        result = migrate(self.path)
        backup = Path(result['backup']) / 'stats.db'
        with sqlite3.connect(backup) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM games').fetchone()[0], 4)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT id FROM games ORDER BY id').fetchall(), [(1,), (4,)])
            self.assertEqual(conn.execute("SELECT password_hash FROM site_users WHERE username='tyler'").fetchone()[0], 't')
            self.assertEqual(conn.execute('SELECT count(*) FROM tournaments').fetchone()[0], 1)
        for user, expected in [('tyler', [2]), ('dan', [3]), ('arbel', [])]:
            own = account_for_user(self.path, user)
            with sqlite3.connect(provision_database(str(self.path), own['id'])) as conn:
                self.assertEqual([r[0] for r in conn.execute('SELECT id FROM games')], expected)
                self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='tournaments'").fetchone())
                self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='site_users'").fetchone())
                if user == 'tyler':
                    self.assertEqual(conn.execute('SELECT comments,entered_by,updated_by FROM games').fetchone(), ('move','Tyler','kyle'))
                    self.assertEqual({r[0] for r in conn.execute('SELECT full_name FROM players')}, {'Tyler','Kyle'})
        self.assertTrue(all(r.get('already_migrated') for r in migrate(self.path)['moved'].values()))
        self.assertEqual(sum(sum(r.values()) for r in ownership_report(self.path).values()), 0)
        # Kyle's combined view preserves all games without putting them back in Kyle's file.
        snapshot = build_stats_view(str(self.path), str(self.path), sources_for_user(str(self.path), 'kyle', admin=True))
        try:
            with sqlite3.connect(snapshot) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM games').fetchone()[0], 4)
                self.assertEqual(conn.execute('SELECT count(*) FROM vollis_games').fetchone()[0], 1)
                self.assertEqual(conn.execute('SELECT count(*) FROM other_games').fetchone()[0], 1)
                self.assertEqual(conn.execute('SELECT count(*) FROM players').fetchone()[0], 4)
        finally:
            os.unlink(snapshot)

    def test_collision_rolls_back_source_and_target_together(self):
        from private_accounts import init_accounts
        init_accounts(str(self.path))
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO private_accounts (id,username) VALUES (?, 'tyler')", ('a'*32,))
        target = provision_database(str(self.path), 'a'*32)
        with sqlite3.connect(target) as conn:
            conn.execute("INSERT INTO games(id,winner1) VALUES (2,'Existing personal game')")
        with self.assertRaises(sqlite3.IntegrityError):
            migrate(self.path)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("SELECT winner1 FROM games WHERE id=2").fetchone()[0], 'Tyler')
            self.assertEqual(conn.execute("SELECT count(*) FROM personal_database_migrations WHERE username='tyler'").fetchone()[0], 0)
        with sqlite3.connect(target) as conn:
            self.assertEqual(conn.execute('SELECT winner1 FROM games WHERE id=2').fetchone()[0], 'Existing personal game')


if __name__ == '__main__':
    unittest.main()
