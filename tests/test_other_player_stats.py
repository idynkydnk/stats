"""Native Other player pages accept display records and all player slots."""
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask
import ios_api
from other_functions import total_other_stats, other_opponent_stats_by_year


class OtherPlayerStatsTests(unittest.TestCase):
    def test_team_and_multiplayer_opponents_exclude_teammates_and_other_losers(self):
        games = [
            dict(winner1='Kyle', winner15='Lisa', loser1='Ashleigh', loser15='Leonel'),
            dict(winner1='Ashleigh', loser1='Kyle', loser15='Lisa'),
            dict(winner1='Kyle', loser1='Leonel'),
        ]
        self.assertEqual(total_other_stats('Lisa', games), [['Lisa', 1, 1, .5, 2]])
        opponents = {r['opponent']: (r['wins'], r['losses'])
                     for r in other_opponent_stats_by_year('Lisa', games)}
        self.assertEqual(opponents, {'Ashleigh': (1, 1), 'Leonel': (1, 0)})
        self.assertEqual(total_other_stats('Nobody', games), [['Nobody', 0, 0, 0, 0]])
        self.assertEqual(other_opponent_stats_by_year('Nobody', games), [])

    def test_native_player_endpoint_with_real_game_conversion_and_empty_season(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        slots = ', '.join(f'{side}{i} TEXT' for side in ('winner', 'loser') for i in range(1, 16))
        conn.execute(f'CREATE TABLE other_games (id INTEGER PRIMARY KEY, game_date TEXT, game_name TEXT, {slots})')
        conn.executemany('''INSERT INTO other_games
            (game_date, game_name, winner1, winner2, loser1, loser2)
            VALUES (?, 'Sequence', ?, ?, ?, ?)''', [
                ('2025-01-01', 'Lisa Hoang', None, 'Kyle Thomson', None),
                ('2026-01-01', 'Kyle Thomson', 'Leonel Valencia', 'Ashleigh Wodzinski', 'Lisa Hoang'),
                ('2026-01-02', 'Lisa Hoang', None, 'Kyle Thomson', 'Ashleigh Wodzinski'),
            ])
        app = Flask(__name__)
        app.config.update(TESTING=True)
        with patch('ios_api._ensure_deleted_table'):
            ios_api.register_ios_api(app)
        server = SimpleNamespace(player_avatar_context=lambda name: {})
        with patch('other_functions.set_cur', side_effect=conn.cursor), patch('ios_api._S', return_value=server):
            for year, wins, losses in [('All years', 2, 1), ('2026', 1, 1), ('2024', 0, 0)]:
                with self.subTest(year=year):
                    response = app.test_client().get('/api/other/players/Lisa%20Hoang', query_string={'year': year})
                    self.assertEqual(response.status_code, 200)
                    data = response.get_json()
                    self.assertEqual((data['stats']['wins'], data['stats']['losses']), (wins, losses))
                    self.assertEqual(len(data['games']), wins + losses)
                    self.assertEqual(set(data['all_years']), {'2025', '2026', 'All years'})
                    if not wins + losses:
                        self.assertEqual(data['opponents'], [])
                    else:
                        self.assertTrue(all('id' in game for game in data['games']))


if __name__ == '__main__':
    unittest.main()
