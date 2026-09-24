import io
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask, jsonify, request, session, redirect

from PIL import Image, ImageDraw

from email_content import (
    _email_hero_html, _normalize_image_mode, _try_generate_email_hero_image,
    generate_email_hero_image,
)
from recap_animation import animation_gif_from_sheet, animation_sheet_prompt, animation_subject


def sample_sheet():
    sheet = Image.new('RGB', (1536, 1440))
    draw = ImageDraw.Draw(sheet)
    colors = [(i * 20, 40, 220 - i * 15) for i in range(12)]
    for i, color in enumerate(colors):
        x, y = (i % 4) * 384, (i // 4) * 480
        draw.rectangle((x, y, x + 383, y + 479), fill=color)
    buf = io.BytesIO()
    sheet.save(buf, 'PNG')
    return buf.getvalue(), colors


class RecapAnimationTests(unittest.TestCase):
    def test_website_and_app_queue_animation_and_correct_action(self):
        # Load the real handlers without the production app's startup DB writes.
        root = Path(__file__).resolve().parents[1]
        for native in (False, True):
            with self.subTest(native=native):
                app = Flask(__name__)
                app.secret_key = 'test'
                jobs = SimpleNamespace(enqueue_job=Mock(return_value=42), daemon_is_alive=lambda: True)
                service = SimpleNamespace(ai_jobs=jobs, _normalize_image_mode=_normalize_image_mode, log_activity=Mock())
                namespace = dict(app=app, request=request, session=session, jsonify=jsonify,
                                 redirect=redirect, url_for=lambda *a, **kw: '/job/42',
                                 login_required=lambda f: f, api_login_required=lambda f: f,
                                 ai_jobs=jobs, log_activity=service.log_activity,
                                 _normalize_image_mode=_normalize_image_mode, _S=lambda: service)
                filename = 'ios_api.py' if native else 'stats.py'
                name = 'api_ai_summary_json' if native else 'preview_ai_summary_with_prompt'
                node = next(n for n in ast.walk(ast.parse((root / filename).read_text()))
                            if isinstance(n, ast.FunctionDef) and n.name == name)
                exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), namespace)
                payload = dict(game_ids=['1'], image_mode='animation', image_details='Moving player: Sam\nAction: wave' if native else 'sunset', animation_details='wave', animation_player='Sam')
                client = app.test_client()
                response = client.post('/api/ai/summary', json=payload) if native else client.post('/preview_ai_summary_with_prompt/', data=payload)
                self.assertIn(response.status_code, (200, 302))
                self.assertEqual(jobs.enqueue_job.call_args.kwargs['image_mode'], 'animation')
                self.assertEqual(jobs.enqueue_job.call_args.kwargs['image_details'], 'Moving player: Sam\nAction: wave')

    def test_twelve_frames_in_order_with_loop_and_portrait_dimensions(self):
        sheet, colors = sample_sheet()
        animation = Image.open(io.BytesIO(animation_gif_from_sheet(sheet)))
        self.assertEqual(animation.format, 'GIF')
        self.assertEqual(animation.n_frames, 12)
        self.assertEqual(animation.size, (384, 480))
        self.assertEqual(animation.info['loop'], 0)
        for i, color in enumerate(colors):
            animation.seek(i)
            self.assertEqual(animation.info['duration'], 160)
            self.assertEqual(animation.convert('RGB').getpixel((192, 240)), color)

    def test_small_or_invalid_sheets_are_rejected(self):
        with self.assertRaises(Exception):
            animation_gif_from_sheet(b'not an image')
        buf = io.BytesIO()
        Image.new('RGB', (40, 30)).save(buf, 'PNG')
        with self.assertRaises(ValueError):
            animation_gif_from_sheet(buf.getvalue())

    def test_older_pillow_without_resampling_or_dither_enums(self):
        sheet, colors = sample_sheet()
        legacy_image = SimpleNamespace(
            open=Image.open, new=Image.new, composite=Image.composite, LANCZOS=1, NONE=0,
        )
        with patch('recap_animation.Image', legacy_image):
            result = animation_gif_from_sheet(sheet)
        animation = Image.open(io.BytesIO(result))
        self.assertEqual(animation.n_frames, 12)
        self.assertEqual(animation.info['loop'], 0)
        for i, color in enumerate(colors):
            animation.seek(i)
            self.assertEqual(animation.convert('RGB').getpixel((192, 240)), color)

    def test_animation_uses_same_references_and_saves_gif_without_still_conversion(self):
        raw, _ = sample_sheet()
        refs = [{'text': 'Reference for Sam'}, {'text': 'Reference for Alex'}]
        with (
            patch('email_content.filter_illustratable_players', return_value=['Sam', 'Alex']),
            patch('email_content._players_in_session_rank_order', return_value=['Sam', 'Alex']),
            patch('email_content._image_labels_for_players', return_value={}),
            patch('email_content._reference_parts_from_uploaded_photos', return_value=(refs, ['Sam', 'Alex'])),
            patch('email_content._append_group_picture_details', side_effect=lambda p, *_: p),
            patch('email_content._generate_image_bytes', return_value=(raw, 'image/png')) as generate,
            patch('email_content._save_email_image', return_value=('https://example.com/hero.gif', '/tmp/hero.gif')) as save,
            patch('email_content._normalize_image_bytes_to_aspect', return_value=(raw, 'image/png')) as normalize,
        ):
            result = generate_email_hero_image(
                'unused', 'doubles', [], ['Sam', 'Alex'],
                image_details='Moving player: Sam\nAction: Bump the ball.',
                custom_scene_prompt='Both players at the beach.', animation=True,
            )
        self.assertTrue(result[0].endswith('.gif'))
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(generate.call_args_list[0].kwargs['reference_parts'], refs)
        self.assertEqual(generate.call_args.kwargs['reference_parts'][:2], refs)
        self.assertIn('STARTING FRAME', generate.call_args.kwargs['reference_parts'][2]['text'])
        self.assertEqual(generate.call_args.kwargs['output_size'], '1536x1440')
        self.assertIn('ONLY MOVING PERSON: Sam', generate.call_args.args[0])
        self.assertIn('Requested movement: Bump the ball.', generate.call_args.args[0])
        self.assertEqual(save.call_args.args[1], 'gif')
        self.assertEqual(Image.open(io.BytesIO(save.call_args.args[0])).n_frames, 12)
        normalize.assert_called_once()
        self.assertIn('hero.gif', _email_hero_html(result[0]))
        self.assertIn('hero-image-card', _email_hero_html(result[0]))

    def test_mode_dispatch_and_generation_failure_preserve_recap_contract(self):
        self.assertEqual(_normalize_image_mode('animation'), 'animation')
        with (
            patch('email_content._illustration_meta', return_value={'api_calls': 1}),
            patch('email_content.generate_email_hero_image', side_effect=ValueError('bad sheet')) as generate,
        ):
            result = _try_generate_email_hero_image('unused', 'doubles', [], ['Sam'], image_mode='animation')
        self.assertTrue(generate.call_args.kwargs['animation'])
        self.assertIsNone(result[0])
        self.assertTrue(result[2])

    def test_stationary_area_is_identical_to_first_frame(self):
        sheet, _ = sample_sheet()
        first = Image.new('RGB', (384, 480), (30, 200, 90))
        first_buf = io.BytesIO()
        first.save(first_buf, 'PNG')
        animation = Image.open(io.BytesIO(animation_gif_from_sheet(sheet, first_buf.getvalue())))
        animation.seek(0)
        fixed = animation.convert('RGB').crop((192, 0, 384, 480)).tobytes()
        self.assertEqual(animation.n_frames, 12)
        for i in range(1, 12):
            animation.seek(i)
            self.assertEqual(animation.convert('RGB').crop((192, 0, 384, 480)).tobytes(), fixed)
        self.assertNotEqual(animation.convert('RGB').getpixel((20, 240)), (30, 200, 90))

    def test_selected_player_must_have_a_reference(self):
        self.assertEqual(animation_subject('Moving player: Sam\nAction: Wave', ['Alex', 'Sam']), ('Sam', 'Wave'))
        with self.assertRaises(ValueError):
            animation_subject('Moving player: Stranger\nAction: Wave', ['Sam'])
        self.assertEqual(animation_subject('', ['Sam'])[0], 'Sam')

    def test_default_action_and_user_action(self):
        self.assertIn('Wave', animation_sheet_prompt('beach', ''))
        self.assertIn('EXACTLY 12', animation_sheet_prompt('beach', 'wave'))
        self.assertIn('Requested movement: wave', animation_sheet_prompt('beach', 'wave'))


if __name__ == '__main__':
    unittest.main()
