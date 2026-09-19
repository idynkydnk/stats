"""One-time provisioning of the requested Jen login during deployment.

Only the generated password hash is stored here. Existing accounts, including
changed passwords and inactive accounts, are never overwritten or reactivated.
A completed migration will not recreate an account that was later deleted.
"""

MIGRATION_ID = '2026-09-19-create-jen'
INITIAL_PASSWORD_HASH = 'pbkdf2:sha256:260000$iWi0NygdH5Ic1uLC$28d6c1fdfcb074f523f9f5b2526ac06e3c60de6db7c544eb6dcde49257490551'


def migrate(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS site_account_migrations (id TEXT PRIMARY KEY)')
    if conn.execute('SELECT 1 FROM site_account_migrations WHERE id = ?', (MIGRATION_ID,)).fetchone():
        return
    conn.execute(
        "INSERT INTO site_users (username, password_hash, is_admin) "
        "SELECT ?, ?, 0 WHERE NOT EXISTS (SELECT 1 FROM site_users WHERE lower(username) = 'jen')",
        ('Jen', INITIAL_PASSWORD_HASH),
    )
    conn.execute('INSERT INTO site_account_migrations (id) VALUES (?)', (MIGRATION_ID,))
