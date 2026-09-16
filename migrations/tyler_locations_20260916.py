"""One-time, live-data correction approved on September 16, 2026.

Never copy a local database or local game IDs onto the server. Classify the
server's own recorded days, leave ambiguous days for review, and retain an
undo record for every changed location in the same transaction.
"""
import json
from collections import defaultdict
from location_functions import TABLES, game_players, location_games
from player_identity import player_name_identity_key as identity

NAME = 'tyler-locations-2026-09-16'
OASIS = {'christian vincent', 'greg diaz', 'eddie molina', 'ian hall',
         'kevin ellis', 'selcuk mutlu', 'danny menken', 'joe cain'}
BEACH = {'ryan mccoy', 'darryl olejniczak', 'chris lahiff',
         'chris fortunes', 'steve devlin'}


def backfill_tyler_locations(conn):
    # Serialize startup workers and game writes while taking this short snapshot.
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS location_migrations (name TEXT PRIMARY KEY)')
        if conn.execute('SELECT 1 FROM location_migrations WHERE name=?', (NAME,)).fetchone():
            conn.commit()
            return 0
        games = location_games(conn, 'All years', end='2026-09-16')
        days = defaultdict(set)
        for game in games:
            days[game['game_date'][:10]].update(identity(p) for p in game_players(game))
        conn.execute('''CREATE TABLE IF NOT EXISTS location_migration_audit (
            migration TEXT, game_key TEXT, before_json TEXT, new_location TEXT,
            PRIMARY KEY (migration, game_key))''')
        count = 0
        for game in games:
            if 'tyler weston' not in {identity(p) for p in game_players(game)}:
                continue
            players = days[game['game_date'][:10]]
            oasis, beach = bool(players & OASIS), bool(players & BEACH)
            if oasis == beach:
                continue
            location = 'The Oasis' if oasis else 'Clearwater Beach'
            old = (game.get('location') or '').strip()
            # The live site used this broad city label for both groups.
            if old.casefold() not in {'', 'clearwater, florida', location.casefold()}:
                continue
            if old == location:
                continue
            conn.execute('INSERT INTO location_migration_audit VALUES (?,?,?,?)',
                         (NAME, game['key'], json.dumps(game), location))
            conn.execute(f"UPDATE {TABLES[game['kind']]} SET location=?, updated_at=datetime('now') WHERE id=?",
                         (location, game['id']))
            count += 1
        conn.execute('INSERT INTO location_migrations VALUES (?)', (NAME,))
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
