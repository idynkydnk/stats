"""
Firestore dual-write for doubles games. When the web app adds/updates/deletes
a game in stats.db, the same change is written to Firestore so the iPhone app
stays in sync. If Firebase is not configured, all functions no-op.
"""
import os

_firestore_client = None
_initialized = False

def _get_credentials_path():
    """Path to Firebase service account JSON. Prefer env var, then same folder as key."""
    path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if path and os.path.isfile(path):
        return path
    # Key in stats folder (same dir as this file)
    base = os.path.dirname(os.path.abspath(__file__))
    for name in os.listdir(base or '.'):
        if 'firebase' in name.lower() and 'adminsdk' in name.lower() and name.endswith('.json'):
            return os.path.join(base, name)
    return None

def _get_firestore():
    """Lazy init Firebase and return Firestore client. Returns None if not configured."""
    global _firestore_client, _initialized
    if _initialized:
        return _firestore_client
    _initialized = True
    creds_path = _get_credentials_path()
    if not creds_path:
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(creds_path))
        _firestore_client = firestore.client()
        return _firestore_client
    except Exception:
        return None

def _collection():
    name = os.environ.get('FIRESTORE_DOUBLES_COLLECTION', 'doubles_games')
    db = _get_firestore()
    return db.collection(name) if db else None

def _serialize_game(data):
    """Convert game dict for Firestore (dates to ISO strings)."""
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
    """Create or overwrite a game document in Firestore. No-op if Firebase not configured."""
    col = _collection()
    if not col:
        return
    try:
        doc = col.document(str(game_id))
        doc.set(_serialize_game(game_dict))
    except Exception:
        pass  # Don't break the web app if Firestore fails

def update_game(game_id, game_dict):
    """Update a game document in Firestore. No-op if Firebase not configured."""
    col = _collection()
    if not col:
        return
    try:
        doc = col.document(str(game_id))
        doc.set(_serialize_game(game_dict))  # set() overwrites; matches write_game
    except Exception:
        pass

def delete_game(game_id):
    """Delete a game document from Firestore. No-op if Firebase not configured."""
    col = _collection()
    if not col:
        return
    try:
        col.document(str(game_id)).delete()
    except Exception:
        pass
