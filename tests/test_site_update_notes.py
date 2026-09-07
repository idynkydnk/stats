import unittest
from unittest.mock import patch
from site_update_notes import parse_site_update_note
from scripts.check_site_updates import check
from admin_functions import parse_git_log_output


class SiteUpdateNoteTests(unittest.TestCase):
    def test_readable_paragraph_does_not_include_technical_details(self):
        body = ('Internal implementation details.\n\nSite-Update: Save your flyer\n'
                'Save a picture to your phone\nso you can share it.\n\n'
                'More technical details.\nCo-authored-by: Someone')
        self.assertEqual(parse_site_update_note(body), {
            'subject': 'Save your flyer',
            'body': 'Save a picture to your phone so you can share it.',
        })

    def test_title_only_does_not_consume_the_next_paragraph(self):
        self.assertEqual(parse_site_update_note('Site-Update: Easier search\n\nInternal details'),
                         {'subject': 'Easier search', 'body': ''})

    def test_missing_and_skipped_notes_stay_out_of_the_page(self):
        raw = ('a\x1f2026-09-07\x1fAuto-update\x1f\x1e'
               'b\x1f2026-09-07\x1fMaintenance\x1fSite-Update: none\x1e'
               'c\x1f2026-09-07\x1fInternal title\x1fSite-Update: Easier search\x1e')
        changes = parse_git_log_output(raw, {'c'})
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['subject'], 'Easier search')
        self.assertTrue(changes[0]['already_shared'])

    def test_push_check_rejects_missing_note_and_accepts_explicit_decisions(self):
        for body, result in [('Technical details', 1), ('Site-Update: none', 0),
                             ('Site-Update: Easier search\nFind players faster.', 0),
                             ('Site-Update: ', 1)]:
            with self.subTest(body=body), patch('scripts.check_site_updates.subprocess.check_output',
                                               side_effect=['newcommit\n', body]):
                self.assertEqual(check('before', 'after'), result)


if __name__ == '__main__':
    unittest.main()
