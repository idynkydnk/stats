"""Account deletion, with per-account coordination across web and AI workers."""
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import threading
import time

_local = threading.local()


class AccountBusy(Exception):
    pass


def username_digest(username):
    return hashlib.sha256(username.casefold().encode()).hexdigest()


@contextmanager
def account_lock(site_path, username, *, exclusive=False, timeout=3):
    """Hold through a request/job so deletion cannot race its writes.

    Lock files contain no identity data and must not be unlinked: a waiter may
    already have an open descriptor for the same inode.
    """
    root = Path(site_path).resolve().parent / '.account-locks'
    root.mkdir(mode=0o700, exist_ok=True)
    path = str(root / username_digest(username))
    held = getattr(_local, 'held', None)
    if held is None:
        held = _local.held = {}
    if path in held:
        if exclusive and not held[path]:
            raise AccountBusy('Cannot delete during an active account operation.')
        yield
        return
    with open(path, 'a') as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise AccountBusy('A save or AI creation is finishing. Please try deleting your account again in a moment.')
                time.sleep(0.05)
        held[path] = exclusive
        try:
            yield
        finally:
            held.pop(path, None)
            fcntl.flock(handle, fcntl.LOCK_UN)


def _delete_matching(conn, table, column, value):
    columns = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
    if column in columns:
        conn.execute(f'DELETE FROM "{table}" WHERE "{column}"=? COLLATE NOCASE', (value,))


def delete_owned_media(site_path, username, account_id):
    """Use existing ownership-aware deletion and preserve other creators' images."""
    import admin_functions as admin
    import flyer_functions as flyers
    import player_functions as players
    from ai_library import library_lock, live_image_filenames
    from flask import g
    g.admin_database_path = site_path
    with library_lock():
        g.account_deletion_cleanup = True
        try:
            recaps, _ = admin.list_ai_recap_pages(username=username, per_page=2**31 - 1)
            flyer_rows, _ = flyers.list_flyer_pages(username=username, per_page=2**31 - 1)
        finally:
            g.pop('account_deletion_cleanup', None)
        image_candidates = set()
        for row in recaps:
            image_candidates |= admin._email_image_filenames_from_text(json.dumps(admin.get_ai_recap_page(row['share_id']) or row))
        for row in flyer_rows:
            image_candidates |= admin._email_image_filenames_from_text(json.dumps(flyers.get_flyer_page(row['share_id']) or row))
        recap_ids = {r['share_id'] for r in recaps}
        with sqlite3.connect(site_path) as conn:
            conn.row_factory = sqlite3.Row
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ('ai_prompt_log', 'ai_auto_send_jobs'):
                if table in tables:
                    for row in conn.execute(f'SELECT * FROM "{table}" WHERE username=? COLLATE NOCASE', (username,)):
                        image_candidates |= admin._email_image_filenames_from_text(json.dumps(dict(row)))
            if 'content_removal_work' in tables:
                # Moderation can remove metadata before an image unlink fails.
                # Carry its durable candidates into the account cleanup journal
                # before the identity transaction erases moderation work rows.
                for row in conn.execute('SELECT assets_json FROM content_removal_work WHERE author=? COLLATE NOCASE', (username,)):
                    image_candidates.update(json.loads(row[0]))
            prior = conn.execute('SELECT cleanup_json FROM account_deletion_work WHERE username=?', (username,)).fetchone()
            if prior:
                pending = json.loads(prior[0])
                image_candidates.update(pending.get('images', []))
                recap_ids.update(pending.get('recaps', []))
            conn.execute('INSERT OR REPLACE INTO account_deletion_work VALUES (?,?)',
                         (username, json.dumps({'images': sorted(image_candidates), 'recaps': sorted(recap_ids)})))
        # A sender holds content while sending. Keep the account retryable until
        # it finishes instead of reporting a deletion that left public content.
        with sqlite3.connect(site_path) as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='recap_email_queue'").fetchone():
                for row in recaps:
                    if conn.execute("SELECT 1 FROM recap_email_queue WHERE share_id=? AND status='sending'", (row['share_id'],)).fetchone():
                        raise AccountBusy('A recap email is finishing. Please try deleting your account again in a moment.')
        for row in recaps:
            if not admin.delete_ai_recap_page(row['share_id']):
                raise OSError('Could not remove a saved recap. Please retry account deletion.')
        for row in flyer_rows:
            if not flyers.delete_flyer_page(row['share_id']):
                raise OSError('Could not remove a saved flyer. Please retry account deletion.')
        # Ordinary library cleanup is best-effort. Account deletion must detect
        # a failed image unlink instead of silently declaring complete erasure.
        if image_candidates:
            for name in image_candidates - live_image_filenames():
                if Path(name).name != name:
                    raise ValueError('Invalid stored image filename')
                path = Path(admin.email_images_dir()) / name
                if path.suffix.lower() in admin._AI_IMAGE_EXTENSIONS:
                    path.unlink(missing_ok=True)
        # Private photo filenames are prefixed by the unguessable account ID.
        # Never follow links or use user-supplied paths to remove files.
        for path in Path(players.player_photos_dir()).glob(account_id + '_*'):
            if path.is_file() or path.is_symlink():
                path.unlink()
        return sorted(recap_ids)


def delete_identity_and_data(site_path, account, private_path, recap_ids):
    """Remove identifying records; keep only a hash preventing stale name reuse."""
    username = account['username']
    # Do this before identity removal: a filesystem failure leaves an account
    # that can retry cleanup. No account writer can run under the exclusive lock.
    for suffix in ('', '-wal', '-shm', '-journal'):
        Path(str(private_path) + suffix).unlink(missing_ok=True)
    purge_stats_caches(site_path)
    with sqlite3.connect(site_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA secure_delete=ON')
        conn.execute('BEGIN IMMEDIATE')
        user = conn.execute('SELECT * FROM site_users WHERE username=? COLLATE NOCASE', (username,)).fetchone()
        email = dict(user).get('login_email') if user else None
        for table, column in (
            ('auth_tokens', 'username'), ('passkey_credentials', 'username'),
            ('passkey_users', 'username'), ('passkey_challenges', 'username'),
            ('web_login_events', 'username'), ('web_email_codes', 'link_username'),
            ('activity_log', 'username'), ('user_actions', 'username'),
            ('ai_prompt_log', 'username'),
            ('user_actions_log', 'username'), ('ai_auto_send_jobs', 'username'),
            ('stats_source_group', 'username'), ('account_stats_sources', 'viewer'),
            ('account_stats_sources', 'owner'), ('apple_account_tokens', 'username'),
            ('account_deletion_work', 'username'),
            ('seasons', 'owner'),
        ):
            _delete_matching(conn, table, column, username)
        if email:
            for table, column in (('web_email_codes', 'email'), ('ai_recap_subscriptions', 'email')):
                _delete_matching(conn, table, column, email)
            from flask import current_app
            key = current_app.secret_key
            key = key.encode() if isinstance(key, str) else key
            for kind in ('email', 'wrong_email'):
                digest = hmac.new(key, (kind + ':' + email).encode(), hashlib.sha256).hexdigest()
                _delete_matching(conn, 'web_login_events', 'key_hash', digest)
        for share_id in recap_ids:
            _delete_matching(conn, 'recap_email_queue', 'share_id', share_id)
        from content_safety import delete_account_safety_data
        delete_account_safety_data(conn, username)
        conn.execute('INSERT OR IGNORE INTO private_deleted_accounts VALUES (?)', (username_digest(username),))
        conn.execute('DELETE FROM private_accounts WHERE id=?', (account['id'],))
        conn.execute('DELETE FROM site_users WHERE username=? COLLATE NOCASE', (username,))


def purge_stats_caches(site_path):
    """Discard derived cache copies which may contain the deleted user's games."""
    from flask import current_app
    from stats_response_cache import local_cache_directory
    root = Path(current_app.config.get('STATS_RESPONSE_CACHE_DIR') or
                os.environ.get('STATS_RESPONSE_CACHE_DIR') or
                local_cache_directory(site_path, current_app.secret_key))
    responses = root / 'responses.db'
    if responses.exists():
        with sqlite3.connect(responses, timeout=10) as conn:
            conn.execute('PRAGMA secure_delete=ON')
            conn.execute('DELETE FROM responses')
    snapshots = root / 'snapshots'
    if snapshots.exists():
        with open(snapshots / 'build.lock', 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            for path in snapshots.glob('*.db'):
                path.unlink(missing_ok=True)
