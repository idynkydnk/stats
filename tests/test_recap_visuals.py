import base64
import json
import unittest
from unittest.mock import Mock, patch

from email_content import (
    _generate_ai_text_openai, _generate_image_bytes_openai,
    _try_generate_email_hero_image, generate_email_hero_image,
)
from recap_visuals import (
    check_and_correct_picture, check_visual_checklist,
    extract_visual_checklist, prioritize_visual_checklist,
)


SOURCE = '''Do you guys want to talk about today's games? No, dude. I don't.
Jordan regrets not taking two ibuprofen before playing. Look at the weather forecast.
A ball got stuck under a line. Put Tyler holding a sign saying missing two balls.
Tyler lost two balls in two days. Put a sand monster stealing the balls in the picture.
Tyler's balls are colorful and they say Tyler and Steph on it.
Are you going to Tuesday fours? I don't know. Jordan drank a lot of honey.
No, I only had two sips. Let's put Jordan on the ground, drowning in honey.
Honey everywhere, all over his face and his body. We replayed four different points.
Lisa and Pepper Jack showed up. Pepper Jack's not allowed to be in there.
Pepper Jack is definitely in the picture. Pepper Jack is on Lisa's back.
Lisa Huang from the database. She's not in the games.
Put the sun inside Evan's eyes. Evan is not wearing glasses.'''

DETAILS = [
    "Literal suns inside Evan's eyes; Evan is not wearing glasses.",
    'Jordan lies on the ground covered in honey across his face and body.',
    'A sand monster visibly steals two colorful balls labeled "Tyler and Steph".',
]


def checks(missing=()):
    return json.dumps({'checks': [
        {'item': i, 'present': i not in missing,
         'evidence': 'The requested action is missing.' if i in missing else 'The action is visible.'}
        for i in range(1, len(DETAILS) + 1)
    ]})


class VisualChecklistTests(unittest.TestCase):
    def test_extraction_uses_full_transcript_and_rejects_unsupported_details(self):
        ai = Mock(return_value=json.dumps({'items': [
            {'detail': DETAILS[0], 'source_quote': "Put the sun inside Evan's eyes."},
            {'detail': DETAILS[1], 'source_quote': 'Honey everywhere, all over his face and his body.'},
            {'detail': DETAILS[2], 'source_quote': 'Put a sand monster stealing the balls in the picture.'},
        ]}))
        self.assertEqual(extract_visual_checklist(SOURCE, ai), DETAILS)
        self.assertIn(json.dumps(SOURCE, ensure_ascii=False), ai.call_args.args[0])
        ai.return_value = '{"items": [{"detail": "Add a dragon", "source_quote": "dragon"}]}'
        with self.assertRaisesRegex(ValueError, 'Could not extract'):
            extract_visual_checklist(SOURCE, ai)

    def test_blank_source_skips_ai_and_malformed_checklists_fail_explicitly(self):
        ai = Mock()
        self.assertEqual(extract_visual_checklist(' ', ai), [])
        ai.assert_not_called()
        for raw in ('{}', 'not json', '{"items": ["honey"]}',
                    '{"items": [{"detail": "", "source_quote": "honey"}]}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'Could not extract'):
                extract_visual_checklist(SOURCE, Mock(return_value=raw))

    def test_remakes_replace_priority_block_and_retain_scene(self):
        scene = 'Player names, stats, character references and weather.'
        first = prioritize_visual_checklist(scene, DETAILS)
        second = prioritize_visual_checklist(first, ['New requirement'])
        self.assertEqual(second.count('[RECAP VISUAL CHECKLIST]'), 1)
        self.assertNotIn(DETAILS[0], second)
        self.assertTrue(second.endswith(scene))
        self.assertLess(second.index('New requirement'), second.index(scene))
        self.assertEqual(prioritize_visual_checklist(second, []), scene)

    def test_review_requires_one_boolean_verdict_for_every_item(self):
        for raw in ('{}', '{"checks": []}', checks().replace('true', '"true"'),
                    checks().replace('"item": 2', '"item": 1'),
                    checks().replace('"item": 3', '"item": 99')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                check_visual_checklist(b'pixels', 'image/png', DETAILS, Mock(return_value=raw))

    def test_complete_image_is_checked_without_correction(self):
        ai, edit = Mock(return_value=checks()), Mock()
        raw, mime, audit = check_and_correct_picture(b'first', 'image/jpeg', DETAILS, 'scene', ai, edit)
        self.assertEqual((raw, mime), (b'first', 'image/jpeg'))
        ai.assert_called_once()
        self.assertEqual(ai.call_args.kwargs, {'image_bytes': b'first', 'image_mime': 'image/jpeg'})
        edit.assert_not_called()
        self.assertIn('"correction_attempted": false', audit)

    def test_missing_details_get_one_edit_of_actual_pixels_and_a_final_check(self):
        ai = Mock(side_effect=[checks((1, 2, 3)), checks((3,))])
        edit = Mock(return_value=(b'corrected', 'image/png'))
        raw, _, audit = check_and_correct_picture(b'first', 'image/jpeg', DETAILS, 'scene', ai, edit)
        self.assertEqual(raw, b'corrected')
        edit.assert_called_once()
        correction, refs = edit.call_args.args
        for detail in DETAILS:
            self.assertIn(detail, correction)
        self.assertEqual(base64.b64decode(refs[1]['inline_data']['data']), b'first')
        self.assertEqual(refs[1]['inline_data']['mime_type'], 'image/jpeg')
        self.assertEqual(ai.call_count, 2)
        self.assertEqual(ai.call_args.kwargs['image_bytes'], b'corrected')
        self.assertIn('"selected_image": "corrected"', audit)
        self.assertIn('"remaining_items": [\n    3', audit)

    def test_regression_or_no_improvement_keeps_original_without_retry(self):
        for remaining in ((2, 3), (1, 2)):
            with self.subTest(remaining=remaining):
                ai = Mock(side_effect=[checks((1, 2)), checks(remaining)])
                edit = Mock(return_value=(b'worse', 'image/png'))
                raw, _, audit = check_and_correct_picture(b'first', 'image/png', DETAILS, 'scene', ai, edit)
                self.assertEqual(raw, b'first')
                edit.assert_called_once()
                self.assertIn('"selected_image": "original"', audit)

    def test_failed_check_or_edit_preserves_original_and_records_failure(self):
        for phase in ('initial', 'edit', 'final'):
            with self.subTest(phase=phase), self.assertLogs('recap_visuals', level='WARNING'):
                ai = Mock(side_effect=ValueError('unavailable')) if phase == 'initial' else Mock(
                    side_effect=[checks((1,)), ValueError('bad review')])
                edit = Mock(side_effect=ValueError('edit failed')) if phase == 'edit' else Mock(
                    return_value=(b'new', 'image/png'))
                raw, _, audit = check_and_correct_picture(b'first', 'image/png', DETAILS, 'scene', ai, edit)
                self.assertEqual(raw, b'first')
                self.assertIn('"error":', audit)
                self.assertLessEqual(edit.call_count, 1)


class RecapVisualIntegrationTests(unittest.TestCase):
    def test_full_source_survives_lossy_routing_and_saved_prompt_contains_checklist(self):
        for custom in (None, 'Remove honey. Keep the sun effect.'):
            with (
                self.subTest(custom=custom),
                patch('email_content.filter_illustratable_players', return_value=['Evan']),
                patch('email_content._players_in_session_rank_order', return_value=['Evan']),
                patch('email_content._image_labels_for_players', return_value={}),
                patch('email_content._recap_name_replacer', return_value=lambda s: s or ''),
                patch('email_content._reference_parts_from_uploaded_photos', return_value=([], ['Evan'])),
                patch('recap_visuals.extract_visual_checklist', return_value=DETAILS) as extract,
                patch('email_content.generate_ai_text', side_effect=[checks((1, 2)), checks()]),
                patch('email_content._generate_image_bytes', side_effect=[
                    (b'first', 'image/png'), (b'corrected', 'image/png')]) as generate,
                patch('email_content._normalize_image_bytes_to_aspect', side_effect=lambda raw, **kw: (raw, 'image/jpeg')),
                patch('email_content._save_email_image', return_value=('url', 'path')) as save,
            ):
                result = generate_email_hero_image(
                    'key', 'doubles', [], ['Evan'], image_details='Sunny beach.',
                    visual_source=SOURCE, custom_scene_prompt=custom,
                )
                self.assertEqual(extract.call_args.args[0], custom or SOURCE)
                self.assertEqual(generate.call_count, 2)
                self.assertTrue(generate.call_args.kwargs['edit'])
                self.assertIn(DETAILS[1], generate.call_args_list[0].args[0])
                self.assertIn(DETAILS[1], result[4])
                self.assertIn('"selected_image": "corrected"', result[2])
                save.assert_called_once_with(b'corrected', 'jpg')

    def test_text_only_skips_checklist_generation(self):
        with patch('recap_visuals.extract_visual_checklist') as extract:
            _try_generate_email_hero_image('key', 'doubles', [], [], image_mode='none', visual_source=SOURCE)
        extract.assert_not_called()

    def test_openai_vision_receives_actual_image_and_mime(self):
        response = Mock(status_code=200)
        response.json.return_value = {'choices': [{'message': {'content': checks()}}]}
        with patch('requests.post', return_value=response) as post:
            _generate_ai_text_openai('Review this', 'key', image_bytes=b'pixels', image_mime='image/jpeg')
        content = post.call_args.kwargs['json']['messages'][0]['content']
        self.assertEqual(content[1]['image_url']['url'], 'data:image/jpeg;base64,cGl4ZWxz')

    def test_correction_forces_edit_and_never_falls_back_or_retries(self):
        for status in (400, 503):
            response = Mock(status_code=status)
            response.json.return_value = {'error': {'message': 'unavailable'}}
            with (
                self.subTest(status=status),
                patch('requests.post', return_value=response) as post,
                patch('time.sleep') as sleep,
                self.assertRaises(ValueError),
            ):
                _generate_image_bytes_openai('Fix missing sun', 'key', edit=True, reference_parts=[
                    {'inline_data': {'mime_type': 'image/png', 'data': 'cGl4ZWxz'}},
                ])
            post.assert_called_once()
            sleep.assert_not_called()
            self.assertEqual(post.call_args.kwargs['json']['tools'][0]['action'], 'edit')


if __name__ == '__main__':
    unittest.main()
