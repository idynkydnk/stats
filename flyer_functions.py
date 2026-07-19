"""Disk persistence for shareable AI flyer pages (mirrors recap storage)."""
import json
import os
from datetime import datetime, timezone


def _flyer_storage_dir():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, 'static', 'flyers')
    os.makedirs(path, exist_ok=True)
    return path


def _safe_flyer_share_id(share_id):
    safe_id = ''.join(ch for ch in (share_id or '') if ch.isalnum() or ch in ('-', '_'))
    if not safe_id:
        raise ValueError('Invalid flyer id')
    return safe_id


def _flyer_meta_path(share_id):
    safe_id = _safe_flyer_share_id(share_id)
    return os.path.join(_flyer_storage_dir(), f'{safe_id}.json')


def _write_json_atomic(path, payload):
    tmp_path = f'{path}.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def insert_flyer_page(
    share_id,
    username,
    players,
    game_type,
    event_date,
    event_time,
    location,
    game_name='',
    image_details='',
    flyer_image_url='',
    flyer_image_error='',
    solo_images=None,
    scene_prompt='',
):
    """Persist a new flyer page meta JSON on disk."""
    safe_id = _safe_flyer_share_id(share_id)
    meta = {
        'share_id': safe_id,
        'created_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
        'username': username or 'unknown',
        'players': list(players or []),
        'game_type': game_type or 'doubles',
        'game_name': game_name or '',
        'event_date': event_date or '',
        'event_time': event_time or '',
        'location': location or '',
        'image_details': image_details or '',
        'flyer_image_url': flyer_image_url or '',
        'flyer_image_error': flyer_image_error or '',
        'solo_images': list(solo_images or []),
        'scene_prompt': scene_prompt or '',
    }
    _write_json_atomic(_flyer_meta_path(safe_id), meta)
    return meta


def get_flyer_page(share_id):
    """Load flyer meta, or None if missing."""
    try:
        safe_id = _safe_flyer_share_id(share_id)
    except ValueError:
        return None
    path = _flyer_meta_path(safe_id)
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def update_flyer_page(share_id, **meta_updates):
    """Update flyer metadata fields on disk."""
    safe_id = _safe_flyer_share_id(share_id)
    meta = get_flyer_page(safe_id) or {'share_id': safe_id}
    for key, value in meta_updates.items():
        if value is None:
            continue
        meta[key] = value
    _write_json_atomic(_flyer_meta_path(safe_id), meta)
    return meta
