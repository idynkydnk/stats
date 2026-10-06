"""Enable the current group's sources once, without enrolling future sign-ups."""

MIGRATION = 'enable-existing-stats-sources-v1'


def migrate(conn):
    # The caller holds a write transaction so concurrent startup workers cannot
    # capture different groups or reset a preference saved after the rollout.
    conn.execute('''CREATE TABLE IF NOT EXISTS stats_source_rollouts (
        name TEXT PRIMARY KEY, completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS stats_source_group (
        username TEXT PRIMARY KEY COLLATE NOCASE
    )''')
    if conn.execute('SELECT 1 FROM stats_source_rollouts WHERE name=?', (MIGRATION,)).fetchone():
        return
    conn.execute('INSERT INTO stats_source_group SELECT username FROM site_users WHERE active=1')
    conn.execute('''INSERT INTO account_stats_sources (viewer, owner, enabled)
        SELECT viewer.username, owner.username, 1
        FROM stats_source_group viewer CROSS JOIN stats_source_group owner
        WHERE viewer.username != owner.username
        ON CONFLICT(viewer, owner) DO UPDATE SET enabled=1''')
    conn.execute('''UPDATE private_accounts SET show_starter_stats=1, share_stats=1
        WHERE username IN (SELECT username FROM stats_source_group)''')
    conn.execute('INSERT INTO stats_source_rollouts (name) VALUES (?)', (MIGRATION,))
