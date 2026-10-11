"""Repeatable local measurements using synthetic data in temporary databases only."""
import ast
from contextlib import closing
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from account_stats_views import build_stats_view
from game_browse_page import game_page
import kob_functions as kob
from stats_snapshot_cache import prepared_snapshot


def measure(function, runs=5):
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        function()
        times.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(times), 2)


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        database = str(root / 'stats.db')
        with closing(sqlite3.connect(database)) as conn, conn:
            conn.executescript("""CREATE TABLE games (id INTEGER PRIMARY KEY, game_date TEXT,
                winner1 TEXT, winner2 TEXT, loser1 TEXT, loser2 TEXT, winner_score INTEGER, loser_score INTEGER);
                CREATE TABLE players (id INTEGER PRIMARY KEY, full_name TEXT);
                CREATE TABLE sessions (id INTEGER PRIMARY KEY, session_number INTEGER, start_time TEXT,
                end_time TEXT, total_games INTEGER, doubles_games INTEGER, vollis_games INTEGER,
                one_v_one_games INTEGER, other_games INTEGER, created_at TEXT);""")
            games = []
            for group in range(1000):
                for index, (w1, w2, l1, l2) in enumerate([('A', 'B', 'C', 'D'), ('A', 'C', 'B', 'D'), ('A', 'D', 'B', 'C')]):
                    date = datetime(2020, 1, 1, 10) + timedelta(days=group, minutes=index * 30)
                    games.append((len(games) + 1, date.isoformat(' '), w1, w2, l1, l2, 21, 10))
            conn.executemany('INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?)', games)
        results = {}
        def snapshot():
            Path(build_stats_view(database, database, [])).unlink()
        databases = [(database, 0)]
        def reused():
            Path(prepared_snapshot(root / 'cache', databases, lambda: build_stats_view(database, database, []))).unlink()
        results['combined_view_rebuild_ms'] = measure(snapshot)
        reused()
        results['combined_view_reuse_ms'] = measure(reused)
        app = Flask(__name__)
        with closing(sqlite3.connect(database)) as conn:
            conn.row_factory = sqlite3.Row
            def full_list():
                return json.dumps([dict(r) for r in conn.execute('SELECT * FROM games ORDER BY game_date DESC')])
            def page():
                rows, metadata = game_page(conn, 'games')
                return json.dumps(dict(games=[dict(r) for r in rows], **metadata))
            with app.test_request_context('/?limit=50'):
                results['full_history_ms'] = measure(full_list)
                results['first_50_games_ms'] = measure(page)
                results['full_history_bytes'] = len(full_list())
                results['first_50_games_bytes'] = len(page())
        baseline = subprocess.check_output(['git', 'show', 'HEAD:kob_functions.py'], text=True)
        node = next(n for n in ast.parse(baseline).body if isinstance(n, ast.FunctionDef) and n.name == 'update_kobs')
        namespace = dict(kob.__dict__)
        namespace['create_connection'] = lambda _: sqlite3.connect(database)
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<baseline-kobs>', 'exec'), namespace)
        results['tournament_full_rebuild_ms'] = measure(namespace['update_kobs'], runs=3)
        with closing(sqlite3.connect(database)) as conn:
            before = conn.execute('SELECT session_number, start_time, end_time, total_games FROM sessions ORDER BY session_number').fetchall()
        with patch.object(kob, 'create_connection', side_effect=lambda _: sqlite3.connect(database)):
            kob.update_kobs()
            def changed_group():
                with closing(sqlite3.connect(database)) as conn, conn:
                    conn.execute('UPDATE games SET winner_score=winner_score+1 WHERE id=3000')
                kob.update_kobs()
            results['tournament_one_group_changed_ms'] = measure(changed_group)
        with closing(sqlite3.connect(database)) as conn:
            after = conn.execute('SELECT session_number, start_time, end_time, total_games FROM sessions ORDER BY session_number').fetchall()
        assert before == after
        results['games'] = len(games)
        results['tournaments'] = len(after)
        print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
