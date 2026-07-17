"""Admin dashboard helpers: activity log, site users, undo, and overview queries.

The activity_log table records every meaningful action on the site (game
add/edit/delete, player changes, logins, emails, deploys). Game mutations
store full before/after row snapshots as JSON so an admin can undo them.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone


def stats_db_path():
    """Same DB resolution logic as stats.py (PythonAnywhere path first)."""
    path = '/home/Idynkydnk/stats/stats.db'
    if os.path.exists(path):
        return path
    return 'stats.db'


def _connect():
    conn = sqlite3.connect(stats_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _recap_storage_dir():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, 'static', 'recaps')
    os.makedirs(path, exist_ok=True)
    return path


def _safe_recap_share_id(share_id):
    safe_id = ''.join(ch for ch in (share_id or '') if ch.isalnum() or ch in ('-', '_'))
    if not safe_id:
        raise ValueError('Invalid recap id')
    return safe_id


def _recap_html_path(share_id):
    safe_id = _safe_recap_share_id(share_id)
    return os.path.join(_recap_storage_dir(), f'{safe_id}.html')


def _recap_meta_path(share_id):
    safe_id = _safe_recap_share_id(share_id)
    return os.path.join(_recap_storage_dir(), f'{safe_id}.json')


def _write_json_atomic(path, payload):
    tmp_path = f'{path}.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False)
    os.replace(tmp_path, path)


def write_recap_html_file(share_id, html_body):
    path = _recap_html_path(share_id)
    tmp_path = f'{path}.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as handle:
        handle.write(html_body or '')
    os.replace(tmp_path, path)
    return path


def update_ai_recap_page(share_id, html_body=None, **meta_updates):
    """Update a published recap's HTML and/or JSON metadata on disk."""
    safe_id = _safe_recap_share_id(share_id)
    meta = _read_recap_meta_file(safe_id) or {'share_id': safe_id}
    if html_body is not None:
        write_recap_html_file(safe_id, html_body)
    for key, value in meta_updates.items():
        if value is None:
            continue
        meta[key] = value
    meta.pop('html_body', None)
    _write_json_atomic(_recap_meta_path(safe_id), meta)
    return meta


def read_recap_html_file(share_id):
    for candidate in (_recap_html_path(share_id),):
        if os.path.isfile(candidate):
            with open(candidate, encoding='utf-8') as handle:
                return handle.read()
    legacy = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recaps', f'{_safe_recap_share_id(share_id)}.html')
    if os.path.isfile(legacy):
        with open(legacy, encoding='utf-8') as handle:
            return handle.read()
    return None


def _read_recap_meta_file(share_id):
    path = _recap_meta_path(share_id)
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


# Undo-able targets and their tables. Only tables listed here can ever be
# touched by the undo machinery.
TARGET_TABLES = {
    'doubles_game': 'games',
    'vollis_game': 'vollis_games',
    'other_game': 'other_games',
}


def init_activity_log_db():
    conn = _connect()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            target_id INTEGER,
            summary TEXT,
            before_json TEXT,
            after_json TEXT,
            undone INTEGER DEFAULT 0
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_activity_log_created ON activity_log(created_at DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_activity_log_username ON activity_log(username)')
    conn.commit()
    conn.close()


def insert_activity(username, action, target=None, target_id=None, summary=None, before=None, after=None):
    """Insert one activity log row. Snapshots are dicts; stored as JSON."""
    conn = _connect()
    conn.execute('''
        INSERT INTO activity_log (username, action, target, target_id, summary, before_json, after_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        username, action, target, target_id, summary,
        json.dumps(before, default=str) if before else None,
        json.dumps(after, default=str) if after else None,
    ))
    conn.commit()
    conn.close()


def _decorate_activity_row(row):
    """Add undo metadata to an activity_log row dict."""
    d = dict(row)
    undoable = (
        not d['undone']
        and d['target'] in TARGET_TABLES
        and d['target_id'] is not None
        and (d['before_json'] or d['after_json'])
    )
    d['undoable'] = bool(undoable)
    if d['before_json'] and d['after_json']:
        d['undo_kind'] = 'edit'
    elif d['before_json']:
        d['undo_kind'] = 'delete'
    elif d['after_json']:
        d['undo_kind'] = 'add'
    else:
        d['undo_kind'] = None
    return d


def get_activity_page(page=1, per_page=50, username=None, q=None):
    """One page of activity entries (newest first) plus total count.

    Optional filters: username (exact, case-insensitive) and q (substring match
    across username/action/summary).
    """
    offset = (max(page, 1) - 1) * per_page
    clauses = []
    params = []
    if username:
        clauses.append('lower(username) = lower(?)')
        params.append(username.strip())
    if q:
        needle = f'%{q.strip()}%'
        clauses.append('(username LIKE ? OR action LIKE ? OR IFNULL(summary, "") LIKE ?)')
        params.extend([needle, needle, needle])
    where = f'WHERE {" AND ".join(clauses)}' if clauses else ''

    conn = _connect()
    total = conn.execute(f'SELECT COUNT(*) FROM activity_log {where}', params).fetchone()[0]
    rows = conn.execute(f'''
        SELECT id, created_at, username, action, target, target_id, summary,
               before_json, after_json, undone
        FROM activity_log {where}
        ORDER BY id DESC LIMIT ? OFFSET ?
    ''', (*params, per_page, offset)).fetchall()
    conn.close()
    return [_decorate_activity_row(r) for r in rows], total


def get_activity_entry(log_id):
    conn = _connect()
    row = conn.execute('SELECT * FROM activity_log WHERE id = ?', (log_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def snapshot_row(target, row_id):
    """Full row of a target table as a dict, or None."""
    table = TARGET_TABLES[target]
    conn = _connect()
    row = conn.execute(f'SELECT * FROM {table} WHERE id = ?', (row_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def snapshot_last_row(target):
    """Most recently inserted row of a target table (for logging adds)."""
    table = TARGET_TABLES[target]
    conn = _connect()
    row = conn.execute(f'SELECT * FROM {table} ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    return dict(row) if row else None


def undo_entry(log_id):
    """Reverse the change recorded in an activity log entry.

    Returns (ok, message, target). Edit -> restore the before snapshot;
    delete -> re-insert the before snapshot; add -> delete the row.
    """
    entry = get_activity_entry(log_id)
    if not entry:
        return False, 'Log entry not found.', None
    if entry['undone']:
        return False, 'This change was already undone.', None
    target = entry['target']
    if target not in TARGET_TABLES or entry['target_id'] is None:
        return False, 'This entry cannot be undone.', None

    table = TARGET_TABLES[target]
    before = json.loads(entry['before_json']) if entry['before_json'] else None
    after = json.loads(entry['after_json']) if entry['after_json'] else None
    if not before and not after:
        return False, 'No snapshot stored for this entry.', None

    conn = _connect()
    try:
        if before:
            # Edit or delete: put the old row back exactly as it was.
            cols = list(before.keys())
            placeholders = ', '.join('?' * len(cols))
            col_list = ', '.join(cols)
            conn.execute(
                f'INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})',
                [before[c] for c in cols],
            )
            message = 'Restored previous version of the game.' if after else 'Deleted game restored.'
        else:
            # Add: remove the inserted row.
            conn.execute(f'DELETE FROM {table} WHERE id = ?', (entry['target_id'],))
            message = 'Added game removed.'
        conn.execute('UPDATE activity_log SET undone = 1 WHERE id = ?', (log_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f'Undo failed: {e}', None
    conn.close()
    return True, message, target


# --- Site users (login accounts, stored hashed in the DB) ---

def init_users_db(seed_users=None, seed_admins=None):
    """Create site_users and seed it from the legacy USERS dict on first run."""
    conn = _connect()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS site_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    count = conn.execute('SELECT COUNT(*) FROM site_users').fetchone()[0]
    if count == 0 and seed_users:
        admins = {a.lower() for a in (seed_admins or set())}
        for username, password_hash in seed_users.items():
            conn.execute(
                'INSERT INTO site_users (username, password_hash, is_admin) VALUES (?, ?, ?)',
                (username, password_hash, 1 if username.lower() in admins else 0),
            )
    conn.commit()
    conn.close()


def get_site_user(username):
    conn = _connect()
    row = conn.execute(
        'SELECT * FROM site_users WHERE lower(username) = lower(?)', (username or '',)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_site_users():
    """All users with their last activity timestamp (from the activity log)."""
    conn = _connect()
    rows = conn.execute('''
        SELECT u.id, u.username, u.is_admin, u.active, u.created_at,
               (SELECT MAX(created_at) FROM activity_log a WHERE a.username = u.username) AS last_seen,
               (SELECT MAX(created_at) FROM activity_log a
                WHERE a.username = u.username AND a.action LIKE 'Logged in%') AS last_login
        FROM site_users u ORDER BY last_seen DESC, u.username
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_site_user(username, password_hash, is_admin=False):
    conn = _connect()
    try:
        conn.execute(
            'INSERT INTO site_users (username, password_hash, is_admin) VALUES (?, ?, ?)',
            (username, password_hash, 1 if is_admin else 0),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return False
    conn.close()
    return True


def update_site_user(username, password_hash=None, is_admin=None, active=None):
    sets, params = [], []
    if password_hash is not None:
        sets.append('password_hash = ?')
        params.append(password_hash)
    if is_admin is not None:
        sets.append('is_admin = ?')
        params.append(1 if is_admin else 0)
    if active is not None:
        sets.append('active = ?')
        params.append(1 if active else 0)
    if not sets:
        return False
    params.append(username)
    conn = _connect()
    cur = conn.execute(
        f"UPDATE site_users SET {', '.join(sets)} WHERE lower(username) = lower(?)", params
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


# --- Dashboard overview queries ---

def games_counts(today_str, week_ago_str):
    """Per-game-type counts for today and the last 7 days."""
    conn = _connect()
    out = {}
    for label, table in (('doubles', 'games'), ('vollis', 'vollis_games'), ('other', 'other_games')):
        today = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE strftime('%Y-%m-%d', game_date) = ?", (today_str,)
        ).fetchone()[0]
        week = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE strftime('%Y-%m-%d', game_date) >= ?", (week_ago_str,)
        ).fetchone()[0]
        total = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        out[label] = {'today': today, 'week': week, 'total': total}
    conn.close()
    return out


def most_recent_game():
    """The single most recent game across all three tables."""
    conn = _connect()
    candidates = []
    row = conn.execute(
        'SELECT id, game_date, winner1, winner2, loser1, loser2, winner_score, loser_score FROM games ORDER BY game_date DESC LIMIT 1'
    ).fetchone()
    if row:
        candidates.append(('doubles', row['game_date'],
                           f"{row['winner1']} & {row['winner2']} beat {row['loser1']} & {row['loser2']} {row['winner_score']}-{row['loser_score']}"))
    row = conn.execute(
        'SELECT id, game_date, winner, loser, winner_score, loser_score FROM vollis_games ORDER BY game_date DESC LIMIT 1'
    ).fetchone()
    if row:
        candidates.append(('vollis', row['game_date'],
                           f"{row['winner']} beat {row['loser']} {row['winner_score']}-{row['loser_score']}"))
    row = conn.execute(
        'SELECT id, game_date, game_name, winner1, loser1 FROM other_games ORDER BY game_date DESC LIMIT 1'
    ).fetchone()
    if row:
        candidates.append(('other', row['game_date'],
                           f"{row['game_name']}: {row['winner1']} beat {row['loser1']}"))
    conn.close()
    if not candidates:
        return None
    candidates.sort(key=lambda c: str(c[1] or ''), reverse=True)
    kind, game_date, summary = candidates[0]
    return {'kind': kind, 'game_date': game_date, 'summary': summary}


# --- AI prompt log (saved summary generations for admin review) ---

def init_ai_prompt_log_db():
    conn = _connect()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ai_prompt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            username TEXT NOT NULL,
            game_type TEXT NOT NULL,
            prompt_style TEXT,
            custom_prompt TEXT,
            game_ids_json TEXT,
            prompt_text TEXT NOT NULL,
            summary_text TEXT,
            image_prompt_text TEXT,
            subject TEXT,
            hero_image_url TEXT,
            hero_image_error TEXT
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_ai_prompt_log_created ON ai_prompt_log(created_at DESC)'
    )
    try:
        conn.execute('ALTER TABLE ai_prompt_log ADD COLUMN image_prompt_text TEXT')
    except sqlite3.OperationalError as e:
        if 'duplicate column' not in str(e).lower():
            raise
    try:
        conn.execute('ALTER TABLE ai_prompt_log ADD COLUMN solo_images_json TEXT')
    except sqlite3.OperationalError as e:
        if 'duplicate column' not in str(e).lower():
            raise
    conn.commit()
    conn.close()


def insert_ai_prompt_log(username, game_type, prompt_style, custom_prompt, game_ids,
                         prompt_text, summary_text, subject=None,
                         hero_image_url=None, hero_image_error=None,
                         image_prompt_text=None, solo_images_json=None):
    conn = _connect()
    conn.execute('''
        INSERT INTO ai_prompt_log (
            username, game_type, prompt_style, custom_prompt, game_ids_json,
            prompt_text, summary_text, image_prompt_text, subject,
            hero_image_url, hero_image_error, solo_images_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        username, game_type, prompt_style or '', custom_prompt or '',
        json.dumps(list(game_ids), default=str) if game_ids else '[]',
        prompt_text, summary_text or '', image_prompt_text or '', subject or '',
        hero_image_url or '', hero_image_error or '', solo_images_json or '',
    ))
    conn.commit()
    conn.close()


def get_ai_prompt_log_page(page=1, per_page=25):
    offset = (max(page, 1) - 1) * per_page
    conn = _connect()
    total = conn.execute('SELECT COUNT(*) FROM ai_prompt_log').fetchone()[0]
    rows = conn.execute('''
        SELECT id, created_at, username, game_type, prompt_style, custom_prompt,
               game_ids_json, prompt_text, summary_text, image_prompt_text, subject,
               hero_image_url, hero_image_error, solo_images_json
        FROM ai_prompt_log ORDER BY id DESC LIMIT ? OFFSET ?
    ''', (per_page, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


# --- Published AI recap pages (shareable links) ---

def init_ai_recap_pages_db():
    conn = _connect()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ai_recap_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            share_id TEXT NOT NULL UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            username TEXT NOT NULL,
            game_type TEXT NOT NULL,
            prompt_style TEXT,
            subject TEXT,
            html_body TEXT NOT NULL,
            plain_text_body TEXT,
            hero_image_url TEXT,
            hero_image_error TEXT,
            game_ids_json TEXT,
            solo_images_json TEXT
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_ai_recap_pages_share_id ON ai_recap_pages(share_id)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_ai_recap_pages_created ON ai_recap_pages(created_at DESC)'
    )
    conn.commit()
    conn.close()


def insert_ai_recap_page(share_id, username, game_type, html_body, subject='',
                         plain_text_body='', hero_image_url='', hero_image_error='',
                         game_ids_json='[]', prompt_style='', solo_images_json='',
                         image_details='', image_mode='none', custom_prompt='',
                         style_instructions='', scene_prompt=''):
    """Persist a published recap to disk (no SQLite — avoids db disk I/O errors)."""
    safe_id = _safe_recap_share_id(share_id)
    write_recap_html_file(safe_id, html_body)
    _write_json_atomic(_recap_meta_path(safe_id), {
        'share_id': safe_id,
        'created_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
        'username': username,
        'game_type': game_type,
        'prompt_style': prompt_style or '',
        'custom_prompt': custom_prompt or '',
        'style_instructions': style_instructions or custom_prompt or '',
        'subject': subject or '',
        'plain_text_body': plain_text_body or '',
        'hero_image_url': hero_image_url or '',
        'hero_image_error': hero_image_error or '',
        'game_ids_json': game_ids_json or '[]',
        'solo_images_json': solo_images_json or '',
        'image_details': image_details or '',
        'image_mode': image_mode or 'none',
        'scene_prompt': scene_prompt or '',
    })


def get_ai_recap_page(share_id):
    try:
        safe_id = _safe_recap_share_id(share_id)
    except ValueError:
        return None

    meta = _read_recap_meta_file(safe_id)
    if meta:
        file_html = read_recap_html_file(safe_id)
        meta['html_body'] = file_html if file_html is not None else ''
        return meta

    conn = _connect()
    try:
        row = conn.execute('''
            SELECT share_id, created_at, username, game_type, prompt_style, subject,
                   html_body, plain_text_body, hero_image_url, hero_image_error,
                   game_ids_json, solo_images_json
            FROM ai_recap_pages WHERE share_id = ?
        ''', (safe_id,)).fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        conn.close()
    if row:
        data = dict(row)
        file_html = read_recap_html_file(safe_id)
        if file_html is not None:
            data['html_body'] = file_html
        return data

    # Oldest publishes may only have an HTML file on disk.
    file_html = read_recap_html_file(safe_id)
    if file_html is None:
        return None
    try:
        mtime = os.path.getmtime(_recap_html_path(safe_id))
        created_at = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime(
            '%Y-%m-%d %H:%M:%S'
        )
    except OSError:
        created_at = ''
    return {
        'share_id': safe_id,
        'created_at': created_at,
        'username': '',
        'game_type': 'doubles',
        'prompt_style': '',
        'subject': 'Game Recap',
        'html_body': file_html,
        'plain_text_body': '',
        'hero_image_url': extract_recap_hero_image_url(file_html),
        'hero_image_error': '',
        'game_ids_json': '[]',
        'solo_images_json': '',
    }


def _is_usable_hero_image_url(url):
    """True when url can be used as a public WhatsApp/Open Graph image."""
    value = (url or '').strip()
    if not value:
        return False
    if value.startswith('cid:'):
        return False
    if value.startswith('https://') or value.startswith('http://'):
        return '/static/email_images/' in value or value.lower().endswith(
            ('.png', '.jpg', '.jpeg', '.gif', '.webp')
        )
    if value.startswith('/static/email_images/'):
        return True
    return False


# Bump when OG/thumbnail plumbing changes so WhatsApp re-scrapes old share URLs.
RECAP_SHARE_PREVIEW_VERSION = '2'


def recap_share_preview_token(hero_image_url=''):
    """Token for share URLs so WhatsApp/Facebook re-scrape after image changes.

    Derived from the hero filename so uploads/remakes automatically get a new
    share link (and thus a fresh link preview).
    """
    import re

    url = (hero_image_url or '').strip()
    if not url:
        return '0'
    filename = url.rstrip('/').split('/')[-1].split('?')[0]
    stem = os.path.splitext(filename)[0]
    safe = re.sub(r'[^A-Za-z0-9_-]', '', stem)[:24]
    return safe or '1'


def recap_share_query_args(hero_image_url=''):
    """Query args for a shareable recap URL (image token + OG version)."""
    return {
        'm': recap_share_preview_token(hero_image_url),
        't': RECAP_SHARE_PREVIEW_VERSION,
    }


def absolutize_hero_image_url(hero_image_url, site_base=''):
    """Return an https absolute hero URL suitable for Open Graph tags."""
    url = (hero_image_url or '').strip()
    if not url:
        return ''
    base = (site_base or '').rstrip('/')
    if url.startswith('/'):
        url = (base + url) if base else url
    elif url.startswith('http://'):
        url = 'https://' + url[len('http://'):]
    return url


def og_image_mime_type(hero_image_url=''):
    """Best-effort image MIME type for og:image:type."""
    path = (hero_image_url or '').split('?', 1)[0].lower()
    if path.endswith('.jpg') or path.endswith('.jpeg'):
        return 'image/jpeg'
    if path.endswith('.gif'):
        return 'image/gif'
    if path.endswith('.webp'):
        return 'image/webp'
    if path.endswith('.png'):
        return 'image/png'
    return ''


def extract_recap_hero_image_url(html_body):
    """Best-effort hero image URL from published recap HTML (for OG / admin thumbs)."""
    import re

    if not html_body:
        return ''

    hero_match = re.search(
        r'class=["\'][^"\']*hero-image-card[^"\']*["\'][\s\S]{0,1200}?<img[^>]+src=["\']([^"\']+)["\']',
        html_body,
        re.I,
    )
    if hero_match:
        candidate = (hero_match.group(1) or '').strip()
        if _is_usable_hero_image_url(candidate):
            return candidate

    for match in re.finditer(
        r'(https?://[^\s"\']+/static/email_images/([A-Za-z0-9._-]+)|/static/email_images/([A-Za-z0-9._-]+))',
        html_body,
    ):
        filename = match.group(2) or match.group(3) or ''
        if filename.startswith('solo_'):
            continue
        candidate = (match.group(1) or '').strip()
        if _is_usable_hero_image_url(candidate):
            return candidate
    return ''


def ensure_recap_hero_image_url(share_id, row=None):
    """Return a usable hero URL, backfilling JSON meta when found in HTML."""
    try:
        safe_id = _safe_recap_share_id(share_id)
    except ValueError:
        return ''

    data = row
    if data is None:
        data = get_ai_recap_page(safe_id) or {}

    hero = (data.get('hero_image_url') or '').strip()
    if _is_usable_hero_image_url(hero):
        return hero

    hero = extract_recap_hero_image_url(data.get('html_body') or '')
    if not hero:
        hero = extract_recap_hero_image_url(read_recap_html_file(safe_id) or '')
    if not _is_usable_hero_image_url(hero):
        return ''

    try:
        update_ai_recap_page(safe_id, hero_image_url=hero)
    except (OSError, ValueError, TypeError):
        pass
    return hero


def delete_ai_recap_page(share_id):
    """Remove a published AI recap from disk (and legacy SQLite if present).

    Returns True if anything was deleted, False if the recap was not found.
    Illustration files in static/email_images/ are left alone (clean up via AI Images).
    """
    import shutil

    try:
        safe_id = _safe_recap_share_id(share_id)
    except ValueError:
        return False

    removed = False
    for path in (
        _recap_html_path(safe_id),
        _recap_meta_path(safe_id),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recaps', f'{safe_id}.html'),
    ):
        try:
            os.remove(path)
            removed = True
        except FileNotFoundError:
            pass
        except OSError:
            pass

    # Instagram carousel slides live in static/recaps/<share_id>/
    ig_dir = os.path.join(_recap_storage_dir(), safe_id)
    if os.path.isdir(ig_dir):
        try:
            shutil.rmtree(ig_dir)
            removed = True
        except OSError:
            pass

    conn = _connect()
    try:
        cur = conn.execute('DELETE FROM ai_recap_pages WHERE share_id = ?', (safe_id,))
        conn.commit()
        if cur.rowcount:
            removed = True
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

    return removed


def list_ai_recap_pages(page=1, per_page=25):
    """Return (page_entries, total) for all published AI recap pages, newest first."""
    page = max(int(page or 1), 1)
    per_page = max(int(per_page or 25), 1)
    entries_by_id = {}

    recap_dir = _recap_storage_dir()
    disk_ids = set()
    if os.path.isdir(recap_dir):
        for name in os.listdir(recap_dir):
            if name.endswith('.json') or name.endswith('.html'):
                disk_ids.add(name.rsplit('.', 1)[0])

    for share_id in disk_ids:
        try:
            meta = _read_recap_meta_file(share_id)
        except (OSError, json.JSONDecodeError, ValueError):
            meta = None
        if meta:
            sid = (meta.get('share_id') or share_id or '').strip()
            if not sid:
                continue
            hero = ensure_recap_hero_image_url(sid, {
                **meta,
                'html_body': read_recap_html_file(sid) or '',
            })
            created_at = meta.get('created_at') or ''
            if not created_at:
                path = _recap_html_path(sid)
                if not os.path.isfile(path):
                    path = _recap_meta_path(sid)
                try:
                    created_at = datetime.fromtimestamp(
                        os.path.getmtime(path), tz=timezone.utc,
                    ).strftime('%Y-%m-%d %H:%M:%S')
                except OSError:
                    created_at = ''
            entries_by_id[sid] = {
                'share_id': sid,
                'created_at': created_at,
                'username': meta.get('username') or '',
                'game_type': meta.get('game_type') or '',
                'prompt_style': meta.get('prompt_style') or '',
                'subject': meta.get('subject') or '',
                'hero_image_url': hero,
                'hero_image_error': meta.get('hero_image_error') or '',
                'image_mode': meta.get('image_mode') or '',
            }
            continue

        # HTML on disk without JSON (older publishes): recover from SQLite or HTML alone.
        page_row = get_ai_recap_page(share_id)
        if not page_row:
            html = read_recap_html_file(share_id) or ''
            if not html:
                continue
            try:
                mtime = os.path.getmtime(_recap_html_path(share_id))
                created_at = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime(
                    '%Y-%m-%d %H:%M:%S'
                )
            except OSError:
                created_at = ''
            page_row = {
                'share_id': share_id,
                'created_at': created_at,
                'username': '',
                'game_type': '',
                'prompt_style': '',
                'subject': 'Game Recap',
                'html_body': html,
                'hero_image_url': '',
                'hero_image_error': '',
            }
        sid = (page_row.get('share_id') or share_id).strip()
        hero = ensure_recap_hero_image_url(sid, page_row)
        entries_by_id[sid] = {
            'share_id': sid,
            'created_at': page_row.get('created_at') or '',
            'username': page_row.get('username') or '',
            'game_type': page_row.get('game_type') or '',
            'prompt_style': page_row.get('prompt_style') or '',
            'subject': page_row.get('subject') or '',
            'hero_image_url': hero,
            'hero_image_error': page_row.get('hero_image_error') or '',
            'image_mode': page_row.get('image_mode') or '',
        }

    conn = _connect()
    try:
        rows = conn.execute('''
            SELECT share_id, created_at, username, game_type, prompt_style, subject,
                   hero_image_url, hero_image_error, html_body
            FROM ai_recap_pages
            ORDER BY created_at DESC
        ''').fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()

    for row in rows:
        sid = (row['share_id'] or '').strip()
        if not sid or sid in entries_by_id:
            continue
        hero = ensure_recap_hero_image_url(sid, dict(row))
        entries_by_id[sid] = {
            'share_id': sid,
            'created_at': row['created_at'] or '',
            'username': row['username'] or '',
            'game_type': row['game_type'] or '',
            'prompt_style': row['prompt_style'] or '',
            'subject': row['subject'] or '',
            'hero_image_url': hero,
            'hero_image_error': row['hero_image_error'] or '',
            'image_mode': '',
        }

    pages = list(entries_by_id.values())
    pages.sort(key=lambda item: item.get('created_at') or '', reverse=True)
    total = len(pages)
    start = (page - 1) * per_page
    return pages[start:start + per_page], total


# --- AI illustration files (static/email_images) ---

_AI_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}


def email_images_dir():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'email_images')
    os.makedirs(path, exist_ok=True)
    return path


def _format_bytes(num_bytes):
    size = float(num_bytes or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            if unit == 'B':
                return f'{int(size)} {unit}'
            return f'{size:.1f} {unit}'
        size /= 1024
    return f'{int(num_bytes or 0)} B'


def _email_image_filenames_from_text(text):
    """Extract email_images filenames mentioned in HTML/JSON/text."""
    import re
    if not text:
        return set()
    found = set()
    for match in re.finditer(r'/static/email_images/([A-Za-z0-9._-]+)', str(text)):
        found.add(match.group(1))
    for match in re.finditer(r'"([^"/\\]+\.(?:png|jpg|jpeg|gif|webp))"', str(text), re.I):
        name = match.group(1)
        # Only treat bare filenames as email images if they look like our uuid names
        if re.fullmatch(r'[0-9a-f]{16,}\.(?:png|jpg|jpeg|gif|webp)', name, re.I):
            found.add(name)
    # Keep WhatsApp OG JPEG previews paired with each hero image.
    for name in list(found):
        if name.startswith('og_') or name.startswith('solo_'):
            continue
        stem = name.rsplit('.', 1)[0]
        if stem:
            found.add(f'og_{stem}.jpg')
    return found


def referenced_email_image_filenames():
    """Filenames still referenced by published recaps or the AI prompt log."""
    referenced = set()
    recap_dir = _recap_storage_dir()
    if os.path.isdir(recap_dir):
        for name in os.listdir(recap_dir):
            path = os.path.join(recap_dir, name)
            if not os.path.isfile(path):
                continue
            if not (name.endswith('.html') or name.endswith('.json')):
                continue
            try:
                with open(path, encoding='utf-8') as handle:
                    referenced |= _email_image_filenames_from_text(handle.read())
            except OSError:
                continue

    legacy_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recaps')
    if os.path.isdir(legacy_dir):
        for name in os.listdir(legacy_dir):
            path = os.path.join(legacy_dir, name)
            if not os.path.isfile(path):
                continue
            if not (name.endswith('.html') or name.endswith('.json')):
                continue
            try:
                with open(path, encoding='utf-8') as handle:
                    referenced |= _email_image_filenames_from_text(handle.read())
            except OSError:
                continue

    conn = _connect()
    try:
        rows = conn.execute('''
            SELECT hero_image_url, solo_images_json
            FROM ai_prompt_log
            WHERE hero_image_url IS NOT NULL AND hero_image_url != ''
               OR solo_images_json IS NOT NULL AND solo_images_json != ''
        ''').fetchall()
        for row in rows:
            referenced |= _email_image_filenames_from_text(row['hero_image_url'])
            referenced |= _email_image_filenames_from_text(row['solo_images_json'])
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
    return referenced


def list_ai_email_images():
    """List AI illustration files with size/date and whether a recap still uses them."""
    directory = email_images_dir()
    referenced = referenced_email_image_filenames()
    images = []
    total_bytes = 0
    for name in os.listdir(directory):
        if name.startswith('.'):
            continue
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in _AI_IMAGE_EXTENSIONS:
            continue
        try:
            stat = os.stat(path)
        except OSError:
            continue
        total_bytes += stat.st_size
        is_solo = name.startswith('solo_')
        images.append({
            'filename': name,
            'path': path,
            'url': f'/static/email_images/{name}',
            'size_bytes': stat.st_size,
            'size_label': _format_bytes(stat.st_size),
            'mtime': stat.st_mtime,
            'mtime_label': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime('%Y-%m-%d %H:%M'),
            # Solo caricatures are temporary creator previews; don't treat as
            # permanently "in use" so unused cleanup can remove them.
            'in_use': (name in referenced) and not is_solo,
            'is_solo': is_solo,
        })
    images.sort(key=lambda item: item['mtime'], reverse=True)
    unused_bytes = sum(item['size_bytes'] for item in images if not item['in_use'])
    return {
        'images': images,
        'count': len(images),
        'total_bytes': total_bytes,
        'total_label': _format_bytes(total_bytes),
        'unused_count': sum(1 for item in images if not item['in_use']),
        'unused_bytes': unused_bytes,
        'unused_label': _format_bytes(unused_bytes),
    }


def delete_ai_email_images(filenames, allow_in_use=True):
    """Delete selected AI illustration files. Returns (deleted, missing, blocked)."""
    directory = email_images_dir()
    referenced = referenced_email_image_filenames() if not allow_in_use else set()
    deleted = []
    missing = []
    blocked = []
    for raw in filenames or []:
        name = os.path.basename(str(raw or '').strip())
        if not name or name.startswith('.'):
            continue
        if os.path.splitext(name)[1].lower() not in _AI_IMAGE_EXTENSIONS:
            continue
        if name in referenced:
            blocked.append(name)
            continue
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            missing.append(name)
            continue
        try:
            os.remove(path)
            deleted.append(name)
        except OSError:
            missing.append(name)
    return deleted, missing, blocked
