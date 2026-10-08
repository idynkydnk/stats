"""Destructive retention checks use only disposable storage and a test database."""
import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import admin_functions as admin
import ai_library as library
import flyer_functions as flyers
import recap_email_queue as queue


class LibraryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in ('recaps', 'flyers', 'images', 'legacy'):
            (self.root / name).mkdir()
        self.db = str(self.root / 'stats.db')
        for replacement in (
            patch.object(admin, '_recap_storage_dir', return_value=str(self.root / 'recaps')),
            patch.object(admin, '_legacy_recap_dir', return_value=str(self.root / 'legacy')),
            patch.object(admin, 'email_images_dir', return_value=str(self.root / 'images')),
            patch.object(admin, 'stats_db_path', return_value=self.db),
            patch.object(flyers, '_flyer_storage_dir', return_value=str(self.root / 'flyers')),
            patch.dict(sys.modules, {'ai_auto_send_jobs': SimpleNamespace(list_jobs_with_share_ids=lambda **kw: [])}),
            patch.dict('os.environ', {'AI_RECAP_LIMIT': '2', 'AI_FLYER_LIMIT': '2'}),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)
        admin.init_ai_recap_pages_db()

    def recap(self, sid, owner='alice', image='', **extra):
        admin.insert_ai_recap_page(sid, owner, 'doubles', '<p>Story</p>', hero_image_url=image)
        admin.update_ai_recap_page(sid, created_at='2020-01-' + sid[-2:] + ' 12:00:00', **extra)

    def flyer(self, sid, owner='alice', event='2020-01-01', image='/static/email_images/flyer.jpg', **extra):
        flyers.insert_flyer_page(sid, owner, ['Player'], 'doubles', event, '12:00', 'Beach', flyer_image_url=image)
        flyers.update_flyer_page(sid, created_at='2020-01-' + sid[-2:] + ' 12:00:00', **extra)

    def test_recap_limit_is_per_owner_and_oldest_first(self):
        self.recap('r01', owner='ALICE')
        self.recap('r02')
        self.recap('r03')
        self.recap('b01', owner='bob')
        self.assertEqual(library.enforce('recap', 'r03'), ['r01'])
        self.assertIsNotNone(admin.get_ai_recap_page('b01'))
        self.assertEqual(admin.list_ai_recap_pages(username='alice')[1], 2)

    def test_favorites_protected_and_pin_persists_in_lists(self):
        for sid in ('r01', 'r02', 'r03'):
            self.recap(sid)
        library.set_pin('recap', 'r01', True, lambda owner: owner == 'alice')
        self.assertTrue(next(e for e in admin.list_ai_recap_pages()[0] if e['share_id'] == 'r01')['pinned'])
        self.assertEqual(library.enforce('recap', 'r03'), ['r02'])
        library.set_pin('recap', 'r01', False, lambda _: True)
        self.recap('r04')
        self.assertEqual(library.enforce('recap', 'r04'), ['r01'])

    def test_pin_does_not_postpone_subscriber_email(self):
        self.recap('r01')
        queue.schedule('r01', 'alice', 'doubles', [1])
        with sqlite3.connect(self.db) as conn:
            due = conn.execute('SELECT due_at FROM recap_email_queue').fetchone()[0]
        library.set_pin('recap', 'r01', True, lambda _: True)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT due_at FROM recap_email_queue').fetchone()[0], due)

    def test_unauthorized_and_missing_favorites_do_not_write(self):
        self.flyer('f01')
        with self.assertRaises(PermissionError):
            library.set_pin('flyer', 'f01', True, lambda _: False)
        self.assertFalse(flyers.get_flyer_page('f01').get('pinned'))
        with self.assertRaises(KeyError):
            library.set_pin('flyer', 'missing', True, lambda _: True)
        self.assertIsNone(flyers.get_flyer_page('missing'))

    def test_upcoming_and_pinned_flyers_can_exceed_target(self):
        self.flyer('f01', event='2999-01-01')
        self.flyer('f02', pinned=True)
        self.flyer('f03', event='2999-01-02')
        self.assertEqual(library.enforce('flyer', 'f03'), [])
        self.assertEqual(flyers.list_flyer_pages()[1], 3)
        self.flyer('f04')
        self.flyer('f05')
        self.assertEqual(library.enforce('flyer', 'f05'), ['f04'])
        self.assertIsNotNone(flyers.get_flyer_page('f05'))

    def test_flyer_dates_fail_safe_and_include_today(self):
        today = date(2026, 10, 8)
        for value in ('2026-10-08', '2026-10-09', 'October 8'):
            self.assertTrue(library.upcoming({'event_date': value}, today))
        self.assertFalse(library.upcoming({'event_date': '2026-10-07'}, today))

    def test_failed_and_missing_publishes_never_evict(self):
        for sid in ('r01', 'r02', 'r03'):
            self.recap(sid)
        admin.update_ai_recap_page('r03', hero_image_error='Failed')
        self.assertEqual(library.enforce('recap', 'r03'), [])
        self.assertEqual(library.enforce('recap', 'missing'), [])
        for sid in ('f01', 'f02', 'f03'):
            self.flyer(sid)
        flyers.update_flyer_page('f03', flyer_image_url='', flyer_image_error='Failed')
        self.assertEqual(library.enforce('flyer', 'f03'), [])
        self.assertEqual(flyers.list_flyer_pages()[1], 3)

    def test_deleted_flyer_does_not_reappear_from_jobs(self):
        self.flyer('f01')
        jobs = SimpleNamespace(list_jobs_with_share_ids=lambda **kw: [{'share_id': 'f01', 'username': 'alice'}])
        with patch.dict(sys.modules, {'ai_auto_send_jobs': jobs}):
            self.assertTrue(flyers.delete_flyer_page('f01'))
            self.assertEqual(flyers.list_flyer_pages(), ([], 0))

    def test_cleanup_preserves_shared_images_until_last_page_is_deleted(self):
        for name in ('shared.jpg', 'og_shared.jpg', 'unrelated.jpg'):
            (self.root / 'images' / name).write_bytes(b'picture')
        url = '/static/email_images/shared.jpg'
        self.recap('r01', image=url)
        self.flyer('f01', image=url, owner='bob')
        slides = self.root / 'recaps' / 'r01'
        slides.mkdir()
        (slides / 'slide.jpg').write_bytes(b'slide')
        self.assertTrue(admin.delete_ai_recap_page('r01'))
        self.assertFalse(slides.exists())
        self.assertTrue((self.root / 'images' / 'shared.jpg').exists())
        self.assertTrue(flyers.delete_flyer_page('f01'))
        self.assertFalse((self.root / 'images' / 'shared.jpg').exists())
        self.assertFalse((self.root / 'images' / 'og_shared.jpg').exists())
        self.assertTrue((self.root / 'images' / 'unrelated.jpg').exists())

    def test_legacy_database_images_are_protected(self):
        image = '/static/email_images/shared.jpg'
        (self.root / 'images' / 'shared.jpg').write_bytes(b'picture')
        with sqlite3.connect(self.db) as conn:
            conn.execute('INSERT INTO ai_recap_pages (share_id, username, game_type, html_body, hero_image_url) VALUES (?, ?, ?, ?, ?)', ('legacy', 'bob', 'doubles', '<p>old</p>', image))
        self.flyer('f01', image=image)
        flyers.delete_flyer_page('f01')
        self.assertTrue((self.root / 'images' / 'shared.jpg').exists())

    def test_unreadable_reference_aborts_image_cleanup(self):
        self.flyer('f01', image='/static/email_images/shared.jpg')
        (self.root / 'images' / 'shared.jpg').write_bytes(b'picture')
        with patch.object(library, 'live_image_filenames', side_effect=OSError('unreadable')):
            with self.assertLogs('ai_library', level='ERROR'):
                flyers.delete_flyer_page('f01')
        self.assertTrue((self.root / 'images' / 'shared.jpg').exists())

    def test_pending_mail_cancelled_and_sending_recap_protected(self):
        self.recap('r01')
        self.recap('r02')
        queue.schedule('r01', 'alice', 'doubles', [1])
        queue.schedule('r02', 'alice', 'doubles', [2])
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE recap_email_queue SET status='sending' WHERE share_id='r02'")
        self.assertTrue(admin.delete_ai_recap_page('r01'))
        self.assertFalse(admin.delete_ai_recap_page('r02'))
        self.assertIsNotNone(admin.get_ai_recap_page('r02'))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT status FROM recap_email_queue WHERE share_id='r01'").fetchone()[0], 'cancelled')

    def test_simultaneous_cleanup_is_idempotent(self):
        for i in range(1, 10):
            self.recap(f'r{i:02}')
        with ThreadPoolExecutor(max_workers=3) as workers:
            results = list(workers.map(lambda _: library.enforce('recap', 'r09'), range(3)))
        self.assertEqual(sum(map(len, results)), 7)
        self.assertEqual(admin.list_ai_recap_pages()[1], 2)
        self.assertIsNotNone(admin.get_ai_recap_page('r09'))

    def test_late_remake_cannot_resurrect_deleted_item(self):
        self.recap('r01')
        self.flyer('f01')
        admin.delete_ai_recap_page('r01')
        flyers.delete_flyer_page('f01')
        with self.assertRaises(ValueError):
            admin.update_ai_recap_page('r01', html_body='<p>Late remake</p>')
        with self.assertRaises(ValueError):
            flyers.update_flyer_page('f01', flyer_image_url='/new.jpg')
        self.assertIsNone(admin.get_ai_recap_page('r01'))
        self.assertIsNone(flyers.get_flyer_page('f01'))

    def test_pin_migrates_legacy_body_without_losing_content(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute('INSERT INTO ai_recap_pages (share_id, username, game_type, html_body) VALUES (?, ?, ?, ?)', ('legacy', 'alice', 'doubles', '<p>Keep this story</p>'))
        library.set_pin('recap', 'legacy', True, lambda owner: owner == 'alice')
        row = admin.get_ai_recap_page('legacy')
        self.assertTrue(row['pinned'])
        self.assertEqual(row['username'], 'alice')
        self.assertEqual(row['html_body'], '<p>Keep this story</p>')

    def publisher(self, name):
        root = Path(__file__).resolve().parents[1]
        node = next(n for n in ast.parse((root / 'stats.py').read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == name)
        ns = dict(adminfx=admin, secrets=SimpleNamespace(token_urlsafe=lambda _: 'new-id'),
                  json=json, recap_email_queue=queue, _refresh_instagram_slides=lambda *a, **kw: None)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'stats.py', 'exec'), ns)
        return ns[name]

    def test_real_recap_publication_enforces_after_saving_new_page(self):
        self.recap('r01')
        self.recap('r02')
        sid = self.publisher('_publish_ai_recap')({'html_body': '<p>New story</p>'}, 'default', '', [1], username='alice')
        self.assertEqual(sid, 'new-id')
        self.assertIsNotNone(admin.get_ai_recap_page(sid))
        self.assertIsNone(admin.get_ai_recap_page('r01'))
        self.assertIsNotNone(admin.get_ai_recap_page('r02'))

    def test_real_flyer_publication_skips_failures_then_enforces_on_success(self):
        self.flyer('f01')
        self.flyer('f02')
        publish = self.publisher('_publish_flyer_page')
        publish('alice', {'event_date': '2020-01-01'}, flyer_error='Failed')
        self.assertIsNotNone(flyers.get_flyer_page('f01'))
        flyers.delete_flyer_page('new-id')
        publish('alice', {'event_date': '2020-01-01'}, flyer_url='/picture.jpg')
        self.assertIsNone(flyers.get_flyer_page('f01'))
        self.assertIsNotNone(flyers.get_flyer_page('f02'))
        self.assertIsNotNone(flyers.get_flyer_page('new-id'))

    def test_defaults_and_invalid_limits(self):
        with patch.dict('os.environ', {'AI_RECAP_LIMIT': 'bad', 'AI_FLYER_LIMIT': 'bad'}):
            self.assertEqual(library.limits(), {'recap': 100, 'flyer': 50})


if __name__ == '__main__':
    unittest.main()
