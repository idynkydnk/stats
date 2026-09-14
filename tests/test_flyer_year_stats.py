import sqlite3
import unittest
from datetime import datetime
from unittest.mock import patch

import email_content as content


class FlyerYearStatsTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch('email_content.datetime')
        self.clock.start().now.return_value = datetime(2026, 9, 13)
        self.addCleanup(self.clock.stop)

    def cursor(self):
        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE games (game_date, winner1, winner2, loser1, loser2)')
        conn.executemany('INSERT INTO games VALUES (?, ?, ?, ?, ?)', [
            ('2026-01-01', ' Alex ', 'Bea', 'Cam', 'Dee'),
            ('2026-09-13', 'Cam', 'Dee', 'Alex', 'Bea'),
            ('2025-12-31', 'Alex', 'Bea', 'Cam', 'Dee'),
            ('2026-09-14', 'Alex', 'Bea', 'Cam', 'Dee'),
            ('2027-01-01', 'Alex', 'Bea', 'Cam', 'Dee'),
        ])
        return conn.cursor()

    def test_current_year_only_and_no_games(self):
        with patch('stat_functions.set_cur', side_effect=self.cursor):
            block = content._flyer_current_year_stats_block(
                ['Alex', 'New Player'], {'Alex': 'Ace'},
            )
        self.assertIn('2026 DOUBLES STATS', block)
        self.assertIn('Alex (display name: Ace): 2 GP · 1 W · 1 L · 50% WIN', block)
        self.assertIn('New Player (display name: New Player): 0 GP', block)
        self.assertIn('WIN — · No games this year', block)
        self.assertNotIn('Cam (display name:', block)

    def test_refresh_replaces_stale_stats_and_preserves_custom_design(self):
        old = ('Use sunny colors.\n[CURRENT-YEAR DOUBLES STATS]\n'
               '2025: Alex 99 wins\n[/CURRENT-YEAR DOUBLES STATS]\nBig faces.')
        with patch('stat_functions.set_cur', side_effect=self.cursor):
            prompt = content._refresh_flyer_current_year_stats(old, ['Alex'])
            prompt = content._refresh_flyer_current_year_stats(prompt, ['Alex'])
        self.assertIn('Use sunny colors.', prompt)
        self.assertIn('Big faces.', prompt)
        self.assertNotIn('99 wins', prompt)
        self.assertEqual(prompt.count('[CURRENT-YEAR DOUBLES STATS]'), 1)
        self.assertIn('2 GP · 1 W · 1 L', prompt)

    def test_default_doubles_layout_has_flexible_lighting_and_stats(self):
        with patch('email_content._clean_player_lines_block',
                   return_value=('Alex', 1, ['Alex'])), \
             patch('stat_functions.set_cur', side_effect=self.cursor):
            prompt = content.build_flyer_scene_prompt(
                ['Alex'], 'doubles', event_date='2027-02-01', location='Beach',
            )
        self.assertIn('hero lineup', prompt)
        self.assertIn('A dark background is optional', prompt)
        self.assertIn('2026 DOUBLES STATS', prompt)
        self.assertIn('When: 2027-02-01', prompt)

    def test_other_sports_do_not_read_doubles_stats(self):
        with patch('stat_functions.set_cur') as cursor:
            prompt = content.build_flyer_scene_prompt([], 'vollis')
        cursor.assert_not_called()
        self.assertNotIn('CURRENT-YEAR DOUBLES STATS', prompt)

    def test_custom_generation_refreshes_stats_before_image_call(self):
        with patch('email_content._image_labels_for_players', return_value={}), \
             patch('email_content._reference_parts_from_uploaded_photos',
                   return_value=([], ['Alex'])), \
             patch('stat_functions.set_cur', side_effect=self.cursor), \
             patch('email_content._generate_image_bytes', return_value=(b'image', 'image/png')) as generate, \
             patch('email_content._normalize_image_bytes_to_aspect', return_value=(b'image', 'image/png')), \
             patch('email_content._save_email_image', return_value=('/image.png', '/tmp/image.png')):
            result = content.generate_flyer_image(
                'test-key', ['Alex'], 'doubles', custom_scene_prompt='Sunny beach poster.',
            )
        self.assertIn('2 GP · 1 W · 1 L', generate.call_args.args[0])
        self.assertIn('Sunny beach poster.', result[4])
        self.assertIn('2026 DOUBLES STATS', result[4])


if __name__ == '__main__':
    unittest.main()
