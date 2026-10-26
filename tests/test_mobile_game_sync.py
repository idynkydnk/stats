import concurrent.futures
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from flask import Flask, g, jsonify, session
from mobile_game_sync import commit_insert, idempotent_game, local_game_snapshot, ensure_receipts
from private_accounts import connect_data
from account_stats_views import build_stats_view


class MobileSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'stats.db')
        with sqlite3.connect(self.path) as conn:
            for table in ['games', 'vollis_games', 'other_games']:
                conn.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, game_date TEXT, winner1 TEXT)')
            conn.execute('CREATE TABLE players (id INTEGER PRIMARY KEY, full_name TEXT)')
        self.stub = patch.dict(sys.modules, stats=SimpleNamespace(_stats_db_path=lambda: self.path))
        self.stub.start()
        self.addCleanup(self.stub.stop)
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.app.testing = True
        self.runs = 0
        self.fail_after_commit = False
        self.race_snapshot = False
        for kind, table in [('doubles', 'games'), ('vollis', 'vollis_games'), ('other', 'other_games')]:
            def create(kind=kind, table=table):
                self.runs += 1
                with closing(connect_data(self.path)) as conn:
                    commit_insert(conn, kind, lambda: conn.execute(
                        f"INSERT INTO {table}(game_date, winner1) VALUES ('2026-10-26', 'A')").lastrowid)
                if self.fail_after_commit:
                    self.fail_after_commit = False
                    return jsonify(error='response lost'), 500
                return jsonify(message='Game created'), 201
            self.app.add_url_rule('/' + kind, kind, idempotent_game(kind)(create), methods=['POST'])

        @self.app.get('/snapshot')
        @local_game_snapshot
        def snapshot():
            with closing(connect_data(self.path)) as conn:
                count = conn.execute('SELECT count(*) FROM games').fetchone()[0]
            if self.race_snapshot:
                with sqlite3.connect(self.path) as conn:
                    conn.execute("INSERT INTO games(winner1) VALUES ('raced')")
            return jsonify(total=count)
        self.client = self.app.test_client()
        self.login('alice')

    def login(self, owner):
        with self.client.session_transaction() as s:
            s['username'] = owner
            s['logged_in'] = True

    def payload(self):
        return {'client_game_id': str(uuid.uuid4()), 'winner': 'A', 'loser': 'B'}

    def count(self, table='games'):
        with sqlite3.connect(self.path) as conn:
            return conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]

    def test_lost_response_and_repeated_retries_all_game_types(self):
        for kind, table in [('doubles', 'games'), ('vollis', 'vollis_games'), ('other', 'other_games')]:
            payload = self.payload()
            self.fail_after_commit = True
            self.assertEqual(self.client.post('/' + kind, json=payload).status_code, 500)
            before = self.runs
            for _ in range(4):
                response = self.client.post('/' + kind, json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json['synced'])
                self.assertEqual(response.json['client_game_id'], payload['client_game_id'])
            self.assertEqual(self.count(table), 1)
            self.assertEqual(self.runs, before)

    def test_identical_rematches_are_separate_and_changed_retry_rejected(self):
        p = self.payload()
        self.assertEqual(self.client.post('/doubles', json=p).status_code, 201)
        changed = {**p, 'winner': 'C'}
        self.assertEqual(self.client.post('/doubles', json=changed).status_code, 409)
        self.assertEqual(self.client.post('/doubles', json=self.payload()).status_code, 201)
        self.assertEqual(self.count(), 2)

    def test_owner_isolation_and_deleted_game_is_not_resurrected(self):
        p = self.payload()
        self.client.post('/doubles', json=p)
        self.login('bob')
        self.assertEqual(self.client.post('/doubles', json=p).status_code, 201)
        self.assertEqual(self.count(), 2)
        with sqlite3.connect(self.path) as conn:
            conn.execute('DELETE FROM games')
        self.login('alice')
        self.assertEqual(self.client.post('/doubles', json=p).status_code, 200)
        self.assertEqual(self.count(), 0)
        snap = self.client.get('/snapshot', headers={'X-Stats-Local-Snapshot': '1'})
        self.assertEqual(snap.json['synced_local_game_ids'], [p['client_game_id']])
        self.assertEqual(snap.json['total'], 0)

    def test_concurrent_workers_insert_once(self):
        p = self.payload()
        def upload(_):
            client = self.app.test_client()
            with client.session_transaction() as s:
                s['username'] = 'alice'
            return client.post('/doubles', json=p).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(upload, range(12)))
        self.assertTrue(all(status in (200, 201) for status in statuses), statuses)
        self.assertEqual(self.count(), 1)

    def test_failed_transaction_does_not_reserve_id(self):
        with self.app.test_request_context('/'):
            g.mobile_game_write = ('alice', str(uuid.uuid4()), 'doubles', 'hash')
            with closing(sqlite3.connect(self.path)) as conn:
                def broken():
                    conn.execute("INSERT INTO games(winner1) VALUES ('A')")
                    raise RuntimeError('disk failed')
                with self.assertRaises(RuntimeError):
                    commit_insert(conn, 'doubles', broken)
                self.assertEqual(conn.execute('SELECT count(*) FROM games').fetchone()[0], 0)
                commit_insert(conn, 'doubles', lambda: conn.execute("INSERT INTO games(winner1) VALUES ('A')").lastrowid)
        self.assertEqual(self.count(), 1)

    def test_snapshot_and_receipts_change_together(self):
        p = self.payload()
        before = self.client.get('/snapshot', headers={'X-Stats-Local-Snapshot': '1'})
        self.assertEqual(before.json, {'total': 0, 'synced_local_game_ids': []})
        self.client.post('/doubles', json=p)
        after = self.client.get('/snapshot', headers={'X-Stats-Local-Snapshot': '1'})
        self.assertEqual(after.json, {'total': 1, 'synced_local_game_ids': [p['client_game_id']]})
        self.race_snapshot = True
        self.assertEqual(self.client.get('/snapshot', headers={'X-Stats-Local-Snapshot': '1'}).status_code, 503)

    def test_combined_view_preserves_own_receipts(self):
        p = self.payload()
        self.client.post('/doubles', json=p)
        snapshot = build_stats_view(self.path, self.path, [])
        self.addCleanup(lambda: Path(snapshot).unlink(missing_ok=True))
        with sqlite3.connect(snapshot) as conn:
            self.assertEqual(conn.execute('SELECT client_id FROM mobile_game_receipts').fetchone()[0], p['client_game_id'])
            self.assertEqual(conn.execute('SELECT count(*) FROM games').fetchone()[0], 1)
        with sqlite3.connect(self.path) as conn:
            conn.execute('DELETE FROM games')
        with self.app.test_request_context('/snapshot', headers={'X-Stats-Local-Snapshot': '1'}):
            session['username'] = 'alice'
            g.stats_view_database = snapshot
            response = self.app.view_functions['snapshot']()
            self.assertEqual(response.json, {'total': 1, 'synced_local_game_ids': [p['client_game_id']]})

    def test_actual_insert_functions_commit_game_and_receipt_together(self):
        from create_games_database import create_game
        from create_vollis_database import create_vollis_game
        from create_other_database import BASE_INSERT_COLUMNS, create_other_game
        for kind, table, fields, values, create in [
            ('doubles', 'games', ['game_date', 'winner1', 'winner2', 'winner_score', 'loser1', 'loser2', 'loser_score', 'updated_at', 'comments', 'entered_timezone', 'updated_by'],
             ('2026-10-26', 'A', 'B', 21, 'C', 'D', 15, '2026-10-26', '', 'UTC', 'alice', 'Beach'), create_game),
            ('vollis', 'vollis_games', ['game_date', 'winner', 'winner_score', 'loser', 'loser_score', 'updated_at', 'entered_timezone'],
             ('2026-10-26', 'A', 11, 'B', 9, '2026-10-26', 'UTC', 'Beach', 'alice'), create_vollis_game),
            ('other', 'other_games', BASE_INSERT_COLUMNS,
             tuple({'game_date': '2026-10-26', 'game_type': 'Board games', 'game_name': 'Chess', 'winner1': 'A', 'loser1': 'B', 'entered_by': 'alice'}.get(f) for f in BASE_INSERT_COLUMNS), create_other_game),
        ]:
            with self.subTest(kind=kind), self.app.test_request_context('/'):
                g.mobile_game_write = ('alice', str(uuid.uuid4()), kind, 'hash')
                with closing(sqlite3.connect(':memory:')) as conn:
                    conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, " + ','.join(f'{f} TEXT' for f in fields) + ')')
                    one = create(conn, values)
                    two = create(conn, values)
                    self.assertEqual(one, two)
                    self.assertEqual(conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 1)
                    self.assertEqual(conn.execute('SELECT game_id FROM mobile_game_receipts').fetchone()[0], one)

    def test_legacy_requests_and_invalid_ids(self):
        self.assertEqual(self.client.post('/doubles', json={'winner': 'A'}).status_code, 201)
        self.assertEqual(self.client.post('/doubles', json={'client_game_id': 'bad'}).status_code, 400)
        self.assertNotIn('synced_local_game_ids', self.client.get('/snapshot').json)
        self.assertEqual(self.count(), 1)


if __name__ == '__main__':
    unittest.main()
