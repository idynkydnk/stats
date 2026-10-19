import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from scripts.warm_public_pages import fetch


class PublicPageWarmupTests(unittest.TestCase):
    def test_recovers_transient_timeout_and_still_reads_response(self):
        response = MagicMock(status=200, url='https://example.com/stats/')
        context = MagicMock()
        context.__enter__.return_value = response
        with patch('scripts.warm_public_pages.urlopen', side_effect=[TimeoutError(), context]) as open_url, \
                patch('scripts.warm_public_pages.time.sleep'):
            self.assertEqual(fetch('https://example.com/'), response.url)
            self.assertEqual(open_url.call_count, 2)
            response.read.assert_called_once()

    def test_permanent_failures_are_not_hidden(self):
        with patch('scripts.warm_public_pages.urlopen', side_effect=TimeoutError()) as open_url, \
                patch('scripts.warm_public_pages.time.sleep'):
            with self.assertRaises(TimeoutError):
                fetch('https://example.com/')
            self.assertEqual(open_url.call_count, 4)
        error = HTTPError('https://example.com/', 404, 'Missing', {}, None)
        with patch('scripts.warm_public_pages.urlopen', side_effect=error) as open_url:
            with self.assertRaises(HTTPError):
                fetch('https://example.com/')
            self.assertEqual(open_url.call_count, 1)
