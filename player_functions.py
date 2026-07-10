from create_players_database import *
from datetime import datetime
import base64
import json
import os
import uuid

ALLOWED_PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_FULL_BODY_PHOTOS = 10

# Canonical SELECT for players — avoids breakage when legacy columns (e.g. phone) exist.
PLAYERS_SELECT = """
    SELECT id, full_name, email, date_of_birth, height, notes,
           created_at, updated_at, photo_path, full_body_photo_path
    FROM players
"""

PLAYERS_SELECT_COLUMNS = 10


def init_players_photo_column():
    """Ensure players photo columns exist (safe to call on every startup)."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    if conn is None:
        return
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(players)')
    cols = [row[1] for row in cur.fetchall()]
    if 'photo_path' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN photo_path TEXT')
    if 'full_body_photo_path' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN full_body_photo_path TEXT')
    if 'full_body_photo_paths' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN full_body_photo_paths TEXT')
    if 'ai_image_traits' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN ai_image_traits TEXT')
    if 'face_photo_focus' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN face_photo_focus TEXT')
    conn.commit()
    conn.close()


def player_photos_dir():
    """Absolute path to static/player_photos."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, 'static', 'player_photos')
    os.makedirs(path, exist_ok=True)
    return path


def get_player_photo_path(full_name):
    """Return stored photo_path (e.g. player_photos/3.jpg) or None."""
    cur = set_cur()
    cur.execute(
        'SELECT photo_path FROM players WHERE full_name = ?',
        (full_name,),
    )
    row = cur.fetchone()
    return row[0] if row and row[0] else None


def _parse_face_photo_focus(raw):
    if not raw:
        return 50.0, 50.0
    try:
        parts = str(raw).split(',')
        if len(parts) != 2:
            return 50.0, 50.0
        x = max(0.0, min(100.0, float(parts[0])))
        y = max(0.0, min(100.0, float(parts[1])))
        return x, y
    except (TypeError, ValueError):
        return 50.0, 50.0


def get_player_face_photo_focus(full_name):
    """Return object-position focus (x%, y%) for the face circle crop."""
    cur = set_cur()
    cur.execute(
        'SELECT face_photo_focus FROM players WHERE full_name = ?',
        (full_name,),
    )
    row = cur.fetchone()
    return _parse_face_photo_focus(row[0] if row else None)


def set_player_face_photo_focus(player_id, x, y):
    """Save face crop focus as percentages for object-position."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    x = max(0.0, min(100.0, float(x)))
    y = max(0.0, min(100.0, float(y)))
    now = datetime.now()
    focus = f'{x:.1f},{y:.1f}'
    with conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE players SET face_photo_focus = ?, updated_at = ? WHERE id = ?',
            (focus, now, player_id),
        )
        conn.commit()
    return x, y


def get_player_full_body_photo_path(full_name):
    """Return first full-body path (legacy helper)."""
    paths = get_player_full_body_photo_paths(full_name)
    return paths[0] if paths else None


def _parse_body_paths_json(raw):
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, str) and p.strip()]


def _body_paths_from_row(paths_json, legacy_path):
    paths = _parse_body_paths_json(paths_json)
    if paths:
        return paths
    if legacy_path:
        return [legacy_path]
    return []


def _existing_body_paths(paths):
    return [p for p in paths if read_player_image_file(p)[0]]


def get_player_full_body_photo_paths(full_name):
    """Return all stored full-body photo paths for a player."""
    cur = set_cur()
    cur.execute(
        'SELECT full_body_photo_paths, full_body_photo_path FROM players WHERE full_name = ?',
        (full_name,),
    )
    row = cur.fetchone()
    if not row:
        return []
    return _existing_body_paths(_body_paths_from_row(row[0], row[1]))


def get_player_full_body_photo_paths_by_id(player_id):
    cur = set_cur()
    cur.execute(
        'SELECT full_body_photo_paths, full_body_photo_path FROM players WHERE id = ?',
        (player_id,),
    )
    row = cur.fetchone()
    if not row:
        return []
    return _existing_body_paths(_body_paths_from_row(row[0], row[1]))


def set_player_full_body_photo_paths(player_id, paths):
    """Persist full-body photo paths as JSON; clears legacy single-path column."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    now = datetime.now()
    clean = [p for p in paths if p]
    with conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE players SET full_body_photo_paths = ?, full_body_photo_path = NULL, updated_at = ? WHERE id = ?',
            (json.dumps(clean), now, player_id),
        )
        conn.commit()


def get_player_photo_paths(full_name):
    """Return face path and list of full-body paths for a player."""
    cur = set_cur()
    cur.execute(
        'SELECT photo_path, full_body_photo_paths, full_body_photo_path FROM players WHERE full_name = ?',
        (full_name,),
    )
    row = cur.fetchone()
    if not row:
        return None, []
    face = row[0] or None
    body_paths = _existing_body_paths(_body_paths_from_row(row[1], row[2]))
    return face, body_paths


def get_player_ai_image_traits(full_name):
    """Return free-text signature traits for AI image exaggeration."""
    cur = set_cur()
    cur.execute(
        'SELECT ai_image_traits FROM players WHERE full_name = ?',
        (full_name,),
    )
    row = cur.fetchone()
    return (row[0] or '').strip() if row and row[0] else ''


def set_player_ai_image_traits(player_id, traits):
    """Save signature traits used to exaggerate players in AI email images."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    now = datetime.now()
    clean = (traits or '').strip()[:500] or None
    with conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE players SET ai_image_traits = ?, updated_at = ? WHERE id = ?',
            (clean, now, player_id),
        )
        conn.commit()


def collect_player_ai_image_traits(player_names):
    """Traits to exaggerate for players in an AI email illustration."""
    traits = []
    for name in sorted(player_names):
        text = get_player_ai_image_traits(name)
        if text:
            traits.append({'name': name, 'traits': text})
    return traits


def set_player_photo_path(player_id, photo_path):
    """Update photo_path for a player."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    now = datetime.now()
    with conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE players SET photo_path = ?, updated_at = ? WHERE id = ?',
            (photo_path, now, player_id),
        )
        conn.commit()


def _validate_photo_upload(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError('No photo file provided.')

    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        raise ValueError('Photo must be JPG, PNG, WebP, or GIF.')

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_PHOTO_BYTES:
        raise ValueError('Photo must be 5 MB or smaller.')
    return ext


def _remove_stored_photo(rel_path):
    if not rel_path:
        return
    base = os.path.dirname(os.path.abspath(__file__))
    abs_path = os.path.join(base, 'static', rel_path)
    if os.path.isfile(abs_path):
        os.remove(abs_path)


def _mime_for_photo_path(rel_path):
    ext = os.path.splitext(rel_path or '')[1].lower()
    return {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
    }.get(ext, 'image/jpeg')


def read_player_image_file(rel_path):
    """Load bytes and mime type for a stored player photo, or (None, None)."""
    if not rel_path:
        return None, None
    base = os.path.dirname(os.path.abspath(__file__))
    abs_path = os.path.join(base, 'static', rel_path)
    if not os.path.isfile(abs_path):
        return None, None
    with open(abs_path, 'rb') as f:
        return f.read(), _mime_for_photo_path(rel_path)


def save_player_photo_upload(player_id, file_storage):
    """Validate and save a face photo upload. Returns relative static path."""
    ext = _validate_photo_upload(file_storage)
    dest_dir = player_photos_dir()
    filename = f'{player_id}{ext}'
    abs_path = os.path.join(dest_dir, filename)
    file_storage.save(abs_path)

    rel_path = f'player_photos/{filename}'
    set_player_photo_path(player_id, rel_path)
    set_player_face_photo_focus(player_id, 50, 50)
    return rel_path


def set_player_full_body_photo_path(player_id, photo_path):
    """Legacy: set a single full-body path (wraps paths list)."""
    set_player_full_body_photo_paths(player_id, [photo_path] if photo_path else [])


def save_player_full_body_photo_upload(player_id, file_storage):
    """Validate and append a full-body photo upload. Returns relative static path."""
    ext = _validate_photo_upload(file_storage)
    paths = get_player_full_body_photo_paths_by_id(player_id)
    if len(paths) >= MAX_FULL_BODY_PHOTOS:
        raise ValueError(f'Maximum {MAX_FULL_BODY_PHOTOS} full-body photos per player.')

    dest_dir = player_photos_dir()
    filename = f'{player_id}_body_{uuid.uuid4().hex[:12]}{ext}'
    abs_path = os.path.join(dest_dir, filename)
    file_storage.save(abs_path)

    rel_path = f'player_photos/{filename}'
    paths.append(rel_path)
    set_player_full_body_photo_paths(player_id, paths)
    return rel_path


def remove_player_full_body_photo(player_id, rel_path=None):
    """Delete one full-body photo (by path) or all if rel_path is None."""
    paths = get_player_full_body_photo_paths_by_id(player_id)
    if rel_path:
        if rel_path in paths:
            _remove_stored_photo(rel_path)
            paths = [p for p in paths if p != rel_path]
            set_player_full_body_photo_paths(player_id, paths)
        return
    for path in paths:
        _remove_stored_photo(path)
    set_player_full_body_photo_paths(player_id, [])


def remove_player_photo(player_id):
    """Delete face photo file and clear photo_path."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    cur.execute('SELECT photo_path FROM players WHERE id = ?', (player_id,))
    row = cur.fetchone()
    if row and row[0]:
        _remove_stored_photo(row[0])
    set_player_photo_path(player_id, None)
    set_player_face_photo_focus(player_id, 50, 50)


def collect_player_reference_images(player_names, max_players=5, max_body_per_player=3):
    """Build Gemini reference image parts for AI email illustrations."""
    references = []
    for name in sorted(player_names):
        if len(references) >= max_players:
            break
        face_path, body_paths = get_player_photo_paths(name)
        if not face_path and not body_paths:
            continue
        entry = {'name': name, 'parts': []}
        if face_path:
            raw, mime = read_player_image_file(face_path)
            if raw:
                entry['parts'].append({
                    'label': f'Face reference photo for {name}.',
                    'mime': mime,
                    'data_b64': base64.b64encode(raw).decode('ascii'),
                })
        for idx, body_path in enumerate(body_paths[:max_body_per_player], start=1):
            raw, mime = read_player_image_file(body_path)
            if raw:
                entry['parts'].append({
                    'label': f'Full-body reference photo {idx} for {name}.',
                    'mime': mime,
                    'data_b64': base64.b64encode(raw).decode('ascii'),
                })
        if entry['parts']:
            references.append(entry)
    return references


def set_cur():
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    return cur

def get_all_players():
    """Get all players from the database with their first game date and game count"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    
    # Get all unique player names from all game tables
    all_player_names = set()
    
    # From doubles games
    cur.execute("SELECT DISTINCT winner1 FROM games WHERE winner1 IS NOT NULL AND winner1 != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    cur.execute("SELECT DISTINCT winner2 FROM games WHERE winner2 IS NOT NULL AND winner2 != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    cur.execute("SELECT DISTINCT loser1 FROM games WHERE loser1 IS NOT NULL AND loser1 != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    cur.execute("SELECT DISTINCT loser2 FROM games WHERE loser2 IS NOT NULL AND loser2 != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    
    # From vollis games
    cur.execute("SELECT DISTINCT winner FROM vollis_games WHERE winner IS NOT NULL AND winner != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    cur.execute("SELECT DISTINCT loser FROM vollis_games WHERE loser IS NOT NULL AND loser != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    
    # From other games
    for position in ['winner1', 'winner2', 'winner3', 'winner4', 'winner5', 'winner6', 
                     'loser1', 'loser2', 'loser3', 'loser4', 'loser5', 'loser6']:
        cur.execute(f"SELECT DISTINCT {position} FROM other_games WHERE {position} IS NOT NULL AND {position} != ''")
        all_player_names.update([row[0] for row in cur.fetchall()])
    
    # For each player name, build their stats
    players_with_stats = []
    for player_name in all_player_names:
        # Check if player exists in players table
        cur.execute(f"{PLAYERS_SELECT} WHERE full_name = ?", (player_name,))
        player_record = cur.fetchone()
        
        # Count doubles games
        cur.execute("""
            SELECT COUNT(*), MIN(game_date) FROM games 
            WHERE winner1 = ? OR winner2 = ? OR loser1 = ? OR loser2 = ?
        """, (player_name, player_name, player_name, player_name))
        doubles_result = cur.fetchone()
        doubles_count = doubles_result[0] if doubles_result and doubles_result[0] else 0
        doubles_date = doubles_result[1] if doubles_result else None
        
        # Count vollis games
        cur.execute("""
            SELECT COUNT(*), MIN(game_date) FROM vollis_games 
            WHERE winner = ? OR loser = ?
        """, (player_name, player_name))
        vollis_result = cur.fetchone()
        vollis_count = vollis_result[0] if vollis_result and vollis_result[0] else 0
        vollis_date = vollis_result[1] if vollis_result else None
        
        # Count other games
        cur.execute("""
            SELECT COUNT(*), MIN(game_date) FROM other_games 
            WHERE winner1 = ? OR winner2 = ? OR winner3 = ? OR winner4 = ? OR winner5 = ? OR winner6 = ?
               OR loser1 = ? OR loser2 = ? OR loser3 = ? OR loser4 = ? OR loser5 = ? OR loser6 = ?
        """, (player_name, player_name, player_name, player_name, player_name, player_name,
              player_name, player_name, player_name, player_name, player_name, player_name))
        other_result = cur.fetchone()
        other_count = other_result[0] if other_result and other_result[0] else 0
        other_date = other_result[1] if other_result else None
        
        # Calculate total games and earliest date
        total_games = int(doubles_count + vollis_count + other_count)
        dates = [d for d in [doubles_date, vollis_date, other_date] if d is not None]
        first_game_date = min(dates) if dates else None
        
        # Build player record
        if player_record:
            player_list = list(player_record)
        else:
            from datetime import datetime
            now = datetime.now()
            player_list = [None, player_name, None, None, None, None, now, now, None, None]

        while len(player_list) < PLAYERS_SELECT_COLUMNS:
            player_list.append(None)
        player_list = player_list[:PLAYERS_SELECT_COLUMNS]
        
        player_list.append(first_game_date)  # index 10
        player_list.append(int(total_games))  # index 11
        players_with_stats.append(tuple(player_list))
    
    # Sort by total games (descending) - safely handle any type issues
    def safe_game_count(player):
        try:
            return int(player[11]) if len(player) > 11 and player[11] is not None else 0
        except (ValueError, TypeError):
            return 0
    
    players_with_stats.sort(key=safe_game_count, reverse=True)
    
    conn.close()
    return players_with_stats

def get_player_by_id(player_id):
    """Get a specific player by ID"""
    cur = set_cur()
    cur.execute(f"{PLAYERS_SELECT} WHERE id=?", (player_id,))
    player = cur.fetchone()
    return player

def get_player_by_name(full_name):
    """Get a specific player by full name"""
    cur = set_cur()
    cur.execute(f"{PLAYERS_SELECT} WHERE full_name=?", (full_name,))
    player = cur.fetchone()
    return player

def add_new_player(full_name, email=None, date_of_birth=None, height=None, notes=None):
    """Add a new player to the database"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    now = datetime.now()
    with conn:
        player = (full_name, email, date_of_birth, height, notes, now, now)
        player_id = create_player(conn, player)
        return player_id

def update_player_info(player_id, full_name, email=None, date_of_birth=None, height=None, notes=None):
    """Update a player's information and update their name across all game tables"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    cur = conn.cursor()
    
    # Get the old name first
    cur.execute("SELECT full_name FROM players WHERE id=?", (player_id,))
    result = cur.fetchone()
    old_name = result[0] if result else None
    
    now = datetime.now()
    
    # If name has changed, update it across all game tables
    if old_name and old_name != full_name:
        # Update doubles games
        cur.execute("UPDATE games SET winner1 = ? WHERE winner1 = ?", (full_name, old_name))
        cur.execute("UPDATE games SET winner2 = ? WHERE winner2 = ?", (full_name, old_name))
        cur.execute("UPDATE games SET loser1 = ? WHERE loser1 = ?", (full_name, old_name))
        cur.execute("UPDATE games SET loser2 = ? WHERE loser2 = ?", (full_name, old_name))
        
        # Update vollis games
        try:
            cur.execute("UPDATE vollis_games SET winner = ? WHERE winner = ?", (full_name, old_name))
            cur.execute("UPDATE vollis_games SET loser = ? WHERE loser = ?", (full_name, old_name))
        except:
            pass  # Table might not exist
        
        # Other games (winner1, winner2, etc.) updated via database_functions.update_player_name_in_all_tables
        
        conn.commit()
    
    # Update the player record
    with conn:
        player = (full_name, email, date_of_birth, height, notes, now, player_id)
        update_player(conn, player)

def remove_player(player_id):
    """Delete a player from the database"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn:
        delete_player(conn, player_id)

def search_players(search_term):
    """Search for players by name or email"""
    cur = set_cur()
    cur.execute("SELECT * FROM players WHERE full_name LIKE ? OR email LIKE ? ORDER BY full_name ASC", 
                (f'%{search_term}%', f'%{search_term}%'))
    players = cur.fetchall()
    return players

