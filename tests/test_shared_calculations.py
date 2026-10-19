import pickle
import tempfile
import time
import unittest
from unittest.mock import patch

from flask import Flask, g

from prepared_calculations import reuse_calculation, clear_prepared_calculations
from shared_calculations import SharedCalculations


class SharedCalculationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = Flask(__name__)
        self.app.extensions['stats_calculation_cache'] = SharedCalculations(self.directory.name, 'secret', 'deployment')
        clear_prepared_calculations()
        self.addCleanup(clear_prepared_calculations)

    def test_other_worker_reuses_copy_but_different_revision_recomputes(self):
        calls = []
        def calculate():
            calls.append(1)
            return ['data']
        def read(revision):
            with self.app.test_request_context('/'):
                g.stats_data_revision = revision
                return reuse_calculation(calculate, (), {})
        read('source-one').append('not shared')
        clear_prepared_calculations()
        self.app.extensions['stats_calculation_cache'] = SharedCalculations(self.directory.name, 'secret', 'deployment')
        self.assertEqual(read('source-one'), ['data'])
        self.assertEqual(len(calls), 1)
        read('source-two')
        self.assertEqual(len(calls), 2)

    def test_corrupted_substituted_or_other_deployment_bytes_are_not_deserialized(self):
        cache = self.app.extensions['stats_calculation_cache']
        cache.save('first', pickle.dumps(['valid']))
        self.assertEqual(pickle.loads(cache.load('first')[0]), ['valid'])
        with patch.object(cache.disk, 'load', return_value=b'x' * 32 + b'untrusted'):
            self.assertIsNone(cache.load('first'))
        packed = cache.disk.load(cache.ticket('first'))
        cache.disk.save(cache.ticket('second'), packed)
        self.assertIsNone(cache.load('second'))
        self.assertIsNone(SharedCalculations(self.directory.name, 'different-secret', 'deployment').load('first'))
        self.assertIsNone(SharedCalculations(self.directory.name, 'secret', 'new-deployment').load('first'))

    def test_shared_expiry_respects_calculation_ttl(self):
        cache = self.app.extensions['stats_calculation_cache']
        cache.save('short', pickle.dumps(['valid']), ttl=2)
        with patch('shared_calculations.time.time', return_value=time.time() + 3):
            self.assertIsNone(cache.load('short'))
