"""Tie entry and receipts use an explicit result, with no volleyball tie option."""
from pathlib import Path
import unittest
from flask import Flask, render_template

ROOT = Path(__file__).resolve().parents[1]


class OtherGameOutcomeTemplateTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'))

    def test_saved_tie_is_selected_and_explained(self):
        with self.app.test_request_context('/edit_other_game/1/'):
            html = render_template('partials/other_game_result.html',
                                   game={'game_type': 'Cards', 'is_tie': True})
        self.assertIn('<option value="1" selected>Tie</option>', html)
        self.assertIn('For a 1–1 tie, enter 1 for both scores.', html)
        self.assertIn('<div class="sr-result-field" data-one-on-one="0">', html)

    def test_volleyball_and_one_on_one_hide_and_clear_tie(self):
        for path, game_type in [('/edit_other_game/1/', ' Beach VoLlEyBaLl '),
                                ('/add_other_game/?one_on_one=1', '')]:
            with self.subTest(path=path), self.app.test_request_context(path):
                html = render_template('partials/other_game_result.html',
                                       game={'game_type': game_type, 'is_tie': True})
                self.assertRegex(html, r'<div class="sr-result-field" data-one-on-one="[01]" hidden>')
                self.assertIn('<option value="0" selected>Win / loss</option>', html)
                self.assertNotIn('<option value="1" selected>', html)

    def test_tied_receipt_labels_sides_and_shows_result(self):
        with self.app.test_request_context('/add_other_game/'):
            html = render_template('partials/saved_game_popup.html', saved_game={
                'title': 'Sequence', 'is_tie': True, 'winners': 'Alice',
                'losers': 'Bob', 'winner_score': 1, 'loser_score': 1,
            })
        self.assertIn('data-saved-game="winner_label">Side 1</strong>', html)
        self.assertIn('data-saved-game="loser_label">Side 2</strong>', html)
        self.assertIn('data-saved-game="result" >Tie</p>', html)


if __name__ == '__main__':
    unittest.main()
