"""
Supabase dual-write for doubles games. When the web app adds/updates/deletes
a game in stats.db, the same change is written to Supabase. If Supabase is
not configured, all functions no-op.

Expects Supabase table `games` with: id (uuid), db_id (uuid, FK to public.databases
= which game set e.g. KT), game_date, winner1, winner2, winner_score, loser1,
loser2, loser_score, comments, updated_at, entered_timezone, updated_by,
editor_db_id (uuid, optional).

Row identity: id = deterministic UUID from SQLite game_id (for update/delete).
db_id = which game set (e.g. KT). Games are written to the set given by
SUPABASE_DATABASE_ID; default is KT.
"""
import os
import uuid

# Namespace for deterministic id from SQLite game_id (so we can find row on update/delete)
_ID_NAMESPACE = uuid.UUID('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11')

# Default database id from public.databases (game set to write games to)
_DEFAULT_DATABASE_ID = '2720b654-b3f7-4868-825d-e595d7be3d78'


def _id_for_sqlite_game(game_id):
    """Deterministic UUID from SQLite game id; used as games.id for lookup on update/delete."""
    return str(uuid.uuid5(_ID_NAMESPACE, str(game_id)))


def _target_database_id():
    """UUID of the Supabase 'database' (game set) to write games to, e.g. KT."""
    return os.environ.get('SUPABASE_DATABASE_ID', '').strip() or _DEFAULT_DATABASE_ID

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
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning('Supabase init failed: %s', e)
        return None


def _table():
    name = os.environ.get('SUPABASE_DOUBLES_TABLE', 'games')
    client = _get_supabase()
    return client.table(name) if client else None


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
    """Insert a game row into Supabase. Returns True on success, False on failure, None if not configured."""
    tbl = _table()
    if not tbl:
        return None
    try:
        row = _serialize_game(game_dict)
        # id = deterministic from SQLite game_id (for update/delete); db_id = game set (KT)
        payload = {
            'id': _id_for_sqlite_game(game_id),
            'db_id': _target_database_id(),
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
        return True
    except Exception:
        return False


def update_game(game_id, game_dict):
    """Update a game row in Supabase by id. Returns True/False/None."""
    tbl = _table()
    if not tbl:
        return None
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
        tbl.update(payload).eq('id', _id_for_sqlite_game(game_id)).execute()
        return True
    except Exception:
        return False


def delete_game(game_id):
    """Delete a game row from Supabase by id. Returns True/False/None."""
    tbl = _table()
    if not tbl:
        return None
    try:
        tbl.delete().eq('id', _id_for_sqlite_game(game_id)).execute()
        return True
    except Exception:
        return False
