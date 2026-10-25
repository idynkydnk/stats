import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from jinja2 import FileSystemLoader
from private_accounts import account_for_user, provision_database
from season_stats import group_standings, season_status
from seasons import register_seasons, validate_season
from tests import test_private_accounts as fixtures


class SeasonTests(unittest.TestCase):
    register = fixtures.PrivateAccountTests.register

    def setUp(self):
        fixtures.PrivateAccountTests.setUp(self)
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''DROP TABLE games;
                CREATE TABLE games(id INTEGER PRIMARY KEY, game_date TEXT, winner1 TEXT, winner2 TEXT,
                    winner_score INTEGER, loser1 TEXT, loser2 TEXT, loser_score INTEGER,
                    entered_by TEXT, division TEXT DEFAULT 'open');
                CREATE TABLE vollis_games(id INTEGER PRIMARY KEY, game_date TEXT, winner TEXT,
                    winner_score INTEGER, loser TEXT, loser_score INTEGER, entered_by TEXT);
                CREATE TABLE other_games(id INTEGER PRIMARY KEY, game_date TEXT, game_name TEXT,
                    game_type TEXT, winner1 TEXT, loser1 TEXT, winner_score INTEGER, loser_score INTEGER,
                    entered_by TEXT, is_tie INTEGER DEFAULT 0);''')
        register_seasons(self.app, self.service)
        self.app.jinja_loader = FileSystemLoader(str(Path(__file__).resolve().parents[1] / 'templates'))
        # Render the real base/menu; the test app does not need unrelated implementations.
        for endpoint in ('index', 'login', 'logout', 'stats_default', 'stats_sources_page', 'player_list',
                         'my_ai_recaps', 'my_ai_flyers', 'ai_summary', 'create_flyer'):
            if endpoint not in self.app.view_functions:
                self.app.add_url_rule('/stub/' + endpoint, endpoint, lambda: '')
        self.headers = self.register(self.a, 'alice')
        self.other_headers = self.register(self.b, 'bob')
        account = account_for_user(self.path, 'alice')
        self.own_path = provision_database(self.path, account['id'])
        self.defaults = dict(name='Winter league', start_date='2025-12-31', end_date='2026-01-02',
                             minimum_mode='automatic', timezone='America/Los_Angeles')

    def create(self, **changes):
        result = self.a.post('/api/seasons', headers=self.headers, json=dict(self.defaults, **changes))
        self.assertEqual(result.status_code, 201, result.text)
        return result.json

    def game(self, ident, day='2026-01-01', winner='A', loser='C', owner='alice', path=None, division='open'):
        with sqlite3.connect(path or self.own_path) as conn:
            conn.execute('INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (ident, day, winner, 'B', 21, loser, 'D', 15, owner, division))

    def get(self, season):
        return self.a.get('/api/seasons/' + season['id'], headers=self.headers).json

    def test_owned_entries_only_inclusive_dates_and_ignored_browse_filters(self):
        for ident, day in enumerate(('2025-12-30 23:59:59', '2025-12-31 00:00:00',
                                    '2026-01-02 23:59:59.999', '2026-01-03 00:00:00'), 1):
            self.game(ident, day)
        self.game(5, owner='bob', winner='Foreign')
        self.game(1, path=self.path, owner='alice', winner='Wrong database')
        result = self.create()
        self.assertEqual(result['game_count'], 2)
        self.assertEqual(result['groups'][0]['stats'][0]['games'], 2)
        self.assertNotIn('Foreign', json.dumps(result))
        self.assertNotIn('Wrong database', json.dumps(result))
        alternate = self.a.get('/api/seasons/' + result['season']['id'] + '?location=Missing&start_date=1900-01-01&end_date=1900-01-01', headers=self.headers)
        self.assertEqual(alternate.json, result)
        self.assertEqual(self.a.get('/api/seasons/' + result['season']['id'] + '?view=bad', headers=self.headers).status_code, 403)

    def test_admin_also_only_sees_original_entries(self):
        self.game(1, path=self.path, owner='Kyle', winner='Kyle entry')
        self.game(2, path=self.path, owner='alice', winner='Alice entry')
        client = self.app.test_client()
        result = client.post('/api/seasons', headers={'Authorization': 'Bearer shared-token'}, json=self.defaults)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json['game_count'], 1)
        self.assertNotIn('Alice entry', result.text)

    def test_automatic_threshold_grows_and_fixed_minimum_can_be_changed(self):
        for i in range(60):
            self.game(i + 1, winner='Rare' if i == 0 else 'A')
        result = self.create()
        group = result['groups'][0]
        self.assertEqual(group['minimum_games'], 2)
        self.assertEqual(group['rare_stats'][0]['name'], 'Rare')
        self.assertEqual(group['rare_stats'][0]['games_needed'], 1)
        sid = result['season']['id']
        for mode, minimum, expected in [('fixed', 3, 3), ('automatic', 999, 2)]:
            updated = self.a.put('/api/seasons/' + sid, headers=self.headers,
                                 json=dict(self.defaults, minimum_mode=mode, minimum_games=minimum))
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json['groups'][0]['minimum_games'], expected)
        self.game(61, winner='Rare')
        self.assertEqual(self.get(result['season'])['groups'][0]['rare_stats'], [])

    def test_separate_formats_divisions_and_ties(self):
        self.game(1)
        self.game(2, division='women')
        with sqlite3.connect(self.own_path) as conn:
            conn.execute("INSERT INTO vollis_games VALUES (1,'2026-01-01','Solo',21,'Rival',15,'alice')")
            conn.execute("INSERT INTO other_games VALUES (1,'2026-01-01','Sequence','Board games','Solo','Rival',1,1,'alice',1)")
            conn.execute("INSERT INTO other_games VALUES (2,'2026-01-01','Uno','Card games','Solo','Rival',1,0,'alice',0)")
        result = self.create()
        self.assertEqual(len(result['groups']), 5)
        sequence = next(g for g in result['groups'] if g['title'] == 'Sequence')
        self.assertFalse(sequence['rating_enabled'])
        self.assertEqual(sequence['stats'][0]['ties'], 1)
        self.assertEqual(sequence['stats'][0]['wins'], 0)
        self.assertEqual(sequence['stats'][0]['losses'], 0)
        uno = next(g for g in result['groups'] if g['title'] == 'Uno')
        self.assertEqual(uno['award_metric'], 'win_pct')
        self.assertEqual(uno['champions'][0]['name'], 'Solo')

    def test_rating_matches_existing_doubles_and_improvement_uses_end_of_first_day(self):
        from stat_functions import _calculate_trueskill_from_games
        self.game(1, day='2025-12-31 10:00:00')
        self.game(2, day='2025-12-31 11:00:00')
        self.game(3, day='2026-01-02 10:00:00')
        with sqlite3.connect(self.own_path) as conn:
            rows = conn.execute('SELECT * FROM games ORDER BY game_date,id').fetchall()
        expected = {p['player']: p['rating'] for p in _calculate_trueskill_from_games(rows)}
        first_day = {p['player']: p['rating'] for p in _calculate_trueskill_from_games(rows[:2])}
        result = self.create()
        group = result['groups'][0]
        for row in group['stats']:
            self.assertEqual(row['rating'], expected[row['name']])
            self.assertEqual(row['first_rating'], first_day[row['name']])
            self.assertEqual(row['rating_gain'], round(row['rating'] - row['first_rating'], 2))
        self.assertEqual({r['name'] for r in group['champions']}, {'A', 'B'})
        self.assertTrue(group['most_improved'])
        # Preseason games never seed the baseline or rating.
        self.game(4, day='2025-12-30', winner='C', loser='A')
        self.assertEqual(self.get(result['season'])['groups'], result['groups'])
        with sqlite3.connect(self.own_path) as conn:
            conn.execute('DELETE FROM games WHERE id=3')
        self.assertEqual(self.get(result['season'])['groups'][0]['most_improved'], [])

    def test_champions_board_completed_only_and_qualification(self):
        self.game(1)
        completed = self.create()['season']
        self.create(name='Future', start_date='2099-01-01', end_date='2099-12-31')
        self.create(name='No eligible players', minimum_mode='fixed', minimum_games=100)
        library = self.a.get('/api/seasons', headers=self.headers).json
        self.assertEqual(len(library['seasons']), 3)
        self.assertEqual({r['season_id'] for r in library['champions']}, {completed['id']})
        self.assertEqual({r['name'] for r in library['champions']}, {'A', 'B'})
        self.assertEqual(season_status(completed, '2026-01-02'), 'Active')
        self.assertEqual(season_status(completed, '2025-12-30'), 'Upcoming')
        self.assertEqual(season_status(completed, '2026-01-03'), 'Completed')

    def test_private_crud_sharing_revocation_and_account_deletion(self):
        self.game(1, winner='Private athlete')
        season = self.create()['season']
        sid = season['id']
        self.assertIsNone(season['share_url'])
        outsider = self.app.test_client()
        self.assertEqual(outsider.get('/api/seasons/' + sid).status_code, 401)
        for method in ('get', 'put', 'delete'):
            result = getattr(self.b, method)('/api/seasons/' + sid, headers=self.other_headers, json=self.defaults)
            self.assertEqual(result.status_code, 404)
        self.assertEqual(self.b.post('/api/seasons/' + sid + '/share', headers=self.other_headers).status_code, 404)
        shared = self.a.post('/api/seasons/' + sid + '/share', headers=self.headers).json['season']['share_url']
        path = urlsplit(shared).path
        response = outsider.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(b'Private athlete', response.data)
        self.assertNotIn(b'Edit season', response.data)
        self.assertNotIn(b'Delete season', response.data)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn('noindex', response.headers['X-Robots-Tag'])
        self.assertEqual(outsider.post(path, data=self.defaults).status_code, 405)
        self.assertEqual(self.b.get(path, headers=self.other_headers).status_code, 200)
        self.a.delete('/api/seasons/' + sid + '/share', headers=self.headers)
        self.assertEqual(outsider.get(path).status_code, 404)
        again = self.a.post('/api/seasons/' + sid + '/share', headers=self.headers).json['season']['share_url']
        self.assertNotEqual(shared, again)
        self.assertEqual(self.a.delete('/api/account', headers=self.headers).status_code, 200)
        self.assertEqual(outsider.get(urlsplit(again).path).status_code, 404)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM seasons').fetchone()[0], 0)

    def test_web_form_csrf_validation_rendering_and_scoped_player_links(self):
        form = self.a.get('/seasons/new/', headers=self.headers)
        self.assertEqual(form.status_code, 200)
        self.assertIn(b'divide the number of games', form.data)
        self.assertIn(b'90 games', form.data)
        with self.a.session_transaction() as session:
            csrf = session['season_csrf']
        self.assertEqual(self.a.post('/seasons/new/', data=self.defaults).status_code, 400)
        saved = self.a.post('/seasons/new/', data=dict(self.defaults, csrf_token=csrf))
        self.assertEqual(saved.status_code, 302)
        self.game(1, winner='Zoë & <script>')
        page = self.a.get(saved.location)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Zo', page.data)
        self.assertNotIn(b'Zo\xc3\xab & <script>', page.data)
        sid = saved.location.strip('/').split('/')[1]
        player = self.a.get('/api/seasons/' + sid, headers=self.headers,
                            query_string={'group': 'doubles:open', 'player': 'Zoë & <script>'})
        self.assertEqual(player.status_code, 200)
        self.assertEqual(len(player.json['player']['games']), 1)
        page = self.a.get(saved.location, query_string={'group': 'doubles:open', 'player': 'Zoë & <script>'})
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Games in this season', page.data)
        self.assertEqual(self.a.get('/seasons/').status_code, 200)
        deleted = self.a.post(saved.location + 'delete/', data={'csrf_token': csrf})
        self.assertEqual(deleted.status_code, 302)
        with sqlite3.connect(self.own_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM games').fetchone()[0], 1)

    def test_bad_input_and_auth_never_save(self):
        for changes in ({'name': ''}, {'name': 'x' * 81}, {'name': 42}, {'start_date': '2026-02-30'},
                        {'start_date': '2026-01-03'}, {'minimum_mode': 'bad'}, {'minimum_mode': []},
                        *({'minimum_mode': 'fixed', 'minimum_games': x} for x in (0, -1, 1.5, True, '1.0', None, 100001)),
                        {'timezone': 'nowhere'}, {'timezone': ['bad']}, {'start_date': None}):
            with self.subTest(changes=changes):
                self.assertEqual(self.a.post('/api/seasons', headers=self.headers, json=dict(self.defaults, **changes)).status_code, 400)
        self.assertEqual(self.a.post('/api/seasons', headers=self.headers, json=['bad']).status_code, 400)
        self.assertEqual(self.a.get('/api/seasons', headers=self.headers).json['seasons'], [])
        self.assertEqual(self.app.test_client().post('/api/seasons', json=self.defaults).status_code, 401)
        self.assertEqual(self.a.post('/api/seasons', headers={'Authorization': 'Bearer bad'}, json=self.defaults).status_code, 401)
        self.assertEqual(self.a.post('/api/seasons', headers={**self.headers, 'X-Stats-Preview': '1'}, json=self.defaults).status_code, 403)

    def test_incomplete_doubles_roster_does_not_break_ratings(self):
        self.game(1)
        with sqlite3.connect(self.own_path) as conn:
            conn.execute("UPDATE games SET winner2='', loser2='' WHERE id=1")
        result = self.create()
        self.assertEqual(result['groups'][0]['unrated_games'], 1)
        self.assertEqual(result['groups'][0]['stats'][0]['games'], 1)

    def test_shared_player_link_updates_with_edits_and_honors_restrictions(self):
        self.game(1)
        season = self.create()['season']
        sid = season['id']
        shared = self.a.post('/api/seasons/' + sid + '/share', headers=self.headers).json['season']['share_url']
        path = urlsplit(shared).path
        visitor = self.app.test_client()
        response = visitor.get(path, query_string={'group': 'doubles:open', 'player': 'A'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Games in this season', response.data)
        self.assertNotIn(b'Edit season', response.data)
        self.assertEqual(visitor.get(path, query_string={'group': 'doubles:open', 'player': 'Not here'}).status_code, 404)
        updated = self.a.put('/api/seasons/' + sid, headers=self.headers,
                             json=dict(self.defaults, name='New name', minimum_mode='fixed', minimum_games=100)).json
        self.assertEqual(updated['season']['share_url'], shared)
        self.assertIn(b'New name', visitor.get(path).data)
        self.assertIn(b'99 more games', visitor.get(path).data)
        with patch('content_safety.restricted_authors', return_value={'alice'}):
            self.assertEqual(visitor.get(path).status_code, 404)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET active=0 WHERE username='alice'")
        self.assertEqual(visitor.get(path).status_code, 404)

    def test_web_navigation_keeps_the_selected_game_and_cancel_returns_to_season(self):
        from bs4 import BeautifulSoup
        from urllib.parse import parse_qs
        self.game(1)
        self.game(2, division='women')
        sid = self.create()['season']['id']
        path = '/seasons/' + sid + '/'
        page = self.a.get(path, headers=self.headers, query_string={'group': 'doubles:women'})
        html = BeautifulSoup(page.data, 'html.parser')
        visible = [group for group in html.select('[data-season-group]') if not group.has_attr('hidden')]
        self.assertEqual([group['data-season-group'] for group in visible], ['doubles:women'])
        self.assertEqual(html.select_one('#season-group option[selected]')['value'], 'doubles:women')
        self.assertEqual(html.select_one('[data-season-group-field]')['value'], 'doubles:women')
        edit_url = html.select_one('[data-season-group-link]')['href']
        edit = BeautifulSoup(self.a.get(edit_url, headers=self.headers).data, 'html.parser')
        cancel = next(a['href'] for a in edit.select('a') if a.get_text(strip=True) == 'Cancel')
        self.assertEqual(urlsplit(cancel).path, path)
        self.assertEqual(parse_qs(urlsplit(cancel).query)['group'], ['doubles:women'])
        player_link = visible[0].select_one('.sr-player a')['href']
        player = BeautifulSoup(self.a.get(player_link, headers=self.headers).data, 'html.parser')
        back = next(a['href'] for a in player.select('.season-header a') if 'Back to season' in a.get_text())
        self.assertEqual(urlsplit(back).path, path)
        self.assertEqual(parse_qs(urlsplit(back).query)['group'], ['doubles:women'])
        self.assertNotIn('player', parse_qs(urlsplit(back).query))
        # Shared player pages keep the public path when going back as well.
        shared = self.a.post('/api/seasons/' + sid + '/share', headers=self.headers).json['season']['share_url']
        public = self.app.test_client().get(urlsplit(shared).path, query_string={'group': 'doubles:women', 'player': 'A'})
        back = BeautifulSoup(public.data, 'html.parser').select_one('.season-header a')['href']
        self.assertEqual(urlsplit(back).path, urlsplit(shared).path)
        self.assertEqual(parse_qs(urlsplit(back).query)['group'], ['doubles:women'])

    def test_web_edit_errors_keep_values_and_share_actions_keep_navigation(self):
        from bs4 import BeautifulSoup
        from urllib.parse import parse_qs
        sid = self.create()['season']['id']
        path = '/seasons/' + sid + '/'
        page = self.a.get(path + 'edit/', headers=self.headers)
        csrf = BeautifulSoup(page.data, 'html.parser').select_one('[name=csrf_token]')['value']
        values = dict(self.defaults, csrf_token=csrf, group='doubles:open', name='My changes', minimum_mode='fixed', minimum_games='12')
        failed = self.a.post(path + 'edit/', data=dict(values, end_date='2025-01-01'))
        self.assertEqual(failed.status_code, 400)
        html = BeautifulSoup(failed.data, 'html.parser')
        self.assertEqual(html.select_one('#season-name')['value'], 'My changes')
        self.assertEqual(html.select_one('#season-minimum')['value'], '12')
        self.assertEqual(html.select_one('#season-minimum-mode option[selected]')['value'], 'fixed')
        self.assertIsNotNone(html.select_one('#season-form-error[tabindex="-1"]'))
        saved = self.a.post(path + 'edit/', data=values)
        self.assertEqual(parse_qs(urlsplit(saved.location).query)['group'], ['doubles:open'])
        for action in ('start', 'stop'):
            response = self.a.post(path + 'share/', data={'csrf_token': csrf, 'group': 'doubles:women', 'action': action})
            self.assertEqual(parse_qs(urlsplit(response.location).query), {'group': ['doubles:women'], 'sharing': ['1']})
        self.assertIsNone(self.a.get('/api/seasons/' + sid, headers=self.headers).json['season']['share_url'])


if __name__ == '__main__':
    unittest.main()
