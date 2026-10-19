"""Loading optimizations must preserve freshness, privacy, and shared filters."""
from hashlib import sha256
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from flask import Flask, url_for

from asset_delivery import register_asset_delivery
from tests import test_private_accounts as fixtures


class AssetTests(unittest.TestCase):
    def test_runtime_bundles_preserve_sources_order_fonts_and_immutable_versions(self):
        root = Path(__file__).resolve().parents[1] / 'static'
        app = Flask(__name__, static_folder=str(root), static_url_path='/static')
        register_asset_delivery(app)
        with app.test_request_context('/'):
            js_url = url_for('static', filename='js/common.bundle.js')
            css_url = url_for('static', filename='css/site.bundle.css')
        client = app.test_client()
        js = client.get(js_url)
        scripts = ['menu.js', 'stats-sharing.js', 'search-filter.js', 'mobile-keyboard.js', 'responsiveness.js']
        self.assertEqual(js.data, b'\n;\n'.join((root / 'js' / name).read_bytes() for name in scripts))
        self.assertIn('immutable', js.headers['Cache-Control'])
        self.assertEqual(client.get(js_url, headers={'If-None-Match': js.headers['ETag']}).status_code, 304)
        css = client.get(css_url)
        self.assertIn(b'../vendor/fontawesome/fa-solid-900.', css.data)
        self.assertTrue(css.data.endswith((root / 'css/appearance.css').read_bytes()))
        self.assertIn((root / 'css/stats.css').read_bytes(), css.data)
        self.assertIn('immutable', css.headers['Cache-Control'])
        self.assertNotIn('immutable', client.get('/static/css/site.bundle.css?v=wrong').headers['Cache-Control'])
        self.assertNotIn('Set-Cookie', js.headers)

    def test_only_current_versioned_code_is_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'js').mkdir()
            (root / 'js/theme.js').write_text('window.theme = 1;')
            (root / 'photo.jpg').write_bytes(b'uploaded photo')
            app = Flask(__name__, static_folder=directory, static_url_path='/static')
            register_asset_delivery(app)
            with app.test_request_context('/'):
                url = url_for('static', filename='js/theme.js', v='old-manual-version')
            digest = sha256((root / 'js/theme.js').read_bytes()).hexdigest()[:16]
            self.assertEqual(parse_qs(urlsplit(url).query), {'v': [digest]})
            client = app.test_client()
            response = client.get(url)
            self.assertIn('immutable', response.headers['Cache-Control'])
            conditional = client.get(url, headers={'If-None-Match': response.headers['ETag']})
            self.assertEqual(conditional.status_code, 304)
            for path in ['/static/js/theme.js', '/static/js/theme.js?v=wrong', '/static/photo.jpg?v=123', '/static/js/missing.js?v=123']:
                self.assertNotIn('immutable', client.get(path).headers.get('Cache-Control', ''))
            (root / 'js/theme.js').write_text('window.theme = 2;')
            restarted = Flask(__name__, static_folder=directory, static_url_path='/static')
            register_asset_delivery(restarted)
            with restarted.test_request_context('/'):
                self.assertNotEqual(url, url_for('static', filename='js/theme.js'))

    def test_local_icon_coverage_and_font_fingerprints(self):
        root = Path(__file__).resolve().parents[1]
        folder = root / 'static/vendor/fontawesome'
        css = (folder / 'icons.css').read_text()
        files = list((root / 'templates').rglob('*.html')) + list((root / 'static/js').glob('*.js')) + list(root.glob('*.py'))
        used = set(re.findall(r'\bfa-[a-z0-9-]+', '\n'.join(p.read_text() for p in files)))
        self.assertTrue(used.issubset(set(re.findall(r'\bfa-[a-z0-9-]+', css))))
        for name in re.findall(r'url\("([^"]+)"\)', css):
            digest = sha256((folder / name).read_bytes()).hexdigest()[:16]
            self.assertIn('.' + digest + '.', name)
        self.assertIn('.sr-only{', css)
        base = (root / 'templates/base.html').read_text()
        self.assertNotIn('cdnjs.cloudflare.com', base)
        self.assertNotIn("filename='js/theme.js'", base)
        self.assertLess(base.index('theme_bootstrap'), base.index('rel="stylesheet"'))


class LandingTests(unittest.TestCase):
    setUp = fixtures.PrivateAccountTests.setUp
    register = fixtures.PrivateAccountTests.register

    def test_public_assets_skip_authentication_and_cookie_refresh(self):
        folder = Path(self.directory.name) / 'assets'
        (folder / 'js').mkdir(parents=True)
        (folder / 'js/theme.js').write_text('window.theme = 1;')
        self.app.static_folder = str(folder)
        register_asset_delivery(self.app)
        self.a.set_cookie('remember_token', 'shared-token')
        with self.app.test_request_context('/'):
            url = url_for('static', filename='js/theme.js')
        with patch.object(self.service, 'validate_auth_token', side_effect=AssertionError('Asset authenticated')):
            response = self.a.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Set-Cookie', response.headers)
        self.assertNotIn('Cookie', response.headers.get('Vary', ''))
        self.assertIn('immutable', response.headers['Cache-Control'])

    def add_pages(self):
        from private_accounts import connect_data
        def standings(year):
            with connect_data(self.path) as conn:
                return str(conn.execute('SELECT winner1 FROM games').fetchall())
        self.app.add_url_rule('/', 'index', lambda: self.fail('Extra landing hop'))
        self.app.add_url_rule('/stats/', 'stats_default', lambda: self.fail('Extra landing hop'))
        self.app.add_url_rule('/stats/<year>/<date>/', 'stats_by_date', lambda **kw: self.fail('Extra landing hop'))
        self.app.add_url_rule('/stats/<year>/', 'stats', standings)

    def test_landing_has_one_redirect_preserving_repeated_filters(self):
        self.add_pages()
        for path in ['/', '/stats/', '/stats/2025/2025-01-01/']:
            response = self.a.get(path + '?location=Beach&division=women&q=one&q=two')
            parsed = urlsplit(response.location)
            self.assertRegex(parsed.path, r'^/stats/\d{4}/$')
            if '2025' in path:
                self.assertEqual(parsed.path, '/stats/2025/')
            args = parse_qs(parsed.query)
            self.assertEqual(args['q'], ['one', 'two'])
            self.assertEqual(args['location'], ['Beach'])
            self.assertEqual(args['division'], ['women'])
            self.assertIn('view', args)
            self.assertEqual(self.a.get(response.location).status_code, 200)

    def test_private_landing_retains_selected_data_and_validates_share(self):
        self.add_pages()
        headers = self.register(self.a, 'alice')
        self.a.post('/api/games', headers=headers, json={'name': 'Alice private'})
        response = self.a.get('/')
        page = self.a.get(response.location)
        self.assertIn(b'Alice private', page.data)
        public = self.b.get(self.b.get('/').location)
        self.assertNotIn(b'Alice private', public.data)
        self.assertEqual(self.a.get('/?view=invalid').status_code, 404)


class NarrowReadsTests(unittest.TestCase):
    def test_cached_today_counts_and_locations_refresh_after_edits(self):
        import stat_functions as doubles
        import database_functions as database
        from datetime import date
        from flask import g
        from stats_snapshot_cache import source_revision
        from stats_location_filter import filter_stats_connection
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'games.db'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE games (id INTEGER PRIMARY KEY, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, entered_timezone, location, division)')
                conn.execute('INSERT INTO games VALUES (1, ?, "A", "B", 21, "C", "D", 10, NULL, NULL, NULL, "Beach", "open")', (date.today().isoformat(),))
            def cursor():
                conn = sqlite3.connect(path)
                filter_stats_connection(conn, 'games')
                return conn.cursor()
            app = Flask(__name__)
            app.add_url_rule('/stats', endpoint='stats')
            def read(query=''):
                with app.test_request_context('/stats' + query):
                    g.stats_source_databases = [(str(path), 0)]
                    g.stats_data_revision = source_revision(g.stats_source_databases)
                    return doubles.year_games_count('All years'), doubles.todays_games(), database.saved_game_locations()
            with patch.object(doubles, 'set_cur', side_effect=cursor), patch.object(database, 'create_connection', side_effect=lambda _: sqlite3.connect(path)):
                first = read()
                self.assertEqual(first[0], 1)
                self.assertEqual(first[2], ['Beach'])
                self.assertEqual(read(), first)
                with sqlite3.connect(path) as conn:
                    conn.execute("UPDATE games SET winner1='Edited', location='Park'")
                edited = read()
                self.assertEqual(edited[1][0][2], 'Edited')
                self.assertEqual(edited[2], ['Park'])
                self.assertEqual(read('?division=women')[:2], (0, []))

    def test_navigation_reads_only_labels_and_respects_location_and_revision(self):
        import other_functions as other
        from flask import g
        from stats_location_filter import filter_stats_connection
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'games.db'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE other_games (id INTEGER PRIMARY KEY, game_name, game_type, game_date, location)')
                conn.executemany('INSERT INTO other_games VALUES (?,?,?,?,?)', [
                    (1, 'Cards', 'Old category', '2025-01-01', 'Beach'),
                    (2, 'Cards', 'Card games', '2026-01-01', 'Park'),
                    (3, 'Chess', 'Board games', '2026-01-02', 'Beach')])
            opened = []
            def cursor():
                connection = sqlite3.connect(path)
                filter_stats_connection(connection, 'other_games')
                opened.append(connection)
                return connection.cursor()
            app = Flask(__name__)
            app.add_url_rule('/stats', endpoint='other_stats')
            def read(query='', revision='first'):
                with app.test_request_context('/stats' + query):
                    g.stats_data_revision = str(path) + revision
                    return other.other_navigation_catalog()
            with patch.object(other, 'set_cur', side_effect=cursor), patch.object(other, 'other_year_games_raw', side_effect=AssertionError('Full history loaded')):
                expected = [('Volleyball', ['No jump']), ('Board games', ['Chess']), ('Card games', ['Cards'])]
                self.assertEqual(read(), expected)
                self.assertEqual(read(), expected)
                self.assertEqual(len(opened), 1)
                self.assertIn(('Old category', ['Cards']), read('?location=Beach'))
                with sqlite3.connect(path) as conn:
                    conn.execute("UPDATE other_games SET game_type='Changed' WHERE id=2")
                self.assertIn(('Changed', ['Cards']), read(revision='edited'))
            for connection in opened:
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute('SELECT 1')

    def test_avatar_fields_use_one_read_and_preserve_case_fallback(self):
        import player_functions as players
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'players.db'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE players (full_name, photo_path, ai_image_path, ai_image_traits, face_photo_focus)')
                conn.execute("INSERT INTO players VALUES ('Alice', 'face.jpg', 'ai.jpg', NULL, '30,40,2')")
            opened = []
            def cursor():
                connection = sqlite3.connect(path)
                opened.append(connection)
                return connection.cursor()
            with patch.object(players, 'set_cur', side_effect=cursor):
                photo, ai, traits, focus = players.get_player_avatar_fields('alice')
                self.assertEqual((photo, ai, focus), ('face.jpg', 'ai.jpg', (30, 40, 2)))
                self.assertEqual(len(opened), 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                opened[0].execute('SELECT 1')


if __name__ == '__main__':
    unittest.main()
