"""Small, bounded previews of images that are already publicly served as static files."""
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.parse import unquote, urlsplit

from flask import abort, redirect, send_file, url_for


def register_image_previews(app):
    root = Path(app.static_folder).resolve()

    def source(filename):
        path = (root / filename).resolve()
        if not any(path.is_relative_to(root / folder) for folder in ('email_images', 'flyers', 'player_photos')):
            return None
        return path if path.is_file() else None

    def preview_url(image_url):
        parsed = urlsplit(image_url or '')
        path = unquote(parsed.path)
        if not path.startswith('/static/'):
            return image_url
        filename = path[len('/static/'):]
        try:
            original = source(filename)
            if original is None:
                return image_url
            return url_for('image_preview', filename=filename, v=original.stat().st_mtime_ns, _external=True)
        except (OSError, ValueError):
            return image_url

    app.extensions['image_preview_url'] = preview_url
    app.jinja_env.globals['image_preview_url'] = preview_url

    @app.get('/image-preview/<path:filename>')
    def image_preview(filename):
        original = source(filename)
        if original is None:
            abort(404)
        stamp = original.stat()
        key = hashlib.sha256(f'{original}:{stamp.st_mtime_ns}:{stamp.st_size}:640-v1'.encode()).hexdigest()
        directory = Path(app.config.get('IMAGE_PREVIEW_CACHE_DIR') or
                         (root.parent / 'private_data' / 'image_previews'))
        try:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            target = directory / (key + '.jpg')
            if not target.exists():
                from PIL import Image, ImageOps
                with Image.open(original) as image:
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((640, 640))
                    image = image.convert('RGB')
                    fd, temp = tempfile.mkstemp(dir=directory, suffix='.jpg')
                    try:
                        with os.fdopen(fd, 'wb') as stream:
                            image.save(stream, 'JPEG', quality=78, optimize=True)
                        os.replace(temp, target)
                    finally:
                        if os.path.exists(temp):
                            os.unlink(temp)
                files = sorted(directory.glob('*.jpg'), key=lambda p: p.stat().st_mtime, reverse=True)
                for old in files[256:]:
                    old.unlink(missing_ok=True)
            return send_file(target, mimetype='image/jpeg', conditional=True, max_age=86400)
        except (OSError, ValueError):
            return redirect(url_for('static', filename=filename))
