import os
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from flask import g, jsonify, request, url_for
from account_stats_views import build_stats_view, init_stats_views, sources_for_user, SOURCE_ID_STRIDE
from private_accounts import account_for_user, connect_data, provision_database
from migrations.separate_existing_accounts import migrate, ownership_report
from tests import test_private_accounts as account_fixtures


def apply_rollout_to_existing_users(path):
    """Simulate upgrading a database that already has personal accounts."""
    with sqlite3.connect(path) as conn:
        conn.execute('DROP TABLE stats_source_group')
        conn.execute('DROP TABLE stats_source_rollouts')
    init_stats_views(path)


class StatsSourceAPITests(unittest.TestCase):
    setUp = account_fixtures.PrivateAccountTests.setUp
    register = account_fixtures.PrivateAccountTests.register

    def test_combined_doubles_suggestions_include_players_without_profiles(self):
        from stat_functions import all_players_ordered_for_doubles
        from flask import session
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                DROP TABLE games;
                CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
                    winner1 TEXT, winner2 TEXT, winner_score INTEGER,
                    loser1 TEXT, loser2 TEXT, loser_score INTEGER, updated_by TEXT);
                INSERT INTO games VALUES (1, '2026-10-06', 'KT One', 'KT Two', 21,
                    'KT Three', 'KT Four', 15, 'Kyle');
                CREATE TABLE doubles_player_last_played (player_name TEXT, last_game_date TEXT);
                INSERT INTO doubles_player_last_played VALUES ('KT One', '2026-10-06');
            ''')

        @self.app.get('/api/doubles_players', endpoint='api_doubles_players')
        def players():
            return jsonify(all_players_ordered_for_doubles(session.get('username')))

        headers = {**self.register(self.a, 'alice'), 'X-Stats-Combined': '1'}
        with patch('stat_functions.set_cur', side_effect=lambda: connect_data(self.path).cursor()), \
             patch('player_functions._players_db_connection', side_effect=lambda: connect_data(self.path)):
            response = self.a.get('/api/doubles_players', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, ['KT One', 'KT Two', 'KT Three', 'KT Four', 'Shared player'])

    def test_add_game_player_suggestions_follow_enabled_sources(self):
        # Exercise the routing used by each iPhone autocomplete endpoint.
        paths = ['/api/doubles_players', '/api/vollis_players', '/api/other_game_players/Sequence']
        endpoints = ['api_doubles_players', 'api_vollis_players', 'get_other_game_players']

        def players():
            with connect_data(self.path) as conn:
                return jsonify([row[0] for row in conn.execute('SELECT full_name FROM players ORDER BY full_name')])

        for path, endpoint in zip(paths, endpoints):
            self.app.add_url_rule(path, endpoint, players)

        own_headers = self.register(self.a, 'alice')
        self.register(self.b, 'bob')
        alice = account_for_user(self.path, 'alice')
        bob = account_for_user(self.path, 'bob')
        with sqlite3.connect(provision_database(self.path, bob['id'])) as conn:
            conn.execute("INSERT INTO players VALUES (1, 'Bob private player')")
        headers = {**own_headers, 'X-Stats-Combined': '1'}
        self.assertTrue(self.a.get('/api/account/stats-sources', headers=own_headers).json['sources'][0]['enabled'])

        for path in paths:
            with self.subTest(path=path, state='new account'):
                response = self.a.get(path, headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, ['Shared player'])
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual(self.a.get(path, headers=own_headers).json, [])

        with sqlite3.connect(provision_database(self.path, alice['id'])) as conn:
            self.assertEqual(conn.execute('SELECT * FROM players').fetchall(), [])
            conn.executemany('INSERT INTO players VALUES (?, ?)', [(1, 'Alice player'), (2, 'Shared player')])

        for enabled, expected in [(False, ['Alice player', 'Shared player']),
                                  (True, ['Alice player', 'Shared player'])]:
            # A duplicate own/KT name appears once. Disabling KT keeps owned names.
            self.a.put('/api/account/stats-sources', headers=own_headers, json={'owner': 'kyle', 'enabled': enabled})
            for path in paths:
                self.assertEqual(self.a.get(path, headers=headers).json, expected)

        with sqlite3.connect(provision_database(self.path, alice['id'])) as conn:
            conn.execute("DELETE FROM players WHERE full_name='Shared player'")
        self.a.put('/api/account/stats-sources', headers=own_headers, json={'owner': 'kyle', 'enabled': False})
        for path in paths:
            self.assertEqual(self.a.get(path, headers=headers).json, ['Alice player'])
        self.a.put('/api/account/stats-sources', headers=own_headers, json={'owner': 'kyle', 'enabled': True})
        for path in paths:
            self.assertEqual(self.a.get(path, headers=headers).json, ['Alice player', 'Shared player'])

        # Even with Combined on the request, writes remain in the owned database.
        self.a.post('/api/games', headers=headers, json={'name': 'Shared player'})
        with sqlite3.connect(provision_database(self.path, alice['id'])) as conn:
            self.assertEqual(conn.execute('SELECT * FROM games').fetchall(), [(2, 'Shared player')])
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT * FROM games').fetchall(), [(1, 'Shared player')])

    def test_current_users_use_full_roster_names_and_kt_stays_unchanged(self):
        self.register(self.a, 'tyler')
        self.register(self.b, 'jen')
        with sqlite3.connect(self.path) as conn:
            conn.execute('ALTER TABLE site_users ADD COLUMN player_name TEXT')
            conn.execute("UPDATE site_users SET player_name='tyler weston' WHERE username='tyler'")
            conn.executemany('INSERT INTO players (full_name) VALUES (?)',
                             [('Tyler Weston',), ('Tyler Bird',), ('Jen Example',), ('Kyle Thomson',)])
        admin_headers = {'Authorization': 'Bearer shared-token'}
        payload = self.app.test_client().get('/api/account/stats-sources', headers=admin_headers).json
        self.assertEqual({source['owner']: source['title'] for source in payload['sources']},
                         {'kyle': 'My stats (KT Stats)', 'tyler': 'Tyler Weston’s stats', 'jen': 'Jen Example’s stats'})
        own = self.a.get('/api/account/stats-sources').json
        self.assertEqual(own['sources'][0]['title'], 'KT Stats')
        self.assertEqual(own['sources'][0]['owner'], 'kyle')

    def test_source_titles_use_social_names_but_keep_stable_owner_keys(self):
        claims = {'sub': 'profile-person', 'email_verified': True, 'name': 'Jamie McDonald'}
        with patch('google.oauth2.id_token.verify_oauth2_token', return_value=claims):
            response = self.a.post('/api/auth/google', json={'id_token': 'verified'})
        owner = response.json['username']
        admin_headers = {'Authorization': 'Bearer shared-token'}
        payload = self.b.get('/api/account/stats-sources', headers=admin_headers).json
        source = next(s for s in payload['sources'] if s['owner'] == owner)
        self.assertEqual(source['title'], 'Jamie McDonald’s stats')
        response = self.b.put('/api/account/stats-sources', headers=admin_headers,
                              json={'owner': owner, 'enabled': True})
        self.assertEqual(response.status_code, 200)
        with sqlite3.connect(self.path) as conn:
            conn.execute('UPDATE site_users SET display_name=NULL WHERE username=?', (owner,))
        payload = self.b.get('/api/account/stats-sources', headers=admin_headers).json
        source = next(s for s in payload['sources'] if s['owner'] == owner)
        self.assertEqual(source['title'], 'Google account’s stats')
        self.assertTrue(source['enabled'])

    def test_kyle_can_select_only_one_account_and_uncheck_own_stats(self):
        a = self.register(self.a, 'alice')
        b = self.register(self.b, 'bob')
        self.a.post('/api/games', headers=a, json={'name': 'Alice game'})
        self.b.post('/api/games', headers=b, json={'name': 'Bob game'})
        admin = self.app.test_client()
        headers = {'Authorization': 'Bearer shared-token', 'X-Stats-Combined': '1'}
        payload = admin.get('/api/account/stats-sources', headers=headers).json
        self.assertTrue(payload['can_select_only'])
        self.assertEqual(payload['sources'][0], dict(owner='kyle', title='My stats (KT Stats)', enabled=True))
        admin.put('/api/account/stats-sources', headers=headers, json={'owner': 'bob', 'enabled': True})
        response = admin.put('/api/account/stats-sources', headers=headers,
                             json={'owner': 'ALICE', 'enabled': True, 'only': True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([s['owner'] for s in response.json['sources'] if s['enabled']], ['alice'])
        rows = admin.get('/api/games', headers=headers).json['rows']
        self.assertEqual([r[1] for r in rows], ['Alice game'])
        self.assertGreater(rows[0][0], SOURCE_ID_STRIDE)
        init_stats_views(self.path)
        self.assertEqual(admin.get('/api/games', headers=headers).json['rows'], rows)
        for enabled, expected in [(True, {'Shared player', 'Alice game'}), (False, {'Alice game'})]:
            admin.put('/api/account/stats-sources', headers=headers, json={'owner': 'kyle', 'enabled': enabled})
            self.assertEqual({r[1] for r in admin.get('/api/games', headers=headers).json['rows']}, expected)
        # Deselecting everything must produce an empty view, never the KT fallback.
        admin.put('/api/account/stats-sources', headers=headers, json={'owner': 'alice', 'enabled': False})
        self.assertEqual(admin.get('/api/games', headers=headers).json['rows'], [])
        # The owned/sync view and writes still address Kyle's original database.
        owned = {'Authorization': 'Bearer shared-token', 'X-Stats-Owned': '1'}
        self.assertEqual(admin.get('/api/games', headers=owned).json['rows'], [[1, 'Shared player']])
        admin.post('/api/games', headers=headers, json={'name': 'Kyle new game'})
        self.assertEqual(admin.get('/api/games', headers=headers).json['rows'], [])
        self.assertEqual(self.a.get('/api/games', headers=a).json['rows'], [[2, 'Alice game']])
        self.assertEqual(len(admin.get('/api/games', headers=owned).json['rows']), 2)

    def test_select_only_validates_before_changing_any_preferences(self):
        a = self.register(self.a, 'alice')
        self.assertFalse(self.a.get('/api/account/stats-sources', headers=a).json['can_select_only'])
        self.assertEqual(self.a.put('/api/account/stats-sources', headers=a,
                         json={'owner': 'kyle', 'enabled': True, 'only': True}).status_code, 403)
        self.assertEqual(self.a.put('/api/account/stats-sources', headers=a,
                         json={'owner': 'alice', 'enabled': False}).status_code, 403)
        admin = self.app.test_client()
        headers = {'Authorization': 'Bearer shared-token'}
        before = admin.get('/api/account/stats-sources', headers=headers).json
        for body, status in [({'owner': 'missing', 'enabled': True, 'only': True}, 403),
                             ({'owner': 'alice', 'enabled': False, 'only': True}, 400),
                             ({'owner': 'alice', 'enabled': True, 'only': 'true'}, 400)]:
            self.assertEqual(admin.put('/api/account/stats-sources', headers=headers, json=body).status_code, status)
            self.assertEqual(admin.get('/api/account/stats-sources', headers=headers).json, before)

    def test_selected_stats_context_respects_an_empty_selection(self):
        from account_stats_views import selected_stats_context

        @self.app.post('/selected-stats')
        def selected():
            with selected_stats_context(), connect_data(self.path) as conn:
                return jsonify(rows=conn.execute('SELECT * FROM games').fetchall())

        admin = {'Authorization': 'Bearer shared-token'}
        self.a.put('/api/account/stats-sources', headers=admin, json={'owner': 'kyle', 'enabled': False})
        self.assertEqual(self.a.post('/selected-stats', headers=admin).json['rows'], [])

    def test_mobile_snapshots_do_not_add_local_games_when_own_stats_are_off(self):
        from mobile_game_sync import local_game_snapshot

        @self.app.get('/api/standings', endpoint='api_vollis_stats')
        @local_game_snapshot
        def standings():
            with connect_data(self.path) as conn:
                return jsonify(rows=conn.execute('SELECT winner1 FROM games').fetchall())

        alice = self.register(self.a, 'alice')
        self.a.post('/api/games', headers=alice, json={'name': 'Alice game'})
        admin = self.app.test_client()
        headers = {'Authorization': 'Bearer shared-token', 'X-Stats-Combined': '1', 'X-Stats-Local-Snapshot': '1'}
        with patch.dict('sys.modules', {'stats': SimpleNamespace(_stats_db_path=lambda: self.path)}):
            self.assertTrue(admin.get('/api/standings', headers=headers).json['includes_own_stats'])
            admin.put('/api/account/stats-sources', headers=headers,
                      json={'owner': 'alice', 'enabled': True, 'only': True})
            for _ in range(2):  # Cached snapshots must keep the exclusion too.
                response = admin.get('/api/standings', headers=headers)
                self.assertEqual(response.json['rows'], [['Alice game']])
                self.assertFalse(response.json['includes_own_stats'])
                self.assertEqual(response.json['synced_local_game_ids'], [])
            owned = {k: v for k, v in headers.items() if k != 'X-Stats-Combined'}
            owned['X-Stats-Owned'] = '1'
            self.assertTrue(admin.get('/api/standings', headers=owned).json['includes_own_stats'])

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
        apply_rollout_to_existing_users(self.path)
        self.a.put('/api/account/stats-sharing', headers=a, json={'share_stats': False})
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

    def test_existing_defaults_are_applied_once_and_opt_out_survives_restart(self):
        a = self.register(self.a, 'alice')
        b = self.register(self.b, 'bob')
        self.a.put('/api/account/stats-sources', headers=a, json={'owner': 'kyle', 'enabled': False})
        apply_rollout_to_existing_users(self.path)
        for client, headers, other in [(self.a, a, 'bob'), (self.b, b, 'alice')]:
            payload = client.get('/api/account/stats-sources', headers=headers).json
            self.assertEqual({s['owner'].lower() for s in payload['sources']}, {'kyle', other})
            self.assertTrue(all(s['enabled'] for s in payload['sources']))
            self.assertTrue(payload['share_stats'])
        admin = self.app.test_client().get('/api/account/stats-sources', headers={'Authorization': 'Bearer shared-token'}).json
        self.assertTrue(all(s['enabled'] for s in admin['sources']))
        for owner in ('kyle', 'bob'):
            self.a.put('/api/account/stats-sources', headers=a, json={'owner': owner, 'enabled': False})
        self.a.put('/api/account/stats-sharing', headers=a, json={'share_stats': False})
        init_stats_views(self.path)
        payload = self.a.get('/api/account/stats-sources', headers=a).json
        self.assertTrue(all(not s['enabled'] for s in payload['sources']))
        self.assertFalse(payload['share_stats'])
        self.assertFalse(account_for_user(self.path, 'alice')['show_starter_stats'])
        self.assertEqual([s['owner'] for s in self.b.get('/api/account/stats-sources', headers=b).json['sources']], ['kyle'])

    def test_future_password_google_and_apple_users_only_get_kt(self):
        a = self.register(self.a, 'dan')
        self.register(self.b, 'tyler')
        self.a.post('/api/games', headers=a, json={'name': 'Dan game'})
        apply_rollout_to_existing_users(self.path)
        for provider in ('password', 'google', 'apple'):
            with self.subTest(provider=provider):
                client = self.app.test_client()
                if provider == 'password':
                    headers = self.register(client, 'newperson')
                    username = 'newperson'
                else:
                    if provider == 'google':
                        with patch('google.oauth2.id_token.verify_oauth2_token', return_value={'sub': 'new-google', 'email_verified': True}):
                            response = client.post('/api/auth/google', json={'id_token': 'verified'})
                    else:
                        nonce = client.post('/api/auth/apple/challenge').json['nonce']
                        with patch('jwt.PyJWKClient.get_signing_key_from_jwt', return_value=SimpleNamespace(key='test')), \
                             patch('jwt.decode', return_value={'sub': 'new-apple', 'nonce': hashlib.sha256(nonce.encode()).hexdigest()}):
                            response = client.post('/api/auth/apple', json={'id_token': 'verified', 'nonce': nonce})
                    self.assertEqual(response.status_code, 200, response.json)
                    username = response.json['username']
                    headers = {'Authorization': 'Bearer ' + response.json['token']}
                # A restart and even a stale/forged selection must not grant access.
                with sqlite3.connect(self.path) as conn:
                    conn.execute('INSERT INTO account_stats_sources VALUES (?, ?, 1)', (username, 'dan'))
                init_stats_views(self.path)
                payload = client.get('/api/account/stats-sources', headers=headers).json
                self.assertEqual(payload['sources'], [{'owner': 'kyle', 'title': 'KT Stats', 'enabled': True}])
                self.assertFalse(payload['share_stats'])
                for owner in ('dan', 'tyler'):
                    self.assertEqual(client.put('/api/account/stats-sources', headers=headers, json={'owner': owner, 'enabled': True}).status_code, 403)
                combined = {**headers, 'X-Stats-Combined': '1'}
                self.assertEqual(client.get('/api/games', headers=combined).json['rows'], [[SOURCE_ID_STRIDE + 1, 'Shared player']])
                client.put('/api/account/stats-sources', headers=headers, json={'owner': 'kyle', 'enabled': False})
                self.assertEqual(client.get('/api/games', headers=combined).json['rows'], [])

    def test_reused_username_does_not_inherit_existing_group_access(self):
        self.register(self.a, 'dan')
        self.register(self.b, 'removed')
        apply_rollout_to_existing_users(self.path)
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM site_users WHERE username='removed'")
            conn.execute("DELETE FROM private_accounts WHERE username='removed'")
        headers = self.register(self.b, 'removed')
        payload = self.b.get('/api/account/stats-sources', headers=headers).json
        self.assertEqual(payload['sources'], [{'owner': 'kyle', 'title': 'KT Stats', 'enabled': True}])
        self.assertFalse(payload['share_stats'])

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


class SharedStatsLinkTests(unittest.TestCase):
    register = account_fixtures.PrivateAccountTests.register

    def setUp(self):
        account_fixtures.PrivateAccountTests.setUp(self)

        @self.app.get('/stats/<year>/', endpoint='stats')
        def stats_page(year):
            with connect_data(self.path) as conn:
                rows = conn.execute('SELECT * FROM games ORDER BY id').fetchall()
            return jsonify(rows=rows, token=getattr(g, 'stats_share_token', None),
                           titles=getattr(g, 'stats_shared_titles', []),
                           next=url_for('stats', year='2025'),
                           api=url_for('api_doubles_list'),
                           read_only=getattr(g, 'stats_shared_read_only', False),
                           location=request.args.get('location'),
                           snapshot=getattr(g, 'stats_view_database', None))

    def own_game(self, client, name):
        headers = self.register(client, name)
        client.post('/api/games', headers=headers, json={'name': name + ' game'})
        client.put('/api/account/stats-sources', headers=headers, json={'owner': 'kyle', 'enabled': False})
        return headers

    def test_personal_url_works_for_guests_and_other_accounts(self):
        self.own_game(self.a, 'dan')
        self.own_game(self.b, 'bob')
        redirect = self.a.get('/stats/2026/?location=Beach&division=womens')
        self.assertEqual(redirect.status_code, 302)
        link = redirect.location
        self.assertIn('division=womens', link)
        self.assertIn('view=', link)
        guest = self.app.test_client()
        for client in [self.a, guest, self.b]:
            page = client.get(link)
            self.assertEqual(page.json['rows'], [[2, 'dan game']])
            self.assertEqual(page.json['location'], 'Beach')
            self.assertEqual(page.json['read_only'], client != self.a)
            self.assertEqual(page.headers['Cache-Control'], 'no-store')
            self.assertEqual(page.headers['Referrer-Policy'], 'same-origin')
            self.assertFalse(Path(page.json['snapshot']).exists())
            self.assertEqual(client.get(page.json['next']).json['rows'], [[2, 'dan game']])
            self.assertEqual(client.get(page.json['api']).json['rows'], [[2, 'dan game']])
        # Following Dan's link changes neither authentication nor preferences.
        self.assertEqual(self.b.get('/api/games').json['rows'], [[2, 'bob game']])
        with guest.session_transaction() as session:
            self.assertFalse(session.get('logged_in'))
        self.assertFalse(account_for_user(self.path, 'dan')['share_stats'])

    def test_link_freezes_sources_and_preserves_game_ids(self):
        headers = self.own_game(self.a, 'dan')
        own_link = self.a.get('/stats/2026/').location
        self.a.put('/api/account/stats-sources', headers=headers, json={'owner': 'kyle', 'enabled': True})
        combined_link = self.a.get('/stats/2026/').location
        self.assertNotEqual(own_link, combined_link)
        expected = [[2, 'dan game'], [SOURCE_ID_STRIDE + 1, 'Shared player']]
        guest = self.app.test_client()
        self.assertEqual(guest.get(combined_link).json['rows'], expected)
        self.a.put('/api/account/stats-sources', headers=headers, json={'owner': 'kyle', 'enabled': False})
        self.assertEqual(guest.get(combined_link).json['rows'], expected)
        self.assertEqual(guest.get(own_link).json['rows'], [[2, 'dan game']])
        self.assertEqual(self.a.get('/stats/2026/').location, own_link)

    def test_saved_share_link_uses_updated_display_name(self):
        self.own_game(self.a, 'dan')
        link = self.a.get('/stats/2026/').location
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET display_name='Dan Ferris' WHERE username='dan'")
        page = self.app.test_client().get(link)
        self.assertEqual(page.json['titles'], ['Dan Ferris’s stats'])
        self.assertEqual(page.json['rows'], [[2, 'dan game']])

    def test_shared_link_uses_linked_roster_name_and_keeps_kt_title(self):
        headers = self.own_game(self.a, 'tyler')
        self.a.put('/api/account/stats-sources', headers=headers, json={'owner': 'kyle', 'enabled': True})
        link = self.a.get('/stats/2026/').location
        with sqlite3.connect(self.path) as conn:
            conn.execute('ALTER TABLE site_users ADD COLUMN player_name TEXT')
            conn.execute("UPDATE site_users SET player_name='Tyler Weston' WHERE username='tyler'")
        self.assertEqual(self.app.test_client().get(link).json['titles'], ['Tyler Weston’s stats', 'KT Stats'])

    def test_public_link_overrides_recipient_personal_preferences(self):
        guest = self.app.test_client()
        link = guest.get('/stats/2026/').location
        self.own_game(self.a, 'dan')
        self.assertEqual(self.a.get(link).json['rows'], [[1, 'Shared player']])
        self.assertIsNone(guest.get(link).json['snapshot'])

    def test_kyle_only_selection_survives_web_and_app_share_links(self):
        alice = self.own_game(self.a, 'alice')
        admin = self.app.test_client()
        headers = {'Authorization': 'Bearer shared-token'}
        admin.put('/api/account/stats-sources', headers=headers,
                  json={'owner': 'alice', 'enabled': True, 'only': True})
        # Admin access does not grant permission to publish another user's stats.
        page = admin.get('/stats/2026/', headers=headers)
        self.assertEqual([r[1] for r in page.json['rows']], ['alice game'])
        self.assertIsNone(page.json['token'])
        self.assertEqual(admin.get('/api/account/stats-share', headers=headers).status_code, 403)
        self.a.put('/api/account/stats-sharing', headers=alice, json={'share_stats': True})
        web_link = admin.get('/stats/2026/', headers=headers).location
        app_token = admin.get('/api/account/stats-share', headers=headers).json['view']
        guest = self.app.test_client()
        for link in [web_link, '/stats/2026/?view=' + app_token]:
            for viewer in [guest, admin, self.a]:
                response = viewer.get(link)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([r[1] for r in response.json['rows']], ['alice game'])
                self.assertGreater(response.json['rows'][0][0], SOURCE_ID_STRIDE)
                self.assertEqual(response.json['titles'], ['Alice’s stats'])
                self.assertTrue(response.json['read_only'])
        admin.put('/api/account/stats-sources', headers=headers, json={'owner': 'kyle', 'enabled': True})
        self.assertEqual([r[1] for r in guest.get(web_link).json['rows']], ['alice game'])
        self.a.put('/api/account/stats-sharing', headers=alice, json={'share_stats': False})
        self.assertEqual(guest.get(web_link).status_code, 404)

    def test_kyle_empty_selection_share_link_stays_empty(self):
        headers = {'Authorization': 'Bearer shared-token'}
        self.a.put('/api/account/stats-sources', headers=headers, json={'owner': 'kyle', 'enabled': False})
        link = self.a.get('/stats/2026/', headers=headers).location
        for client in [self.a, self.app.test_client()]:
            response = client.get(link)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['rows'], [])
            self.assertEqual(response.json['titles'], [])
        owned = self.a.get('/api/account/stats-share?owned=1', headers=headers).json['view']
        self.assertEqual(self.b.get('/stats/2026/?view=' + owned).json['rows'], [[1, 'Shared player']])

    def test_web_names_select_only_and_checkboxes_allow_excluding_kyle(self):
        from flask import redirect
        from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader
        self.app.add_url_rule('/stats/', 'stats_default', lambda: redirect(url_for('stats', year='2026')))
        self.app.jinja_loader = ChoiceLoader([
            DictLoader({'base.html': '{% block extra_css %}{% endblock %}{% block content %}{% endblock %}'}),
            FileSystemLoader(str(Path(__file__).resolve().parents[1] / 'templates')),
        ])
        self.own_game(self.a, 'alice')
        admin = self.app.test_client()
        headers = {'Authorization': 'Bearer shared-token'}
        page = admin.get('/account/stats-sources/', headers=headers)
        self.assertIn('My stats (KT Stats)', page.text)
        self.assertIn('name="only_owner" value="alice"', page.text)
        with admin.session_transaction() as session:
            csrf = session['stats_sources_csrf']
        self.assertEqual(admin.post('/account/stats-sources/', data={'only_owner': 'alice'}).status_code, 400)
        response = admin.post('/account/stats-sources/', data={
            'csrf': csrf, 'owner': ['kyle', 'alice'], 'only_owner': 'alice'}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r[1] for r in response.json['rows']], ['alice game'])
        for owners, expected in [(['kyle', 'alice'], {'Shared player', 'alice game'}),
                                 (['alice'], {'alice game'}), ([], set())]:
            response = admin.post('/account/stats-sources/', data={'csrf': csrf, 'owner': owners}, follow_redirects=True)
            self.assertEqual({r[1] for r in response.json['rows']}, expected)
        page = self.a.get('/account/stats-sources/')
        self.assertNotIn('name="only_owner"', page.text)
        self.assertIn('Your own games are always included.', page.text)
        with self.a.session_transaction() as session:
            csrf = session['stats_sources_csrf']
        self.assertEqual(self.a.post('/account/stats-sources/', data={
            'csrf': csrf, 'only_owner': 'kyle'}).status_code, 403)

    def test_tampering_and_writes_fail_without_falling_back(self):
        self.own_game(self.a, 'dan')
        link = self.a.get('/stats/2026/').location
        token = self.a.get(link).json['token']
        guest = self.app.test_client()
        for value in ['', 'dan', token + 'bad']:
            self.assertEqual(guest.get('/stats/2026/', query_string={'view': value}).status_code, 404)
        for method in ['POST', 'PUT', 'DELETE']:
            response = guest.open('/api/games', method=method, query_string={'view': token},
                                  json={'id': 2, 'name': 'Tampered'})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(guest.get('/admin', query_string={'view': token}).status_code, 403)
        self.assertEqual(self.a.get('/api/games').json['rows'], [[2, 'dan game']])
        self.assertEqual(guest.get('/api/games').json['rows'], [[1, 'Shared player']])

    def test_disabled_or_deleted_owner_invalidates_link(self):
        self.own_game(self.a, 'dan')
        link = self.a.get('/stats/2026/').location
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET active=0 WHERE username='dan'")
        self.assertEqual(self.app.test_client().get(link).status_code, 404)
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM private_accounts WHERE username='dan'")
        self.assertEqual(self.app.test_client().get(link).status_code, 404)

    def test_shared_foreign_source_revocation_and_admin_privacy(self):
        a = self.own_game(self.a, 'dan')
        b = self.own_game(self.b, 'bob')
        apply_rollout_to_existing_users(self.path)
        for client, headers in [(self.a, a), (self.b, b)]:
            client.put('/api/account/stats-sources', headers=headers, json={'owner': 'kyle', 'enabled': False})
        self.a.put('/api/account/stats-sharing', headers=a, json={'share_stats': True})
        self.b.put('/api/account/stats-sources', headers=b, json={'owner': 'dan', 'enabled': True})
        link = self.b.get('/stats/2026/').location
        guest = self.app.test_client()
        self.assertEqual({r[1] for r in guest.get(link).json['rows']}, {'dan game', 'bob game'})
        self.a.put('/api/account/stats-sharing', headers=a, json={'share_stats': False})
        self.assertEqual(guest.get(link).status_code, 404)
        admin = self.app.test_client()
        auth = {'Authorization': 'Bearer shared-token'}
        admin.put('/api/account/stats-sources', headers=auth, json={'owner': 'dan', 'enabled': True})
        page = admin.get('/stats/2026/')
        self.assertEqual(page.status_code, 200)
        self.assertIsNone(page.json['token'])
        self.assertEqual({r[1] for r in page.json['rows']}, {'Shared player', 'dan game', 'bob game'})


class SharedStatsSafetyTests(unittest.TestCase):
    register = SharedStatsLinkTests.register
    own_game = SharedStatsLinkTests.own_game

    def setUp(self):
        SharedStatsLinkTests.setUp(self)
        from content_safety import register_content_safety
        register_content_safety(self.app, self.service)

    def test_block_removes_selected_author_and_rejects_existing_share_links(self):
        a = self.own_game(self.a, 'dan')
        b = self.own_game(self.b, 'bob')
        apply_rollout_to_existing_users(self.path)
        for client, headers in [(self.a, a), (self.b, b)]:
            client.put('/api/account/stats-sources', headers=headers,
                       json={'owner': 'kyle', 'enabled': False})
        link = self.a.get('/stats/2026/').location
        combined = {**b, 'X-Stats-Combined': '1'}
        # Warm both snapshots and response caches before changing visibility.
        self.assertEqual({row[1] for row in self.b.get('/api/games', headers=combined).json['rows']},
                         {'dan game', 'bob game'})
        self.assertEqual(self.b.get(link).status_code, 200)
        blocked = self.b.post('/api/content/blocked-users', headers=b, json={'username': 'dan'})
        self.assertEqual(blocked.status_code, 200)
        sources = self.b.get('/api/account/stats-sources', headers=b).json['sources']
        self.assertNotIn('dan', [source['owner'] for source in sources])
        self.assertEqual(self.b.get('/api/games', headers=combined).json['rows'], [[2, 'bob game']])
        self.assertEqual(self.b.get(link).status_code, 404)
        self.assertEqual(self.app.test_client().get(link).status_code, 200)
        self.assertEqual(self.a.get('/api/games', headers=a).json['rows'], [[2, 'dan game']])
        self.b.delete('/api/content/blocked-users', headers=b, json={'username': 'dan'})
        self.assertEqual(self.b.get(link).status_code, 200)

    def test_suspension_revokes_links_but_keeps_owned_read_and_account_deletion(self):
        a = self.own_game(self.a, 'dan')
        b = self.own_game(self.b, 'bob')
        apply_rollout_to_existing_users(self.path)
        for client, headers in [(self.a, a), (self.b, b)]:
            client.put('/api/account/stats-sources', headers=headers,
                       json={'owner': 'kyle', 'enabled': False})
        link = self.a.get('/stats/2026/').location
        guest = self.app.test_client()
        self.assertEqual(guest.get(link).status_code, 200)
        combined = {**b, 'X-Stats-Combined': '1'}
        self.assertEqual(len(self.b.get('/api/games', headers=combined).json['rows']), 2)
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO content_suspensions(username) VALUES ('dan')")
        self.assertEqual(guest.get(link).status_code, 404)
        self.assertEqual(self.b.get('/api/games', headers=combined).json['rows'], [[2, 'bob game']])
        self.assertEqual(self.a.get('/api/games', headers=a).json['rows'], [[2, 'dan game']])
        own_page = self.a.get('/stats/2026/')
        self.assertEqual(own_page.status_code, 200)
        self.assertIsNone(own_page.json['token'])
        self.assertEqual(self.a.put('/api/games', headers=a,
                                   json={'id': 2, 'name': 'changed'}).status_code, 403)
        self.assertEqual(guest.get('/api/games').json['rows'], [[1, 'Shared player']])
        deleted = self.a.delete('/api/account', headers=a)
        self.assertEqual(deleted.status_code, 200, deleted.json)
        self.assertIsNone(account_for_user(self.path, 'dan'))

    def test_blocking_public_author_hides_their_stats_only_for_that_viewer(self):
        a = self.own_game(self.a, 'dan')
        self.a.put('/api/account/stats-sources', headers=a, json={'owner': 'kyle', 'enabled': True})
        guest = self.app.test_client()
        public_link = guest.get('/stats/2026/').location
        combined = {**a, 'X-Stats-Combined': '1'}
        self.assertEqual(len(self.a.get('/api/games', headers=combined).json['rows']), 2)
        self.a.post('/api/content/blocked-users', headers=a, json={'username': 'kyle'})
        self.assertEqual(self.a.get('/api/account/stats-sources', headers=a).json['sources'], [])
        self.assertEqual(self.a.get('/api/games', headers=combined).json['rows'], [[2, 'dan game']])
        self.assertEqual(self.a.get(public_link).status_code, 404)
        self.assertEqual(guest.get(public_link).json['rows'], [[1, 'Shared player']])
        self.assertEqual(guest.get('/api/games').json['rows'], [[1, 'Shared player']])


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

    def test_rollout_before_personal_separation_and_inactive_sources(self):
        from private_accounts import init_accounts
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET active=0 WHERE username='arbel'")
        init_accounts(str(self.path))
        init_stats_views(str(self.path))
        migrate(self.path)
        for user in ('tyler', 'dan'):
            self.assertTrue(account_for_user(self.path, user)['share_stats'])
            sources = sources_for_user(self.path, user)
            self.assertEqual({s['owner'] for s in sources}, {'kyle', 'dan' if user == 'tyler' else 'tyler'})
            self.assertTrue(all(s['enabled'] for s in sources))
        self.assertFalse(account_for_user(self.path, 'arbel')['share_stats'])


if __name__ == '__main__':
    unittest.main()
