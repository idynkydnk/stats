import errno
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from stats_snapshot_cache import prepared_snapshot


class SnapshotFilesystemTests(unittest.TestCase):
    def test_cross_mount_publication_reuses_one_build_and_stays_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.db'
            with sqlite3.connect(source) as conn:
                conn.execute('CREATE TABLE games(id INTEGER PRIMARY KEY, value TEXT)')
                conn.execute("INSERT INTO games VALUES(1, 'before')")
            calls = []
            def build():
                fd, result = tempfile.mkstemp(suffix='.db')
                os.close(fd)
                with sqlite3.connect(source) as src, sqlite3.connect(result) as dest:
                    src.backup(dest)
                calls.append(result)
                return result
            replace = os.replace
            def cross_mount(src, dest):
                if Path(src).parent != Path(dest).parent:
                    raise OSError(errno.EXDEV, 'Cross-device link')
                return replace(src, dest)
            with patch('stats_snapshot_cache.os.replace', side_effect=cross_mount):
                for _ in range(2):
                    result = prepared_snapshot(root / 'cache', [(str(source), 0)], build)
                    with sqlite3.connect(result) as conn:
                        self.assertEqual(conn.execute('SELECT value FROM games').fetchone()[0], 'before')
                    os.unlink(result)
                self.assertEqual(len(calls), 1)
                with sqlite3.connect(source) as conn:
                    conn.execute("UPDATE games SET value='after'")
                result = prepared_snapshot(root / 'cache', [(str(source), 0)], build)
                with sqlite3.connect(result) as conn:
                    self.assertEqual(conn.execute('SELECT value FROM games').fetchone()[0], 'after')
                os.unlink(result)
                self.assertEqual(len(calls), 2)
            self.assertFalse(list((root / 'cache/snapshots').glob('*.building')))
            self.assertTrue(all(not Path(path).exists() for path in calls))

    def test_failed_publication_returns_built_snapshot_without_repeating_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.db'
            with sqlite3.connect(source) as conn:
                conn.execute('CREATE TABLE games(id INTEGER)')
            built = root / 'built.db'
            built.write_bytes(b'already built')
            with patch('stats_snapshot_cache.os.replace', side_effect=PermissionError), patch('stats_snapshot_cache.source_revision', return_value='unchanged'):
                result = prepared_snapshot(root / 'cache', [(str(source), 0)], lambda: str(built))
            self.assertEqual(result, str(built))
            self.assertEqual(built.read_bytes(), b'already built')
            self.assertFalse(list((root / 'cache/snapshots').glob('*.building')))
