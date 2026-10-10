"""Bounded history output and request reuse without changing totals or scope."""
import ast
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask, request, url_for
import other_functions as other
import stat_functions as doubles
from game_ratings import attach_other_ratings, summarize_games
from stats_location_filter import filter_stats_connection


class RequestReuseTests(unittest.TestCase):
    def test_cards_share_one_read_but_next_request_sees_edits_and_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'games.db'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE other_games (id INTEGER PRIMARY KEY, game_date, game_name, game_type, winner1, loser1, location)')
                conn.executemany('INSERT INTO other_games VALUES (?,?,?,?,?,?,?)', [
                    (1, '2026-01-01', 'No jump', 'Volleyball', 'A', 'B', 'Beach'),
                    (2, '2026-02-01', 'Scrabble', 'Board games', 'C', 'D', 'Park'),
                    (3, '2025-02-01', 'Scrabble', 'Board games', 'D', 'C', 'Beach'),
                ])
            opened = []
            def cursor():
                conn = sqlite3.connect(path)
                conn.row_factory = sqlite3.Row
                filter_stats_connection(conn, 'other_games')
                opened.append(conn)
                return conn.cursor()
            app = Flask(__name__)
            app.add_url_rule('/stats', endpoint='other_stats', view_func=lambda: '')
            with patch.object(other, 'set_cur', side_effect=cursor), \
                 patch.object(other, 'readable_games_data', wraps=other.readable_games_data) as format_rows:
                with app.test_request_context('/stats'):
                    raw = other.other_year_games_raw('2026')
                    expected = {name: summarize_games([dict(r) for r in raw if r['game_name'] == name])
                                for name in ('No jump', 'Scrabble')}
                    for name in expected:
                        card = attach_other_ratings(dict(game_name=name, stats=[], rare_stats=[]), '2026')
                        for key, value in expected[name].items():
                            self.assertEqual(card[key], value)
                    other.other_year_games('2026')
                    other.other_year_games('2026')
                    self.assertEqual(format_rows.call_count, 1)
                    self.assertEqual(len(opened), 1)
                    self.assertEqual(other.game_name_years('Scrabble'), ['2026', '2025', 'All years'])
                    self.assertEqual(other.game_name_years('No jump'), ['2026', 'All years'])
                    self.assertEqual(len(opened), 2)
                with sqlite3.connect(path) as conn:
                    conn.execute("UPDATE other_games SET winner1='Changed' WHERE id=1")
                with app.test_request_context('/stats?location=Beach'):
                    rows = other.other_year_games_raw('2026')
                    self.assertEqual([(r['id'], r['winner1']) for r in rows], [(1, 'Changed')])
                    self.assertEqual(other.game_name_years('Scrabble'), ['2025', 'All years'])
                with app.test_request_context('/stats'):
                    self.assertEqual(len(other.other_year_games_raw('2026')), 2)
                    self.assertEqual(other.game_name_years('Scrabble'), ['2026', '2025', 'All years'])
                for connection in opened:
                    with self.assertRaises(sqlite3.ProgrammingError):
                        connection.execute('SELECT 1')


class PlayerPageTests(unittest.TestCase):
    def test_web_pages_preserve_all_totals_and_share_filters(self):
        source = Path(__file__).resolve().parents[1] / 'stats.py'
        node = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'player_stats')
        games = [(i, '2026-10-01 10:00:00', 'A', 'B', 21, 'C', 'D', 18) for i in range(1, 66)]
        app = Flask(__name__)
        namespace = dict(app=app, request=request, url_for=url_for,
                         games_from_player_by_year=lambda year, name, raw: games,
                         all_years_player=lambda name: ['2026'], total_stats=doubles.total_stats,
                         player_matchup_min_games=doubles.player_matchup_min_games,
                         partner_stats_by_year=doubles.partner_stats_by_year,
                         opponent_stats_by_year=doubles.opponent_stats_by_year,
                         calculate_trueskill_rankings=lambda year: [],
                         convert_ampm=doubles.convert_ampm, player_avatar_context=lambda name: {},
                         render_template=lambda template, **context: context)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        collected = []
        for page, expected in [(1, list(range(65, 35, -1))), (2, list(range(35, 5, -1))), (3, list(range(5, 0, -1)))]:
            with app.test_request_context(f'/player/2026/A/?history_page={page}&view=shared-token&division=women&location=Beach'):
                context = namespace['player_stats']('2026', 'A')
                ids = [game[0] for game in reversed(context['history_games'])]
                self.assertEqual(ids, expected)
                collected.extend(ids)
                self.assertEqual(context['stats'][0][1], 65)
                self.assertEqual(context['current_streak'], dict(type='W', length=65))
                self.assertEqual(context['recent_form'], ['W'] * 10)
                self.assertEqual(context['history_pages'], 3)
                for link in [context['history_next'], context['history_previous']]:
                    if link:
                        for text in ('view=shared-token', 'division=women', 'location=Beach', '#player-games'):
                            self.assertIn(text, link)
        self.assertEqual(collected, list(range(65, 0, -1)))
        for requested, expected in [('999', 3), ('-5', 1), ('bad', 1)]:
            with app.test_request_context('/?history_page=' + requested):
                self.assertEqual(namespace['player_stats']('2026', 'A')['history_page'], expected)


if __name__ == '__main__':
    unittest.main()
