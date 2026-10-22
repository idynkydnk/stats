"""Ties survive saving/editing without assigning either side a win or loss."""
import sqlite3
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from create_other_database import (BASE_INSERT_COLUMNS, BASE_UPDATE_COLUMNS,
                                   create_other_game, database_update_other_game)
from game_ratings import summarize_games
from other_game_outcomes import parse_is_tie, validate_tie_scores, validate_tie_game_type
import other_functions as other


def game(**changes):
    return dict(dict(id=1, game_date='2026-10-21 19:00:00', game_type='Board games',
                     game_name='Sequence', winner1='Alice', winner2='Beth',
                     loser1='Cara', loser2='Dana', winner_score=1, loser_score=1,
                     is_tie=True), **changes)


class OtherTieTests(unittest.TestCase):
    def test_flag_parsing_does_not_turn_strings_or_legacy_scores_into_ties(self):
        for flag in (None, '', False, 0, '0', 'false', 'off'):
            self.assertFalse(parse_is_tie(flag))
        for flag in (True, 1, '1', 'true', 'on'):
            self.assertTrue(parse_is_tie(flag))
        with self.assertRaises(ValueError):
            parse_is_tie('winner')
        legacy = game()
        del legacy['is_tie']
        row = other.readable_games_data([legacy])[0]
        self.assertFalse(row['is_tie'])
        self.assertEqual(other.total_other_stats('Alice', [legacy])[0], ['Alice', 1, 0, 1, 1, 0])

    def test_team_and_individual_tie_scores_must_agree(self):
        validate_tie_scores(True, 'team', [], [], 1, '1')
        validate_tie_scores(True, 'individual', [1, 1], [1, '1'])
        validate_tie_scores(True, 'none', [], [])
        validate_tie_scores(True, 'team', [], [])
        for args in [('team', [], [], 1, 2), ('team', [], [], 1, None),
                     ('individual', [1, 1], [1, 2], None, None),
                     ('individual', ['bad'], [1], None, None),
                     ('individual', [1.2], [1.2], None, None)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_tie_scores(True, *args)

    def test_volleyball_cannot_tie(self):
        for category in ['Volleyball', ' volleyball ', 'VOLLEYBALL', 'Beach Volleyball']:
            with self.subTest(category=category), self.assertRaises(ValueError):
                validate_tie_game_type(True, category)
        validate_tie_game_type(False, 'Volleyball')
        validate_tie_game_type(True, 'Board games')

    def test_decisive_team_scores_cannot_be_equal_but_individual_scores_can(self):
        with self.assertRaisesRegex(ValueError, 'different team scores'):
            validate_tie_scores(False, 'team', [], [], 1, '1')
        validate_tie_scores(False, 'team', [], [], 2, 1)
        validate_tie_scores(False, 'team', [], [])
        validate_tie_scores(False, 'individual', [1], [1])

    def test_tie_counts_once_for_every_player_and_only_opposing_players(self):
        tied = game(winner15='Alice')
        self.assertEqual(other.total_game_name_stats([tied]),
                         [[name, 0, 0, 0, 1, 1] for name in ['Alice', 'Beth', 'Cara', 'Dana']])
        for name in ['Alice', 'Beth', 'Cara', 'Dana']:
            self.assertEqual(other.total_other_stats(name, [tied])[0], [name, 0, 0, 0, 1, 1])
        opponents = other.other_opponent_stats_by_year('Alice', [tied])
        self.assertEqual([row['opponent'] for row in opponents], ['Cara', 'Dana'])
        self.assertTrue(all((row['wins'], row['losses'], row['ties'], row['total_games']) ==
                            (0, 0, 1, 1) for row in opponents))
        self.assertEqual(other.total_other_stats('Nobody', [tied])[0], ['Nobody', 0, 0, 0, 0, 0])

    def test_mixed_history_and_tie_only_players_use_all_games_for_thresholds(self):
        games = [game(), game(id=2, is_tie=False, winner_score=2),
                 game(id=3, is_tie=False, winner1='Cara', loser1='Alice', winner_score=2)]
        stats = other.player_game_name_stats(games, 'Alice')
        self.assertEqual(stats, dict(wins=1, losses=1, ties=1, total_games=3, win_percentage=1/3))
        with patch.object(other, 'other_year_games', return_value=[game()]):
            self.assertEqual(len(other.other_stats_per_year('2026', 1)), 4)
            self.assertEqual(other.rare_other_stats_per_year('2026', 1), [])
            dashboard = other.get_other_dashboard_data('2026')
            self.assertEqual(len(dashboard['top_games_played']), 4)
            self.assertEqual(dashboard['top_games_played'][0][5], 1)

    def test_today_standings_have_ties_and_no_point_margin(self):
        with patch.object(other, 'todays_other_games', return_value=[game()]):
            expected = [[name, 0, 0, 0, 0, 1] for name in ['Alice', 'Beth', 'Cara', 'Dana']]
            self.assertEqual(other.todays_other_stats(), expected)
            self.assertEqual(other.todays_other_stats_by_game(),
                             [dict(game_name='Sequence', game_count=1, stats=expected)])

    def test_decisive_rating_model_skips_ties(self):
        tied = game()
        decisive = game(id=2, is_tie=False, winner_score=2)
        self.assertEqual(summarize_games([tied])['ratings'], {})
        self.assertEqual(summarize_games([tied, decisive])['ratings'],
                         summarize_games([decisive])['ratings'])
        self.assertEqual(summarize_games([tied, decisive])['unrated_games'], 1)


class OtherTiePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.conn.execute('CREATE TABLE other_games (id INTEGER PRIMARY KEY, ' +
                          ', '.join(BASE_INSERT_COLUMNS) + ')')

    def values(self, columns, **changes):
        row = game(**changes)
        return [row.get(column) for column in columns]

    def row(self):
        return dict(self.conn.execute('SELECT * FROM other_games WHERE id=1').fetchone())

    def test_old_schema_save_edit_and_change_back_to_decisive(self):
        create_other_game(self.conn, self.values(BASE_INSERT_COLUMNS), is_tie=True)
        self.assertEqual(self.row()['is_tie'], 1)
        self.assertTrue(other.readable_games_data([self.row()])[0]['is_tie'])
        # Omitted result on older clients preserves the saved outcome.
        database_update_other_game(self.conn, self.values(BASE_UPDATE_COLUMNS, comment='Edited') + [1])
        self.assertEqual(self.row()['is_tie'], 1)
        self.assertEqual(self.row()['comment'], 'Edited')
        database_update_other_game(self.conn,
                                   self.values(BASE_UPDATE_COLUMNS, winner_score=2) + [1], is_tie=False)
        self.assertEqual(self.row()['is_tie'], 0)
        self.assertEqual(self.row()['winner_score'], 2)

    def test_existing_equal_scores_are_not_reclassified_during_schema_upgrade(self):
        self.conn.execute('INSERT INTO other_games (winner_score, loser_score) VALUES (1, 1)')
        create_other_game(self.conn, self.values(BASE_INSERT_COLUMNS), is_tie=True)
        self.assertEqual(self.row()['is_tie'], 0)

    def test_invalid_tie_never_replaces_saved_game(self):
        create_other_game(self.conn, self.values(BASE_INSERT_COLUMNS), is_tie=True)
        before = self.row()
        with self.assertRaises(ValueError):
            database_update_other_game(self.conn, self.values(BASE_UPDATE_COLUMNS, loser_score=2) + [1])
        self.assertEqual(self.row(), before)

    def test_volleyball_ties_are_rejected_on_insert_and_edit(self):
        with self.assertRaises(ValueError):
            create_other_game(self.conn, self.values(BASE_INSERT_COLUMNS, game_type='Volleyball'), is_tie=True)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM other_games').fetchone()[0], 0)
        create_other_game(self.conn, self.values(BASE_INSERT_COLUMNS, game_type='Volleyball', winner_score=2))
        with self.assertRaises(ValueError):
            database_update_other_game(self.conn, self.values(BASE_UPDATE_COLUMNS, game_type='Volleyball') + [1], is_tie=True)
        self.assertEqual(self.row()['is_tie'], 0)

    def test_add_other_stats_passes_explicit_result_and_validates_before_saving(self):
        with patch.object(other, 'create_connection', return_value=self.conn):
            other.add_other_stats('2026-10-21', 'Board games', 'Sequence',
                                  ['Alice', 'Beth'], [], ['Cara', 'Dana'], [], '', '2026-10-21',
                                  1, 1, is_tie=True)
            self.assertEqual(self.row()['is_tie'], 1)
            with self.assertRaises(ValueError):
                other.add_other_stats('2026-10-21', 'Board games', 'Sequence',
                                      ['Alice'], [], ['Cara'], [], '', '2026-10-21',
                                      1, 2, is_tie=True)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM other_games').fetchone()[0], 1)


class OtherTieSourceTests(unittest.TestCase):
    def test_personal_tie_survives_combined_stats_with_legacy_site_schema(self):
        from account_stats_views import build_stats_view, SOURCE_ID_STRIDE
        from private_accounts import provision_database
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site_path = str(root / 'site.db')
            with sqlite3.connect(site_path) as conn:
                conn.execute('CREATE TABLE other_games (id INTEGER PRIMARY KEY, winner1, loser1)')
                conn.execute("INSERT INTO other_games VALUES (1, 'Legacy', 'Opponent')")
            site_before = Path(site_path).read_bytes()
            with patch.dict(os.environ, STATS_PRIVATE_DATA_DIR=str(root / 'private')):
                own_path = provision_database(site_path, 'a' * 32)
            with sqlite3.connect(own_path) as conn:
                conn.execute("INSERT INTO other_games VALUES (1, 'Alice', 'Bob', 1)")
            own_before = Path(own_path).read_bytes()
            with patch('account_stats_views._database_path', return_value=site_path):
                snapshot = build_stats_view(site_path, own_path, [dict(enabled=True, number=1)])
            try:
                with sqlite3.connect(snapshot) as conn:
                    self.assertEqual(conn.execute('SELECT id, is_tie FROM other_games ORDER BY id').fetchall(),
                                     [(1, 1), (SOURCE_ID_STRIDE + 1, 0)])
            finally:
                Path(snapshot).unlink()
            # Schema upgrades touch the new database/snapshot, never source data.
            self.assertEqual(Path(site_path).read_bytes(), site_before)
            self.assertEqual(Path(own_path).read_bytes(), own_before)


if __name__ == '__main__':
    unittest.main()
