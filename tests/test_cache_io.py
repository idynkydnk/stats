from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask, g, session

from prepared_calculations import reuse_calculation, clear_prepared_calculations
from stats_response_cache import StatsResponseCache, database_revisions, local_cache_directory


class CacheIOTests(unittest.TestCase):
    def test_revision_reads_share_one_snapshot_but_publication_rechecks_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'source.db')
            with sqlite3.connect(path) as conn:
                conn.executescript('CREATE TABLE games(id INTEGER); INSERT INTO games VALUES (1);')
            database_revisions([path])  # Install revision tracking before measuring reads.
            app = Flask(__name__)
            connect = sqlite3.connect
            with app.test_request_context('/'), patch('stats_response_cache.sqlite3.connect', wraps=connect) as opened:
                before = database_revisions([path])
                before_games = database_revisions([path], ('games',))
                database_revisions([path], ('players', 'games'))
                self.assertEqual(opened.call_count, 1)
                with connect(path) as conn:
                    conn.execute('INSERT INTO games VALUES (2)')
                self.assertNotEqual(database_revisions([path], fresh=True), before)
                self.assertNotEqual(database_revisions([path], ('games',)), before_games)
                self.assertEqual(opened.call_count, 2)

    def test_local_cache_is_namespaced_and_reinitializes_after_removal(self):
        with tempfile.TemporaryDirectory() as directory, patch('stats_response_cache.tempfile.gettempdir', return_value=directory):
            first = local_cache_directory('/site/a.db', 'private-key')
            self.assertEqual(first, local_cache_directory('/site/a.db', 'private-key'))
            self.assertNotEqual(first, local_cache_directory('/site/b.db', 'private-key'))
            self.assertNotEqual(first, local_cache_directory('/site/a.db', 'other-key'))
            self.assertNotIn('private-key', str(first))
            cache = StatsResponseCache(first)
            cache._connect().close()
            with patch('stats_response_cache.os.chmod', side_effect=AssertionError('Repeated setup')):
                cache._connect().close()
            cache.path.unlink()
            cache._connect().close()
            self.assertEqual(first.stat().st_mode & 0o777, 0o700)
            self.assertEqual(cache.path.stat().st_mode & 0o777, 0o600)

    def test_display_calculations_keep_timezone_separate(self):
        app = Flask(__name__)
        app.secret_key = 'test'
        clear_prepared_calculations()
        self.addCleanup(clear_prepared_calculations)
        def display():
            return session.get('timezone')
        for zone in ('America/Los_Angeles', 'Pacific/Honolulu', 'America/Los_Angeles'):
            with app.test_request_context('/'):
                g.stats_data_revision = 'unchanged'
                session['timezone'] = zone
                self.assertEqual(reuse_calculation(display, (), {}), zone)
