import ast
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock, patch

from flask import Flask, jsonify, request, session

from email_content import (
    RECAP_LENGTH_GUIDANCE,
    DEFAULT_RECAP_STYLE_INSTRUCTIONS,
    _build_recap_style_instructions,
    _resolve_recap_instructions,
    _recap_name_replacer,
    build_doubles_email_payload,
    build_other_email_payload,
    build_vollis_email_payload,
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
        self.conn.execute('''CREATE TABLE vollis_games (id INTEGER PRIMARY KEY, game_date TEXT,
            winner TEXT, winner_score INTEGER, loser TEXT, loser_score INTEGER, updated_at TEXT)''')
        self.conn.execute("INSERT INTO vollis_games VALUES (1, '2026-10-11 12:00:00', 'Alex', 11, 'Sam', 9, '2026-10-11 12:00:00')")
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
            patch('email_content.create_vollis_email_html', return_value=''),
            patch('email_content.create_vollis_email_plain_text', return_value=''),
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

    def test_combined_prompt_routes_picture_details_away_from_summary_for_all_game_types(self):
        picture = 'Show everyone celebrating at a green Martha’s volleyball net.'
        writing = 'Keep the recap short and funny.'
        for builder in (build_doubles_email_payload, build_vollis_email_payload, build_other_email_payload):
            for mode in ('none', 'image'):
                with self.subTest(builder=builder.__name__, mode=mode):
                    self.ai.reset_mock()
                    self.ai.side_effect = [json.dumps({'summary': writing, 'image': picture}),
                                           'HEADLINE: A close day\nSUMMARY: A funny recap.']
                    payload = builder([1], prompt_style='combined',
                                      custom_prompt=writing + ' For the picture, ' + picture,
                                      image_mode=mode)
                    self.assertEqual(self.ai.call_count, 2)
                    self.assertIn(picture, self.ai.call_args_list[0].args[0])
                    summary_prompt = self.ai.call_args_list[1].args[0]
                    self.assertIn(writing, summary_prompt)
                    self.assertNotIn(picture, summary_prompt)
                    self.assertNotIn('Martha', summary_prompt)
                    self.assertEqual(payload['style_instructions'], writing)
                    self.assertEqual(payload['image_details'], picture)
                    self.assertEqual(self.image.call_args.kwargs['image_details'], picture)
                    self.assertEqual(self.image.call_args.kwargs['visual_source'],
                                     writing + ' For the picture, ' + picture)
                    self.assertEqual(self.image.call_args.kwargs['image_mode'], mode)

    def test_full_long_request_reaches_picture_even_when_router_omits_visuals(self):
        transcript = ('Talk about our games. ' * 150
                      + "Put literal suns inside Sam's eyes. Cover Alex in honey. "
                      + 'A sand monster is stealing two colorful volleyballs.')
        for builder in (build_doubles_email_payload, build_vollis_email_payload, build_other_email_payload):
            with self.subTest(builder=builder.__name__):
                self.ai.side_effect = [json.dumps({'summary': 'Funny recap.', 'image': 'Beach scene.'}),
                                       'HEADLINE: Close games\nSUMMARY: A funny recap.']
                builder([1], prompt_style='combined', custom_prompt=transcript,
                        image_details='Keep the sign readable.', image_mode='image')
                source = self.image.call_args.kwargs['visual_source']
                self.assertIn(transcript, source)
                self.assertTrue(source.endswith('Keep the sign readable.'))

    def test_empty_combined_prompt_uses_defaults_without_routing_call(self):
        payload = build_doubles_email_payload([1], prompt_style='combined', custom_prompt='  ')
        self.ai.assert_called_once()
        self.assertEqual(payload['style_instructions'], DEFAULT_RECAP_STYLE_INSTRUCTIONS)
        self.assertEqual(payload['image_details'], '')

    def test_name_replacement_preserves_words_and_nicknames_containing_first_names(self):
        with patch('player_functions.player_display_name', side_effect=lambda name: {
            'Will Smith': 'Big Will', 'Sam Jones': 'Sam',
        }[name]):
            replace = _recap_name_replacer(['Will Smith', 'Sam Jones'])
            text = "Will will beat WILL SMITH's record. Sam Jones watches. Big Will smiles."
            expected = "Big Will will beat Big Will's record. Sam watches. Big Will smiles."
            self.assertEqual(replace(text), expected)
            self.assertEqual(replace(replace(text)), expected)

    def test_names_are_removed_before_routing_writing_and_image_instructions(self):
        for table, fields in (('games', ('winner1', 'loser1')),
                              ('vollis_games', ('winner', 'loser')),
                              ('other_games', ('winner1', 'loser1'))):
            self.conn.execute(f'UPDATE {table} SET {fields[0]}=?, {fields[1]}=?',
                              ('Alex Smith', 'Sam Jones'))
            self.conn.execute(f'ALTER TABLE {table} ADD COLUMN location TEXT')
            self.conn.execute(f'ALTER TABLE {table} ADD COLUMN entered_timezone TEXT')
            self.conn.execute(f'UPDATE {table} SET location=?, entered_timezone=?',
                              ('Hermosa Beach', 'America/Los_Angeles'))
        self.conn.execute('UPDATE games SET comments=?', ("Alex Smith beat Sam Jones's serve.",))
        self.conn.execute('UPDATE other_games SET comment=?', ("Alex Smith beat Sam Jones's serve.",))
        with patch('player_functions.player_display_name',
                   side_effect=lambda name: 'Big Alex' if name == 'Alex Smith' else name.split()[0]):
            for builder in (build_doubles_email_payload, build_vollis_email_payload, build_other_email_payload):
                with self.subTest(builder=builder.__name__):
                    self.ai.reset_mock()
                    self.ai.side_effect = [
                        json.dumps({'summary': 'Roast Big Alex and Sam.', 'image': 'Draw Big Alex and Sam.'}),
                        'HEADLINE: Alex Smith wins\nSUMMARY: Alex Smith beat Sam Jones.',
                    ]
                    payload = builder([1], prompt_style='combined',
                                      custom_prompt='Roast Alex Smith and Sam Jones. Draw them, too.')
                    for call in self.ai.call_args_list:
                        self.assertNotIn('Alex Smith', call.args[0])
                        self.assertNotIn('Sam Jones', call.args[0])
                        self.assertNotIn('Big Big Alex', call.args[0])
                    self.assertEqual(payload['summary'], 'Big Alex beat Sam.')
                    self.assertEqual(payload['subject'], 'Big Alex wins')
                    self.assertEqual(self.image.call_args.kwargs['image_details'], 'Draw Big Alex and Sam.')
                    self.assertNotIn('Alex Smith', self.image.call_args.kwargs['visual_source'])
                    self.assertNotIn('Sam Jones', self.image.call_args.kwargs['visual_source'])
                    weather = self.image.call_args.kwargs['weather_games'][0]
                    self.assertEqual(weather['location'], 'Hermosa Beach')
                    self.assertTrue(weather['game_date'].startswith('2026-10-11 12:'))
                    self.assertEqual(weather['entered_timezone'], 'America/Los_Angeles')

    def test_picture_only_prompt_uses_standard_recap_and_accepts_fenced_json(self):
        self.ai.return_value = '```json\n{"summary": "", "image": "Use a green net."}\n```'
        style, image = _resolve_recap_instructions('combined', '', 'Use a green net.')
        self.assertEqual(style, DEFAULT_RECAP_STYLE_INSTRUCTIONS)
        self.assertEqual(image, 'Use a green net.')

    def test_invalid_routing_result_stops_before_writing_summary_or_picture(self):
        for result in ('not JSON', '[]', '{"summary": null, "image": "net"}',
                       '{"summary": "funny"}'):
            with self.subTest(result=result):
                self.ai.reset_mock()
                self.ai.return_value = result
                with self.assertRaisesRegex(ValueError, 'Could not separate'):
                    build_doubles_email_payload([1], prompt_style='combined', custom_prompt='Use a green net.')
                self.ai.assert_called_once()
                self.image.assert_not_called()


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
