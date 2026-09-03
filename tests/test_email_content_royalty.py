import unittest

from email_content import (
    _append_session_beach_royalty_lock,
    _merge_beach_royalty_phrases,
    _players_in_session_rank_order,
    _session_beach_royalty_lock,
    _session_beach_royalty_names,
)


STATS = [
    ['Christian Vincent', 3, 1, 0.75, 4],
    ['Nathan Gigee', 2, 1, 2 / 3, 4],
    ['Eddie Molina', 3, 2, 0.60, 6],
    ['Juan Carlos', 2, 2, 0.50, 10],
    ['Tyler Weston', 0, 4, 0.0, -24],
]
PLAYERS = [row[0] for row in STATS]


class BeachRoyaltyPromptTests(unittest.TestCase):
    def test_best_win_percentage_beats_best_point_differential(self):
        self.assertEqual(
            _session_beach_royalty_names(STATS),
            ['Christian Vincent'],
        )

    def test_image_identities_follow_stats_table_rank(self):
        shuffled = ['Juan Carlos', 'Christian Vincent', 'Eddie Molina']

        self.assertEqual(
            _players_in_session_rank_order(shuffled, STATS),
            ['Christian Vincent', 'Eddie Molina', 'Juan Carlos'],
        )

    def test_lock_names_leader_and_forbids_crown_on_juan(self):
        lock = _session_beach_royalty_lock(PLAYERS, STATS)

        self.assertIn('Christian Vincent is the only king', lock)
        self.assertIn('Juan Carlos', lock)
        self.assertIn('must have no crown', lock)
        self.assertIn('do not infer royalty from point differential', lock)

    def test_stale_royalty_traits_are_removed_from_nonleader(self):
        merged = _merge_beach_royalty_phrases(
            PLAYERS,
            STATS,
            {
                'Juan Carlos': ['dressed like a king', 'wearing a blue shirt'],
                'Christian Vincent': [],
            },
        )

        self.assertNotIn('dressed like a king', merged['Juan Carlos'])
        self.assertIn('wearing a blue shirt', merged['Juan Carlos'])
        self.assertIn('dressed like a king', merged['Christian Vincent'])

    def test_custom_prompt_also_receives_royalty_lock_once(self):
        prompt = _append_session_beach_royalty_lock(
            'Put everyone on a beach court.', PLAYERS, STATS,
        )
        prompt = _append_session_beach_royalty_lock(prompt, PLAYERS, STATS)

        self.assertEqual(prompt.count('ROYALTY IDENTITY LOCK'), 1)


if __name__ == '__main__':
    unittest.main()
