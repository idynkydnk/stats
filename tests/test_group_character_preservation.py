import unittest
from unittest.mock import patch

from email_content import (
    CHARACTER_PRESERVATION_RULE,
    _reference_parts_from_uploaded_photos,
    build_flyer_scene_prompt,
    build_scene_image_prompt,
)


class GroupCharacterPreservationTests(unittest.TestCase):
    def test_group_and_flyer_prompts_only_use_traits_without_a_character(self):
        players = ['Saved Player', 'Photo Player', 'Traits Player']
        with (
            patch('email_content.filter_illustratable_players', return_value=players),
            patch('email_content._phrases_by_player_name', return_value={
                'Saved Player': ['obsolete red hat'],
                'Photo Player': ['green boots'],
                'Traits Player': ['purple cape'],
            }),
            patch('player_functions.get_player_ai_image_path',
                  side_effect=lambda name: 'character.png' if name == players[0] else None),
        ):
            for builder in (build_scene_image_prompt, build_flyer_scene_prompt):
                with self.subTest(builder=builder.__name__):
                    prompt = builder(
                        **{'players': players, 'game_type': 'vollis',
                           'labels_by_name': {name: name for name in players}}
                    )
                    self.assertNotIn('obsolete red hat', prompt)
                    self.assertIn('green boots', prompt)
                    self.assertIn('purple cape', prompt)
                    self.assertIn(CHARACTER_PRESERVATION_RULE, prompt)

    def test_reference_bundle_ignores_traits_only_for_attached_characters(self):
        players = ['Saved Player', 'Fallback Player']
        with (
            patch('player_functions.collect_player_ai_image_traits', return_value=[
                {'name': players[0], 'phrases': ['obsolete red hat']},
                {'name': players[1], 'phrases': ['green boots']},
            ]),
            patch('player_functions.collect_illustration_reference_images', side_effect=[
                {'kind': 'ai_portrait', 'parts': [
                    {'mime': 'image/png', 'data_b64': 'aW1hZ2U='},
                ]},
                {'kind': None, 'parts': []},
            ]),
            patch('email_content._build_labeled_identity_sheet', return_value=(None, [])),
        ):
            parts, included = _reference_parts_from_uploaded_photos(players)
        text = '\n'.join(part.get('text', '') for part in parts)
        self.assertEqual(included, players)
        self.assertNotIn('obsolete red hat', text)
        self.assertIn('green boots', text)
        self.assertIn(CHARACTER_PRESERVATION_RULE, text)
        self.assertTrue(any('inline_data' in part for part in parts))


if __name__ == '__main__':
    unittest.main()
