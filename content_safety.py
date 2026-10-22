"""Consent, content review, and personal blocking shared by web and native clients.

Automated checks are one layer, not a promise that every harmful item is caught.
Reports remain available for human review. No moderation service failure permits
an unchecked upload or generation to continue.
"""
from contextlib import closing
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from flask import abort, current_app, g, has_app_context, has_request_context, jsonify, request, session

CONSENT_VERSION = '2026-10-21'
CONSENT_DISCLOSURE = (
    'AI features send your selected game records, player names or nicknames, comments, '
    'locations, prompts, signature looks, and selected player photos or saved characters '
    'to OpenAI to create recaps and images. Uploaded images and text '
    'you submit for sharing are also sent to OpenAI to check for harmful content. '
    'Only include people’s photos and personal details when you have their permission. '
    'Generated recaps and flyers have public share links. Automated checks can miss '
    'harmful content; you can report it for review. You can withdraw this permission '
    'in AI privacy settings. Withdrawal stops future processing; it does not recall '
    'data already sent. See the privacy policy for retention and deletion details.'
)
AI_ENDPOINTS = {
    'api_ai_summary_json', 'api_create_flyer', 'api_generate_player_ai_image',
    'api_flyer_prompts', 'create_flyer_generate', 'remake_flyer_image',
    'remake_flyer_solo', 'remake_ai_recap_image', 'remake_ai_recap_summary',
    'api_generate_and_send_ai_summary', 'generate_ai_summary', 'generate_and_email_today',
    'preview_ai_summary_with_prompt',
}
UPLOAD_ENDPOINTS = {
    'api_upload_player_photo', 'api_generate_player_ai_image',
    'upload_flyer_solo', 'upload_ai_recap_image', 'edit_player',
}
TEXT_FIELDS = {
    'custom_prompt', 'scene_prompt', 'image_details', 'summary', 'title', 'prompt',
    'comments', 'comment', 'nickname', 'location', 'name', 'player_name',
    'ai_image_traits', 'phrases', 'style_instructions',
}
# A conservative local layer for ordinary score entry, which must remain usable
# without sending that entry to an AI provider. This is not the publication check.
_ABUSE_PHRASES = re.compile(r'\b(?:kill yourself|go kill yourself|kys|rape you|gas the jews|heil hitler)\b', re.I)


def check_local_text(value):
    if _ABUSE_PHRASES.search(str(value or '')):
        raise ContentSafetyError('Please remove threats or abusive language before saving.')


class ContentSafetyError(ValueError):
    def __init__(self, message, code='content_not_allowed', status=400):
        super().__init__(message)
        self.code, self.status = code, status


def enabled():
    return has_app_context() and bool(current_app.config.get('CONTENT_SAFETY_DB'))


def _path():
    return current_app.config['CONTENT_SAFETY_DB']


def _username():
    return (session.get('username') or '').strip() if has_request_context() else ''


def init_safety(path):
    with sqlite3.connect(path) as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS ai_data_consent (
            username TEXT PRIMARY KEY COLLATE NOCASE, version TEXT NOT NULL,
            granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS content_blocks (
            viewer TEXT COLLATE NOCASE, author TEXT COLLATE NOCASE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(viewer, author));
        CREATE TABLE IF NOT EXISTS content_reports (
            id INTEGER PRIMARY KEY, reporter TEXT, kind TEXT NOT NULL,
            content_id TEXT NOT NULL, author TEXT, reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT);
        CREATE TABLE IF NOT EXISTS content_hidden (
            kind TEXT, content_id TEXT, reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(kind, content_id));
        CREATE TABLE IF NOT EXISTS content_suspensions (
            username TEXT PRIMARY KEY COLLATE NOCASE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS content_removal_work (
            kind TEXT, content_id TEXT, author TEXT COLLATE NOCASE, assets_json TEXT NOT NULL,
            PRIMARY KEY(kind, content_id));
        ''')


def consent_state(username=None):
    username = _username() if username is None else username
    with sqlite3.connect(_path()) as conn:
        row = conn.execute('SELECT version FROM ai_data_consent WHERE username=?', (username,)).fetchone()
    return dict(version=CONSENT_VERSION, granted=bool(row and row[0] == CONSENT_VERSION),
                disclosure=CONSENT_DISCLOSURE, providers=['OpenAI'])


def set_consent(username, granted, version):
    if not username:
        raise ContentSafetyError('Please sign in first.', 'authentication_required', 401)
    if type(granted) is not bool or version != CONSENT_VERSION:
        raise ContentSafetyError('Review the current AI privacy notice before choosing.', 'invalid_consent')
    with sqlite3.connect(_path()) as conn:
        conn.execute('DELETE FROM ai_data_consent WHERE username=?', (username,))
        if granted:
            conn.execute('INSERT INTO ai_data_consent(username,version) VALUES (?,?)', (username, version))
    return consent_state(username)


def require_ai_consent():
    if not enabled():
        return
    owner = getattr(g, 'content_owner', None) if has_request_context() else None
    username = owner or _username()
    if not consent_state(username)['granted']:
        if owner and owner.casefold() != _username().casefold():
            raise ContentSafetyError('This content’s creator must allow AI data sharing before it can be changed.',
                                     'content_owner_consent_required', 403)
        raise ContentSafetyError('Review AI privacy settings and allow data sharing before using this feature.',
                                 'ai_consent_required', 403)
    with sqlite3.connect(_path()) as conn:
        if conn.execute('SELECT 1 FROM content_suspensions WHERE username=?', (username,)).fetchone():
            raise ContentSafetyError('This account cannot publish content.', 'account_suspended', 403)


def reject_unsupported_ai_provider():
    # The deployed general-audience app uses only the provider named in consent.
    # Legacy non-app tools retain their separate provider configuration.
    if enabled():
        raise ContentSafetyError('AI generation is temporarily unavailable. OpenAI must be configured for this app.',
                                 'ai_provider_unavailable', 503)


def moderate_content(text='', image_bytes=None, image_mime='image/jpeg'):
    """Check text/images with OpenAI after consent; never log submitted contents."""
    if not enabled() or (not text and not image_bytes):
        return
    require_ai_consent()
    if image_bytes:
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(io.BytesIO(image_bytes)) as picture:
                if getattr(picture, 'n_frames', 1) != 1:
                    raise ContentSafetyError('Choose a still image. Animated uploads cannot be checked completely.')
                if picture.format not in {'JPEG', 'PNG', 'WEBP', 'GIF'}:
                    raise ContentSafetyError('Choose a JPG, PNG, WebP, or still GIF image.')
                if picture.width * picture.height > 40_000_000:
                    raise ContentSafetyError('Choose an image with fewer than 40 million pixels.')
                image_mime = Image.MIME[picture.format]
                picture.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ContentSafetyError('This image could not be checked. Please choose a different image.') from None
    digest = hashlib.sha256((str(text) + '\0' + image_mime).encode() + (image_bytes or b'')).hexdigest()
    approved = getattr(g, 'moderation_approved', set()) if has_request_context() else set()
    if digest in approved:
        return
    import requests
    key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not key:
        raise ContentSafetyError('Content checks are temporarily unavailable. Please try again later.',
                                 'moderation_unavailable', 503)
    inputs = []
    if text:
        if len(text) > 100000:
            raise ContentSafetyError('Please shorten this text before submitting it.')
        inputs.append({'type': 'text', 'text': text})
    if image_bytes:
        if len(image_bytes) > 20 * 1024 * 1024:
            raise ContentSafetyError('This image is too large to check.')
        inputs.append({'type': 'image_url', 'image_url': {
            'url': 'data:' + image_mime + ';base64,' + base64.b64encode(image_bytes).decode('ascii')}})
    try:
        response = requests.post('https://api.openai.com/v1/moderations',
            headers={'Authorization': 'Bearer ' + key},
            json={'model': 'omni-moderation-latest', 'input': inputs}, timeout=30)
        response.raise_for_status()
        results = response.json().get('results')
        if not isinstance(results, list) or not results or any(
                not isinstance(item, dict) or type(item.get('flagged')) is not bool for item in results):
            raise ValueError('Invalid moderation response')
    except (requests.RequestException, ValueError, TypeError):
        raise ContentSafetyError('Content checks are temporarily unavailable. Please try again later.',
                                 'moderation_unavailable', 503) from None
    if any(item['flagged'] for item in results):
        raise ContentSafetyError('This content could be harmful and cannot be shared. Please choose different text or a different image.')
    if has_request_context():
        approved.add(digest)
        g.moderation_approved = approved


def check_publication_text(text):
    """A final gate also covers queued jobs completed after consent withdrawal."""
    if enabled():
        require_ai_consent()
        moderate_content(text)


def _visible(kind, item, state):
    author = (item.get('username') or '').casefold()
    share_id = item.get('share_id') or ''
    return ((kind, share_id) not in state['hidden'] and author not in state['suspended']
            and author not in state['blocked'])


def visibility_state(viewer=None):
    viewer = _username() if viewer is None else viewer
    with sqlite3.connect(_path()) as conn:
        return {
            'hidden': set(conn.execute('SELECT kind,content_id FROM content_hidden')),
            'suspended': {r[0].casefold() for r in conn.execute('SELECT username FROM content_suspensions')},
            'blocked': {r[0].casefold() for r in conn.execute('SELECT author FROM content_blocks WHERE viewer=?', (viewer,))},
        }


def restricted_authors(viewer=None):
    """Shared stats use the same restrictions before resolving caches or files."""
    if not enabled():
        return set()
    state = visibility_state(viewer)
    return state['suspended'] | state['blocked']


def author_suspended(author):
    if not enabled() or not author:
        return False
    with sqlite3.connect(_path()) as conn:
        return conn.execute('SELECT 1 FROM content_suspensions WHERE username=?', (author,)).fetchone() is not None


def filter_content(kind, items):
    if not enabled():
        return items
    # Set only by trusted account-deletion cleanup, never from request data.
    if has_request_context() and getattr(g, 'account_deletion_cleanup', False):
        return items
    # Admin report review uses raw storage, while ordinary lists respect blocks.
    state = visibility_state()
    return [item for item in items if _visible(kind, item, state)]


def content_visible(kind, item):
    return bool(item) and (not enabled() or _visible(kind, item, visibility_state()))


def _load_content(kind, content_id):
    if kind not in {'recap', 'flyer'} or not re.fullmatch(r'[A-Za-z0-9_-]{1,150}', str(content_id or '')):
        raise ContentSafetyError('Choose an existing recap or flyer.')
    if kind == 'recap':
        from admin_functions import get_ai_recap_page
        row = get_ai_recap_page(content_id)
    else:
        from flyer_functions import get_flyer_page
        row = get_flyer_page(content_id)
    if not row:
        raise ContentSafetyError('This content is no longer available.', 'not_found', 404)
    return row


def content_for_report(kind, content_id):
    row = _load_content(kind, content_id)
    if not content_visible(kind, row):
        raise ContentSafetyError('This content is no longer available.', 'not_found', 404)
    return row


def report_content(kind, content_id, reason):
    if not isinstance(reason, str) or not 5 <= len(reason.strip()) <= 2000:
        raise ContentSafetyError('Describe the problem in 5 to 2,000 characters.')
    row = _load_content(kind, content_id)
    reporter = _username()
    from account_lifecycle import AccountBusy, account_lock
    try:
        with account_lock(_path(), row.get('username') or '__legacy_content__'):
            # Deletion may have run between initial lookup and acquiring its
            # lock. Reload before storing any identifying report evidence.
            row = _load_content(kind, content_id)
            # Anonymous reports cannot hide an item globally; review decides.
            with sqlite3.connect(_path()) as conn:
                prior = conn.execute('SELECT id FROM content_reports WHERE reporter=? AND kind=? AND content_id=? AND status=\'open\'',
                                     (reporter, kind, content_id)).fetchone()
                if not prior:
                    conn.execute('INSERT INTO content_reports(reporter,kind,content_id,author,reason) VALUES (?,?,?,?,?)',
                                 (reporter, kind, content_id, row.get('username') or '', reason.strip()))
    except AccountBusy:
        raise ContentSafetyError('This content is being updated. Please try reporting it again shortly.', 'content_busy', 409) from None
    return {'success': True, 'message': 'Thank you. Your report is queued for review.'}


def blocked_users():
    with sqlite3.connect(_path()) as conn:
        authors = [r[0] for r in conn.execute(
            'SELECT author FROM content_blocks WHERE viewer=? ORDER BY author', (_username(),))]
        from account_names import account_label
        users = []
        for author in authors:
            try:
                row = conn.execute('SELECT display_name FROM site_users WHERE username=? COLLATE NOCASE', (author,)).fetchone()
            except sqlite3.OperationalError:
                row = None
            users.append({'username': author, 'display_name': account_label(author, row[0] if row else None)})
        return {'users': users}


def set_block(username, blocked):
    viewer = _username()
    if not viewer:
        raise ContentSafetyError('Please sign in to manage blocked users.', 'authentication_required', 401)
    if not isinstance(username, str) or not username.strip() or len(username) > 200 or username.casefold() == viewer.casefold():
        raise ContentSafetyError('Choose another content author to block.')
    with sqlite3.connect(_path()) as conn:
        conn.execute('DELETE FROM content_blocks WHERE viewer=? AND author=?', (viewer, username.strip()))
        if blocked:
            conn.execute('INSERT INTO content_blocks(viewer,author) VALUES (?,?)', (viewer, username.strip()))
    return blocked_users()


def list_reports():
    with closing(sqlite3.connect(_path())) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute('SELECT * FROM content_reports ORDER BY status=\'open\' DESC,id DESC LIMIT 500')]


def resolve_report(report_id, action):
    if action not in {'dismiss', 'hide', 'suspend'}:
        raise ContentSafetyError('Choose dismiss, hide, or suspend.')
    with sqlite3.connect(_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT * FROM content_reports WHERE id=?', (report_id,)).fetchone()
        if not row:
            raise ContentSafetyError('Report not found.', 'not_found', 404)
        if action == 'suspend' and (row['author'] or '').casefold() == _username().casefold():
            raise ContentSafetyError('You can remove this content, but cannot suspend your own administrator account.')
        if action in {'hide', 'suspend'}:
            conn.execute('INSERT OR REPLACE INTO content_hidden(kind,content_id,reason) VALUES (?,?,?)',
                         (row['kind'], row['content_id'], 'Removed after review'))
        if action == 'suspend' and row['author']:
            conn.execute('INSERT OR IGNORE INTO content_suspensions(username) VALUES (?)', (row['author'],))
    from account_lifecycle import AccountBusy, account_lock
    # A request normally holds its own shared account lock. Release it only
    # for a self-removal so acquiring the exclusive lock cannot deadlock.
    if row['author'] and row['author'].casefold() == _username().casefold():
        held = g.pop('account_lifecycle_lock', None)
        if held is not None:
            held.__exit__(None, None, None)
    try:
        with account_lock(_path(), row['author'] or '__legacy_content__', exclusive=True):
            _remove_reported_content(row, action)
    except (AccountBusy, OSError, sqlite3.Error):
        # Visibility remains blocked, but keep the report actionable until the
        # files are actually removed. Never report success on partial cleanup.
        with sqlite3.connect(_path()) as conn:
            conn.execute("UPDATE content_reports SET status='open',resolved_at=NULL WHERE id=?", (report_id,))
        raise ContentSafetyError('Content is hidden, but removal is still finishing. Please retry this report shortly.',
                                 'content_removal_pending', 409) from None
    with sqlite3.connect(_path()) as conn:
        conn.execute('UPDATE content_reports SET status=?,resolved_at=CURRENT_TIMESTAMP WHERE id=?', (action, report_id))
    return {'success': True}


def _remove_reported_content(row, action):
    def remove_page(kind, content_id):
        if kind == 'recap':
            from admin_functions import get_ai_recap_page as get, delete_ai_recap_page as remove
        else:
            from flyer_functions import get_flyer_page as get, delete_flyer_page as remove
        content = get(content_id)
        import admin_functions as admin
        from ai_library import library_lock, live_image_filenames
        with library_lock():
            with sqlite3.connect(_path()) as conn:
                pending = conn.execute('SELECT assets_json FROM content_removal_work WHERE kind=? AND content_id=?',
                                       (kind, content_id)).fetchone()
                candidates = set(json.loads(pending[0])) if pending else set()
                if content:
                    candidates |= admin._email_image_filenames_from_text(json.dumps(content))
                if not content and not pending:
                    return
                conn.execute('INSERT OR REPLACE INTO content_removal_work VALUES (?,?,?,?)',
                             (kind, content_id, (content or {}).get('username') or row['author'] or '', json.dumps(sorted(candidates))))
            if content is not None and not remove(content_id):
                raise OSError('Published content removal did not finish')
            # Normal retention cleanup is best effort. Moderation must report
            # an unlink failure so direct static media is not silently left up.
            for name in candidates - live_image_filenames() if candidates else set():
                if Path(name).name != name:
                    raise OSError('Invalid stored image filename')
                asset = Path(admin.email_images_dir()) / name
                if asset.suffix.lower() in admin._AI_IMAGE_EXTENSIONS:
                    asset.unlink(missing_ok=True)
            with sqlite3.connect(_path()) as conn:
                conn.execute('DELETE FROM content_removal_work WHERE kind=? AND content_id=?', (kind, content_id))

    if action == 'suspend' and row['author']:
        # Static hosting can bypass Flask. Remove all published works by this
        # author, while leaving private games/account settings available.
        from admin_functions import delete_ai_recap_page, list_ai_recap_pages
        from flyer_functions import delete_flyer_page, list_flyer_pages
        previous = getattr(g, 'account_deletion_cleanup', False)
        g.account_deletion_cleanup = True
        try:
            for kind, list_pages in [('recap', list_ai_recap_pages), ('flyer', list_flyer_pages)]:
                items, _ = list_pages(page=1, per_page=1000000, username=row['author'])
                for item in items:
                    with sqlite3.connect(_path()) as conn:
                        conn.execute('INSERT OR REPLACE INTO content_hidden(kind,content_id,reason) VALUES (?,?,?)',
                                     (kind, item['share_id'], 'Author suspended after review'))
                    remove_page(kind, item['share_id'])
        finally:
            g.account_deletion_cleanup = previous
        with sqlite3.connect(_path()) as conn:
            pending = list(conn.execute('SELECT kind,content_id FROM content_removal_work WHERE author=?', (row['author'],)))
        for kind, content_id in pending:
            remove_page(kind, content_id)
    if action in {'hide', 'suspend'}:
        # Remove the published files too: production can serve /static directly,
        # bypassing Flask. Existing cleanup preserves images used by other pages.
        remove_page(row['kind'], row['content_id'])


def delete_account_safety_data(conn, username):
    """Called inside account deletion; retain moderation evidence without identity."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table, where, args in [
        ('ai_data_consent', 'username=?', (username,)),
        ('content_blocks', 'viewer=? OR author=?', (username, username)),
        ('content_suspensions', 'username=?', (username,)),
        ('content_removal_work', 'author=?', (username,)),
    ]:
        if table in tables:
            conn.execute('DELETE FROM ' + table + ' WHERE ' + where, args)
    if 'content_reports' in tables:
        conn.execute("UPDATE content_reports SET reporter='',reason='Account deleted; original report details removed.' WHERE reporter=? COLLATE NOCASE", (username,))
        conn.execute("UPDATE content_reports SET author='',reason='Account deleted; original report details removed.' WHERE author=? COLLATE NOCASE", (username,))


def register_content_safety(app, service):
    app.config['CONTENT_SAFETY_DB'] = service._stats_db_path()
    init_safety(app.config['CONTENT_SAFETY_DB'])

    @app.teardown_request
    def release_content_author_lock(error):
        lock = g.pop('content_author_lock', None)
        if lock is not None:
            lock.__exit__(None, None, None)

    def json_body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ContentSafetyError('Send a JSON object.', 'invalid_request')
        return data

    @app.errorhandler(ContentSafetyError)
    def safety_error(exc):
        payload = dict(error=str(exc), code=exc.code)
        if exc.code == 'ai_consent_required':
            payload['consent'] = consent_state()
        if request.path.startswith('/api/') or request.is_json:
            return jsonify(payload), exc.status
        # Root's website page lets people consent before returning to their work.
        from flask import render_template
        return render_template('content_safety_error.html', error=str(exc), code=exc.code), exc.status

    @app.route('/api/privacy/ai-consent', methods=['GET', 'PUT'])
    def api_ai_consent():
        if not _username():
            raise ContentSafetyError('Please sign in first.', 'authentication_required', 401)
        if request.method == 'GET':
            return jsonify(consent_state())
        data = json_body()
        return jsonify(set_consent(_username(), data.get('granted'), data.get('version')))

    @app.post('/api/content/report')
    def api_content_report():
        data = json_body()
        return jsonify(report_content(data.get('kind'), data.get('id'), data.get('reason')))

    @app.route('/api/content/blocked-users', methods=['GET', 'POST', 'DELETE'])
    def api_content_blocks():
        if not _username():
            raise ContentSafetyError('Please sign in first.', 'authentication_required', 401)
        if request.method == 'GET':
            return jsonify(blocked_users())
        data = json_body()
        return jsonify(set_block(data.get('username'), request.method == 'POST'))

    @app.route('/api/admin/content-reports', methods=['GET'])
    def api_content_reports_admin():
        if not service.is_admin():
            abort(403)
        return jsonify(reports=list_reports())

    @app.post('/api/admin/content-reports/<int:report_id>')
    def api_content_report_resolve(report_id):
        if not service.is_admin():
            abort(403)
        data = json_body()
        return jsonify(resolve_report(report_id, data.get('action')))

    @app.before_request
    def enforce_content_safety():
        endpoint = request.endpoint or ''
        args = request.view_args or {}
        share_id = args.get('share_id')
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and share_id:
            # Admin edits/uploads also coordinate with the content owner's
            # deletion or suspension, not just the signed-in admin's account.
            kind = args.get('kind') or ('flyer' if 'flyer' in endpoint else 'recap')
            row = _load_content(kind, share_id)
            author = row.get('username') or ''
            if author and author.casefold() != _username().casefold():
                from account_lifecycle import AccountBusy, account_lock
                lock = account_lock(_path(), author)
                try:
                    lock.__enter__()
                except AccountBusy:
                    raise ContentSafetyError('This content is being updated. Please try again shortly.', 'content_busy', 409) from None
                g.content_author_lock = lock
                row = _load_content(kind, share_id)
            if author:
                with sqlite3.connect(_path()) as conn:
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='site_users'").fetchone():
                        user = conn.execute('SELECT active FROM site_users WHERE username=? COLLATE NOCASE', (author,)).fetchone()
                        if not user or not user[0]:
                            raise ContentSafetyError('The content owner is no longer active.', 'not_found', 404)
                g.content_owner = author
            if request.method != 'DELETE' and not content_visible(kind, row):
                raise ContentSafetyError('This content is no longer available.', 'not_found', 404)
        safety_api = endpoint in {'api_ai_consent', 'api_content_report', 'api_content_blocks',
                                  'api_content_report_resolve'}
        if safety_api and request.method in {'POST', 'PUT', 'DELETE'}:
            if not request.is_json:
                raise ContentSafetyError('Send this request as JSON.', 'invalid_request', 415)
            origin = request.headers.get('Origin')
            allowed_origins = {request.host_url.rstrip('/')}
            configured = current_app.config.get('SITE_BASE_URL') or os.environ.get('SITE_BASE_URL')
            if configured:
                parsed = urlsplit(configured)
                allowed_origins.add(parsed.scheme + '://' + parsed.netloc)
            if origin and origin not in allowed_origins:
                raise ContentSafetyError('This request must come from the stats app or website.', 'invalid_origin', 403)
        if request.method in {'POST', 'PUT', 'PATCH'}:
            submitted = request.get_json(silent=True) if request.is_json else request.form.to_dict()
            if isinstance(submitted, dict):
                for key, value in submitted.items():
                    if key in TEXT_FIELDS:
                        check_local_text(value)
            if _username() and endpoint not in {'api_ai_consent', 'privacy_settings', 'private_delete_account',
                                               'api_logout', 'logout', 'api_content_report', 'report_content_page'}:
                with sqlite3.connect(_path()) as conn:
                    if conn.execute('SELECT 1 FROM content_suspensions WHERE username=?', (_username(),)).fetchone():
                        raise ContentSafetyError('This account has been suspended.', 'account_suspended', 403)
            generating = endpoint in AI_ENDPOINTS
            if endpoint == 'api_generate_player_ai_image' and isinstance(submitted, dict) and (
                    submitted.get('remove') or submitted.get('delete_path')):
                generating = False
            uploading = bool(request.files) and endpoint in UPLOAD_ENDPOINTS
            editing = endpoint == 'api_edit_ai_library_item' and request.method == 'PUT'
            if generating or uploading or editing:
                require_ai_consent()
                data = request.get_json(silent=True) if request.is_json else request.form.to_dict()
                if not isinstance(data, dict):
                    raise ContentSafetyError('Send valid form data.', 'invalid_request')
                text = '\n'.join(str(value) for key, value in data.items() if key in TEXT_FIELDS and value)
                moderate_content(text)
                for upload in request.files.values():
                    raw = upload.read(10 * 1024 * 1024 + 1)
                    upload.stream.seek(0)
                    if len(raw) > 10 * 1024 * 1024:
                        raise ContentSafetyError('Photos must be 10 MB or smaller.')
                    moderate_content(image_bytes=raw, image_mime=upload.mimetype or 'image/jpeg')
        # Check public pages and derivative downloads before any cached file is served.
        if share_id and endpoint in {'view_ai_recap', 'recap_og_image', 'recap_instagram_slide',
                                     'recap_instagram_zip', 'view_flyer', 'download_flyer'}:
            kind = 'flyer' if endpoint in {'view_flyer', 'download_flyer'} else 'recap'
            row = _load_content(kind, share_id)
            if not content_visible(kind, row):
                abort(404)

    @app.after_request
    def safety_response_headers(response):
        if request.endpoint in {'api_ai_consent', 'api_content_report', 'api_content_blocks',
                                'api_content_reports_admin', 'api_content_report_resolve',
                                'view_ai_recap', 'view_flyer', 'api_my_recaps', 'api_my_flyers'}:
            response.headers['Cache-Control'] = 'private, no-store'
            response.vary.add('Cookie')
            response.vary.add('Authorization')
        return response
