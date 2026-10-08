"""Retention and favorites for published recaps and flyers.

Protected items count toward the target but are never automatically removed.
Cleanup only runs after a successful publish, never during a browse or deploy.
"""
from contextlib import contextmanager
from datetime import date, datetime
from functools import wraps
import fcntl
import json
import logging
import os
from pathlib import Path
import threading
from zoneinfo import ZoneInfo

_lock = threading.RLock()
_local = threading.local()
logger = logging.getLogger(__name__)


def limits():
    def value(name, default):
        try:
            return max(1, int(os.environ.get(name, default)))
        except (TypeError, ValueError):
            return default
    return {'recap': value('AI_RECAP_LIMIT', 100), 'flyer': value('AI_FLYER_LIMIT', 50)}


@contextmanager
def library_lock():
    """Serialize publication, pin changes, and cleanup across threads/workers."""
    import admin_functions as admin
    with _lock:
        if getattr(_local, 'locked', False):
            yield
            return
        with open(Path(admin._recap_storage_dir()) / '.library.lock', 'a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            _local.locked = True
            try:
                yield
            finally:
                _local.locked = False
                fcntl.flock(handle, fcntl.LOCK_UN)


def serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with library_lock():
            return function(*args, **kwargs)
    return wrapped


def functions(kind):
    import admin_functions as admin
    import flyer_functions as flyers
    if kind == 'recap':
        return admin.get_ai_recap_page, admin.update_ai_recap_page, admin.list_ai_recap_pages, admin.delete_ai_recap_page
    if kind == 'flyer':
        return flyers.get_flyer_page, flyers.update_flyer_page, flyers.list_flyer_pages, flyers.delete_flyer_page
    raise ValueError('Unknown item type')


@serialized
def set_pin(kind, share_id, pinned, can_manage):
    get, update, _, _ = functions(kind)
    row = get(share_id)
    if not row:
        raise KeyError('Item not found')
    if not can_manage(row.get('username')):
        raise PermissionError('Only the creator or an admin can change this favorite.')
    # Preserve metadata for older recaps stored only in SQLite/HTML.
    import admin_functions as admin
    metadata = {} if kind == 'flyer' or admin._read_recap_meta_file(share_id) else dict(row)
    metadata.pop('share_id', None)
    metadata.pop('html_body', None)
    metadata['pinned'] = bool(pinned)
    update(share_id, **metadata)


def live_image_filenames():
    """Fail closed on unreadable records; prompt history does not own images."""
    import admin_functions as admin
    import flyer_functions as flyers
    referenced = set()
    for directory in (admin._recap_storage_dir(), admin._legacy_recap_dir(), flyers._flyer_storage_dir()):
        root = Path(directory)
        if not root.exists():
            continue
        for path in root.iterdir():
            if path.is_file() and path.suffix in ('.json', '.html'):
                content = path.read_text()
                if path.suffix == '.json':
                    json.loads(content)
                referenced |= admin._email_image_filenames_from_text(content)
    conn = admin._connect()
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'ai_recap_pages'").fetchone():
            for row in conn.execute('SELECT * FROM ai_recap_pages'):
                referenced |= admin._email_image_filenames_from_text(json.dumps(dict(row)))
    finally:
        conn.close()
    return referenced


def cleanup_images(row):
    """Remove only this deleted item's images that no published page still uses."""
    import admin_functions as admin
    candidates = admin._email_image_filenames_from_text(json.dumps(row or {}))
    if not candidates:
        return
    try:
        unused = candidates - live_image_filenames()
        root = Path(admin.email_images_dir())
        for name in unused:
            path = root / name
            if path.suffix.lower() in admin._AI_IMAGE_EXTENSIONS and not path.is_symlink():
                path.unlink(missing_ok=True)
    except Exception:
        # An unreadable reference or failed unlink must not break publication.
        logger.exception('Could not finish unused AI image cleanup')


def upcoming(row, today):
    raw = (row.get('event_date') or '').strip()
    if not raw:
        return False
    try:
        return date.fromisoformat(raw) >= today
    except ValueError:
        # Preserve legacy dates we cannot confidently classify as past events.
        return True


@serialized
def enforce(kind, new_share_id):
    get, _, list_pages, delete = functions(kind)
    new = get(new_share_id)
    if not new or not (new.get('username') or '').strip():
        return []
    # Failed illustrations have an editable page, but must not evict good work.
    if kind == 'flyer' and (not new.get('flyer_image_url') or new.get('flyer_image_error')):
        return []
    if kind == 'recap' and (not new.get('html_body') or new.get('hero_image_error')):
        return []
    entries, _ = list_pages(per_page=2**31 - 1, username=new['username'])
    excess = len(entries) - limits()[kind]
    removed = []
    today = datetime.now(ZoneInfo('America/Los_Angeles')).date()
    for entry in sorted(entries, key=lambda e: (e.get('created_at') or '', e['share_id'])):
        if excess <= 0:
            break
        sid = entry['share_id']
        row = get(sid)
        if not row or sid == new_share_id or row.get('pinned'):
            continue
        if kind == 'flyer' and upcoming(row, today):
            continue
        if delete(sid):
            removed.append(sid)
            excess -= 1
    return removed


def after_publish(kind, share_id):
    try:
        return enforce(kind, share_id)
    except Exception:
        logger.exception('AI library cleanup failed after publishing %s %s', kind, share_id)
        return []
