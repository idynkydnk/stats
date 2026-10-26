import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from flask import Flask, url_for
from stats_date_filter import register_stats_date_filter
from stats_location_filter import filter_stats_connection
from test_stats_location_filter import StatsLocationFilterTests


class DateRangeQueries(StatsLocationFilterTests):
    def test_whole_days_across_years_and_all_tables(self):
        with sqlite3.connect(self.path) as conn:
            for table in ('games', 'vollis_games', 'other_games'):
                for game_id, day in enumerate(('2025-12-30 23:59:59', '2025-12-31 00:00:00',
                                              '2026-01-02 23:59:59.999', '2026-01-03 00:00:00'), 1):
                    conn.execute(f'UPDATE {table} SET game_date=? WHERE id=?', (day, game_id))
        with self.app.test_request_context('/stats/All years/?start_date=2025-12-31&end_date=2026-01-02'):
            for table in ('games', 'vollis_games', 'other_games'):
                with sqlite3.connect(self.path) as conn:
                    filter_stats_connection(conn, table)
                    self.assertEqual([row[0] for row in conn.execute(f'SELECT id FROM {table}')], [2, 3])

    def test_cache_isolation_location_and_rating_cache(self):
        import stat_functions as doubles
        for start, end, expected in [('2011-01-01', '2011-01-01', 1),
                                     ('2011-01-02', '2011-01-03', 0),
                                     ('2011-01-01', '2011-01-01', 1)]:
            with self.app.test_request_context(f'/stats/All years/?start_date={start}&end_date={end}'):
                self.assertEqual(doubles.year_games_count('All years'), expected)
                with patch('database_functions.get_trueskill_from_db') as read, patch('database_functions.save_trueskill_to_db') as save:
                    doubles.calculate_trueskill_rankings('All years')
                    read.assert_not_called()
                    save.assert_not_called()
        with self.app.test_request_context('/stats/All years/?start_date=2011-01-01&end_date=2011-02-01&location=California'):
            self.assertEqual(doubles.year_games_count('All years'), 1)
        with self.app.test_request_context('/edit/?start_date=2011-01-01&end_date=2011-01-01'):
            self.assertEqual(doubles.year_games_count('All years'), 4)


class DateRangeNavigation(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
        register_stats_date_filter(self.app)
        self.app.add_url_rule('/stats/<year>/', 'stats', lambda year: url_for('games', year='2026'))
        self.app.add_url_rule('/games/<year>/', 'games', lambda year: 'games')
        self.client = self.app.test_client()

    def test_selection_preserves_filters_and_crosses_years(self):
        result = self.client.get('/stats-time-frame/', query_string={
            'apply': '1', 'start_date': '2025-12-31', 'end_date': '2026-01-02',
            'next': '/games/2026/?location=Beach&division=women&view=share&page=3'})
        self.assertEqual(result.status_code, 302)
        parts = urlsplit(result.location)
        self.assertIn('All%20years', parts.path)
        self.assertEqual(parse_qs(parts.query), {'start_date': ['2025-12-31'], 'end_date': ['2026-01-02'],
                                              'location': ['Beach'], 'division': ['women'], 'view': ['share']})

    def test_navigation_clear_and_canonical_year(self):
        query = '?start_date=2025-12-31&end_date=2026-01-02'
        result = self.client.get('/stats/2026/' + query)
        self.assertEqual(result.status_code, 302)
        self.assertIn('All%20years', result.location)
        result = self.client.get(result.location)
        self.assertIn('start_date=2025-12-31', result.text)
        with self.app.test_request_context('/stats/All years/' + query):
            context = {}
            self.app.update_template_context(context)
            self.assertNotIn('start_date', context['stats_date_range_clear_url'])
            self.assertEqual(context['stats_date_range'], ('2025-12-31', '2026-01-02'))

    def test_clear_all_filters_keeps_the_current_stats_view(self):
        for location in ({'location': 'Beach'}, {'missing': '1'}):
            with self.subTest(location=location), self.app.test_request_context(
                '/games/All years/', query_string=dict(
                    start_date='2025-12-31', end_date='2026-01-02',
                    division='women', view='shared-stats', page='3', **location),
            ):
                context = {}
                self.app.update_template_context(context)
                dates_only = urlsplit(context['stats_date_range_clear_url'])
                self.assertEqual(parse_qs(dates_only.query), dict(
                    division=['women'], view=['shared-stats'],
                    **{key: [value] for key, value in location.items()}))
                all_filters = urlsplit(context['stats_filters_clear_url'])
                self.assertEqual(all_filters.path, '/games/All%20years/')
                self.assertEqual(parse_qs(all_filters.query), {
                    'division': ['women'], 'view': ['shared-stats'],
                })

    def test_invalid_ranges_and_safe_destination(self):
        for query in ('start_date=2026-02-30&end_date=2026-03-01',
                      'start_date=2026-03-02&end_date=2026-03-01', 'start_date=2026-03-01'):
            self.assertEqual(self.client.get('/stats/All years/?' + query).status_code, 400)
        result = self.client.get('/stats-time-frame/?apply=1&start_date=2026-01-01&end_date=2026-01-01&next=https://example.com/')
        self.assertTrue(result.location.startswith('/stats/'))
        with patch('stats_date_filter.render_template', return_value='Choose both days'):
            self.assertEqual(self.client.get('/stats-time-frame/?apply=1').status_code, 400)


class SharedDateRangeTests(unittest.TestCase):
    def setUp(self):
        from tests.test_private_accounts import PrivateAccountTests
        PrivateAccountTests.setUp(self)
        register_stats_date_filter(self.app)
        with sqlite3.connect(self.path) as conn:
            conn.execute('ALTER TABLE games ADD COLUMN game_date TEXT')
            conn.execute("UPDATE games SET game_date='2025-12-31 00:00:00'")
            conn.execute("INSERT INTO games VALUES (2, 'Last day', '2026-01-02 23:59:59')")
            conn.execute("INSERT INTO games VALUES (3, 'Outside range', '2026-01-03 00:00:00')")

        def stats(year):
            from private_accounts import connect_data
            with connect_data(self.path) as conn:
                filter_stats_connection(conn, 'games')
                return str([row[1] for row in conn.execute('SELECT * FROM games ORDER BY id')])
        self.app.add_url_rule('/stats/<year>/', 'stats', stats)

    def test_shared_link_opens_same_days_in_another_browser(self):
        first = self.a.get('/stats/All%20years/?start_date=2025-12-31&end_date=2026-01-02')
        self.assertEqual(first.status_code, 302)
        link = first.location
        self.assertIn('view=', link)
        own = self.a.get(link)
        shared = self.b.get(link)
        self.assertEqual(own.data, shared.data)
        self.assertIn(b'Shared player', shared.data)
        self.assertIn(b'Last day', shared.data)
        self.assertNotIn(b'Outside range', shared.data)
        unfiltered = self.b.get('/stats/All%20years/', follow_redirects=True)
        self.assertIn(b'Outside range', unfiltered.data)


class APIDateRangeTests(DateRangeQueries):
    def test_api_filters_and_pagination_totals(self):
        from game_browse_page import game_page
        endpoints = ['api_doubles_stats', 'api_doubles_player', 'api_doubles_list',
                     'api_vollis_stats', 'api_vollis_player', 'api_vollis_list',
                     'api_other_stats', 'api_other_player', 'api_other_list', 'api_volleyball_stats']
        for endpoint in endpoints:
            self.app.add_url_rule('/' + endpoint, endpoint, lambda: '')
            with self.app.test_request_context('/' + endpoint + '?year=All+years&start_date=2011-01-01&end_date=2011-02-01&location=California&limit=1'):
                for table in ('games', 'vollis_games', 'other_games'):
                    with sqlite3.connect(self.path) as conn:
                        filter_stats_connection(conn, table)
                        rows, page = game_page(conn, table)
                        self.assertEqual([row[0] for row in rows], [2])
                        self.assertEqual(page, {'total': 1, 'next_offset': None})

    def test_api_range_overrides_year_and_rejects_invalid_days(self):
        register_stats_date_filter(self.app)
        self.app.add_url_rule('/api/doubles/stats', 'api_doubles_stats', lambda: 'OK')
        result = self.app.test_client().get('/api/doubles/stats?year=2026&start_date=2025-12-31&end_date=2026-01-02')
        self.assertEqual(result.status_code, 302)
        self.assertEqual(parse_qs(urlsplit(result.location).query)['year'], ['All years'])
        self.assertEqual(self.app.test_client().get('/api/doubles/stats?start_date=2026-02-30&end_date=2026-03-01').status_code, 400)
