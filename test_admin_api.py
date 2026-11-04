"""Tests for the Kyle-only site activity API."""
import sqlite3
import unittest

from stats import app
import admin_functions as adminfx


def _login(client, username='kyle'):
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['username'] = username


class AdminActivityApiTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        adminfx.init_activity_log_db()
        adminfx.init_users_db()
        conn = sqlite3.connect(adminfx.stats_db_path())
        conn.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY,
                game_date DATETIME NOT NULL,
                winner1 TEXT NOT NULL,
                winner2 TEXT NOT NULL,
                winner_score INTEGER NOT NULL,
                loser1 TEXT NOT NULL,
                loser2 TEXT NOT NULL,
                loser_score INTEGER NOT NULL,
                updated_at DATETIME NOT NULL
            )
        ''')
        conn.execute(
            '''INSERT INTO games (game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at)
               VALUES ('2026-09-01 18:00:00', 'Kyle Thomson', 'Aaron Plumb', 21, 'Dan Ferris', 'Zac Prost', 13, '2026-09-01 18:00:00')'''
        )
        conn.commit()
        conn.close()
        adminfx.insert_activity('kyle', 'Logged in', summary='Web login from 1.2.3.4')
        adminfx.insert_activity('aaron', 'Logged in', summary='iPhone app login from 5.6.7.8')

    def test_catalog_requires_auth(self):
        resp = self.client.get('/api/admin')
        self.assertEqual(resp.status_code, 401)

    def test_catalog_rejects_non_admin(self):
        _login(self.client, 'aaron')
        resp = self.client.get('/api/admin')
        self.assertEqual(resp.status_code, 403)

    def test_catalog_asks_kyle_what_to_see(self):
        _login(self.client)
        resp = self.client.get('/api/admin')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['ask'], 'What do you want to see?')
        ids = [t['id'] for t in data['topics']]
        self.assertIn('games', ids)
        self.assertIn('logins', ids)
        self.assertIn('summaries', ids)
        self.assertIn('everything', ids)

    def test_topic_recent_games(self):
        _login(self.client)
        resp = self.client.get('/api/admin?topic=games')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['topic'], 'games')
        self.assertGreaterEqual(data['total'], 1)
        self.assertEqual(data['games'][0]['kind'], 'doubles')
        self.assertIn('Kyle Thomson', data['games'][0]['summary'])

    def test_logins_endpoint(self):
        _login(self.client)
        resp = self.client.get('/api/admin/logins')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        sources = {row['source'] for row in data['logins']}
        self.assertTrue({'web', 'iphone'} <= sources)
        ips = {row['ip'] for row in data['logins']}
        self.assertIn('1.2.3.4', ips)
        self.assertIn('5.6.7.8', ips)

    def test_unknown_topic(self):
        _login(self.client)
        resp = self.client.get('/api/admin?topic=secrets')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('games', resp.get_json()['known_topics'])

    def test_users_list(self):
        _login(self.client)
        resp = self.client.get('/api/admin/users')
        self.assertEqual(resp.status_code, 200)
        names = {u['username'] for u in resp.get_json()['users']}
        self.assertIn('kyle', names)


if __name__ == '__main__':
    unittest.main()
