import base64
import io
import json
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import email_content as content
from player_functions import collect_illustration_reference_images
from recap_visuals import check_and_correct_picture


def picture(color):
    buf = io.BytesIO()
    Image.new('RGB', (100, 100), color).save(buf, 'PNG')
    return buf.getvalue()


def reference(raw, kind):
    return {'kind': kind, 'mime': 'image/png',
            'data_b64': base64.b64encode(raw).decode('ascii')}


class FaceReferenceTests(unittest.TestCase):
    def test_saved_character_does_not_replace_real_face_and_missing_sources_still_work(self):
        face, character = picture('red'), picture('blue')
        for has_face, has_character in ((True, True), (True, False), (False, True), (False, False)):
            with (
                self.subTest(face=has_face, character=has_character),
                patch('player_functions.collect_player_reference_images', return_value=[
                    {'parts': [reference(face, 'face_photo')]}
                ] if has_face else []),
                patch('player_functions.get_player_ai_image_path', return_value='character.png'),
                patch('player_functions.read_player_image_file',
                      return_value=(character, 'image/png') if has_character else (None, None)),
            ):
                result = collect_illustration_reference_images('Alex')
            expected = []
            if has_face:
                expected.append(('face_photo', face))
            if has_character:
                expected.append(('ai_portrait', character))
            self.assertEqual([(ref['kind'], base64.b64decode(ref['data_b64']))
                              for ref in result['parts']], expected)
            self.assertEqual(result['kind'], 'ai_portrait' if has_character else
                             'face_photo' if has_face else None)

    def test_eight_players_keep_their_own_face_and_character_within_upload_limit(self):
        players = [f'Player {i}' for i in range(8)]
        def sources(name):
            i = players.index(name)
            return {'kind': 'ai_portrait', 'parts': [
                reference(picture((20 + i, 0, 0)), 'face_photo'),
                reference(picture((0, 0, 20 + i)), 'ai_portrait'),
            ]}
        with (
            patch('player_functions.collect_player_ai_image_traits', return_value=[]),
            patch('player_functions.collect_illustration_reference_images', side_effect=sources),
        ):
            parts, included = content._reference_parts_from_uploaded_photos(
                players, labels_by_name={name: name for name in players},
            )
        self.assertEqual(included, players)
        images = [part for part in parts if part.get('inline_data')]
        self.assertEqual(len(images), 9)  # Overview + one complete pair per player.
        for i, part in enumerate(images[1:]):
            self.assertEqual(part['image_name'], players[i])
            self.assertEqual(part['image_index'], i + 2)
            img = Image.open(io.BytesIO(base64.b64decode(part['inline_data']['data'])))
            self.assertEqual(img.getpixel((400, 400)), (20 + i, 0, 0))
            self.assertEqual(img.getpixel((1200, 400)), (0, 0, 20 + i))
        text = '\n'.join(part.get('text', '') for part in parts)
        self.assertIn('LEFT panel (FACE IDENTITY)', text)
        self.assertIn('RIGHT panel (CHARACTER SCENE)', text)
        self.assertIn('face photo wins', text)

    def test_large_roster_never_silently_loses_players_or_references(self):
        players = [f'Player {i}' for i in range(17)]
        with (
            patch('player_functions.collect_player_ai_image_traits', return_value=[]),
            patch('player_functions.collect_illustration_reference_images', return_value={
                'kind': 'face_photo', 'parts': [reference(picture('red'), 'face_photo')],
            }),
        ):
            parts, included = content._reference_parts_from_uploaded_photos(players)
        self.assertEqual(included, players)
        self.assertEqual([part['image_name'] for part in parts if part.get('inline_data')], players)

    def test_both_generation_flows_send_face_character_pairs_and_identity_instructions(self):
        sources = {'kind': 'ai_portrait', 'parts': [
            reference(picture('red'), 'face_photo'), reference(picture('blue'), 'ai_portrait'),
        ]}
        for flow in ('recap', 'flyer'):
            for custom in (None, 'Put Alex on a pirate ship.'):
                with (
                    self.subTest(flow=flow, custom=custom),
                    patch('email_content.filter_illustratable_players', return_value=['Alex']),
                    patch('email_content._image_labels_for_players', return_value={'Alex': 'Alex'}),
                    patch('email_content._recap_name_replacer', return_value=lambda s: s or ''),
                    patch('player_functions.collect_player_ai_image_traits', return_value=[]),
                    patch('player_functions.collect_illustration_reference_images', return_value=sources),
                    patch('email_content.build_flyer_scene_prompt', return_value='Play volleyball'),
                    patch('email_content._refresh_flyer_stats', side_effect=lambda prompt, *args: prompt),
                    patch('recap_visuals.extract_visual_checklist', return_value=[]),
                    patch('email_content._generate_image_bytes', return_value=(b'result', 'image/png')) as generate,
                    patch('email_content._normalize_image_bytes_to_aspect', return_value=(b'result', 'image/png')),
                    patch('email_content._save_email_image', return_value=('url', 'path')),
                ):
                    if flow == 'recap':
                        content.generate_email_hero_image('key', 'doubles', [], ['Alex'],
                                                         custom_scene_prompt=custom)
                    else:
                        content.generate_flyer_image('key', ['Alex'], 'doubles',
                                                     custom_scene_prompt=custom)
                prompt = generate.call_args.args[0]
                self.assertIn('IDENTITY LOCK', prompt)
                self.assertIn('FACE LIKENESS', prompt)
                parts = generate.call_args.kwargs['reference_parts']
                images = [p for p in parts if p.get('inline_data')]
                self.assertEqual(len(images), 1)
                self.assertEqual(images[0]['image_name'], 'Alex')
                self.assertEqual(images[0]['reference_kind'], 'face_and_character')


class ImageTransportTests(unittest.TestCase):
    def test_api_error_fallback_keeps_model_and_all_references(self):
        failure = Mock(status_code=400)
        failure.json.return_value = {'error': {'message': 'Tool request rejected'}}
        success = Mock(status_code=200)
        success.json.return_value = {'data': [{'b64_json': 'cmVzdWx0'}]}
        refs = [{'inline_data': {'mime_type': 'image/png', 'data': value},
                 'image_index': i + 1, 'image_name': name}
                for i, (name, value) in enumerate([('Alex', 'YWxleA=='), ('Sam', 'c2Ft')])]
        with (
            patch('requests.post', side_effect=[failure, success]) as post,
            patch('email_content.OPENAI_IMAGE_MODEL', 'selected-image-model'),
        ):
            result = content._generate_image_bytes_openai('Scene', 'key', reference_parts=refs)
        self.assertEqual(result, (b'result', 'image/png'))
        self.assertEqual(post.call_count, 2)
        first, fallback = post.call_args_list
        self.assertEqual(first.kwargs['json']['tools'][0]['model'], 'selected-image-model')
        self.assertTrue(fallback.args[0].endswith('/images/edits'))
        self.assertEqual(fallback.kwargs['data']['model'], 'selected-image-model')
        self.assertEqual([item[1][1].getvalue() for item in fallback.kwargs['files']], [b'alex', b'sam'])

    def test_fallback_refuses_to_drop_references_over_its_limit(self):
        refs = [{'inline_data': {'mime_type': 'image/png', 'data': 'cGl4ZWxz'}}] * 17
        with (
            patch('email_content._generate_image_bytes_openai_responses', side_effect=ValueError('unavailable')),
            patch('requests.post') as post,
            self.assertRaisesRegex(ValueError, 'all player references'),
        ):
            content._generate_image_bytes_openai('Scene', 'key', reference_parts=refs)
        post.assert_not_called()

    def test_likeness_review_transmits_labeled_reference_pixels_to_vision(self):
        response = Mock(status_code=200)
        response.json.return_value = {'choices': [{'message': {'content': 'review'}}]}
        refs = [{'text': 'Alex face'}, {'image_name': 'Alex', 'image_index': 1,
                'inline_data': {'mime_type': 'image/jpeg', 'data': 'ZmFjZQ=='}}]
        with patch('requests.post', return_value=response) as post:
            content._generate_ai_text_openai('Review', 'key', reference_parts=refs)
        parts = post.call_args.kwargs['json']['messages'][0]['content']
        self.assertEqual(parts[-1]['image_url'], {'url': 'data:image/jpeg;base64,ZmFjZQ==', 'detail': 'high'})
        self.assertIn('reference for Alex', parts[-2]['text'])


class CorrectionLikenessTests(unittest.TestCase):
    def test_recap_keeps_original_when_correction_improves_scene_but_worsens_faces(self):
        refs = [{'text': 'IDENTITY LOCK — Image 1 is Alex.'},
                {'image_index': 1, 'image_name': 'Alex',
                 'inline_data': {'mime_type': 'image/png', 'data': 'ZmFjZQ=='}}]
        with (
            patch('email_content.filter_illustratable_players', return_value=['Alex']),
            patch('email_content._image_labels_for_players', return_value={'Alex': 'Alex'}),
            patch('email_content._recap_name_replacer', return_value=lambda s: s or ''),
            patch('email_content._reference_parts_from_uploaded_photos', return_value=(refs, ['Alex'])),
            patch('recap_visuals.extract_visual_checklist', return_value=['Add a ball']),
            patch('email_content.generate_ai_text', side_effect=[
                json.dumps({'checks': [{'item': 1, 'present': False, 'evidence': 'Missing ball'}]}),
                json.dumps({'checks': [{'item': 1, 'present': True, 'evidence': 'Ball visible'}]}),
                json.dumps({'identities_preserved': False, 'evidence': 'Alex has a different face.'}),
            ]),
            patch('email_content._generate_image_bytes', side_effect=[
                (b'original', 'image/png'), (b'corrected', 'image/png')]) as generate,
            patch('email_content._normalize_image_bytes_to_aspect', side_effect=lambda raw, **kw: (raw, 'image/png')),
            patch('email_content._save_email_image', return_value=('url', 'path')) as save,
        ):
            result = content.generate_email_hero_image('key', 'doubles', [], ['Alex'])
        correction = generate.call_args_list[1]
        self.assertTrue(correction.kwargs['edit'])
        self.assertEqual(correction.kwargs['reference_parts'][:len(refs)], refs)
        self.assertIn('IDENTITY LOCK', correction.args[0])
        self.assertIn('"identities_preserved": false', result[2])
        save.assert_called_once_with(b'original', 'png')

    def test_correction_keeps_reference_indexes_and_rejects_face_regressions(self):
        refs = [{'text': 'Image 1 is Alex; Image 2 is Sam.'}]
        for i, name in enumerate(('Alex', 'Sam'), 1):
            refs.append({'image_name': name, 'image_index': i,
                         'inline_data': {'mime_type': 'image/jpeg', 'data': base64.b64encode(name.encode()).decode()}})
        for verdict in (True, False, 'true', None, 'provider_error'):
            with self.subTest(verdict=verdict):
                review = json.dumps({'identities_preserved': verdict, 'evidence': 'Compared faces.'})
                if verdict == 'provider_error':
                    review = ValueError('Vision unavailable')
                ai = Mock(side_effect=[
                    json.dumps({'checks': [{'item': 1, 'present': False, 'evidence': 'Missing ball'}]}),
                    json.dumps({'checks': [{'item': 1, 'present': True, 'evidence': 'Ball visible'}]}), review,
                ])
                edit = Mock(return_value=(b'corrected', 'image/png'))
                with patch('recap_visuals.logging.getLogger'):
                    raw, _, audit = check_and_correct_picture(
                        b'original', 'image/jpeg', ['Add a ball'], 'scene', ai, edit,
                        reference_parts=refs,
                    )
                self.assertEqual(raw, b'corrected' if verdict is True else b'original')
                sent = edit.call_args.args[1]
                self.assertEqual(sent[:len(refs)], refs)
                self.assertEqual(base64.b64decode(sent[-1]['inline_data']['data']), b'original')
                converted = content._openai_responses_content('', sent)
                self.assertIn('Image 3 attached', converted[-2]['text'])
                self.assertEqual(ai.call_args.kwargs['reference_parts'][:len(refs)], refs)
                self.assertIn('"selected_image": "corrected"' if verdict is True else
                              '"selected_image": "original"', audit)
                edit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
