import base64
import json
import unittest
from unittest.mock import Mock, patch

import requests

import email_content as content
from recap_visuals import (
    check_and_correct_picture, check_character_likenesses,
)


def references():
    return [
        part
        for index, name in enumerate(('Goshow', 'Koki'), 1)
        for part in (
            {'text': f'Reference for {name}.'},
            {'image_name': name, 'image_index': index, 'reference_kind': 'ai_portrait',
             'inline_data': {'mime_type': 'image/png',
                             'data': base64.b64encode(name.encode()).decode()}},
        )
    ]


def review(matches=True):
    return {'players': [
        {'image': 1, 'matches': matches,
         'evidence': 'Same giant mouth.' if matches else 'Goshow lost the exaggerated giant mouth.'},
        {'image': 2, 'matches': True, 'evidence': 'Same face, flowing outfit and hair.'},
    ]}


class RecapCharacterLikenessTests(unittest.TestCase):
    def test_review_compares_all_actual_reference_images_with_the_finished_picture(self):
        ai = Mock(return_value=json.dumps(review()))
        refs = references()
        self.assertEqual(check_character_likenesses(b'finished', 'image/jpeg', refs, 'scene', ai), review())
        sent = ai.call_args.kwargs['reference_parts']
        self.assertEqual(sent[:len(refs)], refs)
        self.assertEqual(base64.b64decode(sent[-1]['inline_data']['data']), b'finished')
        self.assertEqual(sent[-1]['inline_data']['mime_type'], 'image/jpeg')
        self.assertIn('exaggerated/caricature', ai.call_args.args[0])

    def test_incomplete_or_ambiguous_reviews_cannot_pass(self):
        for value in (
            {}, {'players': []}, {'players': [review()['players'][0]]},
            {'players': [review()['players'][0]] * 2},
            {'players': [dict(p, matches='true') for p in review()['players']]},
            {'players': [dict(p, image=99) for p in review()['players']]},
            {'players': [dict(p, evidence='') for p in review()['players']]},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_character_likenesses(b'image', 'image/png', references(), 'scene',
                                          Mock(return_value=json.dumps(value)))

    def test_mixed_review_distinguishes_faces_from_complete_character_pictures(self):
        refs = references()
        refs[3]['reference_kind'] = 'face_photo'
        refs[2]['text'] += ' Signature looks: green boots.'
        ai = Mock(return_value=json.dumps(review()))
        check_character_likenesses(b'finished', 'image/png', refs, 'scene', ai)
        prompt = ai.call_args.args[0]
        self.assertIn('Face photo image numbers: [2]', prompt)
        self.assertIn('check facial identity', prompt)
        self.assertIn("Do not require the photo's outfit", prompt)
        self.assertIn('For saved AI characters, check the same face, body proportions', prompt)
        self.assertEqual(ai.call_args.kwargs['reference_parts'][:len(refs)], refs)

    def test_first_image_is_checked_even_without_extra_scene_requests(self):
        ai = Mock(return_value=json.dumps(review()))
        edit = Mock()
        raw, _, audit = check_and_correct_picture(
            b'original', 'image/png', [], 'scene', ai, edit,
            reference_parts=references(), check_characters=True,
        )
        self.assertEqual(raw, b'original')
        ai.assert_called_once()
        edit.assert_not_called()
        self.assertIn('initial_character_review', audit)

    def test_mismatched_character_gets_one_reference_based_correction(self):
        ai = Mock(side_effect=[json.dumps(review(False)), json.dumps(review(True))])
        edit = Mock(return_value=(b'corrected', 'image/png'))
        refs = references()
        raw, _, audit = check_and_correct_picture(
            b'original', 'image/png', [], 'scene', ai, edit,
            reference_parts=refs, check_characters=True,
        )
        self.assertEqual(raw, b'corrected')
        edit.assert_called_once()
        prompt, sent = edit.call_args.args
        self.assertIn('Goshow lost the exaggerated giant mouth', prompt)
        self.assertEqual(sent[:len(refs)], refs)
        self.assertEqual(base64.b64decode(sent[-1]['inline_data']['data']), b'original')
        self.assertIn('"selected_image": "corrected"', audit)

    def test_failed_or_unverified_correction_keeps_the_completed_picture(self):
        for final in (json.dumps(review(False)), '{}', ValueError('Review unavailable')):
            with self.subTest(final=final), patch('recap_visuals.logging.getLogger'):
                ai = Mock(side_effect=[json.dumps(review(False)), final])
                edit = Mock(return_value=(b'still wrong', 'image/png'))
                raw, mime, audit = check_and_correct_picture(
                    b'original', 'image/png', [], 'scene', ai, edit,
                    reference_parts=references(), check_characters=True,
                )
            edit.assert_called_once()
            self.assertEqual((raw, mime), (b'original', 'image/png'))
            self.assertIn('"selected_image": "original"', audit)

    def test_incomplete_improvement_is_saved_without_requiring_every_character_to_pass(self):
        initial = review(False)
        initial['players'][1]['matches'] = False
        ai = Mock(side_effect=[json.dumps(initial), json.dumps(review(False))])
        edit = Mock(return_value=(b'better', 'image/png'))
        raw, _, audit = check_and_correct_picture(
            b'original', 'image/png', [], 'scene', ai, edit,
            reference_parts=references(), check_characters=True,
        )
        self.assertEqual(raw, b'better')
        self.assertIn('"selected_image": "corrected"', audit)
        edit.assert_called_once()

    def test_correction_does_not_trade_one_players_likeness_for_another(self):
        corrected = review(True)
        corrected['players'][1]['matches'] = False
        ai = Mock(side_effect=[json.dumps(review(False)), json.dumps(corrected)])
        raw, _, _ = check_and_correct_picture(
            b'original', 'image/jpeg', [], 'scene', ai, Mock(return_value=(b'worse', 'image/png')),
            reference_parts=references(), check_characters=True,
        )
        self.assertEqual(raw, b'original')

    def test_review_or_correction_outage_does_not_discard_the_completed_picture(self):
        for phase in ('initial', 'edit'):
            with self.subTest(phase=phase), self.assertLogs('recap_visuals', level='WARNING'):
                ai = Mock(side_effect=ValueError('Unavailable')) if phase == 'initial' else Mock(
                    return_value=json.dumps(review(False)))
                edit = Mock(side_effect=requests.Timeout('Correction timed out'))
                raw, mime, audit = check_and_correct_picture(
                    b'original', 'image/jpeg', [], 'scene', ai, edit,
                    reference_parts=references(), check_characters=True,
                )
            self.assertEqual((raw, mime), (b'original', 'image/jpeg'))
            self.assertIn('"error":', audit)
            self.assertIn('"selected_image": "original"', audit)
            self.assertEqual(edit.call_count, 0 if phase == 'initial' else 1)

    def test_scene_improvement_can_be_used_when_likeness_has_not_regressed(self):
        ai = Mock(side_effect=[
            json.dumps(review(False)),
            json.dumps({'checks': [{'item': 1, 'present': False, 'evidence': 'Ball missing'}]}),
            json.dumps({'checks': [{'item': 1, 'present': True, 'evidence': 'Ball visible'}]}),
            json.dumps(review(False)),
        ])
        raw, _, audit = check_and_correct_picture(
            b'original', 'image/png', ['Add a ball'], 'scene', ai,
            Mock(return_value=(b'better scene', 'image/png')),
            reference_parts=references(), check_characters=True,
        )
        self.assertEqual(raw, b'better scene')
        self.assertIn('"selected_image": "corrected"', audit)

    def test_character_improvement_does_not_drop_existing_scene_details(self):
        ai = Mock(side_effect=[
            json.dumps(review(False)),
            json.dumps({'checks': [{'item': 1, 'present': True, 'evidence': 'Ball visible'}]}),
            json.dumps({'checks': [{'item': 1, 'present': False, 'evidence': 'Ball missing'}]}),
        ])
        raw, _, audit = check_and_correct_picture(
            b'original', 'image/png', ['Add a ball'], 'scene', ai,
            Mock(return_value=(b'less complete', 'image/png')),
            reference_parts=references(), check_characters=True,
        )
        self.assertEqual(raw, b'original')
        self.assertIn('"selected_image": "original"', audit)

    def test_generation_saves_a_picture_even_if_likeness_remains_imperfect(self):
        with (
            patch('email_content.filter_illustratable_players', return_value=['Goshow', 'Koki']),
            patch('email_content._image_labels_for_players', return_value={'Goshow': 'Goshow', 'Koki': 'Koki'}),
            patch('email_content._recap_name_replacer', return_value=lambda s: s or ''),
            patch('email_content._reference_parts_from_uploaded_photos', return_value=(references(), ['Goshow', 'Koki'])),
            patch('recap_visuals.extract_visual_checklist', return_value=[]),
            patch('email_content.generate_ai_text', return_value=json.dumps(review(False))),
            patch('email_content._generate_image_bytes', side_effect=[
                (b'original', 'image/png'), (b'corrected', 'image/png'),
            ]) as generate,
            patch('email_content._normalize_image_bytes_to_aspect', side_effect=lambda raw, **kw: (raw, 'image/png')),
            patch('email_content._save_email_image', return_value=('url', 'path')) as save,
            patch('email_content._illustration_meta', return_value={}),
        ):
            result = content._try_generate_email_hero_image(
                'key', 'doubles', [], ['Goshow', 'Koki'], image_mode='image',
            )
        self.assertEqual(generate.call_count, 2)
        self.assertTrue(all(call.kwargs['reference_edit'] for call in generate.call_args_list))
        self.assertTrue(generate.call_args.kwargs['edit'])
        save.assert_called_once_with(b'original', 'png')
        self.assertEqual(result[:3], ('url', 'path', None))
        self.assertIn('"selected_image": "original"', result[3])
        self.assertTrue(result[4]['scene_prompt'])

    def test_saved_prompt_gets_the_brief_character_rule_only_once(self):
        scene = content._recap_character_prompt(content._LEGACY_RECAP_IMAGE_PROMPT + '\nAdd blue balls.')
        scene = content._recap_character_prompt(scene)
        self.assertIn(content.RECAP_IMAGE_PROMPT, scene)
        self.assertEqual(scene.count(content.RECAP_CHARACTER_RULE), 1)
        self.assertEqual(scene.count(content.RECAP_FACE_RULE), 1)
        self.assertIn('Add blue balls.', scene)


class RecapImageEditTransportTests(unittest.TestCase):
    def test_saved_character_files_and_exact_prompt_go_directly_to_image_editing(self):
        response = Mock(status_code=200)
        response.json.return_value = {'data': [{'b64_json': 'cmVzdWx0'}]}
        with (
            patch('requests.post', return_value=response) as post,
            patch('email_content.OPENAI_RECAP_IMAGE_MODEL', 'recap-edit-model'),
            patch('email_content.OPENAI_IMAGE_MODEL', 'other-image-model'),
        ):
            result = content._generate_image_bytes_openai(
                content.RECAP_IMAGE_PROMPT, 'key', reference_parts=references(), reference_edit=True,
            )
        self.assertEqual(result, (b'result', 'image/png'))
        post.assert_called_once()
        self.assertTrue(post.call_args.args[0].endswith('/images/edits'))
        self.assertEqual(post.call_args.kwargs['data']['model'], 'recap-edit-model')
        self.assertNotIn('input_fidelity', post.call_args.kwargs['data'])
        self.assertTrue(post.call_args.kwargs['data']['prompt'].endswith(content.RECAP_IMAGE_PROMPT))
        self.assertEqual([item[1][1].getvalue() for item in post.call_args.kwargs['files']],
                         [b'Goshow', b'Koki'])

    def test_automatic_correction_uses_the_same_recap_model(self):
        response = Mock(status_code=200)
        response.json.return_value = {'data': [{'b64_json': 'cmVzdWx0'}]}
        with (
            patch('requests.post', return_value=response) as post,
            patch('email_content.OPENAI_RECAP_IMAGE_MODEL', 'recap-edit-model'),
            patch('email_content.OPENAI_IMAGE_MODEL', 'other-image-model'),
        ):
            content._generate_image_bytes_openai(
                'Restore saved character faces', 'key', reference_parts=references(),
                reference_edit=True, edit=True,
            )
        self.assertEqual(post.call_args.kwargs['data']['model'], 'recap-edit-model')
        post.assert_called_once()

    def test_missing_references_never_turn_into_a_new_image_request(self):
        with patch('requests.post') as post, self.assertRaisesRegex(ValueError, 'AI character pictures or face photos'):
            content._generate_image_bytes_openai('scene', 'key', reference_edit=True)
        post.assert_not_called()

    def test_character_correction_is_one_attempt_even_on_transport_failure(self):
        with (
            patch('requests.post', side_effect=requests.Timeout('Timeout')) as post,
            self.assertRaises(requests.Timeout),
        ):
            content._generate_image_bytes_openai(
                'Fix likeness', 'key', reference_parts=references(), reference_edit=True, edit=True,
            )
        post.assert_called_once()


if __name__ == '__main__':
    unittest.main()
