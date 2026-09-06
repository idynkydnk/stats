import os
import tempfile
import unittest
from unittest.mock import patch

from player_functions import (
    _ai_image_filename_for_player,
    _normalize_player_photo_rel_path,
    activate_player_ai_image,
    delete_all_player_ai_images,
    delete_player_ai_image_version,
    list_player_ai_image_versions,
    save_player_ai_image_bytes,
)


TINY_PNG = b'fake-png-bytes'


class PlayerAIImageVersionTests(unittest.TestCase):
    def test_filename_matching_does_not_include_other_player_ids(self):
        self.assertTrue(_ai_image_filename_for_player('ai_3.png', 3))
        self.assertTrue(_ai_image_filename_for_player('ai_3_20260906_ab12cd.png', 3))
        self.assertFalse(_ai_image_filename_for_player('ai_30.png', 3))
        self.assertFalse(_ai_image_filename_for_player('ai_3.png', 30))
        self.assertFalse(_ai_image_filename_for_player('3.jpg', 3))
        self.assertFalse(_ai_image_filename_for_player('photo_3.png', 3))

    def test_normalize_rejects_paths_outside_player_photos(self):
        self.assertEqual(
            _normalize_player_photo_rel_path('player_photos/ai_3.png'),
            'player_photos/ai_3.png',
        )
        self.assertEqual(
            _normalize_player_photo_rel_path('/static/player_photos/ai_3.png?v=1'),
            'player_photos/ai_3.png',
        )
        self.assertIsNone(_normalize_player_photo_rel_path('player_photos/../secrets.txt'))
        self.assertIsNone(_normalize_player_photo_rel_path('email_images/ai_3.png'))

    def test_replace_keeps_previous_file_and_admin_can_switch_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            current = {'path': None}

            def set_path(player_id, rel_path):
                current['path'] = rel_path

            def get_path(player_id):
                return current['path']

            with patch('player_functions.player_photos_dir', return_value=tmp), \
                    patch('player_functions.set_player_ai_image_path', side_effect=set_path), \
                    patch('player_functions.get_player_ai_image_path_by_id', side_effect=get_path), \
                    patch('player_functions._compress_image_bytes_under_limit',
                          side_effect=lambda raw, ext: (raw, '.png')):
                first = save_player_ai_image_bytes(3, TINY_PNG, 'png')
                second = save_player_ai_image_bytes(3, TINY_PNG, 'png')

                self.assertNotEqual(first, second)
                self.assertTrue(os.path.isfile(os.path.join(tmp, os.path.basename(first))))
                self.assertTrue(os.path.isfile(os.path.join(tmp, os.path.basename(second))))
                self.assertEqual(current['path'], second)

                versions = list_player_ai_image_versions(3)
                self.assertEqual(len(versions), 2)
                self.assertEqual(versions[0]['path'], second)
                self.assertTrue(versions[0]['current'])

                activate_player_ai_image(3, first)
                self.assertEqual(current['path'], first)
                versions = list_player_ai_image_versions(3)
                current_paths = [item['path'] for item in versions if item['current']]
                self.assertEqual(current_paths, [first])

                delete_player_ai_image_version(3, second)
                self.assertFalse(os.path.isfile(os.path.join(tmp, os.path.basename(second))))
                self.assertTrue(os.path.isfile(os.path.join(tmp, os.path.basename(first))))
                self.assertEqual(current['path'], first)

                delete_all_player_ai_images(3)
                self.assertEqual(os.listdir(tmp), [])
                self.assertIsNone(current['path'])

    def test_activate_rejects_another_players_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = os.path.join(tmp, 'ai_9.png')
            with open(other, 'wb') as handle:
                handle.write(TINY_PNG)
            with patch('player_functions.player_photos_dir', return_value=tmp), \
                    patch('player_functions.get_player_ai_image_path_by_id', return_value=None):
                with self.assertRaises(ValueError):
                    activate_player_ai_image(3, 'player_photos/ai_9.png')


if __name__ == '__main__':
    unittest.main()
