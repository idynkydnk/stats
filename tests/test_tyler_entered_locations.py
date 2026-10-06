import ast
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask, jsonify, request, session

from migrations.normalize_tyler_entered_locations import NAME, correct_database, migrate


def setup_games(conn):
    for table in ('games', 'vollis_games', 'other_games'):
        conn.execute(f'''CREATE TABLE {table} (id INTEGER PRIMARY KEY,
            entered_by TEXT, updated_by TEXT, winner1 TEXT, loser1 TEXT,
            winner_score INTEGER DEFAULT 21, location TEXT,
            updated_at TEXT DEFAULT 'original')''')
    conn.commit()


class TylerEnteredLocationsTests(unittest.TestCase):
    def test_ownership_and_canonical_names_preserve_results(self):
        with sqlite3.connect(':memory:') as conn:
            setup_games(conn)
            conn.executemany('INSERT INTO games (id,entered_by,updated_by,winner1,location) VALUES (?,?,?,?,?)', [
                (1, ' TYLER ', 'Kyle', 'Another player', None),
                (2, 'Kyle', 'Tyler', 'Tyler Weston', None),
                (3, None, 'Tyler', 'Tyler Weston', ''),
                (4, 'Tyler', 'Tyler', 'Tyler Weston', 'Other venue'),
                (5, 'Kyle', 'Kyle', 'Someone', 'Clearwater, Florida'),
                (6, 'Tyler', 'Tyler', 'Someone', 'Clearwater Beach')])
            for table in ('vollis_games', 'other_games'):
                conn.execute(f"INSERT INTO {table} (id,entered_by,location) VALUES (1,'tyler','  ')")
            conn.commit()
            self.assertEqual(correct_database(conn, {'tyler'}), 4)
            rows = conn.execute('SELECT location,winner_score,updated_by FROM games ORDER BY id').fetchall()
            self.assertEqual([tuple(r) for r in rows], [
                ('The Oasis', 21, 'Kyle'), (None, 21, 'Tyler'), ('', 21, 'Tyler'),
                ('Other venue', 21, 'Tyler'), ('Clearwater Beach', 21, 'Kyle'),
                ('Clearwater Beach', 21, 'Tyler')])
            audit = conn.execute('SELECT before_json FROM location_migration_audit WHERE game_key=?', ('games:1',)).fetchone()
            self.assertIsNone(json.loads(audit[0])['location'])
            self.assertEqual(json.loads(audit[0])['updated_by'], 'Kyle')
            conn.execute("UPDATE games SET location='Later correction' WHERE id=1")
            conn.execute("INSERT INTO games (id,entered_by) VALUES (7,'Tyler')")
            conn.commit()
            self.assertEqual(correct_database(conn, {'tyler'}), 0)
            self.assertEqual(conn.execute('SELECT location FROM games WHERE id=1').fetchone()[0], 'Later correction')
            self.assertIsNone(conn.execute('SELECT location FROM games WHERE id=7').fetchone()[0])

    def test_shared_and_personal_databases_are_corrected_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / 'stats.db'
            personal = root / 'personal'
            personal.mkdir()
            with sqlite3.connect(site) as conn:
                setup_games(conn)
                conn.executescript('''CREATE TABLE site_users (username,player_name,last_location);
                    INSERT INTO site_users VALUES ('tyler','Tyler Weston','Clearwater Beach');
                    INSERT INTO site_users VALUES ('Kyle','Kyle Thomson','Clearwater, Florida');
                    CREATE TABLE private_accounts (id,username);
                    INSERT INTO private_accounts VALUES ('a','tyler');
                    INSERT INTO private_accounts VALUES ('b','someone');
                    INSERT INTO games (id,entered_by,location) VALUES (1,'Kyle','Clearwater, Florida');''')
            for ident, entrant in [('a', 'Tyler'), ('b', 'someone')]:
                with sqlite3.connect(personal / (ident + '.db')) as conn:
                    setup_games(conn)
                    conn.execute('INSERT INTO games (id,entered_by) VALUES (1,?)', (entrant,))
                    conn.execute("INSERT INTO other_games (id,entered_by,location) VALUES (2,?,'Clearwater, Florida')", (entrant,))
            with patch.dict(os.environ, {'STATS_PRIVATE_DATA_DIR': str(personal)}), \
                 patch('migrations.normalize_tyler_entered_locations.subprocess.check_output', return_value='cloud-revision\n'):
                report = migrate(site)
                self.assertEqual(len(report['databases']), 3)
                self.assertEqual(sum(x['applied_now'] for x in report['databases']), 4)
                self.assertTrue(all(x['missing_tyler'] == x['noncanonical_clearwater'] == 0 for x in report['databases']))
                self.assertTrue(all(x['applied_now'] == 0 for x in migrate(site)['databases']))
            with sqlite3.connect(site) as conn:
                self.assertEqual(conn.execute('SELECT last_location FROM site_users ORDER BY username').fetchall(),
                                 [('Clearwater Beach',), ('The Oasis',)])
            with sqlite3.connect(personal / 'b.db') as conn:
                self.assertIsNone(conn.execute('SELECT location FROM games').fetchone()[0])
            saved_report = root / 'backups' / NAME / 'report.json'
            self.assertEqual(json.loads(saved_report.read_text())['revision'], 'cloud-revision')
            self.assertEqual(saved_report.stat().st_mode & 0o777, 0o600)

    def test_completed_correction_does_not_wait_for_a_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stats.db'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE location_migrations (name TEXT PRIMARY KEY)')
                conn.execute('INSERT INTO location_migrations VALUES (?)', (NAME,))
            with sqlite3.connect(path) as writer, sqlite3.connect(path, timeout=0) as reader:
                writer.execute('BEGIN IMMEDIATE')
                self.assertEqual(correct_database(reader, {'tyler'}), 0)
                self.assertFalse(reader.in_transaction)


class TylerAPILocationTests(unittest.TestCase):
    def test_each_api_save_defaults_blank_locations_and_preserves_explicit_venues(self):
        root = Path(__file__).resolve().parents[1]
        app = Flask(__name__)
        app.secret_key = 'test-only'
        app.testing = True
        write = Mock()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'stats.db'
            with sqlite3.connect(database) as conn:
                setup_games(conn)
            namespace = dict(app=app, request=request, session=session, jsonify=jsonify,
                             datetime=datetime, sqlite3=sqlite3, api_login_required=lambda fn: fn,
                             _api_get_db=lambda: str(database), add_game_stats=write,
                             adminfx=SimpleNamespace(get_site_user=lambda _: {}, snapshot_last_row=lambda _: None),
                             _remember_game_location=Mock(), clear_stats_cache=Mock(), update_kobs=Mock(), log_activity=Mock())
            tree = ast.parse((root / 'stats.py').read_text())
            for name in ('_new_game_location', 'api_doubles_create'):
                node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
                exec(compile(ast.Module(body=[node], type_ignores=[]), 'stats.py', 'exec'), namespace)
            namespace['_S'] = lambda: SimpleNamespace(**namespace)
            namespace['_normalize_game_date'] = lambda value: value
            register = next(n for n in ast.parse((root / 'ios_api.py').read_text()).body
                            if isinstance(n, ast.FunctionDef) and n.name == 'register_ios_api')
            for name in ('_other_payload_from_json', 'api_vollis_create', 'api_other_create'):
                node = next(n for n in register.body if isinstance(n, ast.FunctionDef) and n.name == name)
                exec(compile(ast.Module(body=[node], type_ignores=[]), 'ios_api.py', 'exec'), namespace)
            client = app.test_client()
            with client.session_transaction() as state:
                state['username'] = 'Tyler'
            fields = dict(game_date='2026-10-05 10:00:00', winner1='A', winner2='B', loser1='C', loser2='D',
                          winner='A', loser='B', winner_score=21, loser_score=15,
                          game_type='Cards', game_name='Sequence', winners=['A'], losers=['B'], score_type='team')
            with patch('player_functions.get_player_by_name', return_value=True), \
                 patch('vollis_functions.add_vollis_stats', write), patch('other_functions.add_other_stats', write):
                for kind in ('doubles', 'vollis', 'other'):
                    for supplied, expected in [(None, 'The Oasis'), ('', 'The Oasis'),
                                               ('Mission Beach', 'Mission Beach'), ('Clearwater, Florida', 'Clearwater Beach')]:
                        with self.subTest(kind=kind, supplied=supplied):
                            data = dict(fields)
                            if supplied is not None:
                                data['location'] = supplied
                            response = client.post(f'/api/{kind}/games', json=data)
                            self.assertEqual(response.status_code, 201)
                            args = write.call_args
                            self.assertEqual(args.kwargs['location'] if kind == 'other' else args.args[0][-1], expected)


if __name__ == '__main__':
    unittest.main()
