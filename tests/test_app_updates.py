import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import admin_functions as adminfx


class AppUpdateTests(unittest.TestCase):
    def test_app_notes_have_unique_stable_ids_and_real_dates(self):
        from datetime import date
        notes = json.loads((Path(adminfx.__file__).parent / 'data/app_updates.json').read_text())
        self.assertEqual(len({note['id'] for note in notes}), len(notes))
        for note in notes:
            date.fromisoformat(note['date'])
            self.assertTrue(note['id'].startswith('ios-'))
            self.assertTrue(note['subject'].startswith('iPhone:'))
            self.assertTrue(note['body'].strip())

    def test_combined_list_shares_app_ids_and_email_copy(self):
        shared = 'ios-2026-09-07-save-confirmation'
        raw = ('web\x1f2026-09-06\x1fTechnical title\x1f'
               'Site-Update: A website fix\nEasier browsing.\x1e')
        with patch.object(adminfx, 'shared_update_shas', return_value={shared}), \
             patch.object(adminfx.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, raw, '')):
            changes, error = adminfx.list_recent_site_changes()
        self.assertIsNone(error)
        self.assertEqual(changes[0]['sha'], shared)
        self.assertTrue(changes[0]['already_shared'])
        self.assertEqual(changes[-1]['sha'], 'web')
        selected = [item for item in changes if item['sha'] == shared]
        email = adminfx.site_update_plain_body(adminfx.site_update_bullets(selected))
        self.assertIn('iPhone: move on to the next game after saving', email)
        self.assertIn('Prepared for the next app update', email)

    def test_app_notes_survive_unavailable_website_history(self):
        with patch.object(adminfx, 'shared_update_shas', return_value=set()), \
             patch.object(adminfx.subprocess, 'run', side_effect=OSError('unavailable')):
            changes, error = adminfx.list_recent_site_changes(limit=2)
        self.assertEqual(len(changes), 2)
        self.assertTrue(all(item['sha'].startswith('ios-') for item in changes))
        self.assertEqual(error, 'unavailable')
