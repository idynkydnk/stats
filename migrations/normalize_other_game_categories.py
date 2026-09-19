"""Merge category spellings without deleting games or changing any other fields.

The original value is retained per game in the same transaction as the update.
Run against each environment's own database; never copy local data to production.
"""
from other_game_categories import canonical_other_category


def normalize_other_game_categories(conn):
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS other_category_migration_audit (
            game_id INTEGER PRIMARY KEY,
            original_category TEXT NOT NULL,
            canonical_category TEXT NOT NULL,
            changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        rows = conn.execute('SELECT * FROM other_games ORDER BY id').fetchall()
        columns = [r[1] for r in conn.execute('PRAGMA table_info(other_games)')]
        category_index = columns.index('game_type')
        id_index = columns.index('id')
        expected = []
        changed = 0
        for row in rows:
            values = list(row)
            old = values[category_index]
            new = canonical_other_category(old)
            if old != new:
                conn.execute('''INSERT OR IGNORE INTO other_category_migration_audit
                    (game_id, original_category, canonical_category) VALUES (?, ?, ?)''',
                    (values[id_index], old, new))
                conn.execute('UPDATE other_games SET game_type=? WHERE id=?',
                             (new, values[id_index]))
                values[category_index] = new
                changed += 1
            expected.append(tuple(values))
        actual = [tuple(row) for row in conn.execute('SELECT * FROM other_games ORDER BY id')]
        if actual != expected:
            raise RuntimeError('Category migration changed unexpected game data; rolling back')
        conn.commit()
        return changed
    except Exception:
        conn.rollback()
        raise
