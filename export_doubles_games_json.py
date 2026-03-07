#!/usr/bin/env python3
"""
Export all doubles games for all years to a JSON file with all columns.
Run from project root: python export_doubles_games_json.py
Output: doubles_games.json
"""
import json
import sqlite3
from pathlib import Path

DB_PATHS = [
    Path("/home/Idynkydnk/stats/stats.db"),
    Path(__file__).resolve().parent / "stats.db",
]


def get_connection():
    for db_path in DB_PATHS:
        if db_path.exists():
            return sqlite3.connect(str(db_path))
    raise FileNotFoundError("stats.db not found in project root or PythonAnywhere path")


def main():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM games ORDER BY game_date ASC")
    rows = cur.fetchall()
    columns = [d[0] for d in cur.description]

    games = []
    for row in rows:
        game = {}
        for i, col in enumerate(columns):
            val = row[i]
            if hasattr(val, "isoformat"):  # datetime/date
                game[col] = val.isoformat() if val else None
            else:
                game[col] = val
        games.append(game)

    conn.close()

    out_path = Path(__file__).resolve().parent / "doubles_games.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(games, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(games)} games to {out_path}")


if __name__ == "__main__":
    main()
