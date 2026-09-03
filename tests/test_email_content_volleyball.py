import unittest
from unittest.mock import patch

from email_content import (
    PLAYER_CHARACTER_SHEET_STYLE,
    _build_solo_player_prompt,
    _append_volleyball_ball_lock,
    _volleyball_ball_lock,
    build_flyer_scene_prompt,
    build_scene_image_prompt,
)


class VolleyballImagePromptTests(unittest.TestCase):
    def test_summary_image_requires_one_yellow_black_wilson_ball(self):
        prompt = build_scene_image_prompt('doubles', [])

        self.assertIn('yellow-and-black Wilson beach volleyball', prompt)
        self.assertIn('show exactly ONE volleyball total', prompt)

    def test_flyer_uses_wilson_ball_without_summary_limit(self):
        prompt = build_flyer_scene_prompt([], 'doubles')

        self.assertIn('yellow-and-black Wilson beach volleyball', prompt)
        self.assertNotIn('show exactly ONE volleyball total', prompt)

    def test_custom_summary_prompt_receives_lock_once(self):
        prompt = _append_volleyball_ball_lock(
            'Put everyone on a beach court.', 'doubles', summary_image=True,
        )
        prompt = _append_volleyball_ball_lock(
            prompt, 'doubles', summary_image=True,
        )

        self.assertEqual(prompt.count('VOLLEYBALL EQUIPMENT LOCK'), 1)
        self.assertIn('show exactly ONE volleyball total', prompt)

    def test_non_volleyball_image_does_not_receive_ball_rule(self):
        self.assertEqual(_volleyball_ball_lock('other', 'Gin Rummy', True), '')

    def test_solo_images_and_character_sheets_do_not_receive_group_ball_rule(self):
        with patch('player_functions.player_display_name', return_value='Alex'):
            solo_prompt = _build_solo_player_prompt('Alex Smith', [], True)

        self.assertNotIn('yellow-and-black Wilson', solo_prompt)
        self.assertNotIn('yellow-and-black Wilson', PLAYER_CHARACTER_SHEET_STYLE)


if __name__ == '__main__':
    unittest.main()
