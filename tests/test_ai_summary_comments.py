import ast
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock, patch

from flask import Flask, jsonify, request, session

from email_content import (
    RECAP_LENGTH_GUIDANCE,
    _build_recap_style_instructions,
    build_doubles_email_payload,
    build_other_email_payload,
)


ROOT = Path(__file__).resolve().parents[1]
LEGACY_LIMIT = (
    'Keep it to 2 short paragraphs. Each paragraph: 2-3 sentences only. '
    'No long blocks of text.'
)
LONG_SUMMARY = '\n\n'.join(f'Paragraph {i}: ' + 'A funny story. ' * 30 for i in range(4)).strip()


class RecapCommentTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.execute('''CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
            winner1 TEXT, winner2 TEXT, winner_score INTEGER, loser1 TEXT, loser2 TEXT,
            loser_score INTEGER, updated_at TEXT, comments TEXT)''')
        self.conn.execute('''CREATE TABLE other_games (id INTEGER PRIMARY KEY, game_date TEXT,
            game_type TEXT, game_name TEXT, winner1 TEXT, winner_score INTEGER,
            loser1 TEXT, loser_score INTEGER, updated_at TEXT, comment TEXT)''')
        self.conn.execute('CREATE TABLE players (email TEXT, notes TEXT)')
        self.comments = [f'Game {i}: a memorable play.' for i in range(1, 66)]
        self.comments[0] += '\n' + 'Long comment with café and "a quote". ' * 200 + '\nThe ending.'
        self.comments[1] = self.comments[2] = 'Same comment on two different games.'
        for game_id, comment in enumerate(self.comments + ['', None, 'Unselected comment.'], 1):
            date = f'2026-10-11 12:{game_id // 60:02d}:{game_id % 60:02d}'
            self.conn.execute('INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                              (game_id, date, 'Alex', 'Pat', 21, 'Sam', 'Jo', 19, date, comment))
            self.conn.execute('INSERT INTO other_games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                              (game_id, date, 'Cards', 'Gin rummy', 'Alex', 21, 'Sam', 19, date, comment))
        self.selected_ids = list(range(1, 68))
        self.ai = Mock(return_value='HEADLINE: An eventful day\nSUMMARY:\n' + LONG_SUMMARY)
        self.image = Mock(return_value=(None, None, None, '', {}))
        for replacement in (
            patch('email_content.require_ai_api_key', return_value='test-key'),
            patch('email_content.set_cur', side_effect=self.conn.cursor),
            patch('database_functions.create_connection', return_value=self.conn),
            patch('stat_functions.get_current_streaks_last_365_days', return_value=[]),
            patch('player_functions.get_player_by_name', return_value=None),
            patch('email_content._phrases_by_player_name', return_value={'Alex': ['Always wears a lucky hat']}),
            patch('email_content.generate_ai_text', self.ai),
            patch('email_content._try_generate_email_hero_image', self.image),
            patch('email_content.create_doubles_email_html', return_value=''),
            patch('email_content.create_doubles_email_plain_text', return_value=''),
            patch('email_content.create_other_email_html', return_value=''),
            patch('email_content.create_other_email_plain_text', return_value=''),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)

    def test_all_selected_comments_reach_ai_for_default_and_long_custom_prompts(self):
        custom = ('Tell the full story of the day.\n' + 'Include partnerships and comebacks. ' * 100).strip()
        for builder in (build_doubles_email_payload, build_other_email_payload):
            for style in ('default', 'custom'):
                with self.subTest(builder=builder.__name__, style=style):
                    image_details = 'Draw Alex riding a purple dragon on the moon.'
                    payload = builder(self.selected_ids, prompt_style=style, custom_prompt=custom,
                                      image_details=image_details)
                    prompt = self.ai.call_args.args[0]
                    self.assertEqual(payload['ai_prompt'], prompt)
                    self.assertNotIn(image_details, prompt)
                    self.assertIn('Alex: Always wears a lucky hat', prompt)
                    self.assertEqual(payload['image_details'], image_details)
                    self.assertEqual(self.image.call_args.kwargs['image_details'],
                                     image_details)
                    for comment in self.comments:
                        self.assertIn(comment, prompt)
                    self.assertEqual(prompt.count(self.comments[1]), 2)
                    self.assertNotIn('Unselected comment.', prompt)
                    self.assertIn(RECAP_LENGTH_GUIDANCE, prompt)
                    self.assertNotIn(LEGACY_LIMIT, prompt)
                    self.assertNotIn('Write two short', prompt)
                    if style == 'custom':
                        self.assertIn(custom, prompt)
                        self.assertEqual(payload['style_instructions'], custom)
                    self.assertEqual(payload['summary'], LONG_SUMMARY)

    def test_remade_custom_prompt_drops_former_appended_length_cap(self):
        custom = 'Describe the comebacks and every funny story.'
        style = _build_recap_style_instructions('custom', '', custom + '\n' + LEGACY_LIMIT)
        self.assertEqual(style, custom)


class DailySummaryCommentTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.games = [
            [i, '10/11/2026', 'Alex', 'Pat', 21, 'Sam', 'Jo', 19, '', f'Comment for game {i}.']
            for i in range(65, 0, -1)
        ]
        self.games[0][9] += '\n' + 'A long comment. ' * 200 + 'Keep the ending.'
        # Old rows with no comment field, and empty/null comments, remain valid.
        self.games.extend([self.games[0][:9], self.games[0][:9] + [''], self.games[0][:9] + [None]])
        self.ai = Mock(return_value=LONG_SUMMARY)
        self.namespace = dict(
            app=self.app, request=request, session=session, jsonify=jsonify,
            active_ai_provider=lambda: 'openai',
            specific_date_stats=lambda date: ([], self.games), generate_ai_text=self.ai,
            RECAP_LENGTH_GUIDANCE=RECAP_LENGTH_GUIDANCE,
        )
        tree = ast.parse((ROOT / 'stats.py').read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == 'generate_ai_summary']
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'stats.py', 'exec'), self.namespace)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state['username'] = 'Alex'

    def test_daily_summary_includes_all_games_and_complete_comments(self):
        response = self.client.post('/generate_ai_summary', data={'date': '2026-10-11'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['summary'], LONG_SUMMARY)
        self.assertEqual(response.json['games_count'], len(self.games))
        prompt = self.ai.call_args.args[0]
        for game in self.games[:65]:
            self.assertIn(game[9], prompt)
        self.assertIn(RECAP_LENGTH_GUIDANCE, prompt)
        self.assertNotIn('under 100 words', prompt)
        self.assertNotIn('2-3 sentences only', prompt)
        self.assertLess(prompt.index('Comment for game 1.'), prompt.index('Comment for game 65.'))


if __name__ == '__main__':
    unittest.main()
