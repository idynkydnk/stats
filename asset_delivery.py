"""Content-versioned, public code assets; uploaded pictures keep their own policy."""
from hashlib import sha256
from pathlib import Path
import re

from flask import request
from markupsafe import Markup


def register_asset_delivery(app):
    root = Path(app.static_folder)
    versions = {}
    contents = {}
    for directory in ('css', 'js', 'vendor/fontawesome'):
        for path in (root / directory).rglob('*'):
            if path.is_file() and path.suffix in {'.css', '.js', '.woff2'}:
                filename = path.relative_to(root).as_posix()
                contents[filename] = path.read_bytes()
                versions[filename] = sha256(contents[filename]).hexdigest()[:16]

    # Build once at worker startup from the canonical sources, so a source edit
    # cannot leave a stale checked-in bundle. Fewer HTTP/1.1 requests especially
    # help fresh Safari visits over a longer round trip.
    bundles = {}
    scripts = ['js/menu.js', 'js/stats-sharing.js', 'js/search-filter.js',
               'js/mobile-keyboard.js', 'js/responsiveness.js']
    styles = ['vendor/fontawesome/icons.css', 'css/stats.css', 'css/appearance.css']
    if all(name in contents for name in scripts):
        bundles['js/common.bundle.js'] = (b'\n;\n'.join(contents[name] for name in scripts), 'application/javascript')
    if all(name in contents for name in styles):
        icons = contents[styles[0]].replace(b'url("', b'url("../vendor/fontawesome/')
        bundles['css/site.bundle.css'] = (b'\n'.join([icons] + [contents[name] for name in styles[1:]]), 'text/css')
        font = re.search(rb'fa-solid-900\.[a-f0-9]+\.woff2', icons)
        if font:
            app.jinja_env.globals['site_icon_font'] = 'vendor/fontawesome/' + font.group().decode('ascii')
    for filename, (body, _) in bundles.items():
        versions[filename] = sha256(body).hexdigest()[:16]
    original_static = app.view_functions['static']

    def bundled_static(**values):
        filename = values.get('filename')
        if filename not in bundles:
            return original_static(**values)
        body, mimetype = bundles[filename]
        response = app.response_class(body, mimetype=mimetype)
        response.set_etag(versions[filename])
        response.headers['Cache-Control'] = 'no-cache'
        return response.make_conditional(request)

    app.view_functions['static'] = bundled_static

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
