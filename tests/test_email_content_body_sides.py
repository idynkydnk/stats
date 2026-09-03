import os
import unittest
from unittest.mock import patch

from email_content import (
    BODY_SIDE_CONVENTION,
    _append_body_side_convention,
    _generate_image_bytes,
    _image_prompt_bundle,
    build_scene_image_prompt,
)


class BodySideConventionTests(unittest.TestCase):
    def test_default_scene_prompt_defines_left_as_the_persons_own_left(self):
        prompt = build_scene_image_prompt('doubles', [])

        self.assertIn(BODY_SIDE_CONVENTION, prompt)
        self.assertIn("person's own anatomical left or right", prompt)
        self.assertIn("left leg is their own left leg", prompt)

    def test_convention_is_appended_only_once(self):
        prompt = _append_body_side_convention('Raise the left leg.')
        prompt = _append_body_side_convention(prompt)

        self.assertEqual(prompt.count('BODY-SIDE CONVENTION'), 1)

    def test_custom_prompt_receives_convention_before_image_api_call(self):
        with (
            patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}),
            patch('email_content.active_ai_provider', return_value='openai'),
            patch(
                'email_content._generate_image_bytes_openai',
                return_value=(b'image', 'image/png'),
            ) as generate,
        ):
            _generate_image_bytes('Raise the left leg.', 'fallback-key')

        sent_prompt = generate.call_args.args[0]
        self.assertIn(BODY_SIDE_CONVENTION, sent_prompt)
        self.assertEqual(sent_prompt.count('BODY-SIDE CONVENTION'), 1)

    def test_saved_image_prompt_matches_the_api_convention(self):
        bundled = _image_prompt_bundle([], 'Raise the left leg.')

        self.assertIn(BODY_SIDE_CONVENTION, bundled)


if __name__ == '__main__':
    unittest.main()
