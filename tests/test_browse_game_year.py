"""Exercise destination defaults without running application startup jobs."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]


class BrowseGameYearTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / 'stats.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'browse_game_year')
        self.namespace = {
            'grab_all_years': lambda: ['2026', '2025', 'All years'],
            'all_vollis_years': lambda: ['2024', 'All years'],
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'stats.py', 'exec'), self.namespace)
        self.choose = self.namespace['browse_game_year']

    @patch('other_functions.game_name_years')
    def test_destination_defaults(self, years):
        for recorded, expected in [
            (['2023', 'All years'], '2023'),
            (['2026', '2023', 'All years'], 'All years'),
            (['All years'], 'All years'),
            ([None, '2023', 'All years'], '2023'),
        ]:
            years.return_value = recorded
            self.assertEqual(self.choose('Matterhorn'), expected)
        self.assertEqual(self.choose(kind='doubles'), 'All years')
        self.assertEqual(self.choose(kind='vollis'), '2024')

    @patch('other_functions.game_name_years', return_value=['2023', 'All years'])
    def test_explicit_empty_year_remains_selected(self, years):
        from flask import Flask
        tree = ast.parse((ROOT / 'stats.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'game_name_stats_with_year')
        namespace = {
            'app': Flask(__name__),
            '_other_game_card_for_year': lambda year, name: None,
            'render_template': lambda template, **context: context,
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'stats.py', 'exec'), namespace)
        context = namespace['game_name_stats_with_year']('Matterhorn', '2026')
        self.assertEqual(context['year'], '2026')
        self.assertIn('2026', context['all_years'])

    @patch('other_functions.game_name_years', return_value=['2023', 'All years'])
    def test_browse_links_ignore_source_year_for_stats_and_games(self, years):
        env = Environment(loader=FileSystemLoader(ROOT / 'templates'))
        env.globals.update(
            browse_game_year=self.choose,
            other_navigation_groups=lambda: [('Volleyball', ['No jump']), ('Other', ['Matterhorn'])],
            doubles_division_url=lambda division: '?division=' + division,
            url_for=lambda endpoint, **values: endpoint + ':' + values['year'] + ':' + values.get('game_name', ''),
        )
        for mode, endpoint in [('stats', 'game_name_stats_with_year'), ('games', 'other_games_by_name')]:
            html = env.get_template('partials/section_tabs.html').render(
                active_tab='doubles', doubles_division='open', header_mode=mode,
                year='2026', request={'endpoint': 'stats'},
            )
            self.assertIn(endpoint + ':2023:Matterhorn', html)
            self.assertNotIn(':2026:', html)
            self.assertNotIn('All Other', html)


if __name__ == '__main__':
    unittest.main()
