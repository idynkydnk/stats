import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from category_stats import category_results


class CategoryStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'stats.db')
        with sqlite3.connect(self.path) as conn:
            conn.execute('CREATE TABLE other_games (id INTEGER, game_date TEXT, game_type TEXT, game_name TEXT, winner1 TEXT, loser1 TEXT, is_tie INTEGER, location TEXT)')
            conn.executemany('INSERT INTO other_games VALUES (?,?,?,?,?,?,?,?)', [
                (1, '2026-01-01', 'Basketball', '21', 'A', 'B', 0, 'Park'),
                (2, '2026-02-01', 'Basketball', 'Horse', 'B', 'A', 0, 'Park'),
                (3, '2025-01-01', 'Basketball', 'Horse', 'A', 'B', 0, 'Home'),
                (4, '2026-01-01', 'Board game', 'Chess', 'A', 'B', 1, 'Home'),
                (5, '2026-01-01', 'Volleyball', 'No jump', 'A', 'B', 0, 'Park')])
            conn.execute('CREATE TABLE games (id INTEGER, game_date TEXT, winner1 TEXT, winner2 TEXT, loser1 TEXT, loser2 TEXT, location TEXT)')
            conn.execute("INSERT INTO games VALUES (1,'2026-01-01','A','C','B','D','Park')")
            conn.execute('CREATE TABLE vollis_games (id INTEGER, game_date TEXT, winner TEXT, loser TEXT, location TEXT)')
            conn.execute("INSERT INTO vollis_games VALUES (1,'2026-01-01','A','B','Park')")
        self.account = patch('category_stats.connect_data', side_effect=lambda path: sqlite3.connect(path))
        self.account.start()

    def tearDown(self):
        self.account.stop()
        self.temp.cleanup()

    def test_combines_names_and_keeps_category_and_year_separate(self):
        result = category_results(self.path, 'Basketball', '2026')
        self.assertEqual(result['total_games'], 2)
        self.assertEqual(result['stats'][0][1:5], [1, 1, .5, 2])
        self.assertEqual(result['all_years'], ['2026', '2025', 'All years'])
        self.assertEqual(category_results(self.path, 'Basketball')['total_games'], 3)

    def test_category_alias_and_tie(self):
        result = category_results(self.path, 'Board games')
        self.assertEqual(result['stats'][0][1:], [0, 0, 0, 1, 1])

    def test_volleyball_includes_all_three_sources_without_id_collision(self):
        result = category_results(self.path, 'Volleyball')
        self.assertEqual(result['total_games'], 3)
        self.assertEqual(next(r for r in result['stats'] if r[0] == 'A')[1], 3)
        self.assertEqual(category_results(self.path, 'Volleyball', player='C')['total_games'], 1)

    def test_location_and_dates(self):
        app = Flask(__name__)
        from stats_date_filter import register_stats_date_filter
        register_stats_date_filter(app)
        @app.route('/stats', endpoint='other_stats')
        def view():
            return category_results(self.path, 'Basketball')
        result = app.test_client().get('/stats?location=Park&start_date=2026-02-01&end_date=2026-02-28').json
        self.assertEqual(result['total_games'], 1)
        self.assertEqual(result['games'][0]['game_name'], 'Horse')

    def test_empty_category(self):
        self.assertEqual(category_results(self.path, 'Unknown')['stats'], [])

    def test_web_and_api_routes_use_same_category_results(self):
        import ast
        from types import SimpleNamespace
        from flask import jsonify, request, render_template
        from jinja2 import DictLoader
        app = Flask(__name__, template_folder=str(Path('templates').resolve()))
        # Render the actual category page with lightweight surrounding layout.
        original_loader = app.jinja_loader
        from jinja2 import ChoiceLoader
        app.jinja_loader = ChoiceLoader([DictLoader({
            'test_base.html': '{% block content %}{% endblock %}{% block extra_js %}{% endblock %}',
            'partials/section_tabs.html': '',
        }), original_loader])
        @app.context_processor
        def context():
            return dict(base_template='test_base.html', active_tab='other',
                        year_route_base='other_stats', stats_location_url=lambda **kw: '/stats',
                        navigation_locations=['Park'], inline_stats_script='// shared stats script')
        allowed = set()
        for endpoint in ('update', 'update_vollis_game', 'update_other_game'):
            app.add_url_rule('/edit/' + endpoint + '/<int:id>', endpoint, lambda id: '')
        service = SimpleNamespace(_stats_db_path=lambda: self.path)
        for filename, name in [('stats.py', 'other_stats'), ('ios_api.py', 'api_other_stats')]:
            tree = ast.parse(Path(filename).read_text())
            node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
            namespace = dict(app=app, request=request, jsonify=jsonify, render_template=render_template,
                             _stats_db_path=lambda: self.path, _S=lambda: service,
                             _editable_game_ids=lambda table, ids: set(ids) if table in allowed else set(),
                             _year_arg=lambda default: request.args.get('year', default),
                             _other_ranking=lambda row: row, _card_stats=lambda card: card,
                             local_game_snapshot=lambda fn: fn)
            exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), namespace)
        client = app.test_client()
        response = client.get('/other_stats/2026/?category=Basketball')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'2 games', response.data)
        self.assertIn(b'Horse', response.data)
        self.assertNotIn(b'Chess', response.data)
        self.assertIn(b'sr-table sr-standings-table', response.data)
        self.assertIn(b'id="sr-search"', response.data)
        self.assertIn(b'aria-label="Locations"', response.data)
        self.assertIn(b'/other_stats/2025/?category=Basketball', response.data)
        self.assertIn(b'// shared stats script', response.data)
        self.assertIn(b'class="sr-game-team winners"', response.data)
        self.assertIn(b'class="sr-game-team losers"', response.data)
        self.assertIn(b'id="category-games-search"', response.data)
        self.assertIn(b'02/01/26', response.data)
        self.assertNotIn(b'aria-label="Edit game"', response.data)

        response = client.get('/api/other/stats?year=2026&category=Basketball')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['game_cards'][0]['total_games'], 2)
        self.assertEqual(response.json['stats'][0][1:5], [1, 1, .5, 2])
        allowed.update(['games', 'vollis_games', 'other_games'])
        response = client.get('/other_stats/2026/?category=Volleyball')
        for endpoint, game_id in [('update', 1), ('update_vollis_game', 1), ('update_other_game', 5)]:
            self.assertIn(f'/edit/{endpoint}/{game_id}?games_year=2026'.encode(), response.data)
        with sqlite3.connect(self.path) as conn:
            conn.execute('ALTER TABLE other_games ADD COLUMN winner_score INTEGER')
            conn.execute('ALTER TABLE other_games ADD COLUMN loser_score INTEGER')
            conn.execute('UPDATE other_games SET winner_score=0, loser_score=0 WHERE id=4')
        response = client.get('/other_stats/2026/?category=Board+games')
        self.assertEqual(response.data.count(b'class="sr-game-team tied"'), 2)
        self.assertEqual(response.data.count(b'class="sr-team-score">0</span>'), 2)
