import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import admin_functions as adminfx


class SiteUserPresenceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, 'stats.db')
        self.patcher = mock.patch('admin_functions.stats_db_path', return_value=self.db_path)
        self.patcher.start()
        adminfx.init_activity_log_db()
        adminfx.init_users_db()
        self.assertTrue(adminfx.create_site_user('tyler', 'hash'))
        self.assertTrue(adminfx.create_site_user('kyle', 'hash', is_admin=True))

    def tearDown(self):
        self.patcher.stop()
        self.tmpdir.cleanup()

    def _insert_activity(self, username, action, created_at):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            '''INSERT INTO activity_log (created_at, username, action, summary)
               VALUES (?, ?, ?, ?)''',
            (created_at, username, action, f'{action} by {username}'),
        )
        conn.commit()
        conn.close()

    def _create_auth_tokens_table(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS auth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def test_list_site_users_matches_login_activity_case_insensitively(self):
        self._insert_activity('Tyler', 'Logged in', '2026-09-06 15:00:00')
        self._insert_activity('Tyler', 'Added doubles game (iPhone)', '2026-09-06 15:05:00')

        users = {row['username']: row for row in adminfx.list_site_users()}

        self.assertEqual(users['tyler']['last_login'], '2026-09-06 15:00:00')
        self.assertEqual(users['tyler']['last_seen'], '2026-09-06 15:05:00')
        self.assertIsNone(users['kyle']['last_login'])
        self.assertIsNone(users['kyle']['last_seen'])

    def test_list_site_users_uses_auth_token_as_last_login_fallback(self):
        self._create_auth_tokens_table()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            '''INSERT INTO auth_tokens (username, token_hash, expires_at, created_at)
               VALUES (?, ?, ?, ?)''',
            ('Tyler', 'abc', '2026-12-01 00:00:00', '2026-09-05 12:30:00'),
        )
        conn.commit()
        conn.close()

        users = {row['username']: row for row in adminfx.list_site_users()}
        self.assertEqual(users['tyler']['last_login'], '2026-09-05 12:30:00')
        self.assertEqual(users['tyler']['last_seen'], '2026-09-05 12:30:00')

    def test_touch_site_user_records_presence_for_saved_sessions(self):
        self.assertTrue(adminfx.touch_site_user('Tyler', login=True, min_interval_seconds=0))
        users = {row['username']: row for row in adminfx.list_site_users()}
        self.assertIsNotNone(users['tyler']['last_login'])
        self.assertEqual(users['tyler']['last_login'], users['tyler']['last_seen'])

        first_seen = users['tyler']['last_seen']
        self.assertFalse(adminfx.touch_site_user('tyler', login=False, min_interval_seconds=300))
        self.assertTrue(adminfx.touch_site_user('tyler', login=False, min_interval_seconds=0))
        users = {row['username']: row for row in adminfx.list_site_users()}
        self.assertGreaterEqual(users['tyler']['last_seen'], first_seen)

    def test_canonical_username_uses_stored_account_name(self):
        self.assertEqual(adminfx.canonical_username('Tyler'), 'tyler')
        self.assertEqual(adminfx.canonical_username('nobody'), 'nobody')


if __name__ == '__main__':
    unittest.main()
