import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import admin_functions as admin


class RecapDeletionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.storage = os.path.join(directory.name, 'recaps')
        os.makedirs(self.storage)
        jobs = types.SimpleNamespace(list_jobs_with_share_ids=lambda **kwargs: [{
            'share_id': 'deleted-recap', 'username': 'kyle',
            'game_type': 'doubles', 'completed_at': '2026-09-30 17:22:00',
        }])
        for replacement in (
            patch.object(admin, '_recap_storage_dir', return_value=self.storage),
            patch.object(admin, '_legacy_recap_dir', return_value=os.path.join(directory.name, 'legacy')),
            patch.object(admin, 'stats_db_path', return_value=os.path.join(directory.name, 'stats.db')),
            patch.dict(sys.modules, {'ai_auto_send_jobs': jobs}),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)
        admin.init_ai_recap_pages_db()

    def test_deleted_recap_does_not_return_from_completed_job(self):
        admin.insert_ai_recap_page('deleted-recap', 'kyle', 'doubles', '<p>Recap</p>', subject='Original title')
        self.assertEqual(admin.list_ai_recap_pages()[1], 1)
        self.assertTrue(admin.delete_ai_recap_page('deleted-recap'))
        self.assertIsNone(admin.get_ai_recap_page('deleted-recap'))
        self.assertEqual(admin.list_ai_recap_pages(), ([], 0))
        self.assertEqual(admin.list_ai_recap_pages(username='kyle'), ([], 0))

    def test_job_metadata_still_fills_existing_html_only_recap(self):
        admin.write_recap_html_file('deleted-recap', '<p>Legacy recap</p>')
        entries, total = admin.list_ai_recap_pages(username='kyle')
        self.assertEqual(total, 1)
        self.assertEqual(entries[0]['username'], 'kyle')


if __name__ == '__main__':
    unittest.main()
