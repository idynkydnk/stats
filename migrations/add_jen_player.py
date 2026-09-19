"""Create Jen's player profile and link her login once, without resetting edits."""
MIGRATION_ID = '2026-09-19-link-jen-weston'


def migrate(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS site_account_migrations (id TEXT PRIMARY KEY)')
    if conn.execute('SELECT 1 FROM site_account_migrations WHERE id=?', (MIGRATION_ID,)).fetchone():
        return
    row = conn.execute("SELECT full_name FROM players WHERE full_name = ? COLLATE NOCASE", ('Jen Weston',)).fetchone()
    if row:
        name = row[0]
    else:
        name = 'Jen Weston'
        conn.execute('INSERT INTO players (full_name, created_at, updated_at) VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)', (name,))
    conn.execute("UPDATE site_users SET player_name=? WHERE lower(username)='jen'", (name,))
    conn.execute('INSERT INTO site_account_migrations (id) VALUES (?)', (MIGRATION_ID,))
