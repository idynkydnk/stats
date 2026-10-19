import json
from pathlib import Path
import unittest

from flask import Flask, render_template
from bs4 import BeautifulSoup


class DeferredMatchupTests(unittest.TestCase):
    def test_complete_values_safe_names_and_identical_rounding(self):
        app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
        names = ['</script><img src=x onerror=alert(1)>', 'José & Friends', 'Player / ? #']
        records = [dict(partner=name, win_percentage=0.125, wins=1, losses=7,
                        total_games=8, meets_min=False, sample_tier=1) for name in names]
        with app.test_request_context('/'):
            html = render_template('partials/deferred_matchups.html', deferred_id='test-rows',
                                   deferred_name_key='partner', deferred_matchups=records)
        document = BeautifulSoup(html, 'html.parser')
        self.assertEqual(len(document.find_all('script')), 1)
        self.assertFalse(document.find_all('img'))
        self.assertEqual(json.loads(document.script.string),
                         [[name, 0.125, 1, 7, 8, 0, 1, '12'] for name in names])


if __name__ == '__main__':
    unittest.main()
