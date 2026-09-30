"""Public subscriptions to future AI recap emails."""
import re
import sqlite3
from contextlib import contextmanager

import admin_functions as adminfx


@contextmanager
def _connection():
    conn = sqlite3.connect(adminfx.stats_db_path(), timeout=30)
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS ai_recap_subscriptions (
            email TEXT PRIMARY KEY COLLATE NOCASE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        with conn:
            yield conn
    finally:
        conn.close()


def subscribe(email):
    email = (email or '').strip().lower()
    if len(email) > 254 or not re.fullmatch(r'[^@\s<>;,]+@[^@\s<>;,]+\.[^@\s<>;,]+', email):
        raise ValueError('Enter a valid email address.')
    with _connection() as conn:
        conn.execute('INSERT OR IGNORE INTO ai_recap_subscriptions (email) VALUES (?)', (email,))


def unsubscribe(email):
    with _connection() as conn:
        conn.execute('DELETE FROM ai_recap_subscriptions WHERE email = ?', ((email or '').strip(),))


def recipients(existing):
    """Add subscribers once, even when they also played in the games."""
    with _connection() as conn:
        subscribed = [row[0] for row in conn.execute('SELECT email FROM ai_recap_subscriptions ORDER BY email')]
    result = []
    seen = set()
    for address in list(existing) + subscribed:
        address = address.strip()
        if address and address.casefold() not in seen:
            seen.add(address.casefold())
            result.append(address)
    return result
