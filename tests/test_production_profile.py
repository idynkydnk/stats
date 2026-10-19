import os
import time
import unittest
from unittest.mock import patch

from flask import Flask
from performance_metrics import register_performance
from production_profile import signature


class ProductionProfileTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, DEPLOY_TOKEN='diagnostic-test-key')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        register_performance(self.app, lambda: False)
        self.app.add_url_rule('/stats', 'stats', lambda: 'private contents stay out of report', methods=['GET', 'POST'])
        self.app.add_url_rule('/other', 'other', lambda: 'ordinary')
        self.client = self.app.test_client()

    def headers(self, target='/stats', age=0):
        timestamp = str(int(time.time()) - age)
        return {'X-Stats-Profile': timestamp + ':' + signature('diagnostic-test-key', timestamp, target)}

    def test_only_fresh_signed_public_get_is_profiled(self):
        response = self.client.get('/stats', headers=self.headers())
        self.assertEqual(response.json['status'], 200)
        self.assertTrue(response.json['cumulative'])
        self.assertNotIn('private contents', response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertFalse(self.client.get('/stats').is_json)
        self.assertFalse(self.client.get('/stats', headers=self.headers(age=120)).is_json)
        self.assertFalse(self.client.get('/stats?secret=value', headers=self.headers()).is_json)
        self.assertFalse(self.client.get('/stats', headers={'X-Stats-Profile': 'broken'}).is_json)
        self.assertFalse(self.client.post('/stats', headers=self.headers()).is_json)
        self.assertFalse(self.client.get('/other', headers=self.headers('/other')).is_json)
        self.assertFalse(self.client.get('/stats', headers={**self.headers(), 'Authorization': 'Bearer example'}).is_json)
        with self.client.session_transaction() as state:
            state['example'] = True
        self.assertFalse(self.client.get('/stats', headers=self.headers()).is_json)

    def test_signed_filter_does_not_expose_query(self):
        target = '/stats?view=private-link'
        response = self.client.get(target, headers=self.headers(target))
        self.assertTrue(response.is_json)
        self.assertNotIn('private-link', response.text)
        self.assertFalse(self.client.get('/stats').is_json)


if __name__ == '__main__':
    unittest.main()
