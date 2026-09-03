import unittest

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
    def test_default_scene_stages_leader_and_loser_from_stats(self):
        prompt = build_scene_image_prompt(
            'doubles', PLAYERS, player_stats=STATS,
        )

        self.assertIn('PERFORMANCE STAGING LOCK', prompt)
        self.assertIn('Christian Vincent (3-1, 75%, +4 point differential)', prompt)
        self.assertIn('ecstatic and triumphant', prompt)
        self.assertIn('Tyler Weston (0-4, 0%, -24 point differential)', prompt)
        self.assertIn('down on the ground in comically bad shape', prompt)
        self.assertIn('no blood, gore, open wounds', prompt)

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
