import unittest

from scripts.check_recap_likeness import can_repair


class RecapRepairGuardTests(unittest.TestCase):
    def setUp(self):
        self.recap = dict(share_id='recap', username='owner', game_ids_json='[1]',
                          image_details='Blue volleyballs', hero_image_url='')

    def test_unchanged_missing_picture_can_be_repaired(self):
        self.assertTrue(can_repair(self.recap, dict(self.recap)))

    def test_existing_or_deleted_picture_is_never_overwritten(self):
        self.assertFalse(can_repair(self.recap, None))
        self.assertFalse(can_repair(self.recap, dict(self.recap, hero_image_url='/new.jpg')))

    def test_changed_owner_games_or_picture_request_stops_repair(self):
        for key in ('share_id', 'username', 'game_ids_json', 'image_details'):
            with self.subTest(key=key):
                self.assertFalse(can_repair(self.recap, dict(self.recap, **{key: 'changed'})))


if __name__ == '__main__':
    unittest.main()
