"""Content-versioned, public code assets; uploaded pictures keep their own policy."""
from hashlib import sha256
from pathlib import Path

from flask import request
from markupsafe import Markup


def register_asset_delivery(app):
    root = Path(app.static_folder)
    versions = {}
    for directory in ('css', 'js', 'vendor/fontawesome'):
        for path in (root / directory).rglob('*'):
            if path.is_file() and path.suffix in {'.css', '.js', '.woff2'}:
                versions[path.relative_to(root).as_posix()] = sha256(path.read_bytes()).hexdigest()[:16]

    # Trusted repository code, loaded once with the application. Applying the
    # theme inline prevents a network wait and a flash of the wrong appearance.
    app.jinja_env.globals['theme_bootstrap'] = Markup((root / 'js/theme.js').read_text())

    @app.url_defaults
    def version_asset(endpoint, values):
        if endpoint == 'static' and values.get('filename') in versions:
            values['v'] = versions[values['filename']]

    @app.after_request
    def cache_versioned_asset(response):
        if request.endpoint == 'static' and response.status_code in (200, 304):
            filename = (request.view_args or {}).get('filename', '')
            digest = versions.get(filename)
            # Font URLs inside CSS carry their digest in the filename itself.
            if digest and (request.args.get('v') == digest or f'.{digest}.' in filename):
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return response
