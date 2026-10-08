import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import admin_functions as admin
import recap_email_queue as queue


class RecapEmailQueueTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for replacement in (
            patch.object(admin, 'stats_db_path', return_value=str(root / 'stats.db')),
            patch.object(admin, '_recap_storage_dir', return_value=str(root)),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)
        clock_patch = patch.object(queue.time, 'time', return_value=1000)
        self.clock = clock_patch.start()
        self.addCleanup(clock_patch.stop)

    def test_same_games_replace_pending_recap_and_restart_hour(self):
        queue.schedule('first', 'kyle', 'doubles', [1, 2])
        self.clock.return_value = 2000
        queue.schedule('latest', 'kyle', 'doubles', ['2', '1', '1'])
        self.clock.return_value = 4600
        self.assertIsNone(queue.claim_due())
        self.clock.return_value = 5600
        self.assertEqual(queue.claim_due(), 'latest')
        self.assertIsNone(queue.claim_due())

    def test_different_games_sports_and_creators_remain_independent(self):
        for sid, user, sport, games in (
            ('a', 'kyle', 'doubles', [1]), ('b', 'kyle', 'doubles', [2]),
            ('c', 'kyle', 'vollis', [1]), ('d', 'other', 'doubles', [1]),
        ):
            queue.schedule(sid, user, sport, games)
        self.clock.return_value = 4600
        self.assertEqual({queue.claim_due() for _ in range(4)}, {'a', 'b', 'c', 'd'})
        self.assertIsNone(queue.claim_due())

    def test_summary_and_picture_saves_restart_timer(self):
        admin.insert_ai_recap_page('recap', 'kyle', 'doubles', '<p>First</p>')
        queue.schedule('recap', 'kyle', 'doubles', [1])
        for now, changes in (
            (2000, {'html_body': '<p>Remade</p>', 'subject': 'New summary'}),
            (3000, {'hero_image_url': '/static/new.png'}),
        ):
            self.clock.return_value = now
            admin.update_ai_recap_page('recap', **changes)
        self.clock.return_value = 6599
        self.assertIsNone(queue.claim_due())
        self.clock.return_value = 6600
        self.assertEqual(queue.claim_due(), 'recap')
        saved = admin.get_ai_recap_page('recap')
        self.assertEqual(saved['html_body'], '<p>Remade</p>')
        self.assertEqual(saved['hero_image_url'], '/static/new.png')

    def test_metadata_only_edits_do_not_delay_and_sent_mail_is_not_requeued(self):
        admin.insert_ai_recap_page('recap', 'kyle', 'doubles', '<p>First</p>')
        queue.schedule('recap', 'kyle', 'doubles', [1])
        self.clock.return_value = 2000
        admin.update_ai_recap_page('recap', scene_prompt='Try again', hero_image_error='Failed')
        self.clock.return_value = 4600
        self.assertEqual(queue.claim_due(), 'recap')
        queue.finish('recap', 'sent')
        admin.update_ai_recap_page('recap', html_body='<p>Later edit</p>')
        admin.write_recap_html_file('legacy', '<p>Old recap</p>')
        admin.update_ai_recap_page('legacy', html_body='<p>Old recap</p>')
        self.clock.return_value = 10000
        self.assertIsNone(queue.claim_due())

    def test_superseded_page_edit_does_not_revive_its_email(self):
        queue.schedule('old', 'kyle', 'doubles', [1])
        queue.schedule('new', 'kyle', 'doubles', [1])
        with queue.updating('old'):
            pass
        self.clock.return_value = 4600
        self.assertEqual(queue.claim_due(), 'new')
        self.assertIsNone(queue.claim_due())

    def test_failed_save_does_not_reset_timer(self):
        queue.schedule('recap', 'kyle', 'doubles', [1])
        self.clock.return_value = 2000
        with self.assertRaises(OSError), queue.updating('recap'):
            raise OSError('Disk full')
        self.clock.return_value = 4600
        self.assertEqual(queue.claim_due(), 'recap')


if __name__ == '__main__':
    unittest.main()
