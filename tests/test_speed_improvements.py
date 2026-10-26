"""Regression coverage for bounded browsing, prepared data, and incremental KOBs."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask, g, jsonify

from game_browse_page import game_page
from image_previews import register_image_previews
from performance_metrics import register_performance
from prepared_calculations import reuse_calculation
from stats_snapshot_cache import prepared_snapshot
from stats_response_cache import StatsResponseCache
from tests import test_private_accounts as fixtures


class PagedGamesTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript('''CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
            winner1 TEXT, loser1 TEXT, comments TEXT, division TEXT);
            CREATE TABLE other_games (id INTEGER PRIMARY KEY, game_date TEXT,
            winner1 TEXT, loser1 TEXT, game_name TEXT);''')
        self.conn.executemany('INSERT INTO games VALUES (?, ?, ?, ?, ?, ?)',
            [(i, '2026-01-01', 'Rare player' if i == 1 else 'A', 'B', '100% real', 'open') for i in range(1, 132)])
        self.conn.execute("INSERT INTO games VALUES (200, '2025-01-01', 'Earlier', 'B', '', 'women')")
        self.app = Flask(__name__)

    def test_pages_preserve_total_order_and_full_history_search(self):
        collected = []
        for offset, expected_next in [(0, 50), (50, 100), (100, None)]:
            with self.app.test_request_context(f'/?year=2026&limit=50&offset={offset}'):
                rows, page = game_page(self.conn, 'games')
                collected += [row['id'] for row in rows]
                self.assertEqual(page, dict(total=131, next_offset=expected_next))
        self.assertEqual(collected, list(range(131, 0, -1)))
        for query, expected in [('Rare,player', 1), ('100%25', 131), ('missing', 0)]:
            with self.app.test_request_context('/?year=2026&limit=50&q=' + query):
                rows, page = game_page(self.conn, 'games')
                self.assertEqual(page['total'], expected)
                self.assertLessEqual(len(rows), 50)

    def test_other_search_includes_fifteenth_player_and_unicode(self):
        self.conn.execute('ALTER TABLE other_games ADD COLUMN winner15 TEXT')
        self.conn.execute("INSERT INTO other_games VALUES (1, '2026-01-01', 'A', 'B', 'Coed', 'JOSÉ')")
        with self.app.test_request_context('/?q=josé&limit=50'):
            rows, page = game_page(self.conn, 'other_games')
            self.assertEqual([row['id'] for row in rows], [1])

    def test_bounds_filters_and_other_game_selection(self):
        from stats_location_filter import filter_stats_connection
        self.app.add_url_rule('/games', endpoint='api_doubles_list')
        with self.app.test_request_context('/games?division=women&limit=5000&offset=-4'):
            filter_stats_connection(self.conn, 'games')
            rows, page = game_page(self.conn, 'games')
            self.assertEqual([row['id'] for row in rows], [200])
        self.conn.executemany('INSERT INTO other_games VALUES (?, ?, ?, ?, ?)',
                             [(1, '2026-01-01', 'A', 'B', 'Chess'), (2, '2026-01-01', 'C', 'D', 'Cards')])
        with self.app.test_request_context('/?game_name=Chess&limit=bad&offset=bad'):
            rows, page = game_page(self.conn, 'other_games')
            self.assertEqual([row['id'] for row in rows], [1])


class PreparedDataTests(unittest.TestCase):
    setUp = fixtures.PrivateAccountTests.setUp
    register = fixtures.PrivateAccountTests.register

    def test_two_combined_requests_reuse_raw_snapshot_but_edits_refresh(self):
        from account_stats_views import build_stats_view
        headers = {**self.register(self.a, 'alice'), 'X-Stats-Combined': '1'}
        with patch('account_stats_views.build_stats_view', wraps=build_stats_view) as build:
            self.assertEqual(self.a.get('/api/games', headers=headers).status_code, 200)
            self.assertEqual(self.a.get('/api/games', headers=headers).status_code, 200)
            self.assertEqual(build.call_count, 1)
            with sqlite3.connect(self.path) as conn:
                conn.execute("UPDATE games SET winner1='Updated'")
            self.assertIn('Updated', str(self.a.get('/api/games', headers=headers).json))
            self.assertEqual(build.call_count, 2)

    def test_personal_accounts_can_load_previews_and_send_timings(self):
        self.app.add_url_rule('/preview', 'image_preview', lambda: 'preview')
        register_performance(self.app, lambda: False)
        headers = self.register(self.a, 'alice')
        self.assertEqual(self.a.get('/preview', headers=headers).status_code, 200)
        self.assertEqual(self.a.post('/performance-sample', headers=headers,
                                    json=[dict(action='tap', milliseconds=12)]).status_code, 204)
        self.assertEqual(self.a.get('/api/admin/performance', headers=headers).status_code, 403)

    def test_sport_invalidation_does_not_discard_unrelated_responses(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute('CREATE TABLE vollis_games (id INTEGER PRIMARY KEY, winner TEXT)')
        cache = self.app.extensions['stats_response_cache']
        doubles = cache.prepare([(self.path, 0)], 'viewer', 'api_doubles_stats', [], 'open')
        vollis = cache.prepare([(self.path, 0)], 'viewer', 'api_vollis_stats', [], 'open')
        cache.save(doubles, b'doubles')
        cache.save(vollis, b'vollis')
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO vollis_games VALUES (1, 'A')")
        self.assertEqual(cache.load(doubles), b'doubles')
        self.assertIsNone(cache.load(vollis))

    def test_player_response_path_parameters_cannot_collide(self):
        calls = []
        def player(name):
            calls.append(name)
            return jsonify(name=name)
        self.app.add_url_rule('/api/player/<name>', 'api_doubles_player', player)
        for name in ['Alice', 'Bob', 'Alice', 'Bob']:
            self.assertEqual(self.a.get('/api/player/' + name).json['name'], name)
        self.assertEqual(calls, ['Alice', 'Bob'])

    def test_calculations_return_copies_and_change_with_authorized_revision(self):
        calls = []
        def calculate():
            calls.append(1)
            return ['original']
        with self.app.test_request_context('/'):
            g.stats_data_revision = 'first'
            reuse_calculation(calculate, (), {}).append('changed')
            self.assertEqual(reuse_calculation(calculate, (), {}), ['original'])
            g.stats_data_revision = 'second'
            self.assertEqual(reuse_calculation(calculate, (), {}), ['original'])
        self.assertEqual(len(calls), 2)

    def test_website_calculations_keep_unrelated_sports_warm(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute('CREATE TABLE vollis_games (id INTEGER PRIMARY KEY, winner TEXT)')
        calls = []
        def calculate():
            calls.append(1)
            with closing(sqlite3.connect(self.path)) as conn:
                return conn.execute('SELECT winner1 FROM games').fetchall()
        calculate.__module__ = 'stat_functions'
        def read():
            with self.app.test_request_context('/'):
                g.stats_data_revision = 'fallback'
                g.stats_source_databases = [(self.path, 0)]
                return reuse_calculation(calculate, (), {})
        self.assertEqual(read(), [('Shared player',)])
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO vollis_games VALUES (1, 'A')")
        self.assertEqual(read(), [('Shared player',)])
        self.assertEqual(len(calls), 1)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE games SET winner1='Edited'")
        self.assertEqual(read(), [('Edited',)])
        self.assertEqual(len(calls), 2)


class IncrementalTournamentTests(unittest.TestCase):
    def test_only_changed_groups_revalidate_and_sessions_are_atomic(self):
        import kob_functions as kob
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'games.db')
            with sqlite3.connect(path) as conn:
                conn.executescript('''CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
                    winner1 TEXT, winner2 TEXT, loser1 TEXT, loser2 TEXT, winner_score INTEGER, loser_score INTEGER);
                    CREATE TABLE sessions (id INTEGER PRIMARY KEY, session_number INTEGER, start_time TEXT,
                    end_time TEXT, total_games INTEGER, doubles_games INTEGER, vollis_games INTEGER,
                    one_v_one_games INTEGER, other_games INTEGER, created_at TEXT);''')
                conn.executemany('INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, 21, 10)', [
                    (1, '2026-01-01 10:00:00', 'A', 'B', 'C', 'D'),
                    (2, '2026-01-01 10:30:00', 'A', 'C', 'B', 'D'),
                    (3, '2026-01-01 11:00:00', 'A', 'D', 'B', 'C'),
                    (4, '2026-01-02 10:00:00', 'A', 'B', 'C', 'D'),
                ])
            with patch.object(kob, 'create_connection', side_effect=lambda _: sqlite3.connect(path)), \
                 patch.object(kob, 'validate_kob', wraps=kob.validate_kob) as validate:
                kob.update_kobs()
                self.assertEqual(validate.call_count, 2)
                kob.update_kobs()
                self.assertEqual(validate.call_count, 2)
                with sqlite3.connect(path) as conn:
                    before = conn.execute('SELECT * FROM sessions').fetchall()
                    self.assertEqual(len(before), 1)
                    conn.execute('UPDATE games SET winner_score=22 WHERE id=4')
                kob.update_kobs()
                self.assertEqual(validate.call_count, 3)
                with sqlite3.connect(path) as conn:
                    self.assertEqual(conn.execute('SELECT * FROM sessions').fetchall(), before)
                    conn.execute('UPDATE games SET winner_score=23 WHERE id=1')
                with patch.object(kob, 'validate_kob', side_effect=RuntimeError('failed')):
                    with self.assertRaises(RuntimeError):
                        kob.update_kobs()
                with sqlite3.connect(path) as conn:
                    self.assertEqual(conn.execute('SELECT * FROM sessions').fetchall(), before)
                    conn.execute('DELETE FROM games WHERE id=1')
                kob.update_kobs()
                with sqlite3.connect(path) as conn:
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)


class BrowseRouteTests(unittest.TestCase):
    def test_actual_game_routes_return_bounded_serialized_pages(self):
        import ast
        from mobile_game_sync import local_game_snapshot, idempotent_game
        import ios_api
        from types import SimpleNamespace
        from flask import request
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'games.db')
            with sqlite3.connect(path) as conn:
                conn.executescript('''CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT, winner1 TEXT);
                    CREATE TABLE vollis_games (id INTEGER PRIMARY KEY, game_date TEXT, winner TEXT, loser TEXT);
                    CREATE TABLE other_games (id INTEGER PRIMARY KEY, game_date TEXT, game_name TEXT, winner1 TEXT);''')
                for table, extra in [('games', "'A'"), ('vollis_games', "'A', 'B'"), ('other_games', "'Chess', 'A'")]:
                    conn.executemany(f"INSERT INTO {table} VALUES (?, '2026-01-01', {extra})", [(i,) for i in range(1, 132)])
            app = Flask(__name__)
            with patch.object(ios_api, '_ensure_deleted_table'):
                ios_api.register_ios_api(app)
            source = Path(__file__).resolve().parents[1] / 'stats.py'
            nodes = [n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef)
                     and n.name in {'api_doubles_list', '_api_game_row_to_dict'}]
            namespace = dict(app=app, request=request, jsonify=jsonify, sqlite3=sqlite3, _api_get_db=lambda: path)
            namespace.update(local_game_snapshot=local_game_snapshot, idempotent_game=idempotent_game)
            exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
            with patch.object(ios_api, '_S', return_value=SimpleNamespace(_stats_db_path=lambda: path)):
                for kind in ['doubles', 'vollis', 'other']:
                    first = app.test_client().get(f'/api/{kind}/games?limit=50&year=2026')
                    self.assertEqual(first.status_code, 200)
                    self.assertEqual(first.json['total'], 131)
                    self.assertEqual(first.json['next_offset'], 50)
                    self.assertEqual([r['id'] for r in first.json['games']], list(range(131, 81, -1)))
                    last = app.test_client().get(f'/api/{kind}/games?limit=50&offset=100&year=2026')
                    self.assertIsNone(last.json['next_offset'])
                    self.assertEqual(len(last.json['games']), 31)

    def test_combined_other_cards_use_the_same_fallback_year(self):
        from contextlib import ExitStack
        from datetime import date
        from types import SimpleNamespace
        import ios_api
        import other_functions as other
        app = Flask(__name__)
        with patch.object(ios_api, '_ensure_deleted_table'):
            ios_api.register_ios_api(app)
        current = str(date.today().year)
        previous = str(date.today().year - 1)
        service = SimpleNamespace(build_other_game_cards=lambda year: [dict(game_name='Chess', stats=[])],
                                  build_volleyball_game_cards_styled=lambda year: [dict(game_name='Volleyball ' + year, stats=[])])
        with ExitStack() as stack:
            stack.enter_context(patch.object(ios_api, '_S', return_value=service))
            for name, value in [('all_other_years', [previous]), ('other_year_games', []),
                                ('rare_other_stats_per_year', []), ('todays_other_stats_by_game', []),
                                ('todays_other_games', [])]:
                stack.enter_context(patch.object(other, name, return_value=value))
            stack.enter_context(patch.object(other, 'other_stats_per_year', side_effect=lambda year, minimum: [] if year == current else [['A', 1, 0, 1.0]]))
            result = app.test_client().get('/api/other/stats?year=' + current + '&include_volleyball=1').json
            self.assertTrue(result['includes_volleyball'])
            self.assertEqual(result['display_year'], previous)
            self.assertEqual([card['game_name'] for card in result['game_cards']], ['Chess', 'Volleyball ' + previous])


class PreviewAndTimingTests(unittest.TestCase):
    def test_previews_are_small_versioned_and_restrict_paths(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'static/email_images').mkdir(parents=True)
            original = root / 'static/email_images/test.png'
            Image.new('RGB', (1800, 1200), 'red').save(original)
            app = Flask(__name__, static_folder=str(root / 'static'))
            app.config['IMAGE_PREVIEW_CACHE_DIR'] = str(root / 'previews')
            register_image_previews(app)
            client = app.test_client()
            with app.test_request_context('/'):
                first = app.extensions['image_preview_url']('/static/email_images/test.png')
            result = client.get(first)
            self.assertEqual(result.status_code, 200)
            import io
            with Image.open(io.BytesIO(result.data)) as preview:
                self.assertEqual(preview.width, 640)
            self.assertEqual(client.get(first, headers={'If-None-Match': result.headers['ETag']}).status_code, 304)
            (root / 'static/player_photos').mkdir()
            photo = root / 'static/player_photos/face.png'
            Image.new('RGB', (1400, 2100), 'blue').save(photo)
            with app.test_request_context('/'):
                preview_url = app.extensions['image_preview_url']('/static/player_photos/face.png')
            with Image.open(io.BytesIO(client.get(preview_url).data)) as preview:
                self.assertEqual(preview.height, 640)
            with Image.open(photo) as original_photo:
                self.assertEqual(original_photo.size, (1400, 2100))
            for path in ['../secret.png', 'email_images/../../secret.png', 'player_photos/private.png']:
                self.assertEqual(client.get('/image-preview/' + path).status_code, 404)
            original.unlink()
            self.assertEqual(client.get(first).status_code, 404)

    def test_metrics_are_bounded_private_and_do_not_store_user_labels(self):
        app = Flask(__name__)
        allowed = [False]
        register_performance(app, lambda: allowed[0])
        app.add_url_rule('/test', view_func=lambda: 'ok')
        client = app.test_client()
        self.assertIn('app;dur=', client.get('/test?secret=never-store').headers['Server-Timing'])
        self.assertEqual(client.get('/api/admin/performance').status_code, 403)
        client.post('/performance-sample', json=[dict(action='secret-player', milliseconds=123)])
        for _ in range(30):
            client.post('/performance-sample', json=[dict(action='tap', milliseconds=23)] * 12)
        allowed[0] = True
        samples = client.get('/api/admin/performance').json['samples']
        self.assertEqual(len(samples), 256)
        self.assertNotIn('secret', str(samples))
        self.assertEqual(client.post('/performance-sample', data='x' * 5000).status_code, 413)


if __name__ == '__main__':
    unittest.main()
