import unittest

from admin_functions import (
    _pick_player_email,
    parse_git_log_output,
    site_update_bullets,
    site_update_html_body,
    site_update_plain_body,
)


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

    def test_bullets_include_custom_notes_then_selected_subjects(self):
        bullets = site_update_bullets(
            [{'subject': 'Save flyers to Photos'}],
            extra_notes='- The iPhone app got this too\n\n',
        )
        self.assertEqual(
            bullets,
            ['The iPhone app got this too', 'Save flyers to Photos'],
        )

    def test_email_bodies_list_each_change(self):
        bullets = ['Replace AI characters without deleting the old ones']
        plain = site_update_plain_body(bullets)
        html = site_update_html_body(bullets, site_url='https://example.test')
        self.assertIn('• Replace AI characters without deleting the old ones', plain)
        self.assertIn('Replace AI characters without deleting the old ones', html)
        self.assertIn('https://example.test/', html)
        self.assertNotIn('<script>', html)

    def test_pick_player_email_prefers_unique_nickname_then_first_name(self):
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
        self.assertEqual(
            _pick_player_email('dan', by_first, by_nickname)['player_name'],
            'Dan Ferris',
        )
        self.assertIsNone(_pick_player_email('iosapp', by_first, by_nickname))


if __name__ == '__main__':
    unittest.main()
