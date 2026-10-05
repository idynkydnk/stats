import json
import unittest
from unittest.mock import Mock, patch

from wsgi_application import load_application, unavailable_application


class StartupErrorTests(unittest.TestCase):
    def test_successful_start_returns_flask(self):
        app = Mock()
        with patch('wsgi_application.importlib.import_module', return_value=Mock(app=app)):
            self.assertIs(load_application(), app)

    def test_failed_start_returns_fallback_without_exposing_exception(self):
        with patch('wsgi_application.importlib.import_module', side_effect=RuntimeError('private details')):
            with self.assertLogs(level='ERROR'):
                self.assertIs(load_application(), unavailable_application)
        start = Mock()
        body = b''.join(unavailable_application(dict(PATH_INFO='/', REQUEST_METHOD='GET'), start))
        self.assertEqual(start.call_args.args[0], '503 Service Unavailable')
        self.assertIn(b'Try again', body)
        self.assertNotIn(b'private details', body)

    def test_api_and_head_responses(self):
        start = Mock()
        body = b''.join(unavailable_application(dict(PATH_INFO='/api/doubles', REQUEST_METHOD='GET'), start))
        self.assertEqual(json.loads(body)['code'], 503)
        self.assertIn(('Retry-After', '60'), start.call_args.args[1])
        self.assertEqual(unavailable_application(dict(PATH_INFO='/', REQUEST_METHOD='HEAD'), start), [])
