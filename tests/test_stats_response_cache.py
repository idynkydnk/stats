"""Prepared stats reuse without crossing account or source boundaries."""
from datetime import date
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

from flask import Flask, jsonify, request
from itsdangerous import URLSafeSerializer

from account_stats_views import build_stats_view
from private_accounts import account_for_user, connect_data
from stats_response_cache import StatsResponseCache, STATS_ENDPOINTS
from tests import test_private_accounts as fixtures


class StatsResponseCacheTests(unittest.TestCase):
    register = fixtures.PrivateAccountTests.register

    def setUp(self):
        fixtures.PrivateAccountTests.setUp(self)
        self.calls = []
        self.fail = False

        def standings():
            self.calls.append(request.endpoint)
            if self.fail:
                return jsonify(error='unavailable'), 503
            with connect_data(self.path) as conn:
                rows = conn.execute('SELECT winner1 FROM games ORDER BY id').fetchall()
            return jsonify(rows=rows, year=request.args.get('year'), division=request.args.get('division'))

        for endpoint in STATS_ENDPOINTS:
            self.app.add_url_rule('/api/' + endpoint, endpoint, standings)
        self.cache = self.app.extensions['stats_response_cache']

    def get(self, client=None, headers=None, query='?year=All+years', endpoint='api_doubles_stats'):
        response = (client or self.a).get('/api/' + endpoint + query, headers=headers or {})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response.json

    def test_all_stats_endpoints_reuse_results_across_cache_instances(self):
        for endpoint in STATS_ENDPOINTS:
            first = self.get(endpoint=endpoint)
            self.assertEqual(self.get(endpoint=endpoint), first)
        self.assertEqual(len(self.calls), 4)
        other_worker = StatsResponseCache(self.cache.directory)
        ticket = other_worker.prepare([(self.path, 0)], None, 'api_doubles_stats', [('year', 'All years')], 'open')
        self.assertIsNotNone(other_worker.load(ticket))
        self.assertEqual(self.cache.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.cache.path.stat().st_mode & 0o777, 0o600)

    def test_combined_hit_skips_snapshot_and_edits_deletes_additions_invalidate(self):
        own = self.register(self.a, 'alice')
        headers = {**own, 'X-Stats-Combined': '1'}
        with patch('account_stats_views.build_stats_view', wraps=build_stats_view) as build:
            self.assertEqual(self.get(headers=headers)['rows'], [['Shared player']])
            self.get(headers=headers)
            self.assertEqual(build.call_count, 1)
            # Historical edits do not need to change the last date or game count.
            with sqlite3.connect(self.path) as conn:
                conn.execute("UPDATE games SET winner1='Edited player' WHERE id=1")
            self.assertEqual(self.get(headers=headers)['rows'], [['Edited player']])
            self.assertEqual(build.call_count, 2)
            self.a.post('/api/games', headers=own, json={'name': 'Alice game'})
            self.assertEqual(self.get(headers=headers)['rows'], [['Alice game'], ['Edited player']])
            self.a.delete('/api/games', headers=own)
            self.assertEqual(self.get(headers=headers)['rows'], [['Edited player']])
            self.get(headers=headers)
            self.assertEqual(build.call_count, 4)

    def test_accounts_owned_combined_sources_and_filters_stay_separate(self):
        a = self.register(self.a, 'alice')
        b = self.register(self.b, 'bob')
        self.a.post('/api/games', headers=a, json={'name': 'Alice game'})
        self.b.post('/api/games', headers=b, json={'name': 'Bob game'})
        self.assertEqual(self.get(headers=a)['rows'], [['Alice game']])
        self.assertEqual(self.get(self.b, b)['rows'], [['Bob game']])
        combined = {**a, 'X-Stats-Combined': '1'}
        self.assertEqual(self.get(headers=combined)['rows'], [['Alice game'], ['Shared player']])
        self.a.put('/api/account/stats-sources', headers=a, json={'owner': 'kyle', 'enabled': False})
        self.assertEqual(self.get(headers=combined)['rows'], [['Alice game']])
        before = len(self.calls)
        for query in ('?year=2025', '?year=All+years&division=women', '?year=All+years&location=Beach'):
            self.get(headers=a, query=query)
            self.get(headers=a, query=query)
        self.assertEqual(len(self.calls), before + 3)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET active=0 WHERE username='alice'")
        self.assertEqual(self.a.get('/api/api_doubles_stats?year=All+years', headers=a).status_code, 401)

    def test_cached_share_link_rechecks_permission(self):
        a = self.register(self.a, 'alice')
        self.a.post('/api/games', headers=a, json={'name': 'Alice game'})
        self.a.put('/api/account/stats-sharing', headers=a, json={'share_stats': True})
        account = account_for_user(self.path, 'alice')
        token = URLSafeSerializer(self.app.secret_key, salt='shared-stats-view-v1').dumps(
            dict(base=None, sources=[account['id']]))
        query = '?year=All+years&view=' + token
        guest = self.app.test_client()
        self.assertEqual(self.get(guest, query=query)['rows'], [['Shared player'], ['Alice game']])
        self.get(guest, query=query)
        self.assertEqual(len(self.calls), 1)
        self.a.put('/api/account/stats-sharing', headers=a, json={'share_stats': False})
        self.assertEqual(guest.get('/api/api_doubles_stats' + query).status_code, 404)

    def test_wal_updates_invalidate_with_unchanged_main_database(self):
        with sqlite3.connect(self.path) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('PRAGMA wal_autocheckpoint=0')
            self.get()
            before = Path(self.path).stat().st_mtime_ns
            writer.execute("UPDATE games SET winner1='WAL edit'")
            writer.commit()
            self.assertEqual(Path(self.path).stat().st_mtime_ns, before)
            self.assertEqual(self.get()['rows'], [['WAL edit']])
            self.assertEqual(len(self.calls), 2)

    def test_errors_unwritable_cache_expiry_and_clear(self):
        self.fail = True
        self.assertEqual(self.a.get('/api/api_doubles_stats?year=All+years').status_code, 503)
        self.fail = False
        self.get()
        self.get()
        self.assertEqual(len(self.calls), 2)
        with patch('stats_response_cache.time.time', return_value=time.time() + 3600):
            self.get()
        self.assertEqual(len(self.calls), 3)
        from stat_functions import clear_stats_cache
        with self.app.app_context():
            clear_stats_cache()
        self.get()
        self.assertEqual(len(self.calls), 4)
        with patch.object(self.cache, '_connect', side_effect=OSError('unwritable')):
            self.get()
        self.assertEqual(len(self.calls), 5)

    def test_changes_during_calculation_and_midnight_are_not_reused(self):
        ticket = self.cache.prepare([(self.path, 0)], None, 'api_doubles_stats', [], 'open')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE games SET winner1='Changed during request'")
        self.cache.save(ticket, b'{"old":true}')
        self.assertIsNone(self.cache.load(ticket))
        self.get()
        with patch('stats_response_cache.date') as day:
            day.today.return_value = date(2099, 1, 1)
            self.get()
        self.assertEqual(len(self.calls), 2)

    def test_real_doubles_api_recomputes_after_historical_edit(self):
        import ios_api
        import stat_functions as doubles
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''DROP TABLE games;
                CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
                    winner1 TEXT, winner2 TEXT, winner_score INTEGER,
                    loser1 TEXT, loser2 TEXT, loser_score INTEGER);
                INSERT INTO games VALUES (1, '2020-01-01', 'Alice', 'Bob', 21, 'Cara', 'Dan', 10);
                INSERT INTO games VALUES (2, '2020-01-02', 'Alice', 'Bob', 21, 'Cara', 'Dan', 10);
            ''')
        api = Flask('real-stats-routes')
        with patch('ios_api._ensure_deleted_table'):
            ios_api.register_ios_api(api)
        self.app.view_functions['api_doubles_stats'] = api.view_functions['api_doubles_stats']
        with patch.object(doubles, 'create_connection', side_effect=lambda *args: connect_data(self.path)):
            first = self.get()
            self.assertEqual(first, self.get())
            self.assertEqual(next(row['wins'] for row in first['stats'] if row['name'] == 'Alice'), 2)
            with sqlite3.connect(self.path) as conn:
                conn.execute("UPDATE games SET winner1='Cara', winner2='Dan', loser1='Alice', loser2='Bob' WHERE id=1")
            updated = self.get()
            self.assertEqual(next(row['wins'] for row in updated['stats'] if row['name'] == 'Alice'), 1)
            self.assertNotEqual(first['stats'], updated['stats'])
            self.assertEqual(updated, self.get())

    def test_storage_is_bounded(self):
        with patch('stats_response_cache.MAX_ENTRIES', 2):
            for year in (2020, 2021, 2022):
                self.get(query='?year=' + str(year))
        with sqlite3.connect(self.cache.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM responses').fetchone()[0], 2)

    def test_login_activity_keeps_cache_and_roster_edits_invalidate_it(self):
        self.get()
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET password_hash='login activity' WHERE username='Kyle'")
        self.get()
        self.assertEqual(len(self.calls), 1)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE players SET full_name='Updated name' WHERE id=1")
        self.get()
        self.assertEqual(len(self.calls), 2)


if __name__ == '__main__':
    unittest.main()
