"""Durable, one-hour debounce for automatic recap subscriber emails."""
import json
import sqlite3
import time
from contextlib import contextmanager

import admin_functions as adminfx

DELAY_SECONDS = 60 * 60


@contextmanager
def _connection():
    conn = sqlite3.connect(adminfx.stats_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS recap_email_queue (
            share_id TEXT PRIMARY KEY,
            recap_key TEXT NOT NULL,
            due_at REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )''')
        with conn:
            yield conn
    finally:
        conn.close()


def schedule(share_id, username, game_type, game_ids):
    """Replace an unsent recap for the same creator, sport, and set of games."""
    ids = sorted({str(value) for value in game_ids or []})
    key = json.dumps([username, game_type, ids or [share_id]])
    with _connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute("UPDATE recap_email_queue SET status = 'superseded' "
                     "WHERE recap_key = ? AND status = 'pending'", (key,))
        conn.execute('''INSERT INTO recap_email_queue (share_id, recap_key, due_at)
                        VALUES (?, ?, ?)''', (share_id, key, time.time() + DELAY_SECONDS))


@contextmanager
def updating(share_id):
    """Keep a worker from claiming a recap while its saved content is changing.

    Only pending mail is postponed: editing old or already emailed recaps must
    never schedule another email. Roll back the timer if saving fails.
    """
    with _connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        yield
        conn.execute("UPDATE recap_email_queue SET due_at = ? "
                     "WHERE share_id = ? AND status = 'pending'",
                     (time.time() + DELAY_SECONDS, share_id))


def claim_due():
    """Claim once across worker processes; never replay an uncertain SMTP send."""
    with _connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute("SELECT share_id FROM recap_email_queue "
                           "WHERE status = 'pending' AND due_at <= ? "
                           "ORDER BY due_at LIMIT 1", (time.time(),)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE recap_email_queue SET status = 'sending' WHERE share_id = ?",
                     (row['share_id'],))
        return row['share_id']


def finish(share_id, status):
    with _connection() as conn:
        conn.execute("UPDATE recap_email_queue SET status = ? "
                     "WHERE share_id = ? AND status = 'sending'", (status, share_id))
