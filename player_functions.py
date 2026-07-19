from create_players_database import *
from datetime import datetime
import base64
import json
import os
import uuid

from stat_functions import cached

ALLOWED_PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
MAX_PHOTO_BYTES = 10 * 1024 * 1024  # max upload size before compression
MAX_STORED_PHOTO_BYTES = 2 * 1024 * 1024  # on-disk target after compression
MAX_FULL_BODY_PHOTOS = 1
MAX_AI_IMAGE_TRAITS = 12
MAX_AI_IMAGE_TRAITS_CHARS = 500
MAX_STORED_PHOTO_DIMENSION = 2400

# Canonical SELECT for players — avoids breakage when legacy columns (e.g. phone) exist.
PLAYERS_SELECT = """
    SELECT id, full_name, email, date_of_birth, height, notes,
           created_at, updated_at, photo_path, full_body_photo_path
    FROM players
"""

PLAYERS_SELECT_COLUMNS = 10


def init_players_photo_column():
    """Ensure players photo columns exist (safe to call on every startup)."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    if conn is None:
        return
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(players)')
    cols = [row[1] for row in cur.fetchall()]
    if 'photo_path' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN photo_path TEXT')
    if 'full_body_photo_path' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN full_body_photo_path TEXT')
    if 'full_body_photo_paths' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN full_body_photo_paths TEXT')
    if 'ai_image_traits' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN ai_image_traits TEXT')
    if 'face_photo_focus' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN face_photo_focus TEXT')
    if 'full_body_photo_crops' not in cols:
        cur.execute('ALTER TABLE players ADD COLUMN full_body_photo_crops TEXT')
    conn.commit()
    conn.close()
    trim_all_players_full_body_photos()
    try:
        compress_all_oversized_player_photos()
    except Exception:
        # Don't block app startup if an odd photo fails to recompress.
        pass


def trim_player_full_body_photos(player_id):
    """Keep at most MAX_FULL_BODY_PHOTOS; delete extra files and crop metadata."""
    paths = get_player_full_body_photo_paths_by_id(player_id)
    if len(paths) <= MAX_FULL_BODY_PHOTOS:
        return 0
    keep = paths[:MAX_FULL_BODY_PHOTOS]
    for path in paths[MAX_FULL_BODY_PHOTOS:]:
        _remove_stored_photo(path)
    set_player_full_body_photo_paths(player_id, keep)
    return len(paths) - len(keep)


def trim_all_players_full_body_photos():
    """Trim every player to MAX_FULL_BODY_PHOTOS full-body photos."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    if conn is None:
        return 0
    cur = conn.cursor()
    cur.execute('SELECT id FROM players')
    removed = 0
    for (player_id,) in cur.fetchall():
        removed += trim_player_full_body_photos(player_id)
    conn.close()
    return removed


def player_photos_dir():
    """Absolute path to static/player_photos."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, 'static', 'player_photos')
    os.makedirs(path, exist_ok=True)
    return path


def get_player_photo_path(full_name):
    """Return stored photo_path (e.g. player_photos/3.jpg) or None."""
    cur = set_cur()
    cur.execute(
        'SELECT photo_path FROM players WHERE full_name = ?',
        (full_name,),
    )
    row = cur.fetchone()
    return row[0] if row and row[0] else None


MIN_PHOTO_ZOOM = 0.25
MAX_BODY_ZOOM = 6.0
MAX_FACE_ZOOM = 6.0
MIN_FACE_ZOOM = MIN_PHOTO_ZOOM
BODY_CROP_ASPECT = 3 / 4  # width / height for full-body thumbnails
MIN_BODY_ASPECT = 0.45
MAX_BODY_ASPECT = 2.5


def _clamp_body_zoom(zoom):
    return max(MIN_PHOTO_ZOOM, min(MAX_BODY_ZOOM, float(zoom)))


def _clamp_body_aspect(aspect):
    return max(MIN_BODY_ASPECT, min(MAX_BODY_ASPECT, float(aspect)))


def _clamp_face_zoom(zoom):
    return max(MIN_PHOTO_ZOOM, min(MAX_FACE_ZOOM, float(zoom)))


def _clamp_photo_zoom(zoom):
    return _clamp_body_zoom(zoom)


def _parse_photo_focus(raw, max_zoom=MAX_BODY_ZOOM):
    if not raw:
        return 50.0, 50.0, 1.0
    try:
        parts = [p.strip() for p in str(raw).split(',')]
        if len(parts) < 2:
            return 50.0, 50.0, 1.0
        x = max(0.0, min(100.0, float(parts[0])))
        y = max(0.0, min(100.0, float(parts[1])))
        z = 1.0
        if len(parts) >= 3 and parts[2] != '':
            z = max(MIN_PHOTO_ZOOM, min(max_zoom, float(parts[2])))
        return x, y, z
    except (TypeError, ValueError):
        return 50.0, 50.0, 1.0


def _parse_face_photo_focus(raw):
    return _parse_photo_focus(raw, max_zoom=MAX_FACE_ZOOM)


def get_player_face_photo_focus(full_name):
    """Return face crop focus (x%, y%, zoom) for the circle avatar."""
    cur = set_cur()
    cur.execute(
        'SELECT face_photo_focus FROM players WHERE full_name = ?',
        (full_name,),
    )
    row = cur.fetchone()
    return _parse_face_photo_focus(row[0] if row else None)


def set_player_face_photo_focus(player_id, x, y, z=None):
    """Save face crop focus and zoom for object-position + scale."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    if z is None:
        cur.execute('SELECT face_photo_focus FROM players WHERE id = ?', (player_id,))
        row = cur.fetchone()
        _, _, z = _parse_face_photo_focus(row[0] if row else None)
    x = max(0.0, min(100.0, float(x)))
    y = max(0.0, min(100.0, float(y)))
    z = _clamp_face_zoom(z)
    now = datetime.now()
    focus = f'{x:.1f},{y:.1f},{z:.2f}'
    with conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE players SET face_photo_focus = ?, updated_at = ? WHERE id = ?',
            (focus, now, player_id),
        )
        conn.commit()
    return x, y, z


def get_player_full_body_photo_path(full_name):
    """Return first full-body path (legacy helper)."""
    paths = get_player_full_body_photo_paths(full_name)
    return paths[0] if paths else None


def _parse_body_paths_json(raw):
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, str) and p.strip()]


def _body_paths_from_row(paths_json, legacy_path):
    paths = _parse_body_paths_json(paths_json)
    if paths:
        return paths
    if legacy_path:
        return [legacy_path]
    return []


def _existing_body_paths(paths):
    return [p for p in paths if read_player_image_file(p)[0]]


def _parse_body_crops_json(raw):
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    crops = {}
    for path, focus_raw in data.items():
        if not isinstance(path, str) or not path.strip():
            continue
        aspect = BODY_CROP_ASPECT
        if isinstance(focus_raw, dict):
            x = max(0.0, min(100.0, float(focus_raw.get('x', 50))))
            y = max(0.0, min(100.0, float(focus_raw.get('y', 50))))
            if focus_raw.get('w') is not None and focus_raw.get('h') is not None:
                try:
                    w = max(5.0, min(100.0, float(focus_raw['w'])))
                    h = max(5.0, min(100.0, float(focus_raw['h'])))
                    crops[path] = {'x': x, 'y': y, 'w': w, 'h': h}
                    continue
                except (TypeError, ValueError):
                    pass
            x, y, z = _parse_photo_focus(
                f"{focus_raw.get('x', 50)},{focus_raw.get('y', 50)},{focus_raw.get('z', 1)}"
            )
            if focus_raw.get('aspect') is not None:
                try:
                    aspect = _clamp_body_aspect(focus_raw['aspect'])
                except (TypeError, ValueError):
                    aspect = BODY_CROP_ASPECT
        else:
            x, y, z = _parse_photo_focus(focus_raw)
        crops[path] = {'x': x, 'y': y, 'z': z, 'aspect': aspect}
    return crops


def _get_body_crops_by_id(player_id):
    cur = set_cur()
    cur.execute('SELECT full_body_photo_crops FROM players WHERE id = ?', (player_id,))
    row = cur.fetchone()
    return _parse_body_crops_json(row[0] if row else None)


def get_player_full_body_photo_crops(full_name):
    cur = set_cur()
    cur.execute(
        'SELECT full_body_photo_crops FROM players WHERE full_name = ?',
        (full_name,),
    )
    row = cur.fetchone()
    return _parse_body_crops_json(row[0] if row else None)


def get_full_body_photo_crop(full_name, rel_path):
    crops = get_player_full_body_photo_crops(full_name)
    return crops.get(rel_path, {'x': 50.0, 'y': 50.0, 'w': 75.0, 'h': 90.0})


def set_player_full_body_photo_crop(player_id, rel_path, x, y, z=None, aspect=None, w=None, h=None):
    """Save crop for one full-body photo (rect w/h or legacy z/aspect)."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    crops = _get_body_crops_by_id(player_id)
    existing = crops.get(rel_path, {})
    x = max(0.0, min(100.0, float(x)))
    y = max(0.0, min(100.0, float(y)))
    if w is not None and h is not None:
        w = max(5.0, min(100.0, float(w)))
        h = max(5.0, min(100.0, float(h)))
        crops[rel_path] = {'x': x, 'y': y, 'w': w, 'h': h}
        now = datetime.now()
        with conn:
            cur.execute(
                'UPDATE players SET full_body_photo_crops = ?, updated_at = ? WHERE id = ?',
                (json.dumps(crops), now, player_id),
            )
            conn.commit()
        return x, y, w, h
    if z is None:
        z = existing.get('z', 1.0)
    if aspect is None:
        aspect = existing.get('aspect', BODY_CROP_ASPECT)
    z = _clamp_body_zoom(z)
    aspect = _clamp_body_aspect(aspect)
    crops[rel_path] = {'x': x, 'y': y, 'z': z, 'aspect': aspect}
    now = datetime.now()
    with conn:
        cur.execute(
            'UPDATE players SET full_body_photo_crops = ?, updated_at = ? WHERE id = ?',
            (json.dumps(crops), now, player_id),
        )
        conn.commit()
    return x, y, z, aspect


def crop_image_with_focus(image_bytes, x_pct, y_pct, zoom, output_aspect=1.0, max_pixels=768, max_zoom=None):
    """Export a crop matching CSS object-fit:cover + object-position + scale."""
    import io
    from PIL import Image, ImageOps

    if max_zoom is None:
        max_zoom = MAX_FACE_ZOOM if output_aspect == 1.0 else MAX_BODY_ZOOM

    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    iw, ih = img.size
    if not iw or not ih:
        return image_bytes, 'image/jpeg'

    aspect = max(float(output_aspect), 0.1)
    if aspect >= 1:
        out_h = max_pixels
        out_w = max(1, int(max_pixels * aspect))
    else:
        out_w = max_pixels
        out_h = max(1, int(max_pixels / aspect))

    cover_scale = max(out_w / iw, out_h / ih)
    zoom = max(MIN_PHOTO_ZOOM, min(max_zoom, float(zoom)))
    crop_w = out_w / (cover_scale * zoom)
    crop_h = out_h / (cover_scale * zoom)

    cx = (float(x_pct) / 100.0) * iw
    cy = (float(y_pct) / 100.0) * ih
    left = cx - crop_w / 2
    top = cy - crop_h / 2
    right = left + crop_w
    bottom = top + crop_h

    if left < 0:
        right -= left
        left = 0
    if top < 0:
        bottom -= top
        top = 0
    if right > iw:
        shift = right - iw
        left = max(0.0, left - shift)
        right = iw
    if bottom > ih:
        shift = bottom - ih
        top = max(0.0, top - shift)
        bottom = ih

    cropped = img.crop((int(left), int(top), int(right), int(bottom)))
    cropped = cropped.resize((out_w, out_h), _pil_lanczos())
    buf = io.BytesIO()
    cropped.save(buf, format='JPEG', quality=90)
    return buf.getvalue(), 'image/jpeg'


def crop_image_with_rect(image_bytes, x_pct, y_pct, w_pct, h_pct, max_pixels=768):
    """Export an explicit rectangular crop from the source image."""
    import io
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    iw, ih = img.size
    if not iw or not ih:
        return image_bytes, 'image/jpeg'

    crop_w = max(1.0, iw * float(w_pct) / 100.0)
    crop_h = max(1.0, ih * float(h_pct) / 100.0)
    cx = iw * float(x_pct) / 100.0
    cy = ih * float(y_pct) / 100.0
    left = cx - crop_w / 2
    top = cy - crop_h / 2
    right = left + crop_w
    bottom = top + crop_h

    if left < 0:
        right -= left
        left = 0
    if top < 0:
        bottom -= top
        top = 0
    if right > iw:
        left = max(0.0, right - crop_w)
        right = iw
    if bottom > ih:
        top = max(0.0, bottom - crop_h)
        bottom = ih

    cropped = img.crop((int(left), int(top), int(right), int(bottom)))
    if not cropped.width or not cropped.height:
        return image_bytes, 'image/jpeg'

    aspect = cropped.width / cropped.height
    if aspect >= 1:
        out_h = max_pixels
        out_w = max(1, int(max_pixels * aspect))
    else:
        out_w = max_pixels
        out_h = max(1, int(max_pixels / aspect))
    cropped = cropped.resize((out_w, out_h), _pil_lanczos())
    buf = io.BytesIO()
    cropped.save(buf, format='JPEG', quality=90)
    return buf.getvalue(), 'image/jpeg'


def read_cropped_player_image(rel_path, focus, output_aspect=1.0, max_pixels=768):
    """Load a stored photo with pan/zoom crop applied for AI reference images."""
    raw, _mime = read_player_image_file(rel_path)
    if not raw:
        return None, None
    focus = focus or {'x': 50, 'y': 50, 'z': 1}
    try:
        if focus.get('w') is not None and focus.get('h') is not None:
            return crop_image_with_rect(
                raw,
                focus.get('x', 50),
                focus.get('y', 50),
                focus.get('w'),
                focus.get('h'),
                max_pixels=max_pixels,
            )
        if focus.get('aspect') is not None:
            output_aspect = focus.get('aspect')
        return crop_image_with_focus(
            raw,
            focus.get('x', 50),
            focus.get('y', 50),
            focus.get('z', 1),
            output_aspect=output_aspect,
            max_pixels=max_pixels,
        )
    except Exception:
        return raw, _mime


def read_face_avatar_image(full_name, max_pixels=128):
    """Square cropped face avatar bytes for public player pages."""
    path = get_player_photo_path(full_name)
    if not path:
        return None, None
    x, y, z = get_player_face_photo_focus(full_name)
    return read_cropped_player_image(
        path,
        {'x': x, 'y': y, 'z': z},
        output_aspect=1.0,
        max_pixels=max_pixels,
    )


def get_player_full_body_photo_paths(full_name):
    """Return all stored full-body photo paths for a player."""
    cur = set_cur()
    cur.execute(
        'SELECT full_body_photo_paths, full_body_photo_path FROM players WHERE full_name = ?',
        (full_name,),
    )
    row = cur.fetchone()
    if not row:
        return []
    return _existing_body_paths(_body_paths_from_row(row[0], row[1]))


def get_player_full_body_photo_paths_by_id(player_id):
    cur = set_cur()
    cur.execute(
        'SELECT full_body_photo_paths, full_body_photo_path FROM players WHERE id = ?',
        (player_id,),
    )
    row = cur.fetchone()
    if not row:
        return []
    return _existing_body_paths(_body_paths_from_row(row[0], row[1]))


def set_player_full_body_photo_paths(player_id, paths):
    """Persist full-body photo paths as JSON; clears legacy single-path column."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    now = datetime.now()
    clean = [p for p in paths if p]
    crops = _get_body_crops_by_id(player_id)
    keep_crops = {p: crops[p] for p in clean if p in crops}
    with conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE players SET full_body_photo_paths = ?, full_body_photo_path = NULL, '
            'full_body_photo_crops = ?, updated_at = ? WHERE id = ?',
            (
                json.dumps(clean) if clean else None,
                json.dumps(keep_crops) if keep_crops else None,
                now,
                player_id,
            ),
        )
        conn.commit()


def get_player_photo_paths(full_name):
    """Return face path and list of full-body paths for a player."""
    cur = set_cur()
    cur.execute(
        'SELECT photo_path, full_body_photo_paths, full_body_photo_path FROM players WHERE full_name = ?',
        (full_name,),
    )
    row = cur.fetchone()
    if not row:
        return None, []
    face = row[0] or None
    body_paths = _existing_body_paths(_body_paths_from_row(row[1], row[2]))
    return face, body_paths


def normalize_player_ai_image_traits(value):
    """Return a clean phrase list, including values saved by the old text UI."""
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            decoded = None
        values = decoded if isinstance(decoded, list) else [raw]
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        return []

    phrases = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        phrase = ' '.join(value.split())
        key = phrase.casefold()
        if phrase and key not in seen:
            phrases.append(phrase)
            seen.add(key)
    return phrases


def get_player_ai_image_traits(full_name):
    """Return signature-look phrases for AI image exaggeration."""
    cur = set_cur()
    cur.execute(
        'SELECT ai_image_traits FROM players WHERE full_name = ?',
        (full_name,),
    )
    row = cur.fetchone()
    return normalize_player_ai_image_traits(row[0] if row else None)


def set_player_ai_image_traits(player_id, traits):
    """Save signature-look phrases used in AI email images."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    now = datetime.now()
    phrases = normalize_player_ai_image_traits(traits)
    if len(phrases) > MAX_AI_IMAGE_TRAITS:
        raise ValueError(f'Add no more than {MAX_AI_IMAGE_TRAITS} signature-look phrases.')
    if sum(len(phrase) for phrase in phrases) > MAX_AI_IMAGE_TRAITS_CHARS:
        raise ValueError(
            f'Signature-look phrases can contain up to {MAX_AI_IMAGE_TRAITS_CHARS} characters total.'
        )
    clean = json.dumps(phrases, ensure_ascii=False) if phrases else None
    with conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE players SET ai_image_traits = ?, updated_at = ? WHERE id = ?',
            (clean, now, player_id),
        )
        conn.commit()
    return phrases


def collect_player_ai_image_traits(player_names):
    """Traits to exaggerate for players in an AI email illustration."""
    traits = []
    for name in sorted(player_names):
        phrases = get_player_ai_image_traits(name)
        if phrases:
            traits.append({
                'name': name,
                'phrases': phrases,
                'traits': '; '.join(phrases),
            })
    return traits


def set_player_photo_path(player_id, photo_path):
    """Update photo_path for a player."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    now = datetime.now()
    with conn:
        cur = conn.cursor()
        cur.execute(
            'UPDATE players SET photo_path = ?, updated_at = ? WHERE id = ?',
            (photo_path, now, player_id),
        )
        conn.commit()


def _validate_photo_upload(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError('No photo file provided.')

    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        raise ValueError('Photo must be JPG, PNG, WebP, or GIF.')

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_PHOTO_BYTES:
        raise ValueError('Photo must be 10 MB or smaller.')
    return ext


def _pil_lanczos():
    """LANCZOS filter compatible with older Pillow (no Image.Resampling)."""
    from PIL import Image

    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


def _pil_image_to_rgb(img):
    from PIL import Image

    if img.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        alpha = img.split()[-1]
        background.paste(img.convert('RGBA'), mask=alpha)
        return background
    if img.mode == 'P':
        return img.convert('RGBA').convert('RGB')
    if img.mode != 'RGB':
        return img.convert('RGB')
    return img


def _jpeg_bytes_under_limit(img, max_bytes=MAX_STORED_PHOTO_BYTES):
    """Encode image as JPEG under max_bytes by lowering quality, then size."""
    import io

    img = _pil_image_to_rgb(img)
    w, h = img.size
    longest = max(w, h)
    if longest > MAX_STORED_PHOTO_DIMENSION:
        scale = MAX_STORED_PHOTO_DIMENSION / float(longest)
        img = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            _pil_lanczos(),
        )

    best = None
    working = img
    for _ in range(8):
        for quality in (85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 25, 20):
            buf = io.BytesIO()
            working.save(buf, format='JPEG', quality=quality, optimize=True)
            data = buf.getvalue()
            if best is None or len(data) < len(best):
                best = data
            if len(data) <= max_bytes:
                return data
        ww, hh = working.size
        if max(ww, hh) <= 480:
            break
        working = working.resize(
            (max(1, ww // 2), max(1, hh // 2)),
            _pil_lanczos(),
        )
    return best


def _compress_image_bytes_under_limit(raw_bytes, source_ext='.jpg'):
    """Return (bytes, ext). Keeps original bytes/ext when already under the limit."""
    import io
    from PIL import Image, ImageOps

    if not raw_bytes:
        raise ValueError('Empty photo file.')
    if len(raw_bytes) <= MAX_STORED_PHOTO_BYTES:
        return raw_bytes, source_ext.lower() if source_ext else '.jpg'

    img = Image.open(io.BytesIO(raw_bytes))
    img = ImageOps.exif_transpose(img)
    compressed = _jpeg_bytes_under_limit(img)
    if not compressed:
        raise ValueError('Unable to compress photo under 2 MB.')
    return compressed, '.jpg'


def _write_photo_bytes(abs_path, data):
    tmp_path = f'{abs_path}.tmp'
    with open(tmp_path, 'wb') as handle:
        handle.write(data)
    os.replace(tmp_path, abs_path)


def _save_upload_compressed(file_storage, dest_dir, filename_stem, source_ext):
    """Save an upload under 2 MB. Returns (abs_path, filename with ext)."""
    file_storage.stream.seek(0)
    raw = file_storage.read()
    file_storage.stream.seek(0)
    data, ext = _compress_image_bytes_under_limit(raw, source_ext)
    if ext == '.jpeg':
        ext = '.jpg'
    filename = f'{filename_stem}{ext}'
    abs_path = os.path.join(dest_dir, filename)
    _write_photo_bytes(abs_path, data)
    return abs_path, filename


def _compress_existing_photo_file(rel_path):
    """Recompress one stored photo if over 2 MB. Returns new rel_path or None if unchanged."""
    if not rel_path:
        return None
    base = os.path.dirname(os.path.abspath(__file__))
    abs_path = os.path.join(base, 'static', rel_path)
    if not os.path.isfile(abs_path):
        return None
    try:
        size = os.path.getsize(abs_path)
    except OSError:
        return None
    if size <= MAX_STORED_PHOTO_BYTES:
        return None

    source_ext = os.path.splitext(abs_path)[1].lower() or '.jpg'
    with open(abs_path, 'rb') as handle:
        raw = handle.read()
    data, ext = _compress_image_bytes_under_limit(raw, source_ext)
    if ext == '.jpeg':
        ext = '.jpg'

    stem, _old_ext = os.path.splitext(abs_path)
    new_abs = f'{stem}{ext}'
    _write_photo_bytes(new_abs, data)
    if new_abs != abs_path and os.path.isfile(abs_path):
        try:
            os.remove(abs_path)
        except OSError:
            pass

    directory, filename = os.path.split(rel_path)
    new_name = f'{os.path.splitext(filename)[0]}{ext}'
    return f'{directory}/{new_name}' if directory else new_name


def compress_all_oversized_player_photos():
    """Recompress any face/body photos over 2 MB and update DB paths if needed."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    if conn is None:
        return 0

    cur = conn.cursor()
    cur.execute('SELECT id, photo_path FROM players')
    rows = cur.fetchall()
    conn.close()

    changed = 0
    for row in rows:
        player_id = row[0]
        photo_path = row[1]
        if photo_path:
            new_path = _compress_existing_photo_file(photo_path)
            if new_path:
                changed += 1
                if new_path != photo_path:
                    set_player_photo_path(player_id, new_path)

        paths = get_player_full_body_photo_paths_by_id(player_id)
        if not paths:
            continue
        updated_paths = []
        paths_changed = False
        for path in paths:
            new_path = _compress_existing_photo_file(path)
            if new_path:
                changed += 1
                if new_path != path:
                    updated_paths.append(new_path)
                    paths_changed = True
                else:
                    updated_paths.append(path)
            else:
                updated_paths.append(path)
        if paths_changed:
            crops = _get_body_crops_by_id(player_id)
            remapped = {}
            for old_path, new_path in zip(paths, updated_paths):
                if old_path in crops:
                    remapped[new_path] = crops[old_path]
            database = '/home/Idynkydnk/stats/stats.db'
            conn = create_connection(database)
            if conn is None:
                conn = create_connection('stats.db')
            if conn is not None:
                now = datetime.now()
                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        'UPDATE players SET full_body_photo_crops = ?, updated_at = ? WHERE id = ?',
                        (json.dumps(remapped) if remapped else None, now, player_id),
                    )
                    conn.commit()
            set_player_full_body_photo_paths(player_id, updated_paths)
    return changed


def _remove_stored_photo(rel_path):
    if not rel_path:
        return
    base = os.path.dirname(os.path.abspath(__file__))
    abs_path = os.path.join(base, 'static', rel_path)
    if os.path.isfile(abs_path):
        os.remove(abs_path)


def _mime_for_photo_path(rel_path):
    ext = os.path.splitext(rel_path or '')[1].lower()
    return {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
    }.get(ext, 'image/jpeg')


def read_player_image_file(rel_path):
    """Load bytes and mime type for a stored player photo, or (None, None)."""
    if not rel_path:
        return None, None
    base = os.path.dirname(os.path.abspath(__file__))
    abs_path = os.path.join(base, 'static', rel_path)
    if not os.path.isfile(abs_path):
        return None, None
    with open(abs_path, 'rb') as f:
        return f.read(), _mime_for_photo_path(rel_path)


def save_player_photo_upload(player_id, file_storage):
    """Validate and save a face photo upload. Returns relative static path."""
    ext = _validate_photo_upload(file_storage)
    dest_dir = player_photos_dir()
    # Remove any previous face photo with a different extension.
    for old_ext in ALLOWED_PHOTO_EXTENSIONS:
        old_path = os.path.join(dest_dir, f'{player_id}{old_ext}')
        if os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
    _abs_path, filename = _save_upload_compressed(
        file_storage, dest_dir, str(player_id), ext,
    )

    rel_path = f'player_photos/{filename}'
    set_player_photo_path(player_id, rel_path)
    set_player_face_photo_focus(player_id, 50, 50, 1.0)
    return rel_path


def set_player_full_body_photo_path(player_id, photo_path):
    """Legacy: set a single full-body path (wraps paths list)."""
    set_player_full_body_photo_paths(player_id, [photo_path] if photo_path else [])


def save_player_full_body_photo_upload(player_id, file_storage):
    """Validate and save/replace the full-body photo upload. Returns relative static path."""
    ext = _validate_photo_upload(file_storage)
    for path in get_player_full_body_photo_paths_by_id(player_id):
        _remove_stored_photo(path)

    dest_dir = player_photos_dir()
    stem = f'{player_id}_body_{uuid.uuid4().hex[:12]}'
    _abs_path, filename = _save_upload_compressed(file_storage, dest_dir, stem, ext)

    rel_path = f'player_photos/{filename}'
    set_player_full_body_photo_paths(player_id, [rel_path])
    return rel_path


def remove_player_full_body_photo(player_id, rel_path=None):
    """Delete one full-body photo (by path) or all if rel_path is None."""
    paths = get_player_full_body_photo_paths_by_id(player_id)
    if rel_path:
        if rel_path in paths:
            _remove_stored_photo(rel_path)
            paths = [p for p in paths if p != rel_path]
            set_player_full_body_photo_paths(player_id, paths)
        return
    for path in paths:
        _remove_stored_photo(path)
    set_player_full_body_photo_paths(player_id, [])


def remove_player_photo(player_id):
    """Delete face photo file and clear photo_path."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    cur.execute('SELECT photo_path FROM players WHERE id = ?', (player_id,))
    row = cur.fetchone()
    if row and row[0]:
        _remove_stored_photo(row[0])
    set_player_photo_path(player_id, None)
    set_player_face_photo_focus(player_id, 50, 50, 1.0)


def collect_solo_reference_images(name):
    """Face reference for two-pass solo caricatures (signature looks come from traits)."""
    refs = collect_player_reference_images([name], max_players=1)
    if refs:
        return refs[0]
    return {'name': name, 'parts': []}


def collect_player_reference_images(player_names, max_players=4):
    """Build Gemini face-reference image parts for AI email illustrations.

    Uses each player's saved face photo. Signature looks are attached separately via traits.
    """
    references = []
    for name in sorted(player_names):
        if len(references) >= max_players:
            break
        display_name = (name or '').strip()
        if not display_name:
            continue
        entry = {'name': display_name, 'parts': []}

        face_path, _body_paths = get_player_photo_paths(display_name)
        if not face_path:
            continue
        fx, fy, fz = get_player_face_photo_focus(display_name)
        raw, mime = read_cropped_player_image(
            face_path, {'x': fx, 'y': fy, 'z': fz}, output_aspect=1.0,
        )
        if raw:
            entry['parts'].append({
                'label': f'Face reference photo for {display_name}.',
                'mime': mime,
                'data_b64': base64.b64encode(raw).decode('ascii'),
            })
            references.append(entry)
    return references


def set_cur():
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    return cur


def _players_db_connection():
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    return conn


def _game_stats_by_player(cur):
    """Return per-player (count, first_date) for each game type in three dicts."""
    cur.execute("""
        SELECT player, COUNT(*), MIN(game_date)
        FROM (
            SELECT winner1 AS player, game_date FROM games
                WHERE winner1 IS NOT NULL AND winner1 != ''
            UNION ALL
            SELECT winner2, game_date FROM games
                WHERE winner2 IS NOT NULL AND winner2 != ''
            UNION ALL
            SELECT loser1, game_date FROM games
                WHERE loser1 IS NOT NULL AND loser1 != ''
            UNION ALL
            SELECT loser2, game_date FROM games
                WHERE loser2 IS NOT NULL AND loser2 != ''
        )
        GROUP BY player
    """)
    doubles = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

    cur.execute("""
        SELECT player, COUNT(*), MIN(game_date)
        FROM (
            SELECT winner AS player, game_date FROM vollis_games
                WHERE winner IS NOT NULL AND winner != ''
            UNION ALL
            SELECT loser, game_date FROM vollis_games
                WHERE loser IS NOT NULL AND loser != ''
        )
        GROUP BY player
    """)
    vollis = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

    other_positions = [
        'winner1', 'winner2', 'winner3', 'winner4', 'winner5', 'winner6',
        'loser1', 'loser2', 'loser3', 'loser4', 'loser5', 'loser6',
    ]
    union_parts = ' UNION ALL '.join(
        f"SELECT {pos} AS player, game_date FROM other_games "
        f"WHERE {pos} IS NOT NULL AND {pos} != ''"
        for pos in other_positions
    )
    cur.execute(f"""
        SELECT player, COUNT(*), MIN(game_date)
        FROM ({union_parts})
        GROUP BY player
    """)
    other = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
    return doubles, vollis, other


def get_players_list_extras(names):
    """Batch-fetch list-card photo metadata for many players in one query."""
    if not names:
        return {}

    conn = _players_db_connection()
    if conn is None:
        return {}

    cur = conn.cursor()
    placeholders = ','.join('?' * len(names))
    cur.execute(
        f"""
        SELECT full_name, full_body_photo_paths, full_body_photo_path,
               ai_image_traits, face_photo_focus, full_body_photo_crops
        FROM players
        WHERE full_name IN ({placeholders})
        """,
        list(names),
    )

    extras = {}
    for row in cur.fetchall():
        name, paths_json, legacy_path, traits_raw, face_raw, crops_raw = row
        x, y, z = _parse_face_photo_focus(face_raw)
        extras[name] = {
            'body_paths': _body_paths_from_row(paths_json, legacy_path),
            'body_crops': _parse_body_crops_json(crops_raw),
            'traits': normalize_player_ai_image_traits(traits_raw),
            'face_focus': {'x': x, 'y': y, 'z': z},
        }

    conn.close()
    return extras


@cached(ttl=1800)
def get_all_players():
    """Get all players from the database with their first game date and game count."""
    conn = _players_db_connection()
    if conn is None:
        return []

    cur = conn.cursor()
    doubles, vollis, other = _game_stats_by_player(cur)
    all_player_names = set(doubles) | set(vollis) | set(other)

    cur.execute(PLAYERS_SELECT)
    players_by_name = {row[1]: row for row in cur.fetchall()}

    players_with_stats = []
    now = datetime.now()
    for player_name in all_player_names:
        doubles_count, doubles_date = doubles.get(player_name, (0, None))
        vollis_count, vollis_date = vollis.get(player_name, (0, None))
        other_count, other_date = other.get(player_name, (0, None))

        total_games = int(doubles_count + vollis_count + other_count)
        dates = [d for d in [doubles_date, vollis_date, other_date] if d is not None]
        first_game_date = min(dates) if dates else None

        player_record = players_by_name.get(player_name)
        if player_record:
            player_list = list(player_record)
        else:
            player_list = [None, player_name, None, None, None, None, now, now, None, None]

        while len(player_list) < PLAYERS_SELECT_COLUMNS:
            player_list.append(None)
        player_list = player_list[:PLAYERS_SELECT_COLUMNS]
        player_list.append(first_game_date)  # index 10
        player_list.append(int(total_games))  # index 11
        players_with_stats.append(tuple(player_list))

    def safe_game_count(player):
        try:
            return int(player[11]) if len(player) > 11 and player[11] is not None else 0
        except (ValueError, TypeError):
            return 0

    players_with_stats.sort(key=safe_game_count, reverse=True)
    conn.close()
    return players_with_stats

def get_player_by_id(player_id):
    """Get a specific player by ID"""
    cur = set_cur()
    cur.execute(f"{PLAYERS_SELECT} WHERE id=?", (player_id,))
    player = cur.fetchone()
    return player

def get_player_by_name(full_name):
    """Get a specific player by full name"""
    cur = set_cur()
    cur.execute(f"{PLAYERS_SELECT} WHERE full_name=?", (full_name,))
    player = cur.fetchone()
    return player

def add_new_player(full_name, email=None, date_of_birth=None, height=None, notes=None):
    """Add a new player to the database"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    now = datetime.now()
    with conn:
        player = (full_name, email, date_of_birth, height, notes, now, now)
        player_id = create_player(conn, player)
        return player_id

def update_player_info(player_id, full_name, email=None, date_of_birth=None, height=None, notes=None):
    """Update a player's information and update their name across all game tables"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    cur = conn.cursor()
    
    # Get the old name first
    cur.execute("SELECT full_name FROM players WHERE id=?", (player_id,))
    result = cur.fetchone()
    old_name = result[0] if result else None
    
    now = datetime.now()
    
    # If name has changed, update it across all game tables
    if old_name and old_name != full_name:
        # Update doubles games
        cur.execute("UPDATE games SET winner1 = ? WHERE winner1 = ?", (full_name, old_name))
        cur.execute("UPDATE games SET winner2 = ? WHERE winner2 = ?", (full_name, old_name))
        cur.execute("UPDATE games SET loser1 = ? WHERE loser1 = ?", (full_name, old_name))
        cur.execute("UPDATE games SET loser2 = ? WHERE loser2 = ?", (full_name, old_name))
        
        # Update vollis games
        try:
            cur.execute("UPDATE vollis_games SET winner = ? WHERE winner = ?", (full_name, old_name))
            cur.execute("UPDATE vollis_games SET loser = ? WHERE loser = ?", (full_name, old_name))
        except:
            pass  # Table might not exist
        
        # Other games (winner1, winner2, etc.) updated via database_functions.update_player_name_in_all_tables
        
        conn.commit()
    
    # Update the player record
    with conn:
        player = (full_name, email, date_of_birth, height, notes, now, player_id)
        update_player(conn, player)

def remove_player(player_id):
    """Delete a player from the database"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn:
        delete_player(conn, player_id)

def search_players(search_term):
    """Search for players by name or email"""
    cur = set_cur()
    cur.execute("SELECT * FROM players WHERE full_name LIKE ? OR email LIKE ? ORDER BY full_name ASC", 
                (f'%{search_term}%', f'%{search_term}%'))
    players = cur.fetchall()
    return players


def search_email_recipients(search_term, limit=20):
    """Search players with saved emails by name or email address."""
    term = (search_term or '').strip()
    if len(term) < 2:
        return []

    conn = _players_db_connection()
    if conn is None:
        return []

    cur = conn.cursor()
    like = f'%{term}%'
    cur.execute(
        """
        SELECT full_name, email
        FROM players
        WHERE email IS NOT NULL AND TRIM(email) != ''
          AND (full_name LIKE ? OR email LIKE ?)
        ORDER BY full_name ASC
        LIMIT ?
        """,
        (like, like, limit),
    )
    results = []
    seen = set()
    for name, email in cur.fetchall():
        clean_email = (email or '').strip()
        key = clean_email.lower()
        if not clean_email or key in seen:
            continue
        seen.add(key)
        results.append({'name': name, 'email': clean_email})
    conn.close()
    return results
