"""SQLite queue for tap-and-walk-away AI summary email jobs."""
import json
import os
import sqlite3
from datetime import datetime, timezone


def stats_db_path():
    path = '/home/Idynkydnk/stats/stats.db'
    if os.path.exists(path):
        return path
    return 'stats.db'


def _connect():
    conn = sqlite3.connect(stats_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn, table, column, col_def):
    cols = {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}
    if column not in cols:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_def}')


def init_ai_auto_send_jobs_db():
    conn = _connect()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ai_auto_send_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            username TEXT NOT NULL,
            game_type TEXT NOT NULL,
            game_ids_json TEXT NOT NULL,
            prompt_style TEXT NOT NULL,
            custom_prompt TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            result_summary TEXT,
            error TEXT,
            emails_sent INTEGER,
            started_at DATETIME,
            completed_at DATETIME
        )
    ''')
    _ensure_column(conn, 'ai_auto_send_jobs', 'image_mode', "TEXT DEFAULT 'none'")
    _ensure_column(conn, 'ai_auto_send_jobs', 'image_details', 'TEXT')
    _ensure_column(conn, 'ai_auto_send_jobs', 'illustration_players_json', 'TEXT')
    _ensure_column(conn, 'ai_auto_send_jobs', 'share_id', 'TEXT')
    _ensure_column(conn, 'ai_auto_send_jobs', 'job_type', "TEXT DEFAULT 'recap'")
    _ensure_column(conn, 'ai_auto_send_jobs', 'payload_json', 'TEXT')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_ai_auto_send_jobs_status '
        'ON ai_auto_send_jobs(status, id)'
    )
    conn.commit()
    conn.close()


def enqueue_job(
    username, game_ids, game_type, prompt_style, custom_prompt='',
    image_mode='none', image_details='', illustration_players=None,
):
    init_ai_auto_send_jobs_db()
    conn = _connect()
    game_ids_json = json.dumps([str(g) for g in game_ids])
    # Reuse an in-flight identical job so double-clicks don't publish twice.
    existing = conn.execute('''
        SELECT id FROM ai_auto_send_jobs
        WHERE username = ?
          AND game_type = ?
          AND game_ids_json = ?
          AND prompt_style = ?
          AND COALESCE(custom_prompt, '') = ?
          AND COALESCE(image_mode, 'none') = ?
          AND COALESCE(image_details, '') = ?
          AND COALESCE(job_type, 'recap') = 'recap'
          AND status IN ('pending', 'running')
        ORDER BY id DESC
        LIMIT 1
    ''', (
        username,
        game_type,
        game_ids_json,
        prompt_style,
        custom_prompt or '',
        image_mode or 'none',
        image_details or '',
    )).fetchone()
    if existing:
        job_id = existing['id']
        conn.close()
        return job_id

    players_json = json.dumps(list(illustration_players or []), default=str)
    cur = conn.execute('''
        INSERT INTO ai_auto_send_jobs
            (username, game_type, game_ids_json, prompt_style, custom_prompt,
             image_mode, image_details, illustration_players_json, job_type, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'recap', 'pending')
    ''', (
        username,
        game_type,
        game_ids_json,
        prompt_style,
        custom_prompt or '',
        image_mode or 'none',
        image_details or '',
        players_json,
    ))
    job_id = cur.lastrowid
    conn.commit()
    conn.close()
    return job_id


def enqueue_flyer_job(username, payload):
    """Queue a Create Flyer generation job. payload is a dict of flyer form fields."""
    init_ai_auto_send_jobs_db()
    conn = _connect()
    cur = conn.execute('''
        INSERT INTO ai_auto_send_jobs
            (username, game_type, game_ids_json, prompt_style, custom_prompt,
             image_mode, image_details, illustration_players_json, job_type,
             payload_json, status)
        VALUES (?, ?, '[]', 'flyer', '', 'image', '', '[]', 'flyer', ?, 'pending')
    ''', (
        username,
        (payload or {}).get('game_type') or 'doubles',
        json.dumps(payload or {}, default=str),
    ))
    job_id = cur.lastrowid
    conn.commit()
    conn.close()
    return job_id


def enqueue_player_ai_image_job(username, player_name):
    """Queue generation of a saved AI character sheet for one player."""
    init_ai_auto_send_jobs_db()
    name = (player_name or '').strip()
    payload = json.dumps({'player_name': name}, default=str)
    conn = _connect()
    existing = conn.execute('''
        SELECT id FROM ai_auto_send_jobs
        WHERE COALESCE(job_type, '') = 'player_ai_image'
          AND payload_json = ?
          AND status IN ('pending', 'running')
        ORDER BY id DESC
        LIMIT 1
    ''', (payload,)).fetchone()
    if existing:
        job_id = existing['id']
        conn.close()
        return job_id

    cur = conn.execute('''
        INSERT INTO ai_auto_send_jobs
            (username, game_type, game_ids_json, prompt_style, custom_prompt,
             image_mode, image_details, illustration_players_json, job_type,
             payload_json, status)
        VALUES (?, 'player', '[]', 'player_ai_image', ?, 'image', '', '[]',
                'player_ai_image', ?, 'pending')
    ''', (
        username,
        name,
        payload,
    ))
    job_id = cur.lastrowid
    conn.commit()
    conn.close()
    return job_id


def claim_next_pending_job():
    """Atomically take the oldest pending job for processing."""
    init_ai_auto_send_jobs_db()
    conn = _connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('''
            SELECT id, username, game_type, game_ids_json, prompt_style, custom_prompt,
                   image_mode, image_details, illustration_players_json,
                   job_type, payload_json
            FROM ai_auto_send_jobs
            WHERE status = 'pending'
            ORDER BY id ASC
            LIMIT 1
        ''').fetchone()
        if not row:
            conn.rollback()
            return None
        updated = conn.execute('''
            UPDATE ai_auto_send_jobs
            SET status = 'running', started_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
        ''', (row['id'],)).rowcount
        if not updated:
            conn.rollback()
            return None
        conn.commit()
        job = dict(row)
        try:
            job['game_ids'] = json.loads(job.pop('game_ids_json') or '[]')
        except (json.JSONDecodeError, TypeError):
            job.pop('game_ids_json', None)
            job['game_ids'] = []
        job['image_mode'] = job.get('image_mode') or 'none'
        job['image_details'] = job.get('image_details') or ''
        job['job_type'] = (job.get('job_type') or 'recap').strip() or 'recap'
        try:
            job['payload'] = json.loads(job.pop('payload_json') or '{}')
        except (json.JSONDecodeError, TypeError):
            job.pop('payload_json', None)
            job['payload'] = {}
        if not isinstance(job['payload'], dict):
            job['payload'] = {}
        try:
            job['illustration_players'] = json.loads(
                job.pop('illustration_players_json') or '[]'
            )
        except (json.JSONDecodeError, TypeError):
            job.pop('illustration_players_json', None)
            job['illustration_players'] = []
        return job
    finally:
        conn.close()


def complete_job(
    job_id, success, emails_sent=0, result_summary=None, error=None, share_id=None,
):
    conn = _connect()
    conn.execute('''
        UPDATE ai_auto_send_jobs
        SET status = ?, emails_sent = ?, result_summary = ?, error = ?,
            share_id = COALESCE(?, share_id),
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (
        'completed' if success else 'failed',
        emails_sent,
        result_summary,
        error,
        share_id,
        job_id,
    ))
    conn.commit()
    conn.close()


def reset_running_jobs():
    """Re-queue every running job. Call on daemon startup — nothing can still be in-flight."""
    conn = _connect()
    cur = conn.execute('''
        UPDATE ai_auto_send_jobs
        SET status = 'pending', started_at = NULL
        WHERE status = 'running'
    ''')
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def reset_stale_running_jobs(max_age_minutes=20):
    """Re-queue jobs stuck in running (e.g. hung mid-process without a daemon restart)."""
    conn = _connect()
    cur = conn.execute('''
        UPDATE ai_auto_send_jobs
        SET status = 'pending', started_at = NULL
        WHERE status = 'running'
          AND started_at IS NOT NULL
          AND started_at < datetime('now', ? || ' minutes')
    ''', (f'-{int(max_age_minutes)}',))
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def get_job(job_id):
    conn = _connect()
    row = conn.execute('SELECT * FROM ai_auto_send_jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def job_public_dict(row):
    """JSON-safe job row for admin lists and APIs."""
    d = dict(row) if row else {}
    job_type = (d.get('job_type') or 'recap').strip() or 'recap'
    return {
        'id': d.get('id'),
        'created_at': d.get('created_at'),
        'started_at': d.get('started_at'),
        'completed_at': d.get('completed_at'),
        'username': d.get('username') or '',
        'job_type': job_type,
        'status': d.get('status') or '',
        'game_type': d.get('game_type') or '',
        'prompt_style': d.get('prompt_style') or '',
        'share_id': (d.get('share_id') or '').strip(),
        'result_summary': d.get('result_summary') or '',
        'error': d.get('error') or '',
    }


def list_jobs(page=1, per_page=25, job_type=None, username=None, status=None):
    """Return (page_jobs, total) newest first."""
    init_ai_auto_send_jobs_db()
    page = max(int(page or 1), 1)
    per_page = max(int(per_page or 25), 1)
    offset = (page - 1) * per_page
    clauses = []
    params = []
    if job_type:
        clauses.append("COALESCE(job_type, 'recap') = ?")
        params.append(job_type.strip())
    if username:
        clauses.append('lower(username) = lower(?)')
        params.append(username.strip())
    if status:
        clauses.append('status = ?')
        params.append(status.strip())
    where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
    conn = _connect()
    total = conn.execute(f'SELECT COUNT(*) FROM ai_auto_send_jobs {where}', params).fetchone()[0]
    rows = conn.execute(f'''
        SELECT id, created_at, started_at, completed_at, username, job_type, status,
               game_type, prompt_style, share_id, result_summary, error
        FROM ai_auto_send_jobs {where}
        ORDER BY id DESC LIMIT ? OFFSET ?
    ''', (*params, per_page, offset)).fetchall()
    conn.close()
    return [job_public_dict(r) for r in rows], total


def list_jobs_with_share_ids(job_type=None):
    """Jobs that recorded a published share_id (used to backfill recap/flyer lists)."""
    init_ai_auto_send_jobs_db()
    clauses = ["share_id IS NOT NULL", "trim(share_id) != ''"]
    params = []
    if job_type:
        clauses.append("COALESCE(job_type, 'recap') = ?")
        params.append(job_type)
    where = ' AND '.join(clauses)
    conn = _connect()
    try:
        rows = conn.execute(f'''
            SELECT share_id, username, created_at, completed_at, game_type, prompt_style,
                   job_type, status
            FROM ai_auto_send_jobs
            WHERE {where}
            ORDER BY id DESC
        ''', params).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return [dict(r) for r in rows]


def daemon_heartbeat_path():
    root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, 'ai_auto_send_daemon.heartbeat')


def touch_daemon_heartbeat():
    path = daemon_heartbeat_path()
    with open(path, 'w', encoding='utf-8') as f:
        f.write(datetime.now(timezone.utc).isoformat())


def daemon_is_alive(max_age_seconds=90):
    path = daemon_heartbeat_path()
    try:
        with open(path, encoding='utf-8') as f:
            raw = f.read().strip()
        if not raw:
            return False
        ts = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age <= max_age_seconds
    except (OSError, ValueError):
        return False
