import sqlite3
import unittest

from flask import jsonify, session

from player_suggestions import entry_player_names
from private_accounts import account_for_user, connect_data, provision_database
from tests.test_private_accounts import PrivateAccountTests


class EntryPlayerNamesTests(unittest.TestCase):
    setUp = PrivateAccountTests.setUp
    register = PrivateAccountTests.register

    def install_pages(self):
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                ALTER TABLE games ADD COLUMN division TEXT DEFAULT 'open';
                CREATE TABLE vollis_games(id INTEGER PRIMARY KEY, winner TEXT, loser TEXT);
                INSERT INTO vollis_games VALUES (1, 'Vollis Only', ' Shared player ');
                CREATE TABLE other_games(id INTEGER PRIMARY KEY, winner15 TEXT, loser15 TEXT);
                INSERT INTO other_games VALUES (1, 'Last Winner Slot', 'Last Loser Slot');
                INSERT INTO games VALUES (3, 'Women Only', 'women');
                INSERT INTO players VALUES (2, 'Roster Only');
            ''')

        def form():
            with connect_data(self.path) as conn:
                own_games = conn.execute('SELECT winner1 FROM games').fetchall()
            return jsonify(names=entry_player_names(self.path, ['Recent Player'], session['username'],
                                                    self.service.is_admin(session['username'])),
                           games=own_games)

        for endpoint in ('add_game', 'add_vollis_game', 'add_other_game'):
            self.app.add_url_rule('/' + endpoint + '/', endpoint, form)

    def test_all_pages_all_accounts_include_full_sources_without_changing_game_scope(self):
        self.install_pages()
        alice_headers = self.register(self.a, 'alice')
        bob_headers = self.register(self.b, 'bob')
        bob = account_for_user(self.path, 'bob')
        with sqlite3.connect(provision_database(self.path, bob['id'])) as conn:
            conn.execute("INSERT INTO players VALUES (9, 'Bob Private')")
        shared = {'Shared player', 'Vollis Only', 'Last Winner Slot', 'Last Loser Slot',
                  'Women Only', 'Roster Only', 'Recent Player'}
        for client, headers, own in ((self.a, alice_headers, set()), (self.b, bob_headers, {'Bob Private'})):
            for page in ('add_game', 'add_vollis_game', 'add_other_game'):
                response = client.get('/' + page + '/', headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(set(response.json['names']), shared | own)
                self.assertEqual(response.json['names'][0], 'Recent Player')
                self.assertEqual(response.json['names'].count('Shared player'), 1)
                self.assertEqual(response.json['games'], [], 'Today’s games must stay owned')
        self.a.put('/api/account/stats-sources', headers=alice_headers,
                   json={'owner': 'kyle', 'enabled': False})
        for page in ('add_game', 'add_vollis_game', 'add_other_game'):
            self.assertEqual(self.a.get('/' + page + '/', headers=alice_headers).json['names'], ['Recent Player'])
        kyle = self.app.test_client()
        headers = {'Authorization': 'Bearer shared-token', 'X-Stats-Account-Required': '1'}
        self.assertEqual(set(kyle.get('/add_game/', headers=headers).json['names']), shared)

    def test_womens_list_stays_separate_including_enabled_sources(self):
        self.install_pages()

        @self.app.get('/women', endpoint='get_players')
        def women():
            return jsonify(entry_player_names(self.path, ['Jen Weston'], session['username'], women_only=True))

        headers = self.register(self.a, 'alice')
        self.assertEqual(self.a.get('/women', headers=headers).json, ['Jen Weston', 'Women Only'])
        self.a.put('/api/account/stats-sources', headers=headers, json={'owner': 'kyle', 'enabled': False})
        self.assertEqual(self.a.get('/women', headers=headers).json, ['Jen Weston'])


if __name__ == '__main__':
    unittest.main()
