"""Test the real stats route without running application startup jobs."""
import ast
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import Mock
from flask import Flask


class StatsYearFallbackTests(unittest.TestCase):
    def render_stats(self, current_games=None, previous_games=None, selected_year=None, location=''):
        current_year = str(date.today().year)
        previous_year = str(int(current_year) - 1)
        games_by_year = {current_year: current_games or [], previous_year: previous_games or []}
        app = Flask(__name__)
        namespace = dict(
            app=app, date=date,
            year_games=lambda year: games_by_year.get(year, []),
            # Shared season list can include seasons with no women's games.
            grab_all_years=lambda: [current_year, previous_year],
            stats_per_year=lambda year, minimum: ['ranking'] if games_by_year.get(year) else [],
            active_location_filter=lambda: (location, False),
            rare_stats_per_year=Mock(return_value=[]),
            calculate_tile_stats=Mock(return_value={}),
            todays_stats=lambda: [], todays_games=lambda: [],
            render_template=lambda template, **context: context,
        )
        path = Path(__file__).resolve().parents[1] / 'stats.py'
        tree = ast.parse(path.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'stats')
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        context = namespace['stats'](selected_year or current_year)
        return context, current_year, previous_year

    def test_empty_section_keeps_current_year(self):
        context, current, _ = self.render_stats()
        self.assertEqual(context['display_year'], current)
        self.assertFalse(context['showing_previous_year'])
        self.assertEqual(context['stats'], [])

    def test_previous_year_with_games_still_used(self):
        context, _, previous = self.render_stats(previous_games=['game'])
        self.assertEqual(context['display_year'], previous)
        self.assertTrue(context['showing_previous_year'])
        self.assertEqual(context['stats'], ['ranking'])

    def test_current_games_do_not_fall_back(self):
        context, current, _ = self.render_stats(current_games=['game'], previous_games=['game'])
        self.assertEqual(context['display_year'], current)
        self.assertFalse(context['showing_previous_year'])

    def test_explicit_year_and_location_do_not_fall_back(self):
        context, _, _ = self.render_stats(selected_year='2000', previous_games=['game'])
        self.assertEqual(context['display_year'], '2000')
        self.assertFalse(context['showing_previous_year'])
        context, current, _ = self.render_stats(previous_games=['game'], location='Beach')
        self.assertEqual(context['display_year'], current)
        self.assertFalse(context['showing_previous_year'])
