import unittest
from unittest.mock import patch

from email_content import (
    _append_session_performance_staging_lock,
    _session_performance_staging_lock,
    build_scene_image_prompt,
)


STATS = [
    ['Christian Vincent', 3, 1, 0.75, 4],
    ['Eddie Molina', 2, 2, 0.50, 2],
    ['Juan Carlos', 2, 2, 0.50, -2],
    ['Tyler Weston', 0, 4, 0.0, -24],
]
PLAYERS = [row[0] for row in STATS]


class SessionPerformancePromptTests(unittest.TestCase):
    def test_default_scene_includes_stats_without_forced_poses(self):
        labels = {row[0]: f'{row[0]} {row[1]}-{row[2]}' for row in STATS}
        with patch('email_content.filter_illustratable_players', return_value=PLAYERS):
            prompt = build_scene_image_prompt(
                'doubles', PLAYERS, player_stats=STATS, labels_by_name=labels,
            )
        for label in labels.values():
            self.assertIn(label, prompt)
        self.assertNotIn('LOCK', prompt)
        self.assertNotIn('on the ground', prompt)

    def test_middle_players_get_different_direction_from_differential(self):
        lock = _session_performance_staging_lock(PLAYERS, STATS)

        self.assertIn('Eddie Molina (2-2, 50%, +2 point differential)', lock)
        self.assertIn('a strong positive performance', lock)
        self.assertIn('Juan Carlos (2-2, 50%, -2 point differential)', lock)
        self.assertIn('a poor performance', lock)

    def test_custom_prompt_receives_performance_lock_once(self):
        prompt = _append_session_performance_staging_lock(
            'Put everyone on a beach court.', PLAYERS, STATS,
        )
        prompt = _append_session_performance_staging_lock(
            prompt, PLAYERS, STATS,
        )

        self.assertEqual(prompt.count('PERFORMANCE STAGING LOCK'), 1)

    def test_all_tied_players_are_not_called_losers(self):
        tied = [
            ['Alex One', 1, 1, 0.5, 0],
            ['Alex Two', 1, 1, 0.5, 0],
        ]
        lock = _session_performance_staging_lock(
            ['Alex One', 'Alex Two'], tied,
        )

        self.assertNotIn('clear session loser', lock)
        self.assertNotIn('must be on the ground', lock)


if __name__ == '__main__':
    unittest.main()
