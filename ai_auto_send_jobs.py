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
    players_json = json.dumps(list(illustration_players or []), default=str)
    cur = conn.execute('''
        INSERT INTO ai_auto_send_jobs
            (username, game_type, game_ids_json, prompt_style, custom_prompt,
             image_mode, image_details, illustration_players_json, job_type, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'recap', 'pending')
    ''', (
        username,
        game_type,
        json.dumps([str(g) for g in game_ids]),
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


def reset_stale_running_jobs(max_age_minutes=20):
    """Re-queue jobs stuck in running (e.g. after a daemon crash)."""
    conn = _connect()
    conn.execute('''
        UPDATE ai_auto_send_jobs
        SET status = 'pending', started_at = NULL
        WHERE status = 'running'
          AND started_at IS NOT NULL
          AND started_at < datetime('now', ? || ' minutes')
    ''', (f'-{int(max_age_minutes)}',))
    conn.commit()
    conn.close()


def get_job(job_id):
    conn = _connect()
    row = conn.execute('SELECT * FROM ai_auto_send_jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


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
