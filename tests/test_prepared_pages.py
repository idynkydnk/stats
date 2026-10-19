from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from flask import get_flashed_messages, request, session
from itsdangerous import URLSafeSerializer

from private_accounts import account_for_user, connect_data
from prepared_pages import PreparedPages
from tests import test_private_accounts as fixtures


class PreparedPageTests(unittest.TestCase):
    register = fixtures.PrivateAccountTests.register

    def setUp(self):
        fixtures.PrivateAccountTests.setUp(self)
        self.calls = []
        self.fail = False
        self.change_session = False
        self.change_data = False

        def page(year):
            self.calls.append(year)
            if self.fail:
                return 'error', 503
            messages = get_flashed_messages()
            with connect_data(self.path) as conn:
                rows = conn.execute('SELECT winner1 FROM games ORDER BY id').fetchall()
                if self.change_data:
                    conn.execute("UPDATE games SET winner1='Changed while rendering'")
            if self.change_session:
                session['form_token'] = 'new-token'
            return str((rows, dict(session), list(request.args.items(multi=True)), messages, year))

        self.app.add_url_rule('/stats/<year>/', 'stats', page)

    def url(self, client=None, year='2026', query=''):
        response = (client or self.a).get('/stats/' + year + '/' + query)
        return response.location or '/stats/' + year + '/' + query

    def test_reuses_html_and_changes_immediately_after_game_and_roster_edits(self):
        url = self.url()
        first = self.a.get(url)
        self.assertEqual(first.headers['X-Stats-Page-Cache'], 'miss')
        second = self.a.get(url)
        self.assertEqual(second.data, first.data)
        self.assertEqual(second.headers['X-Stats-Page-Cache'], 'hit')
        self.assertEqual(second.headers['Cache-Control'], 'no-store')
        self.assertEqual(len(self.calls), 1)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE games SET winner1='Edited history'")
        self.assertIn(b'Edited history', self.a.get(url).data)
        self.assertEqual(len(self.calls), 2)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE players SET full_name='New profile'")
        self.a.get(url)
        self.assertEqual(len(self.calls), 3)

    def test_second_worker_reuses_completed_page_without_rendering(self):
        url = self.url()
        self.a.get(url)
        pages = self.app.extensions['stats_page_cache']
        second = PreparedPages(self.app.extensions['stats_response_cache'].directory)
        # The hooks close over the existing object: swap only its worker-local memory.
        pages.memory = second.memory
        self.assertEqual(self.a.get(url).headers['X-Stats-Page-Cache'], 'hit')
        self.assertEqual(len(self.calls), 1)

    def test_accounts_sessions_filters_and_paths_never_share_rendered_contents(self):
        alice = self.register(self.a, 'alice')
        bob = self.register(self.b, 'bob')
        self.a.post('/api/games', headers=alice, json={'name': 'Alice private'})
        self.b.post('/api/games', headers=bob, json={'name': 'Bob private'})
        a_url, b_url = self.url(self.a), self.url(self.b)
        for _ in range(2):
            a, b = self.a.get(a_url), self.b.get(b_url)
            self.assertIn(b'Alice private', a.data)
            self.assertNotIn(b'Bob private', a.data)
            self.assertIn(b'Bob private', b.data)
            self.assertNotIn(b'Alice private', b.data)
        self.assertEqual(len(self.calls), 2)
        with self.a.session_transaction() as state:
            state['timezone'] = 'Pacific/Honolulu'
            state['form_token'] = 'alice-only'
        self.assertIn(b'alice-only', self.a.get(a_url).data)
        self.assertNotIn(b'alice-only', self.b.get(b_url).data)
        for suffix in ['&division=women', '&location=Beach', '&q=a&q=b']:
            self.assertEqual(self.a.get(a_url + suffix).headers['X-Stats-Page-Cache'], 'miss')
        self.assertEqual(self.a.get(a_url.replace('/2026/', '/2025/')).headers['X-Stats-Page-Cache'], 'miss')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE site_users SET active=0 WHERE username='alice'")
        self.assertEqual(self.a.get(a_url).status_code, 401)

    def test_share_revocation_is_checked_even_when_html_is_cached(self):
        headers = self.register(self.a, 'alice')
        self.a.post('/api/games', headers=headers, json={'name': 'Alice shared'})
        self.a.put('/api/account/stats-sharing', headers=headers, json={'share_stats': True})
        account = account_for_user(self.path, 'alice')
        token = URLSafeSerializer(self.app.secret_key, salt='shared-stats-view-v1').dumps(dict(base=None, sources=[account['id']]))
        url = '/stats/2026/?view=' + token
        self.assertIn(b'Alice shared', self.b.get(url).data)
        self.assertEqual(self.b.get(url).headers['X-Stats-Page-Cache'], 'hit')
        self.a.put('/api/account/stats-sharing', headers=headers, json={'share_stats': False})
        self.assertEqual(self.b.get(url).status_code, 404)

    def test_flash_session_changes_errors_and_mid_render_edits_are_not_saved(self):
        url = self.url()
        self.fail = True
        self.assertEqual(self.a.get(url).status_code, 503)
        self.fail = False
        self.change_session = True
        self.a.get(url)
        self.change_session = False
        self.assertEqual(self.a.get(url).headers['X-Stats-Page-Cache'], 'miss')
        self.assertEqual(self.a.get(url).headers['X-Stats-Page-Cache'], 'hit')
        with self.a.session_transaction() as state:
            state['_flashes'] = [('message', 'Only once')]
        self.assertIn(b'Only once', self.a.get(url).data)
        self.assertNotIn(b'Only once', self.a.get(url).data)
        self.change_data = True
        self.a.get(url + '&new=1')
        self.change_data = False
        self.assertIn(b'Changed while rendering', self.a.get(url + '&new=1').data)

    def test_explicit_reload_and_clear_bypass_reuse_and_storage_is_bounded(self):
        url = self.url()
        self.a.get(url)
        self.assertEqual(self.a.get(url, headers={'Cache-Control': 'no-cache'}).headers['X-Stats-Page-Cache'], 'miss')
        pages = self.app.extensions['stats_page_cache']
        pages.clear()
        self.assertEqual(self.a.get(url).headers['X-Stats-Page-Cache'], 'miss')
        with patch('prepared_pages.MAX_MEMORY_BYTES', 100):
            pages.remember('oversized', b'x' * 101)
            self.assertEqual(len(pages.memory), 0)
        self.assertEqual(pages.disk.path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
