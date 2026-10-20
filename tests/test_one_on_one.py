import ast
from datetime import date
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from flask import Flask, request
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader
import one_on_one as singles
from stats_location_filter import filter_stats_connection

ROOT = Path(__file__).resolve().parents[1]


class OneOnOneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'games.db')
        with sqlite3.connect(self.path) as c:
            c.execute('CREATE TABLE vollis_games (id INTEGER, game_date TEXT, winner TEXT, winner_score INTEGER, loser TEXT, loser_score INTEGER, updated_at TEXT, entered_timezone TEXT, location TEXT)')
            cols = ['id INTEGER', 'game_date TEXT', 'game_type TEXT', 'game_name TEXT', 'winner_score INTEGER', 'loser_score INTEGER', 'updated_at TEXT', 'entered_timezone TEXT', 'location TEXT', 'comment TEXT']
            cols += [f'{side}{i} TEXT' for side in ('winner', 'loser') for i in range(1, 16)]
            cols += [f'{side}{i}_score INTEGER' for side in ('winner', 'loser') for i in range(1, 16)]
            c.execute('CREATE TABLE other_games (' + ','.join(cols) + ')')
            c.execute("INSERT INTO vollis_games VALUES (1, '2025-01-01 12:00:00', 'A', 21, 'B', 15, '2025-01-01 12:00:00', '', 'Beach')")
        self.add_other(1, 'Italian short court', 'B', 'A')
        self.add_other(2, 'Short court two boxes', 'A', 'C', location='Park')
        self.add_other(3, 'Group', 'C', 'A')
        self.add_other(4, 'Name That Tune', 'C', 'B')
        self.add_other(5, 'No jump', 'C', 'B')
        self.add_other(6, 'Half court long ways', 'A', 'C', winner2='B')
        self.add_other(7, 'Short court three boxes', 'A', 'B', game_type='Board games')
        self.add_other(8, 'Short court three boxes', 'A', 'A')
        self.add_other(9, 'Short court three boxes', 'B', 'C', winner_score=None, loser_score=None, winner1_score=11, loser1_score=0)
        for module, table in [('vollis_functions', 'vollis_games'), ('other_functions', 'other_games')]:
            def cursor(table=table):
                c = sqlite3.connect(self.path)
                c.row_factory = sqlite3.Row
                filter_stats_connection(c, table)
                return c.cursor()
            p = patch(module + '.set_cur', side_effect=cursor)
            p.start()
            self.addCleanup(p.stop)
        self.app = Flask(__name__)
        self.app.add_url_rule('/stats', 'vollis_stats', lambda: '')
        self.app.add_url_rule('/games', 'vollis_games', lambda: '')
        self.app.add_url_rule('/player', 'vollis_player_stats', lambda: '')

    def add_other(self, id, name, winner, loser, **values):
        row = dict(id=id, game_date='2026-01-01 12:00:00', game_type='Volleyball', game_name=name,
                   winner1=winner, loser1=loser, winner_score=21, loser_score=15, location='Beach',
                   updated_at='2026-01-01 12:00:00', **{})
        row.update(values)
        with sqlite3.connect(self.path) as c:
            c.execute('INSERT INTO other_games (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', list(row.values()))

    def test_approved_catalog_and_exclusions(self):
        self.assertEqual(len(singles.FORMATS), 36)
        for name in singles.FORMATS[1:]:
            self.assertIsNotNone(singles.normalize_other(dict(id=1, game_date='2026', game_name=name, game_type='Volleyball', winner1='A', loser1='B')), name)
        for name in ['Name That Tune', 'Group', 'No jump', 'Vollis kings', 'Kings', 'Coed', 'Ping pong']:
            self.assertIsNone(singles.canonical_format(name))
        self.assertEqual(singles.canonical_format(' ITALIAN SHORT COURT '), 'Italian short court')

    def test_four_corners_joins_combined_stats_and_format_filters(self):
        self.add_other(20, 'Four corners', 'C', 'A')
        with self.app.test_request_context('/stats'):
            rows = singles.games()
            self.assertEqual({g['id'] for g in rows}, {1, -1, -2, -9, -20})
            self.assertEqual(singles.ratings(rows)['rated_games'], 5)
            self.assertEqual(singles.player_data('All years', 'C')['stats'][0][1:3], [1, 2])
            self.assertIn('Four corners', singles.api_stats('All years')['formats'])
        with self.app.test_request_context('/stats?format=Four+corners'):
            self.assertEqual(singles.selected_format(), 'Four corners')
            payload = singles.api_stats('All years')
            self.assertEqual({r['name']: r['wins'] for r in payload['stats']}, {'C': 1, 'A': 0})
            rows = singles.games('All years', singles.selected_format())
            self.assertEqual([g['id'] for g in rows], [-20])
            self.assertEqual(rows[0]['other_game']['id'], 20)

    def test_lefty_formats_join_combined_stats_and_format_filters(self):
        names = ['Half court lefty only', 'Half court no jump lefty only',
                 'Half court two touch lefty only']
        for id, name in enumerate(names, 20):
            self.add_other(id, name, 'A', 'B')
        with self.app.test_request_context('/stats'):
            rows = singles.games()
            self.assertEqual(len(rows), 7)
            self.assertEqual(singles.ratings(rows)['rated_games'], 7)
            self.assertEqual(singles.player_data('All years', 'A')['stats'][0][1:3], [5, 1])
            payload = singles.api_stats('All years')
            for name in names:
                self.assertIn(name, payload['formats'])
                self.assertEqual(len(singles.games('All years', name)), 1)
        for name in names:
            with self.app.test_request_context('/stats?' + urlencode({'format': name})):
                payload = singles.api_stats('All years')
                self.assertEqual({r['name']: r['wins'] for r in payload['stats']},
                                 {'A': 1, 'B': 0})

    def test_totals_identity_scores_and_ratings(self):
        rows = singles.games()
        self.assertEqual({g['id'] for g in rows}, {1, -1, -2, -9})
        self.assertEqual({r[0]: r[1:3] for r in singles.rankings(rows)}, {'A': [2, 1], 'B': [2, 1], 'C': [0, 2]})
        self.assertEqual(singles.ratings(rows)['rated_games'], 4)
        self.assertEqual(singles.ratings(rows)['ratings']['B']['rated_games'], 3)
        boxes = next(g for g in rows if g['id'] == -9)
        self.assertEqual((boxes['winner_score'], boxes['loser_score']), (11, 0))
        self.assertEqual(boxes['other_game']['id'], 9)
        self.assertEqual(boxes['other_game']['winners'][0]['score'], 11)
        self.assertEqual(singles.years(), ['2026', '2025', 'All years'])

    def test_filters_and_empty_player(self):
        with self.app.test_request_context('/stats?location=Park'):
            self.assertEqual([g['id'] for g in singles.games()], [-2])
        with self.app.test_request_context('/stats'):
            self.assertEqual(len(singles.games()), 4)
            self.assertEqual(len(singles.games('2025')), 1)
            self.assertEqual([g['id'] for g in singles.games('All years', 'Italian short court')], [-1])
            self.assertEqual(singles.player_data('2024', 'A')['stats'], [['A', 0, 0, 0, 0]])
            detail = singles.player_data('All years', 'A')
            self.assertEqual(detail['stats'], [['A', 2, 1, 2/3, 3]])
            self.assertEqual({r['opponent']: (r['wins'], r['losses']) for r in detail['opponent_stats']}, {'B': (1, 1), 'C': (1, 0)})

    def test_api_pagination_source_permissions_and_format(self):
        service = SimpleNamespace(_editable_game_ids=lambda table, ids: set(ids) if table == 'vollis_games' else set(),
                                  player_avatar_context=lambda name: {})
        with patch.dict('sys.modules', stats=service):
            with self.app.test_request_context('/games?limit=2'):
                page = singles.api_games('All years')
                self.assertEqual((page['total'], len(page['games']), page['next_offset']), (4, 2, 2))
                self.assertTrue(all(g['can_edit'] == (g['source'] == 'vollis') for g in page['games']))
            with self.app.test_request_context('/games?limit=2&offset=2'):
                page2 = singles.api_games('All years')
                self.assertEqual(len({g['id'] for g in page['games'] + page2['games']}), 4)
                self.assertIsNone(page2['next_offset'])
                self.assertTrue(next(g for g in page2['games'] if g['source'] == 'vollis')['can_edit'])
            with self.app.test_request_context('/stats?format=Short+court+three+boxes'):
                stats = singles.api_stats('All years')
                self.assertEqual({r['name']: r['wins'] for r in stats['stats']}, {'B': 1, 'C': 0})
                player = singles.api_player('All years', 'B')
                self.assertEqual(player['games'][0]['game_name'], 'Short court three boxes')
                self.assertEqual(player['games'][0]['winner1'], 'B')
            with self.app.test_request_context('/stats?format=Name+That+Tune'):
                with self.assertRaises(Exception) as error:
                    singles.selected_format()
                self.assertEqual(error.exception.code, 400)

    def test_combined_cache_invalidates_when_other_volleyball_changes(self):
        from stats_response_cache import StatsResponseCache
        cache = StatsResponseCache(Path(self.tmp.name) / 'cache')
        args = [('one_on_one', '1')]
        ticket = cache.prepare([(self.path, 0)], 'user', 'api_vollis_stats', args, None)
        cache.save(ticket, b'combined stats')
        self.assertEqual(cache.load(ticket), b'combined stats')
        self.add_other(10, 'Half court long ways', 'A', 'B')
        updated = cache.prepare([(self.path, 0)], 'user', 'api_vollis_stats', args, None)
        self.assertIsNone(cache.load(updated))

    def test_templates_render_combined_data_and_original_edit_targets(self):
        env = Environment(loader=ChoiceLoader([DictLoader({
            'base': '{% block content %}{% endblock %}',
            'partials/player_avatar.html': '',
        }), FileSystemLoader(ROOT / 'templates')]))
        env.globals.update(url_for=lambda endpoint, **kw: '/' + endpoint + '?' + urlencode(kw),
                           other_navigation_groups=lambda: [('Volleyball', ['No jump'])],
                           browse_game_year=lambda *a, **k: 'All years', navigation_locations=[],
                           stats_location_url=lambda **kw: '/stats?' + urlencode(kw))
        with self.app.test_request_context('/stats?format=Italian+short+court'):
            common = dict(base_template='base', active_tab='vollis', request=request, session={},
                          year='All years', format_name='Italian short court', one_on_one_formats=singles.FORMATS,
                          stats_share_available=False, stats_shared_read_only=False)
            context = singles.standings('All years', 'Italian short court')
            html = env.get_template('vollis_stats.html').render(**(common | context))
            self.assertIn('1v1 Stats', html)
            self.assertIn('format=Italian+short+court', html)
            rows = singles.tuples(singles.games(), display=True)
            html = env.get_template('vollis_games.html').render(**(common | dict(games=rows, editable_game_ids={1, -1})))
            self.assertIn('/update_vollis_game?id=1', html)
            self.assertIn('/update_other_game?id=1', html)
            self.assertNotIn('id=-1', html)
            context = singles.player_data('All years', 'A')
            context['games'] = singles.tuples(context['games'], display=True)
            html = env.get_template('vollis_player.html').render(**(common | context | dict(player='A')))
            self.assertIn('1v1 game history', html)
            self.assertIn('Italian short court', html)


if __name__ == '__main__':
    unittest.main()
