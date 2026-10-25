import unittest
from flask import jsonify
from private_accounts import connect_data
from tests import test_private_accounts as fixtures


class AppStatsSharingTests(unittest.TestCase):
    setUp = fixtures.PrivateAccountTests.setUp
    register = fixtures.PrivateAccountTests.register

    def add_stats_route(self):
        def stats(year):
            with connect_data(self.path) as conn:
                return jsonify([row[0] for row in conn.execute('SELECT winner1 FROM games')])
        self.app.add_url_rule('/stats/<year>/', 'stats', stats)

    def test_personal_link_preserves_combined_sources_for_signed_out_recipient(self):
        self.add_stats_route()
        headers = self.register(self.a, 'alice')
        self.a.post('/api/games', headers=headers, json={'name': 'Alice tournament'})
        response = self.a.get('/api/account/stats-share', headers=headers)
        self.assertEqual(response.status_code, 200)
        shared = self.b.get('/stats/All%20years/?view=' + response.json['view'])
        self.assertEqual(set(shared.json), {'Shared player', 'Alice tournament'})
        owned = self.a.get('/api/account/stats-share?owned=1', headers=headers)
        self.assertEqual(self.b.get('/stats/All%20years/?view=' + owned.json['view']).json, ['Alice tournament'])

    def test_public_preview_and_invalid_auth(self):
        self.add_stats_route()
        response = self.a.get('/api/account/stats-share?preview=1', headers={'X-Stats-Preview': '1', 'X-Stats-Account-Required': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.b.get('/stats/All%20years/?view=' + response.json['view']).json, ['Shared player'])
        response = self.a.get('/api/account/stats-share', headers={'Authorization': 'Bearer invalid'})
        self.assertEqual(response.status_code, 401)

    def test_personal_accounts_can_open_the_web_date_picker(self):
        self.app.add_url_rule('/stats-time-frame/', 'stats_time_frame', lambda: 'Choose days')
        headers = self.register(self.a, 'alice')
        response = self.a.get('/stats-time-frame/', headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_unshareable_source_is_not_published(self):
        from unittest.mock import patch
        headers = self.register(self.a, 'alice')
        # A source permission can be revoked after it was selected.
        source = dict(enabled=True, account_id='missing', owner='removed-user')
        with patch('account_stats_views.sources_for_user', return_value=[source]):
            response = self.a.get('/api/account/stats-share', headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('view', response.json)
