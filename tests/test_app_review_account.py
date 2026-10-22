import sqlite3
import unittest
from werkzeug.security import check_password_hash

from tests.test_private_accounts import PrivateAccountTests
from scripts.create_app_review_account import create_review_account, inspect_target
from private_accounts import account_for_user, provision_database


class AppReviewAccountTests(unittest.TestCase):
    def setUp(self):
        PrivateAccountTests.setUp(self)

    def test_review_account_uses_normal_private_identity_and_only_fictional_data(self):
        result = create_review_account(self.path, 'appreview-test', 'review@example.test', 'a-generated-review-password')
        self.assertEqual(result['username'], 'appreview-test')
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            user = conn.execute("SELECT * FROM site_users WHERE username='appreview-test'").fetchone()
            self.assertFalse(user['is_admin'])
            self.assertEqual(user['login_email'], 'review@example.test')
            self.assertTrue(check_password_hash(user['password_hash'], result['password']))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM games').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM players').fetchone()[0], 1)
        account = account_for_user(self.path, result['username'])
        self.assertFalse(account['share_stats'])
        with sqlite3.connect(provision_database(self.path, account['id'])) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM games').fetchone()[0], 3)
            names = {row[0] for row in conn.execute('SELECT full_name FROM players')}
            self.assertEqual(names, {'Review Alex', 'Review Blair', 'Review Casey', 'Review Drew'})

    def test_dry_run_validation_does_not_create_account_and_never_reuses_identity(self):
        inspect_target(self.path, 'appreview-check', 'review@example.test')
        self.assertIsNone(account_for_user(self.path, 'appreview-check'))
        with self.assertRaises(ValueError):
            inspect_target(self.path, 'Kyle', 'review@example.test')
        create_review_account(self.path, 'appreview-check', 'review@example.test', 'a-generated-review-password')
        with self.assertRaises(ValueError):
            create_review_account(self.path, 'appreview-another', 'review@example.test', 'another-generated-password')


if __name__ == '__main__':
    unittest.main()
