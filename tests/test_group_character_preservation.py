import unittest
from unittest.mock import patch

from email_content import (
    CHARACTER_PRESERVATION_RULE,
    _reference_parts_from_uploaded_photos,
    build_flyer_scene_prompt,
    build_scene_image_prompt,
    generate_email_hero_image,
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

    def test_complete_character_references_and_stats_reach_default_and_custom_generation(self):
        players = ['Kevin Cleary', 'Jordan']
        stats = [[players[0], 3, 0, 1.0, 12], [players[1], 0, 3, 0.0, -12]]
        references = {
            players[0]: {'kind': 'ai_portrait', 'parts': [
                {'mime': 'image/png', 'data_b64': 'a2V2aW4td2l0aC13aWZl'},
            ]},
            players[1]: {'kind': 'ai_portrait', 'parts': [
                {'mime': 'image/png', 'data_b64': 'am9yZGFuLXdpdGgtZnJpZW5k'},
            ]},
        }
        for custom in (None, 'Put them on a pirate ship. No extra people. No text.'):
            with (
                self.subTest(custom=custom),
                patch('email_content.filter_illustratable_players', return_value=players),
                patch('player_functions.player_display_names_map', return_value={
                    players[0]: 'Kevin', players[1]: 'Jordan',
                }),
                patch('player_functions.collect_player_ai_image_traits', return_value=[]),
                patch('player_functions.get_player_ai_image_path', return_value='saved.png'),
                patch('player_functions.collect_illustration_reference_images',
                      side_effect=lambda name: references[name]),
                patch('email_content._build_labeled_identity_sheet',
                      return_value=(b'full contact sheet', ['Kevin', 'Jordan'])),
                patch('email_content._generate_image_bytes',
                      return_value=(b'result', 'image/png')) as generate,
                patch('email_content._normalize_image_bytes_to_aspect',
                      return_value=(b'result', 'image/png')),
                patch('email_content._save_email_image', return_value=('url', 'path')),
            ):
                generate_email_hero_image(
                    'test-key', 'doubles', [], players, player_stats=stats,
                    custom_scene_prompt=custom,
                )
            prompt = generate.call_args.args[0]
            parts = generate.call_args.kwargs['reference_parts']
            text = '\n'.join(part.get('text', '') for part in parts)
            images = [part['inline_data']['data'] for part in parts if 'inline_data' in part]
            self.assertEqual(images[1:], [references[name]['parts'][0]['data_b64'] for name in players])
            self.assertIn('Kevin 3-0 (+12)', text)
            self.assertIn('Jordan 0-3 (-12)', text)
            self.assertIn(CHARACTER_PRESERVATION_RULE, prompt)
            self.assertIn('2 distinct roster players, plus everyone in their character pictures', prompt)
            self.assertIn('companions do not receive player stats', prompt)
            self.assertIn('Existing text is allowed', prompt)
            self.assertNotIn('Do not add extra people', text)
            self.assertNotIn('Each cell is one person', text)
            self.assertNotIn('remove or ignore it', prompt)
            if custom:
                self.assertIn(custom, prompt)
                self.assertIn('override any generic no-extra-people or no-text instruction', prompt)


if __name__ == '__main__':
    unittest.main()
