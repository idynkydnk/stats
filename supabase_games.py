"""
Supabase dual-write for doubles games. When the web app adds/updates/deletes
a game in stats.db, the same change is written to Supabase. If Supabase is
not configured, all functions no-op.

Expects Supabase table `games` with: id (uuid), db_id (uuid), game_date,
winner1, winner2, winner_score, loser1, loser2, loser_score, comments,
updated_at, entered_timezone, updated_by, editor_db_id (uuid, optional).
"""
import os
import uuid

# Namespace for deterministic db_id from SQLite game_id (so we can find row on update/delete)
_DB_ID_NAMESPACE = uuid.UUID('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11')

_supabase_client = None
_initialized = False


def _get_supabase():
    """Lazy init and return Supabase client. Returns None if not configured."""
    global _supabase_client, _initialized
    if _initialized:
        return _supabase_client
    _initialized = True
    url = os.environ.get('SUPABASE_URL', '').strip()
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ.get('SUPABASE_KEY', '').strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception:
        return None


def _table():
    name = os.environ.get('SUPABASE_DOUBLES_TABLE', 'games')
    client = _get_supabase()
    return client.table(name) if client else None


def _db_id_for_sqlite_game(game_id):
    """Deterministic UUID from SQLite game id so we can look up the row on update/delete."""
    return str(uuid.uuid5(_DB_ID_NAMESPACE, str(game_id)))


def _serialize_game(data):
    """Convert game dict for Supabase (dates to ISO strings)."""
    out = dict(data)
    for key in ('game_date', 'updated_at'):
        if key in out and out[key] is not None:
            v = out[key]
            if hasattr(v, 'isoformat'):
                out[key] = v.isoformat()
            else:
                out[key] = str(v)
    return out


def write_game(game_id, game_dict):
    """Insert a game row into Supabase. No-op if not configured."""
    tbl = _table()
    if not tbl:
        return
    try:
        row = _serialize_game(game_dict)
        # Your table: id (uuid), db_id (uuid) required; editor_db_id left null
        payload = {
            'id': str(uuid.uuid4()),
            'db_id': _db_id_for_sqlite_game(game_id),
            'game_date': row.get('game_date'),
            'winner1': row.get('winner1'),
            'winner2': row.get('winner2'),
            'winner_score': row.get('winner_score'),
            'loser1': row.get('loser1'),
            'loser2': row.get('loser2'),
            'loser_score': row.get('loser_score'),
            'comments': row.get('comments') or None,
            'updated_at': row.get('updated_at'),
            'entered_timezone': row.get('entered_timezone'),
            'updated_by': row.get('updated_by'),
        }
        tbl.insert(payload).execute()
    except Exception:
        pass  # Don't break the web app if Supabase fails


def update_game(game_id, game_dict):
    """Update a game row in Supabase by db_id (derived from SQLite game_id). No-op if not configured."""
    tbl = _table()
    if not tbl:
        return
    try:
        row = _serialize_game(game_dict)
        payload = {
            'game_date': row.get('game_date'),
            'winner1': row.get('winner1'),
            'winner2': row.get('winner2'),
            'winner_score': row.get('winner_score'),
            'loser1': row.get('loser1'),
            'loser2': row.get('loser2'),
            'loser_score': row.get('loser_score'),
            'comments': row.get('comments') or None,
            'updated_at': row.get('updated_at'),
            'entered_timezone': row.get('entered_timezone'),
            'updated_by': row.get('updated_by'),
        }
        tbl.update(payload).eq('db_id', _db_id_for_sqlite_game(game_id)).execute()
    except Exception:
        pass


def delete_game(game_id):
    """Delete a game row from Supabase by db_id (derived from SQLite game_id). No-op if not configured."""
    tbl = _table()
    if not tbl:
        return
    try:
        tbl.delete().eq('db_id', _db_id_for_sqlite_game(game_id)).execute()
    except Exception:
        pass
