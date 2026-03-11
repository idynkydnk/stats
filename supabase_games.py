"""
Supabase dual-write for doubles games. When the web app adds/updates/deletes
a game in stats.db, the same change is written to Supabase. If Supabase is
not configured, all functions no-op.
"""
import os

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
    name = os.environ.get('SUPABASE_DOUBLES_TABLE', 'doubles_games')
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
    """Insert a game row into Supabase. No-op if not configured."""
    tbl = _table()
    if not tbl:
        return
    try:
        row = _serialize_game(game_dict)
        row['id'] = game_id
        tbl.insert(row).execute()
    except Exception:
        pass  # Don't break the web app if Supabase fails


def update_game(game_id, game_dict):
    """Update a game row in Supabase. No-op if not configured."""
    tbl = _table()
    if not tbl:
        return
    try:
        row = _serialize_game(game_dict)
        row['id'] = game_id
        # Supabase update: pass only the columns to update (exclude id for the payload)
        payload = {k: v for k, v in row.items() if k != 'id'}
        tbl.update(payload).eq('id', game_id).execute()
    except Exception:
        pass


def delete_game(game_id):
    """Delete a game row from Supabase. No-op if not configured."""
    tbl = _table()
    if not tbl:
        return
    try:
        tbl.delete().eq('id', game_id).execute()
    except Exception:
        pass
