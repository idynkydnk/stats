import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from admin_functions import (
    _pick_player_email,
    parse_git_log_output,
    site_update_bullets,
    site_update_detail_from_patch,
    site_update_html_body,
    site_update_plain_body,
)
import admin_functions as adminfx


class SiteUpdateHelperTests(unittest.TestCase):
    def test_parse_git_log_marks_already_shared_commits(self):
        raw = (
            'abc123\x1f2026-09-06\x1fKeep old AI pictures\x1fUsers can replace them.\x1e'
            'def456\x1f2026-09-05\x1fFix login timeout\x1f\x1e'
        )
        changes = parse_git_log_output(raw, shared_shas={'def456'})
        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0]['subject'], 'Keep old AI pictures')
        self.assertEqual(changes[0]['short_sha'], 'abc123')
        self.assertFalse(changes[0]['already_shared'])
        self.assertTrue(changes[1]['already_shared'])

    def test_empty_commit_body_is_filled_from_patch(self):
        raw = (
            'abc123\x1f2026-09-03\x1fDeduplicate flyer player suggestions\x1f'
            '\ndiff --git a/player_identity.py b/player_identity.py\n'
            '@@ -1,0 +1,3 @@\n'
            '+def player_name_identity_key(value):\n'
            '+    """Return a comparison key for names that render as the same person."""\n'
            '+    return name\n'
            '\x1e'
        )
        changes = parse_git_log_output(raw)
        self.assertEqual(
            changes[0]['body'],
            'Return a comparison key for names that render as the same person.',
        )

    def test_written_commit_body_is_kept(self):
        raw = (
            'abc123\x1f2026-09-06\x1fKeep old AI pictures\x1fUsers can replace them.\n'
            'diff --git a/stats.py b/stats.py\n'
            '@@ -1,0 +1,1 @@\n'
            '+"""Some other note."""\n'
            '\x1e'
        )
        changes = parse_git_log_output(raw)
        self.assertEqual(changes[0]['body'], 'Users can replace them.')

    def test_co_authored_by_is_stripped_from_commit_body(self):
        raw = (
            'abc123\x1f2026-08-23\x1fShow every user recap\x1f'
            'Admin was only seeing Kyle\'s own recaps.\n'
            '\n'
            'Co-authored-by: Cursor <cursoragent@cursor.com>\x1e'
        )
        changes = parse_git_log_output(raw)
        self.assertEqual(changes[0]['body'], "Admin was only seeing Kyle's own recaps.")

    def test_html_templates_are_not_used_as_details(self):
        patch = (
            'diff --git a/admin_functions.py b/admin_functions.py\n'
            '@@ -1,0 +1,3 @@\n'
            '+HTML = """<div style="font-family:sans-serif"><h1>What\'s new</h1></div>"""\n'
            '+def send_update():\n'
            '+    """Email selected site users about chosen website changes."""\n'
        )
        detail = site_update_detail_from_patch(patch, 'Let Kyle email site updates')
        self.assertEqual(
            detail,
            'Email selected site users about chosen website changes.',
        )

    def test_detail_prefers_lock_text_over_return_docstrings(self):
        patch = (
            'diff --git a/email_content.py b/email_content.py\n'
            '@@ -1,0 +1,4 @@\n'
            '+def _valid_session_performance_rows(players, player_stats):\n'
            '+    """Return usable illustration stats for selected players."""\n'
            "+    lines = ['PERFORMANCE STAGING LOCK — the statistics control every "
            "player's pose, body language, and facial expression.']\n"
        )
        detail = site_update_detail_from_patch(patch, 'Make recap images reflect player performance')
        self.assertIn('statistics control every player\'s pose', detail)

    def test_bullets_include_custom_notes_then_selected_subjects(self):
        bullets = site_update_bullets(
            [{'subject': 'Save flyers to Photos'}],
            extra_notes='- The iPhone app got this too\n\n',
        )
        self.assertEqual(
            bullets,
            ['The iPhone app got this too', 'Save flyers to Photos'],
        )

    def test_bullets_append_generated_detail(self):
        bullets = site_update_bullets([
            {
                'subject': 'Deduplicate flyer player suggestions',
                'body': 'Flyer search lists each person once.',
            },
        ])
        self.assertEqual(
            bullets,
            ['Deduplicate flyer player suggestions — Flyer search lists each person once.'],
        )

    def test_email_bodies_list_each_change(self):
        bullets = ['Replace AI characters without deleting the old ones']
        plain = site_update_plain_body(bullets)
        html = site_update_html_body(bullets, site_url='https://example.test')
        self.assertIn('• Replace AI characters without deleting the old ones', plain)
        self.assertIn('Replace AI characters without deleting the old ones', html)
        self.assertIn('https://example.test/', html)
        self.assertNotIn('<script>', html)

    def test_pick_player_email_only_matches_unique_names(self):
        by_first = {
            'dan': [
                {'player_name': 'Dan Ferris', 'email': 'danf@example.com'},
                {'player_name': 'Dan Smith', 'email': 'dans@example.com'},
            ],
            'kyle': [{'player_name': 'Kyle Wodzinski', 'email': 'kyle@example.com'}],
        }
        by_nickname = {
            'troy': [{'player_name': 'Troy Allen', 'email': 'troy@example.com'}],
        }
        self.assertEqual(
            _pick_player_email('kyle', by_first, by_nickname)['email'],
            'kyle@example.com',
        )
        self.assertEqual(
            _pick_player_email('troy', by_first, by_nickname)['email'],
            'troy@example.com',
        )
        self.assertIsNone(_pick_player_email('dan', by_first, by_nickname))
        self.assertIsNone(_pick_player_email('iosapp', by_first, by_nickname))


class SiteUserPlayerLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, 'stats.db')
        self.patcher = mock.patch('admin_functions.stats_db_path', return_value=self.db_path)
        self.patcher.start()
        adminfx.init_activity_log_db()
        adminfx.init_users_db()
        self.assertTrue(adminfx.create_site_user('dan', 'hash'))
        self.assertTrue(adminfx.create_site_user('kyle', 'hash'))
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            '''CREATE TABLE players (
                id INTEGER PRIMARY KEY,
                full_name TEXT,
                email TEXT,
                nickname TEXT
            )'''
        )
        conn.executemany(
            'INSERT INTO players (full_name, email, nickname) VALUES (?, ?, ?)',
            [
                ('Dan Ferris', 'danf@example.com', ''),
                ('Dan Smith', 'dans@example.com', ''),
                ('Kyle Wodzinski', 'kyle@example.com', ''),
            ],
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.patcher.stop()
        self.tmpdir.cleanup()

    def test_ambiguous_first_name_is_not_guessed(self):
        by_name = {row['username']: row for row in adminfx.list_site_update_recipients()}
        self.assertEqual(by_name['dan']['suggested_players'][0]['name'], 'Dan Ferris')
        self.assertEqual(len(by_name['dan']['suggested_players']), 2)
        self.assertEqual(by_name['dan']['player_name'], '')
        self.assertFalse(by_name['dan']['can_email'])
        self.assertEqual(by_name['kyle']['player_name'], 'Kyle Wodzinski')
        self.assertTrue(by_name['kyle']['can_email'])

    def test_saved_player_link_wins_over_shared_first_name(self):
        self.assertTrue(adminfx.set_site_user_player('dan', 'Dan Smith'))
        by_name = {row['username']: row for row in adminfx.list_site_update_recipients()}
        self.assertEqual(by_name['dan']['player_name'], 'Dan Smith')
        self.assertEqual(by_name['dan']['email'], 'dans@example.com')
        self.assertTrue(by_name['dan']['can_email'])
        chosen = adminfx.resolve_site_update_recipients(
            ['dan'], {'dan': 'Dan Ferris'},
        )
        self.assertEqual(chosen[0]['email'], 'danf@example.com')
        self.assertEqual(chosen[0]['player_name'], 'Dan Ferris')


if __name__ == '__main__':
    unittest.main()
