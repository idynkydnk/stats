from flask import Flask, render_template, request, url_for, flash, redirect, session, jsonify, make_response, send_from_directory, abort
from werkzeug.security import check_password_hash
# Flask-Caching is optional - the custom caching in stat_functions.py will still work
try:
    from flask_caching import Cache
    FLASK_CACHING_AVAILABLE = True
except ImportError:
    FLASK_CACHING_AVAILABLE = False
from flask_mail import Mail, Message
from database_functions import *
from stat_functions import *
from stat_functions import clear_stats_cache
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from vollis_functions import *
from other_functions import *
from kob_functions import update_kobs
from email_content import (
    build_doubles_email_payload,
    build_vollis_email_payload,
    build_other_email_payload,
    generate_ai_text,
    email_html_for_inline_preview,
    recap_html_for_page,
    replace_recap_hero_image,
    personalize_ai_email_content,
    plain_text_fallback_from_html,
    image_mode_label,
    _normalize_image_mode,
    _try_generate_email_hero_image,
    EMAIL_PLACEHOLDER,
    SITE_BASE_URL as EMAIL_SITE_BASE_URL,
)
import admin_functions as adminfx
import ai_auto_send_jobs as ai_jobs
import os
import subprocess
import sqlite3
import secrets
import hashlib
import json
import re
import threading
import time
import random

# Load environment variables from .env file if it exists (optional, for local development)
# Only load if dotenv is available - not required on PythonAnywhere where env vars are set in WSGI file
try:
    from dotenv import load_dotenv
    load_dotenv()
except (ImportError, ModuleNotFoundError):
    # dotenv not available (e.g., on PythonAnywhere) - that's fine, use environment variables directly
    pass

app = Flask(__name__)
# SECRET_KEY comes from the environment (.env locally, WSGI file on PythonAnywhere).
# Fallback is a random key per process: the app still runs, but session cookies reset
# on each restart until SECRET_KEY is set. Remember-me tokens live in the DB and survive.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
# Stay logged in across browser closes (session cookie lives 90 days when permanent)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=90)

# Cache configuration - cache expensive calculations for 5 minutes
# Flask-Caching is optional - stat_functions.py has its own caching that works without it
if FLASK_CACHING_AVAILABLE:
    app.config['CACHE_TYPE'] = 'SimpleCache'
    app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutes
    cache = Cache(app)

# Email configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@stats.com')
app.config['AI_EMAIL_COPY_TO'] = os.environ.get('AI_EMAIL_COPY_TO', 'idynkydnk@gmail.com')
app.config['AI_EMAIL_REPLY_TO'] = (
    os.environ.get('AI_EMAIL_REPLY_TO', '').strip()
    or os.environ.get('AI_EMAIL_COPY_TO', 'idynkydnk@gmail.com').split(',')[0].strip()
)
app.config['SITE_BASE_URL'] = os.environ.get('SITE_BASE_URL', EMAIL_SITE_BASE_URL)

mail = Mail(app)


class InlineImageMessage(Message):
    """Flask-Mail Message that uses multipart/related for inline images.

    Flask-Mail nests inline CID images as siblings of multipart/alternative
    inside multipart/mixed. Mobile clients (Gmail iOS, Apple Mail iOS) often
    fail to resolve cid: references in that layout; desktop clients are more
    forgiving. Restructuring to multipart/related fixes mobile rendering.
    """

    def _message(self):
        msg = super()._message()
        return _restructure_inline_image_mime(msg)


def _restructure_inline_image_mime(msg):
    """Move inline image parts under multipart/related with the HTML body."""
    from email.mime.multipart import MIMEMultipart

    if not hasattr(msg, 'get_payload'):
        return msg

    parts = msg.get_payload()
    if not isinstance(parts, list) or len(parts) < 2:
        return msg

    alternative_parts = []
    inline_parts = []
    attachment_parts = []

    for part in parts:
        disposition = (part.get('Content-Disposition') or '').lower()
        if part.get_content_type() == 'multipart/alternative':
            alternative_parts.append(part)
        elif disposition.startswith('inline'):
            inline_parts.append(part)
        else:
            attachment_parts.append(part)

    if not inline_parts:
        return msg

    if attachment_parts:
        outer = MIMEMultipart('mixed')
        related = MIMEMultipart('related')
        for part in alternative_parts + inline_parts:
            related.attach(part)
        outer.attach(related)
        for part in attachment_parts:
            outer.attach(part)
        new_root = outer
    else:
        related = MIMEMultipart('related')
        for part in alternative_parts + inline_parts:
            related.attach(part)
        new_root = related

    for key, value in msg.items():
        if key not in new_root:
            new_root[key] = value
    return new_root


def _ai_email_copy_addresses():
    addrs = set()
    for raw in (app.config.get('AI_EMAIL_COPY_TO') or '').replace(',', ' ').replace(';', ' ').split():
        addr = raw.strip()
        if addr and '@' in addr:
            addrs.add(addr)
    return addrs


def _filter_ai_email_opt_outs(recipients):
    """Skip players who unsubscribed; always keep configured copy addresses."""
    copy_addrs = _ai_email_copy_addresses()
    cur = set_cur()
    out = []
    for addr in recipients:
        if addr in copy_addrs:
            out.append(addr)
            continue
        cur.execute("SELECT notes FROM players WHERE email = ?", (addr,))
        row = cur.fetchone()
        if row and 'AI_EMAILS_OPT_OUT' in (row[0] or ''):
            continue
        out.append(addr)
    return out


def _hero_image_path_from_url(hero_image_url, hero_image_path=None):
    if hero_image_path and os.path.isfile(hero_image_path):
        return hero_image_path
    if not hero_image_url:
        return None
    marker = '/static/email_images/'
    if marker not in hero_image_url:
        return None
    filename = hero_image_url.split(marker, 1)[1].split('?', 1)[0]
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, 'static', 'email_images', filename)
    return path if os.path.isfile(path) else None


def _hero_mime_type(path):
    ext = os.path.splitext(path)[1].lower()
    return {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
    }.get(ext, 'image/png')


def build_ai_summary_message(subject, html_body, plain_text_body, to_addr,
                             hero_image_url=None, hero_image_path=None):
    from email_content import HERO_IMAGE_CID
    from urllib.parse import quote

    hero_path = _hero_image_path_from_url(hero_image_url, hero_image_path)
    html, body = personalize_ai_email_content(
        html_body,
        plain_text_body,
        to_addr,
        hero_image_url=hero_image_url,
        embed_hero=bool(hero_path),
    )
    if not (body or '').strip():
        body = plain_text_fallback_from_html(html) or 'Your game recap is in the HTML version of this email.'

    msg = InlineImageMessage(subject=subject, recipients=[to_addr])
    msg.html = html if html.strip() else '<p>No content.</p>'
    msg.body = body

    reply_to = (app.config.get('AI_EMAIL_REPLY_TO') or '').strip()
    if reply_to:
        msg.reply_to = reply_to

    email_param = quote(to_addr.strip(), safe='')
    site_base = app.config.get('SITE_BASE_URL') or EMAIL_SITE_BASE_URL
    unsub_url = f'{site_base}/opt_out_ai_emails?email={email_param}'
    msg.extra_headers = {
        'List-Unsubscribe': f'<{unsub_url}>',
        'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
    }

    if hero_path:
        ext = os.path.splitext(hero_path)[1] or '.png'
        with open(hero_path, 'rb') as fp:
            data = fp.read()
        msg.attach(
            f'hero{ext}',
            _hero_mime_type(hero_path),
            data,
            'inline',
            headers={'Content-ID': f'<{HERO_IMAGE_CID}>'},
        )
    return msg


def _ai_email_public_recipients(recipients):
    """Recipients shown in send counts.

    Called before copy addresses are appended. A configured copy address
    already in recipients is a player in the game and should be counted;
    copy-only adds happen later via extend_ai_email_recipients.
    """
    return list(recipients)


def _ai_email_public_sent_count(public_recipients, errors):
    """Successful sends among public recipients only."""
    failed = set()
    for err in errors:
        for addr in public_recipients:
            if err.startswith(f'{addr}:'):
                failed.add(addr)
                break
    return len(public_recipients) - len(failed)


def send_ai_summary_messages(subject, html_body, plain_text_body, recipients,
                             hero_image_url=None, hero_image_path=None):
    recipients = _filter_ai_email_opt_outs(recipients)
    public_recipients = _ai_email_public_recipients(recipients)
    all_recipients = extend_ai_email_recipients(recipients)
    if not all_recipients:
        return 0, ['No recipients after filtering opt-outs.']
    messages = [
        build_ai_summary_message(
            subject,
            html_body,
            plain_text_body,
            to_addr,
            hero_image_url=hero_image_url,
            hero_image_path=hero_image_path,
        )
        for to_addr in all_recipients
    ]
    _, errors = send_messages_with_retry(messages)
    return _ai_email_public_sent_count(public_recipients, errors), errors


def extend_ai_email_recipients(recipients):
    """Append configured copy address(es) to every AI summary send."""
    out = list(recipients)
    for raw in (app.config.get('AI_EMAIL_COPY_TO') or '').replace(',', ' ').replace(';', ' ').split():
        addr = raw.strip()
        if addr and '@' in addr and addr not in out:
            out.append(addr)
    return out


def send_messages_with_retry(messages, max_attempts=3):
    """Send email messages over a single SMTP connection, retrying transient failures.

    PythonAnywhere's outbound network intermittently fails with errors like
    '[Errno 101] Network is unreachable' or timeouts; a retry a moment later
    almost always succeeds. Opening one connection for the whole batch (instead
    of one per recipient) also avoids repeated connects, which is where that
    error is raised. Permanent failures (refused recipients) are not retried.

    Returns (sent_count, errors) where errors is a list of 'recipient: error'
    strings for messages that could not be sent.
    """
    import smtplib
    import socket
    import time as _time
    from contextlib import contextmanager

    @contextmanager
    def prefer_ipv4():
        """Sort IPv4 results first in DNS lookups while connecting.

        '[Errno 101] Network is unreachable' usually means the resolver returned
        an IPv6 address first and the server has no IPv6 route. IPv6 results are
        kept as a fallback, just tried last.
        """
        original = socket.getaddrinfo

        def ipv4_first(*args, **kwargs):
            results = original(*args, **kwargs)
            return sorted(results, key=lambda r: 0 if r[0] == socket.AF_INET else 1)

        socket.getaddrinfo = ipv4_first
        try:
            yield
        finally:
            socket.getaddrinfo = original

    pending = list(messages)
    last_error = {}  # id(msg) -> (msg, error string)
    sent = 0

    for attempt in range(1, max_attempts + 1):
        if not pending:
            break
        if attempt > 1:
            _time.sleep(2 * (attempt - 1))
        try:
            with prefer_ipv4(), mail.connect() as conn:
                remaining = []
                for msg in pending:
                    try:
                        conn.send(msg)
                        sent += 1
                        last_error.pop(id(msg), None)
                    except smtplib.SMTPRecipientsRefused as e:
                        # Permanent: bad recipient, don't retry
                        last_error[id(msg)] = (msg, str(e))
                    except Exception as e:
                        # Transient (broken connection etc.): retry next attempt
                        last_error[id(msg)] = (msg, str(e))
                        remaining.append(msg)
                pending = remaining
        except Exception as e:
            # Could not even connect; keep the whole batch for the next attempt
            for msg in pending:
                last_error[id(msg)] = (msg, str(e))

    errors = []
    for msg, err in last_error.values():
        to = ', '.join(msg.recipients or ['(unknown)'])
        errors.append(f'{to}: {err}')
    return sent, errors


def _ai_image_log_note(payload):
    """Short illustration note for activity log entries."""
    mode = _normalize_image_mode(payload.get('image_mode'))
    if mode == 'none':
        return ' (text only)'
    if payload.get('hero_image_url'):
        return f' ({image_mode_label(mode)})'
    if payload.get('hero_image_error'):
        return f' (image failed: {payload["hero_image_error"][:120]})'
    return ''


def _ai_summary_header_label(game_type):
    type_labels = {'doubles': 'Doubles', 'vollis': 'Vollis', 'other': 'Other'}
    return type_labels.get(game_type, 'Doubles')


def _render_ai_summary_preview_page(
    game_type,
    subject,
    email_html,
    plain_text_body,
    players,
    players_without_email,
    selected_game_ids,
    hero_image_url='',
    hero_image_path='',
    hero_image_error='',
    image_mode='none',
    illustration_note='',
    solo_images=None,
    checked_emails=None,
    additional_emails_value='',
):
    """Render the AI summary preview page (used after generation and after send failures)."""
    selected_game_ids = [str(gid) for gid in (selected_game_ids or [])]
    can_send = len(players) > 0 or bool(additional_emails_value.strip())
    template_ctx = {
        'game_type': game_type,
        'header_title': f"{_ai_summary_header_label(game_type)} AI Summary Preview",
        'subject': subject or '',
        'email_html': email_html or '',
        'plain_text_body': plain_text_body or '',
        'email_preview_html': email_html_for_inline_preview(email_html or ''),
        'hero_image_url': hero_image_url or '',
        'hero_image_path': hero_image_path or '',
        'hero_image_error': hero_image_error or '',
        'image_mode': _normalize_image_mode(image_mode),
        'illustration_note': illustration_note or '',
        'solo_images': solo_images or [],
        'players': players or [],
        'players_without_email': players_without_email or [],
        'selected_game_ids_json': json.dumps(selected_game_ids),
        'selected_game_ids': selected_game_ids,
        'send_url': url_for('generate_and_email_today'),
        'back_url': url_for('ai_summary'),
        'can_send': can_send,
        'additional_emails_value': additional_emails_value or '',
    }
    if checked_emails is not None:
        template_ctx['checked_emails'] = set(checked_emails)
    return render_template('preview_ai_summary.html', **template_ctx)


def _parse_solo_images_json(raw):
    try:
        data = json.loads(raw or '[]')
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _ai_summary_preview_from_form(form):
    """Rebuild preview page context from the send-email form (preserves generated content)."""
    players = []
    players_without_email = []
    try:
        players = json.loads(form.get('players_json') or '[]')
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        players_without_email = json.loads(form.get('players_without_email_json') or '[]')
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        'game_type': form.get('game_type') or 'doubles',
        'subject': form.get('subject') or 'Vball Summary',
        'email_html': form.get('email_html') or '',
        'plain_text_body': form.get('plain_text_body') or '',
        'players': players,
        'players_without_email': players_without_email,
        'selected_game_ids': form.getlist('selected_game_ids'),
        'hero_image_url': form.get('hero_image_url') or '',
        'hero_image_path': form.get('hero_image_path') or '',
        'hero_image_error': form.get('hero_image_error') or '',
        'image_mode': form.get('image_mode') or 'none',
        'illustration_note': form.get('illustration_note') or '',
        'solo_images': _parse_solo_images_json(form.get('solo_images_json')),
        'checked_emails': form.getlist('recipient_emails'),
        'additional_emails_value': form.get('additional_emails') or '',
    }


def _build_ai_summary_payload(
    game_type, selected_game_ids, prompt_style, custom_prompt, image_mode='none',
    image_details='',
):
    """Build AI email payload for doubles, vollis, or other games."""
    kwargs = {
        'prompt_style': prompt_style,
        'custom_prompt': custom_prompt,
        'image_mode': image_mode,
        'image_details': image_details,
    }
    if game_type == 'vollis':
        return build_vollis_email_payload(selected_game_ids, **kwargs)
    if game_type == 'other':
        return build_other_email_payload(selected_game_ids, **kwargs)
    return build_doubles_email_payload(selected_game_ids, **kwargs)


def _refresh_instagram_slides(share_id, html_body='', plain_text_body='', subject='',
                              hero_image_url='', force=True):
    """Build (or rebuild) the 4 Instagram carousel JPEGs for a published recap."""
    from email_content import ensure_instagram_slides

    try:
        return ensure_instagram_slides(
            share_id,
            html_body or '',
            plain_text_body=plain_text_body or '',
            subject=subject or '',
            hero_image_url=hero_image_url or '',
            force=force,
        )
    except Exception:
        app.logger.exception('Instagram slide generation failed for /recap/%s/', share_id)
        return []


def _publish_ai_recap(payload, prompt_style, custom_prompt, game_ids, username=None):
    """Save a generated AI recap as a public shareable page."""
    illustration_meta = payload.get('illustration_meta') or {}
    solo_images = illustration_meta.get('solo_images') or []
    style_instructions = (payload.get('style_instructions') or '').strip()
    # Prefer the resolved style for later remakes; fall back to the typed custom prompt.
    saved_custom = style_instructions or (custom_prompt or '').strip()
    share_id = secrets.token_urlsafe(9)
    while adminfx.get_ai_recap_page(share_id):
        share_id = secrets.token_urlsafe(9)
    html_body = payload.get('html_body') or ''
    plain_text_body = payload.get('plain_text_body') or ''
    subject = payload.get('subject') or ''
    hero_image_url = payload.get('hero_image_url') or ''
    adminfx.insert_ai_recap_page(
        share_id=share_id,
        username=username or session.get('username') or 'unknown',
        game_type=payload.get('game_type') or 'doubles',
        subject=subject,
        html_body=html_body,
        plain_text_body=plain_text_body,
        hero_image_url=hero_image_url,
        hero_image_error=payload.get('hero_image_error') or '',
        game_ids_json=json.dumps(list(game_ids), default=str) if game_ids else '[]',
        prompt_style=prompt_style or '',
        custom_prompt=saved_custom,
        style_instructions=style_instructions,
        solo_images_json=json.dumps(solo_images) if solo_images else '',
        image_details=payload.get('image_details') or '',
        image_mode=payload.get('image_mode') or 'none',
    )
    _refresh_instagram_slides(
        share_id,
        html_body=html_body,
        plain_text_body=plain_text_body,
        subject=subject,
        hero_image_url=hero_image_url,
        force=True,
    )
    return share_id


def _load_games_and_players_for_recap(game_type, game_ids):
    """Load selected games and player names for regenerating a recap illustration."""
    ids = [int(gid) for gid in game_ids]
    if not ids:
        raise ValueError('No games saved for this recap.')
    placeholders = ','.join('?' * len(ids))

    if game_type == 'vollis':
        from vollis_functions import convert_vollis_ampm
        from database_functions import create_connection
        conn = create_connection('/home/Idynkydnk/stats/stats.db') or create_connection('stats.db')
        cur = conn.cursor()
        cur.execute(
            f'SELECT * FROM vollis_games WHERE id IN ({placeholders}) ORDER BY game_date DESC',
            ids,
        )
        games = convert_vollis_ampm(cur.fetchall())
        conn.close()
        players = set()
        for game in games:
            for name in (game[2], game[4]):
                if name and str(name).strip():
                    players.add(name)
        return games, players, None

    if game_type == 'other':
        from other_functions import readable_games_data, _is_valid_player_name
        from database_functions import create_connection
        import sqlite3 as _sqlite3
        conn = create_connection('/home/Idynkydnk/stats/stats.db') or create_connection('stats.db')
        conn.row_factory = _sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            f'SELECT * FROM other_games WHERE id IN ({placeholders}) ORDER BY game_date DESC',
            ids,
        )
        games = readable_games_data(cur.fetchall())
        conn.close()
        players = set()
        game_names = set()
        for game in games:
            if game.get('game_name'):
                game_names.add(game['game_name'])
            for side in ('winners', 'losers'):
                for person in game.get(side, []):
                    name = person.get('name', '')
                    if name and _is_valid_player_name(name):
                        players.add(name)
        game_name = ', '.join(sorted(game_names)) if game_names else 'Other'
        return games, players, game_name

    from stat_functions import convert_ampm
    cur = set_cur()
    cur.execute(
        f'SELECT * FROM games WHERE id IN ({placeholders}) ORDER BY game_date DESC',
        ids,
    )
    games = convert_ampm(cur.fetchall())
    players = set()
    for game in games:
        for name in (game[2], game[3], game[5], game[6]):
            if name and str(name).strip():
                players.add(name)
    return games, players, None


def _send_ai_summary_payload(payload, username='unknown'):
    """Email an AI summary payload to all players with addresses plus copy-to."""
    if not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
        raise ValueError('Email not configured.')

    subject = payload.get('subject') or 'Vball Summary'
    email_html = payload.get('html_body') or ''
    plain_text_body = payload.get('plain_text_body') or ''
    hero_image_url = payload.get('hero_image_url')
    hero_image_path = payload.get('hero_image_path')
    recipients = [
        p['email'].strip()
        for p in payload.get('players', [])
        if p.get('email') and str(p['email']).strip()
    ]
    if not recipients:
        raise ValueError('No recipients with email addresses for the selected games.')

    emails_sent, errors = send_ai_summary_messages(
        subject,
        email_html,
        plain_text_body,
        recipients,
        hero_image_url=hero_image_url,
        hero_image_path=hero_image_path,
    )
    if errors:
        log_activity(
            'Email send failed',
            summary=f'AI auto-send "{subject}": sent to {emails_sent}, {len(errors)} failed: {"; ".join(errors)[:200]}',
            username=username,
        )
    else:
        log_activity(
            'Sent email',
            summary=f'AI auto-send "{subject}" to {emails_sent} recipient(s)',
            username=username,
        )
    return emails_sent, errors


def run_ai_auto_send_job(
    username, game_ids, game_type, prompt_style, custom_prompt,
    image_mode='none', image_details='',
):
    """Generate AI summary and publish a shareable recap page."""
    with app.app_context():
        try:
            payload = _build_ai_summary_payload(
                game_type, game_ids, prompt_style, custom_prompt,
                image_mode=image_mode, image_details=image_details,
            )
            _save_ai_prompt_log(payload, prompt_style, custom_prompt, game_ids, username=username)
            img_note = _ai_image_log_note(payload)
            share_id = _publish_ai_recap(
                payload, prompt_style, custom_prompt, game_ids, username=username,
            )
            subject = payload.get('subject') or 'Vball Summary'
            hero_for_share = adminfx.absolutize_hero_image_url(
                payload.get('hero_image_url') or '',
                app.config.get('SITE_BASE_URL') or EMAIL_SITE_BASE_URL,
            )
            share_url = url_for(
                'view_ai_recap',
                share_id=share_id,
                _external=True,
                **adminfx.recap_share_query_args(hero_for_share),
            )
            log_activity(
                'Published AI recap',
                summary=(
                    f'{game_type} recap for {len(game_ids)} game(s), style "{prompt_style}"'
                    + img_note
                ),
                username=username,
            )
            return {
                'success': True,
                'share_id': share_id,
                'share_url': share_url,
                'subject': subject,
            }
        except Exception as e:
            app.logger.exception('AI recap publish failed')
            log_activity(
                'AI summary failed',
                summary=f'{game_type} recap for {len(game_ids)} game(s): {str(e)[:200]}',
                username=username,
            )
            return {'success': False, 'error': str(e)[:300]}


def _supabase_flash_suffix(supabase_ok):
    """Return flash message suffix for Supabase sync status (True/False/None)."""
    if supabase_ok is True:
        return ' Synced to Supabase.'
    if supabase_ok is False:
        return ' Supabase sync failed.'
    return ' (Supabase not configured.)'

# Legacy seed users - only used to populate the site_users DB table on first run.
# After that, users live in the database and are managed from the /admin page.
# Passwords are werkzeug pbkdf2 hashes, never plaintext.
USERS = {
    'kyle': 'pbkdf2:sha256:260000$x1zU6VqW1aTl88DR$e007afc1b4d32fee014d14c1f8376a535b0dc9f62a285bde81374ea4330f2e47',
    'aaron': 'pbkdf2:sha256:260000$9TvOpo8SprF7XljN$67b49134c7baec674e8464475fc8b92605068d9c24005ae4c438ad3708dd4105',
    'dan': 'pbkdf2:sha256:260000$6KBD6pvcm2iolqSA$51e8af1de015b689917d6ceb29cf6dd2b61a9aeeefa6c15a31889708f297e167',
    'ryan': 'pbkdf2:sha256:260000$ieJam4WevIp0HbDv$6f10272595d186052d1392e83c7a5332b46e7277fef1aaddb4b07b15b6bd5710',
    'arbel': 'pbkdf2:sha256:260000$uyEex6wjretzvU9R$ada59f54c3ea7a9cd03e5f6bdb52e619d7e9727ae7fbd88b43e1473a0ed24881',
    'mark': 'pbkdf2:sha256:260000$nMljS3zc86cNQpVa$c7a86794395d1eb70274cc2fd7e429201d92e77ffa55506ce787968d01fdcd16',
    'troy': 'pbkdf2:sha256:260000$KPm2XJKdTb41DX87$636369a4264b2c7d9643551501b62718fc0a07e8db19ff5379c74608392d15bf',
    'jason': 'pbkdf2:sha256:260000$f9ODxWNNQ392rwMq$38681d54120fde7624cebea606413e1800f0fcc17a357e8a551e2de2623ad4ea',
    'iosapp': 'pbkdf2:sha256:260000$BzqYrJSydBHGcaFa$04ac62a42b1af2dadd05d2deaece7dcd8b6ee73abd817e94c729f6ad3b934a80',
}


def verify_password(username, password):
    """Check a username/password pair against the site_users table.
    Inactive (deactivated) users are rejected."""
    if not password:
        return False
    user = adminfx.get_site_user(username)
    if user:
        if not user.get('active'):
            return False
        return check_password_hash(user['password_hash'], password)
    # Fallback for the seed dict in case the DB table is unavailable
    password_hash = USERS.get(username)
    if not password_hash:
        return False
    return check_password_hash(password_hash, password)


# --- Simple in-memory rate limiting for login endpoints (no extra dependency) ---
_login_failures = {}  # ip -> list of failure timestamps
_login_failures_lock = threading.Lock()
LOGIN_MAX_FAILURES = 10       # allowed failures per window
LOGIN_WINDOW_SECONDS = 300    # 5 minutes


def _client_ip():
    """Client IP, preferring the proxy header PythonAnywhere sets."""
    return request.headers.get('X-Real-IP') or request.remote_addr or 'unknown'


def login_rate_limited(ip):
    """True if this IP has too many recent failed logins."""
    now = time.time()
    with _login_failures_lock:
        recent = [t for t in _login_failures.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
        _login_failures[ip] = recent
        return len(recent) >= LOGIN_MAX_FAILURES


def record_login_failure(ip):
    now = time.time()
    with _login_failures_lock:
        _login_failures.setdefault(ip, []).append(now)


def clear_login_failures(ip):
    with _login_failures_lock:
        _login_failures.pop(ip, None)

# Users with access to admin-only pages (dashboard, benchmarks, admin base template)
ADMIN_USERS = {'kyle'}


def is_admin(username=None):
    """True if the given username (or the current session user) is an admin.
    Admin flag lives in the site_users table; ADMIN_USERS is an always-admin fallback."""
    if username is None:
        username = session.get('username', '')
    if not username:
        return False
    if (username or '').lower() in ADMIN_USERS:
        return True
    try:
        user = adminfx.get_site_user(username)
        if user:
            return bool(user.get('is_admin')) and bool(user.get('active'))
    except Exception:
        pass
    return False


def _stats_db_path():
    """Single path for stats DB (games + auth_tokens). Use this everywhere so API and login share the same DB."""
    path = '/home/Idynkydnk/stats/stats.db'
    if os.path.exists(path):
        return path
    return 'stats.db'


@app.context_processor
def inject_base_template():
    """Inject base template and admin flag for shared navigation."""
    return {
        'base_template': 'base.html',
        'is_admin_user': is_admin() if session.get('logged_in') else False,
    }


@app.template_filter('game_year')
def game_year_filter(date_str):
    """Extract a 4-digit year from a display date like 07/15/2026 or 07/15/26."""
    import re
    s = str(date_str or '')
    match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', s)
    if match:
        year = match.group(3)
        if len(year) == 2:
            year = ('19' if int(year) >= 70 else '20') + year
        return year
    match = re.match(r'(\d{4})', s)
    if match:
        return match.group(1)
    return str(date.today().year)


def init_auth_tokens_db():
    """Initialize the auth_tokens table for remember me functionality"""
    conn = sqlite3.connect(_stats_db_path())
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS auth_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def generate_auth_token():
    """Generate a secure random token"""
    return secrets.token_urlsafe(32)

def hash_token(token):
    """Hash a token for secure storage"""
    return hashlib.sha256(token.encode()).hexdigest()

def create_auth_token(username):
    """Create a new authentication token for a user"""
    token = generate_auth_token()
    token_hash = hash_token(token)
    expires_at = datetime.now() + timedelta(days=90)  # Token expires in 90 days
    
    conn = sqlite3.connect(_stats_db_path())
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO auth_tokens (username, token_hash, expires_at)
        VALUES (?, ?, ?)
    ''', (username, token_hash, expires_at))
    conn.commit()
    conn.close()
    
    return token

def validate_auth_token(token):
    """Validate an authentication token and return username if valid"""
    if not token:
        return None
    
    token_hash = hash_token(token)
    conn = sqlite3.connect(_stats_db_path())
    cur = conn.cursor()
    cur.execute('''
        SELECT username FROM auth_tokens 
        WHERE token_hash = ? AND expires_at > ?
    ''', (token_hash, datetime.now()))
    
    result = cur.fetchone()
    conn.close()
    
    return result[0] if result else None

def revoke_auth_token(token):
    """Revoke a specific authentication token"""
    if not token:
        return
    
    token_hash = hash_token(token)
    conn = sqlite3.connect(_stats_db_path())
    cur = conn.cursor()
    cur.execute('DELETE FROM auth_tokens WHERE token_hash = ?', (token_hash,))
    conn.commit()
    conn.close()

def revoke_all_user_tokens(username):
    """Revoke all authentication tokens for a user"""
    conn = sqlite3.connect(_stats_db_path())
    cur = conn.cursor()
    cur.execute('DELETE FROM auth_tokens WHERE username = ?', (username,))
    conn.commit()
    conn.close()

def cleanup_expired_tokens():
    """Remove expired authentication tokens"""
    conn = sqlite3.connect(_stats_db_path())
    cur = conn.cursor()
    cur.execute('DELETE FROM auth_tokens WHERE expires_at <= ?', (datetime.now(),))
    conn.commit()
    conn.close()

def log_user_action(user, action, details=None):
    """Deprecated: activity belongs on the admin dashboard via log_activity."""
    return

def get_user_now():
    """Get the current datetime in the user's timezone (from session).
    Falls back to server local time if no timezone is set."""
    user_tz = session.get('timezone')
    if user_tz:
        try:
            tz = ZoneInfo(user_tz)
            return datetime.now(tz).replace(tzinfo=None)  # Return naive datetime for DB storage
        except Exception:
            pass
    return datetime.now()


def get_user_now_only():
    """Return current time in the user's timezone (from session) for adding games.
    Never uses server time. Returns None if session timezone is not set."""
    user_tz = session.get('timezone')
    if not user_tz:
        return None
    try:
        tz = ZoneInfo(user_tz)
        return datetime.now(tz).replace(tzinfo=None)
    except Exception:
        return None

def parse_client_datetime_for_game(client_date, client_time):
    """Parse browser local date/time. Returns 'YYYY-MM-DD HH:MM:SS' or None.
    Accepts client_time as HH:MM or HH:MM:SS so older clients still work."""
    if not client_date or not client_time:
        return None
    try:
        ct = client_time.strip()
        cd = client_date.strip()
        if len(ct) >= 8 and ct.count(':') >= 2:
            dt = datetime.strptime(f"{cd} {ct[:8]}", '%Y-%m-%d %H:%M:%S')
        else:
            dt = datetime.strptime(f"{cd} {ct[:5]}", '%Y-%m-%d %H:%M')
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return None

# Initialize database tables
init_auth_tokens_db()
adminfx.init_activity_log_db()
adminfx.init_ai_prompt_log_db()
adminfx.init_ai_recap_pages_db()
ai_jobs.init_ai_auto_send_jobs_db()
adminfx.init_users_db(seed_users=USERS, seed_admins=ADMIN_USERS)
from player_functions import init_players_photo_column
init_players_photo_column()


def player_photo_url_for(name):
    """Static URL for a player's uploaded photo, or None."""
    from player_functions import get_player_photo_path
    path = get_player_photo_path(name)
    if path:
        return url_for('static', filename=path)
    return None


@app.route('/player_face_thumb/<path:name>')
def player_face_thumb(name):
    """Serve a small server-cropped face avatar for public player pages."""
    from flask import Response, abort
    from player_functions import read_face_avatar_image

    name = name.strip()
    if not name:
        abort(404)
    data, mime = read_face_avatar_image(name)
    if not data:
        abort(404)
    return Response(
        data,
        mimetype=mime or 'image/jpeg',
        headers={'Cache-Control': 'public, max-age=3600'},
    )


def player_full_body_photos_for(name):
    """Full-body photos with static paths, URLs, and crop focus."""
    from player_functions import get_player_full_body_photo_paths, get_full_body_photo_crop
    photos = []
    for path in get_player_full_body_photo_paths(name):
        focus = get_full_body_photo_crop(name, path)
        photos.append({
            'path': path,
            'url': url_for('static', filename=path),
            'focus': {
                'x': focus['x'],
                'y': focus['y'],
                'z': focus.get('z'),
                'aspect': focus.get('aspect'),
                'w': focus.get('w'),
                'h': focus.get('h'),
            },
        })
    return photos


def player_ai_image_traits_for(name):
    from player_functions import get_player_ai_image_traits
    return get_player_ai_image_traits(name)


def player_face_photo_focus_for(name):
    from player_functions import get_player_face_photo_focus
    x, y, z = get_player_face_photo_focus(name)
    return {'x': x, 'y': y, 'z': z}


def player_profile_fields_for(name):
    """Email, birthday, and height for player profile editing."""
    row = _ensure_player_record(name)
    return {
        'email': (row[2] or '') if row else '',
        'date_of_birth': (row[3] or '') if row else '',
        'height': (row[4] or '') if row else '',
    }


def player_avatar_context(name):
    """Template kwargs shared by player_avatar on stats pages."""
    fields = player_profile_fields_for(name)
    return {
        'player_photo_url': player_photo_url_for(name),
        'player_full_body_photos': player_full_body_photos_for(name),
        'player_ai_image_traits': player_ai_image_traits_for(name),
        'player_face_photo_focus': player_face_photo_focus_for(name),
        'player_email': fields['email'],
        'player_date_of_birth': fields['date_of_birth'],
        'player_height': fields['height'],
    }


def player_list_card_data(player_row):
    """One player row for the list page (clickable avatar + profile JSON)."""
    return build_player_list_cards([player_row])[0]


def build_player_list_cards(players):
    """Build list-page card payloads for many players with batched DB lookups."""
    from player_functions import get_players_list_extras

    if not players:
        return []

    names = [player_row[1] for player_row in players]
    extras = get_players_list_extras(names)
    default_focus = {'x': 50.0, 'y': 50.0, 'z': 1.0}
    default_body_focus = {'x': 50.0, 'y': 50.0, 'w': 75.0, 'h': 90.0}
    cards = []

    for player_row in players:
        name = player_row[1]
        meta = extras.get(name, {})
        photo_path = player_row[8] if len(player_row) > 8 and player_row[8] else None
        body_paths = meta.get('body_paths', [])
        body_crops = meta.get('body_crops', {})
        face_focus = meta.get('face_focus', default_focus)

        cards.append({
            'name': name,
            'email': player_row[2] or '',
            'dateOfBirth': player_row[3] or '',
            'height': player_row[4] or '',
            'games': int(player_row[11]) if len(player_row) > 11 and player_row[11] is not None else 0,
            'firstGame': player_row[10] if len(player_row) > 10 and player_row[10] else '',
            'photoUrl': url_for('static', filename=photo_path) if photo_path else None,
            'fullBodyPhotos': [
                {
                    'path': path,
                    'url': url_for('static', filename=path),
                    'focus': body_crops.get(path, default_body_focus),
                }
                for path in body_paths
            ],
            'aiImageTraits': meta.get('traits', []),
            'faceFocus': face_focus,
        })

    return cards


def _ensure_player_record(name):
    """Return players row for name, creating a minimal record if needed."""
    from player_functions import get_player_by_name, add_new_player
    player = get_player_by_name(name)
    if player:
        return player
    add_new_player(name)
    return get_player_by_name(name)


def log_activity(action, target=None, target_id=None, summary=None, before=None, after=None, username=None):
    """Record an entry in the admin activity log. Never raises - logging must
    not break the action being logged."""
    try:
        user = username or session.get('username') or 'unknown'
        adminfx.insert_activity(user, action, target, target_id, summary, before, after)
    except Exception:
        app.logger.exception('Failed to write activity log')


def _save_ai_prompt_log(payload, prompt_style, custom_prompt, game_ids, username=None):
    """Persist a generated AI summary prompt for admin review."""
    illustration_meta = payload.get('illustration_meta') or {}
    solo_images = illustration_meta.get('solo_images') or []
    try:
        adminfx.insert_ai_prompt_log(
            username=username or session.get('username') or 'unknown',
            game_type=payload.get('game_type') or 'doubles',
            prompt_style=prompt_style,
            custom_prompt=custom_prompt,
            game_ids=game_ids,
            prompt_text=payload.get('ai_prompt') or '',
            summary_text=payload.get('summary') or '',
            subject=payload.get('subject'),
            hero_image_url=payload.get('hero_image_url'),
            hero_image_error=payload.get('hero_image_error'),
            image_prompt_text=payload.get('image_prompt') or '',
            solo_images_json=json.dumps(solo_images) if solo_images else '',
        )
    except Exception:
        app.logger.exception('Failed to save AI prompt log')


def admin_required(f):
    """Require a logged-in admin user. Non-admins get redirected home."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.url))
        if not is_admin():
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in via session
        if session.get('logged_in'):
            return f(*args, **kwargs)
        
        # Check if user is logged in via remember me cookie
        auth_token = request.cookies.get('remember_token')
        if auth_token:
            username = validate_auth_token(auth_token)
            if username:
                # Auto-login the user
                session['logged_in'] = True
                session['username'] = username
                flash(f'Welcome back, {username}!', 'success')
                return f(*args, **kwargs)
            else:
                # Invalid or expired token, clear the cookie
                response = make_response(redirect(url_for('login', next=request.url)))
                response.set_cookie('remember_token', '', expires=0)
                return response
        
        return redirect(url_for('login', next=request.url))
    return decorated_function

def api_login_required(f):
    """Require auth for API: X-API-Key (STATS_API_TOKEN), Authorization Bearer <token>, or session/cookie. Returns 401 JSON if not authenticated."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = None
        api_key = request.headers.get('X-API-Key')
        if api_key and os.environ.get('STATS_API_TOKEN') and secrets.compare_digest(api_key, os.environ.get('STATS_API_TOKEN', '')):
            username = 'api_key'
            session['logged_in'] = True
            session['username'] = username
        if not username:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header[7:].strip()
                if token:
                    username = validate_auth_token(token)
                    if username:
                        session['logged_in'] = True
                        session['username'] = username
        if not username and session.get('logged_in'):
            username = session.get('username')
        if not username:
            auth_token = request.cookies.get('remember_token')
            if auth_token:
                username = validate_auth_token(auth_token)
                if username:
                    session['logged_in'] = True
                    session['username'] = username
        if not username:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def _api_get_db():
    """Return DB path for API (same as rest of app)."""
    return _stats_db_path()

def _api_game_row_to_dict(row):
    """Convert a games row (tuple or Row) to JSON-serializable dict."""
    if hasattr(row, 'keys'):
        d = dict(row)
    else:
        cols = ['id', 'game_date', 'winner1', 'winner2', 'winner_score', 'loser1', 'loser2', 'loser_score', 'updated_at', 'comments', 'entered_timezone', 'updated_by']
        d = {}
        for i, k in enumerate(cols):
            if i < len(row):
                d[k] = row[i]
            else:
                d[k] = None
    for key in ('game_date', 'updated_at'):
        if key in d and d[key] is not None and hasattr(d[key], 'isoformat'):
            d[key] = d[key].isoformat()
    return d

@app.route('/')
def index():
    """Redirect to the main stats page."""
    return redirect(url_for('stats', year=str(date.today().year)))

@app.route('/stats/<year>/<date>/')
def stats_by_date(year, date):
    """Redirect to stats page for the year."""
    return redirect(url_for('stats', year=year))


# ============================================
# STATS PAGE (Steam Charts-inspired)
# ============================================

@app.route('/stats/')
def stats_default():
    return redirect(url_for('stats', year=str(date.today().year)))


@app.route('/stats/<year>/')
def stats(year):
    """Doubles stats page."""
    current_year = str(date.today().year)
    showing_previous_year = False
    display_year = year
    
    games = year_games(year)
    if games:
        if len(games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(games) // 30
    else:
        minimum_games = 1
    
    all_years = grab_all_years()
    stats = stats_per_year(year, minimum_games)
    
    # If no stats for current year, fall back to previous year
    if not stats and year == current_year and all_years:
        previous_year = str(int(current_year) - 1)
        if previous_year in all_years:
            games = year_games(previous_year)
            if games:
                minimum_games = max(1, len(games) // 30)
            stats = stats_per_year(previous_year, minimum_games)
            display_year = previous_year
            showing_previous_year = True
    
    rare_stats = rare_stats_per_year(display_year, minimum_games)
    
    # Calculate tile stats
    tiles = calculate_tile_stats(display_year, stats, games)
    
    # Get today's stats
    today_stats = todays_stats()
    today_games = todays_games()
    
    return render_template('stats.html', 
        all_years=all_years, 
        stats=stats, 
        rare_stats=rare_stats, 
        minimum_games=minimum_games, 
        year=year,
        display_year=display_year,
        showing_previous_year=showing_previous_year,
        tiles=tiles,
        today_stats=today_stats,
        today_games=today_games)


@app.route('/player_network/')
def player_network_default():
    return redirect(url_for('player_network', year=str(date.today().year)))


@app.route('/player_network/<year>/')
def player_network(year):
    """Doubles player connection network (force-directed graph)."""
    current_year = str(date.today().year)
    showing_previous_year = False
    display_year = year

    all_years = grab_all_years()
    games = year_games(year)
    if not games and year == current_year and all_years:
        previous_year = str(int(current_year) - 1)
        if previous_year in all_years and year_games(previous_year):
            display_year = previous_year
            showing_previous_year = True
            games = year_games(previous_year)

    network_data = build_player_network_data(display_year)
    return render_template(
        'player_network.html',
        year=year,
        display_year=display_year,
        showing_previous_year=showing_previous_year,
        all_years=all_years,
        network_data=network_data,
    )


@app.route('/games/')
def games_default():
    return redirect(url_for('games', year=str(date.today().year)))


@app.route('/games/<year>/')
def games(year):
    """Doubles games page. 50 games per page. Optional ?q= for server-side search."""
    all_years = grab_all_years()
    per_page = 50
    page = max(1, request.args.get('page', 1, type=int))
    search_query = request.args.get('q', '').strip()
    if search_query:
        total = year_games_search_count(year, search_query)
    else:
        total = year_games_count(year)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    if search_query:
        games_list = year_games_paginated_search(year, search_query, limit=per_page, offset=offset)
    else:
        games_list = year_games_paginated(year, limit=per_page, offset=offset)
    page_end = min(page * per_page, total)

    # Group games by day for sticky day headers (games are date DESC, so days are contiguous)
    day_groups = []
    for game in games_list:
        day_raw = str(game[1])[:10].strip()
        label = day_raw
        for fmt in ('%m/%d/%Y', '%m/%d/%y'):
            try:
                label = datetime.strptime(day_raw, fmt).strftime('%A, %b %-d')
                break
            except ValueError:
                continue
        if day_groups and day_groups[-1]['day'] == day_raw:
            day_groups[-1]['games'].append(game)
        else:
            day_groups.append({'day': day_raw, 'label': label, 'games': [game]})

    return render_template('games.html', games=games_list, year=year, all_years=all_years,
                           page=page, total_pages=total_pages, total_games=total, per_page=per_page, page_end=page_end,
                           search_query=search_query, day_groups=day_groups)


# ============================================
# VOLLIS ROUTES
# ============================================

@app.route('/vollis_stats/')
def vollis_stats_default():
    return redirect(url_for('vollis_stats', year=str(date.today().year)))

@app.route('/vollis_stats/<year>/')
def vollis_stats(year):
    """Redesigned vollis stats page."""
    current_year = str(date.today().year)
    showing_previous_year = False
    display_year = year
    
    all_years = all_vollis_years()
    stats = vollis_stats_per_year(year, 0)
    
    # If no stats for current year, fall back to previous year
    if not stats and year == current_year and all_years:
        previous_year = str(int(current_year) - 1)
        if previous_year in all_years:
            stats = vollis_stats_per_year(previous_year, 0)
            display_year = previous_year
            showing_previous_year = True
    
    return render_template('vollis_stats.html', stats=stats, all_years=all_years, year=year,
        display_year=display_year, showing_previous_year=showing_previous_year)

@app.route('/vollis_games/')
def vollis_games_default():
    return redirect(url_for('vollis_games', year=str(date.today().year)))

@app.route('/vollis_games/<year>/')
def vollis_games(year):
    """Redesigned vollis games page."""
    all_years = all_vollis_years()
    games = vollis_year_games(year)
    return render_template('vollis_games.html', games=games, all_years=all_years, year=year)


# ============================================
# REDESIGNED OTHER ROUTES
# ============================================

@app.route('/other_stats/')
def other_stats_default():
    return redirect(url_for('other_stats', year=str(date.today().year)))

@app.route('/other_stats/<year>/')
def other_stats(year):
    """Other stats page."""
    current_year = str(date.today().year)
    showing_previous_year = False
    display_year = year
    
    all_years = all_other_years()
    games = other_year_games(year)
    if games:
        if len(games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(games) // 30
    else:
        minimum_games = 1
    stats = other_stats_per_year(year, minimum_games)
    
    # If no stats for current year, fall back to previous year
    if not stats and year == current_year and all_years:
        previous_year = str(int(current_year) - 1)
        if previous_year in all_years:
            games = other_year_games(previous_year)
            if games:
                minimum_games = max(1, len(games) // 30)
            stats = other_stats_per_year(previous_year, minimum_games)
            display_year = previous_year
            showing_previous_year = True
    
    rare_stats = rare_other_stats_per_year(display_year, minimum_games)
    game_cards = build_other_game_cards(display_year)
    
    # Get today's stats grouped by game name
    today_stats_by_game = todays_other_stats_by_game()
    today_other_games = todays_other_games()

    return render_template('other_stats.html', stats=stats, rare_stats=rare_stats,
        all_years=all_years, minimum_games=minimum_games, year=year,
        display_year=display_year, showing_previous_year=showing_previous_year, game_cards=game_cards,
        today_stats_by_game=today_stats_by_game, today_other_games=today_other_games)

@app.route('/other_games/')
def other_games_default():
    return redirect(url_for('other_games', year=str(date.today().year)))

@app.route('/other_games/<year>/')
def other_games(year):
    """Other games page."""
    all_years = all_other_years()
    games = other_year_games(year)
    return render_template('other_games.html', games=games, all_years=all_years, year=year)


@app.route('/other_games/<year>/<game_name>/')
def other_games_by_name(year, game_name):
    """Other games page filtered by game name."""
    from other_functions import total_game_name_stats
    all_years = all_other_years()
    all_games = other_year_games(year)
    # Filter games by game_name
    games = [g for g in all_games if g.get('game_name') == game_name]
    stats = total_game_name_stats(games)
    return render_template('other_games.html', games=games, all_years=all_years, year=year, game_name=game_name, stats=stats)


# ============================================
# EDIT ROUTES
# ============================================

@app.route('/edit_stats/')
@login_required
def edit_stats():
    """Hub page linking to all edit game pages"""
    return render_template('edit_stats.html')

@app.route('/edit_games/')
@login_required
def edit_games_default():
    return redirect(url_for('edit_games', year=str(date.today().year)))

@app.route('/edit_games/<year>/')
@login_required
def edit_games(year):
    """Edit doubles games page. 50 games per page. Optional ?q= for server-side search."""
    all_years = grab_all_years()
    per_page = 50
    page = max(1, request.args.get('page', 1, type=int))
    search_query = request.args.get('q', '').strip()
    if search_query:
        total = year_games_search_count(year, search_query)
    else:
        total = year_games_count(year)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    if search_query:
        games = year_games_paginated_search(year, search_query, limit=per_page, offset=offset)
    else:
        games = year_games_paginated(year, limit=per_page, offset=offset)
    page_end = min(page * per_page, total)
    saved = request.args.get('saved')
    deleted = request.args.get('deleted')
    return render_template('edit_games.html', games=games, year=year, all_years=all_years,
                           page=page, total_pages=total_pages, total_games=total, per_page=per_page, page_end=page_end,
                           search_query=search_query, saved=saved, deleted=deleted)

@app.route('/edit_vollis_games/')
@login_required
def edit_vollis_games_default():
    return redirect(url_for('edit_vollis_games', year=str(date.today().year)))

@app.route('/edit_vollis_games/<year>/')
@login_required
def edit_vollis_games(year):
    """Edit vollis games page."""
    all_years = all_vollis_years()
    games = vollis_year_games(year)
    return render_template('edit_vollis_games.html', games=games, year=year, all_years=all_years)

@app.route('/edit_other_games/')
@login_required
def edit_other_games_default():
    return redirect(url_for('edit_other_games', year=str(date.today().year)))

@app.route('/edit_other_games/<year>/')
@login_required
def edit_other_games(year):
    """Edit other games page."""
    all_years = all_other_years()
    games = other_year_games(year)
    return render_template('edit_other_games.html', games=games, year=year, all_years=all_years)


# ============================================
# REDESIGNED ADD GAME ROUTES
# ============================================

@app.route('/ai_summary/')
@login_required
def ai_summary():
    """AI summary page for selecting games to summarize."""
    doubles_games = recent_games(50)
    vollis_games = recent_vollis_games(50)
    other_games = recent_other_games(50)
    return render_template('ai_summary.html',
                           doubles_games=doubles_games,
                           vollis_games=vollis_games,
                           other_games=other_games)


def _serialize_ai_summary_game(game_type, game):
    """Normalize a game row for the AI summary search API."""
    if game_type == 'doubles':
        return {
            'id': game[0],
            'date': game[1],
            'winner_names': [n for n in (game[2], game[3]) if n],
            'winners': f'{game[2]} & {game[3]}',
            'winner_score': game[4],
            'loser_names': [n for n in (game[5], game[6]) if n],
            'losers': f'{game[5]} & {game[6]}',
            'loser_score': game[7],
        }
    if game_type == 'vollis':
        return {
            'id': game[0],
            'date': game[1],
            'winner_names': [game[2]] if game[2] else [],
            'winners': game[2],
            'winner_score': game[3],
            'loser_names': [game[4]] if game[4] else [],
            'losers': game[4],
            'loser_score': game[5],
        }
    return {
        'id': game['game_id'],
        'date': game['game_date'],
        'game_name': game.get('game_name') or '',
        'winners': game.get('winners') or [],
        'losers': game.get('losers') or [],
        'winner_score': game.get('winner_score'),
        'loser_score': game.get('loser_score'),
    }


@app.route('/api/ai_summary_game_search/')
@login_required
def api_ai_summary_game_search():
    """Search all historical games for the AI summary picker."""
    from stat_functions import search_doubles_games
    from vollis_functions import search_vollis_games
    from other_functions import search_other_games

    q = (request.args.get('q') or '').strip()
    game_type = (request.args.get('game_type') or 'doubles').strip().lower()
    limit = min(max(request.args.get('limit', 50, type=int), 1), 100)

    if not q:
        return jsonify({'success': True, 'games': [], 'query': '', 'game_type': game_type})

    if game_type == 'vollis':
        games = search_vollis_games(q, limit=limit)
    elif game_type == 'other':
        games = search_other_games(q, limit=limit)
    else:
        game_type = 'doubles'
        games = search_doubles_games(q, limit=limit)

    return jsonify({
        'success': True,
        'query': q,
        'game_type': game_type,
        'games': [_serialize_ai_summary_game(game_type, game) for game in games],
    })

@app.route('/select_ai_prompt/', methods=['POST'])
@login_required
def select_ai_prompt():
    """Show prompt selection page after selecting games."""
    selected_game_ids = request.form.getlist('game_ids')
    game_type = request.form.get('game_type', 'doubles')
    if not selected_game_ids:
        flash('Please select at least one game.', 'error')
        return redirect(url_for('ai_summary'))
    return render_template('select_prompt.html', game_ids=selected_game_ids, game_type=game_type)


def _render_select_ai_prompt(
    game_ids, game_type, prompt_style='', custom_prompt='', image_details='', error=None,
):
    """Re-show the style picker with prior selections after a recoverable error."""
    if error:
        flash(str(error), 'error')
    style = _normalize_prompt_style(prompt_style) if prompt_style else ''
    if style and style not in ('random', 'custom'):
        style = 'random'
    return render_template(
        'select_prompt.html',
        game_ids=game_ids,
        game_type=game_type,
        selected_prompt_style=style,
        custom_prompt_value=custom_prompt or '',
        image_details_value=image_details or '',
    )


@app.route('/preview_ai_summary_with_prompt/', methods=['POST'])
@login_required
def preview_ai_summary_with_prompt():
    """Generate AI summary with selected prompt style.

    When the background worker is running, queue the job so the user can browse
    other pages via the menu. Otherwise generate synchronously in this request.
    """
    selected_game_ids = request.form.getlist('game_ids')
    prompt_style = request.form.get('prompt_style', 'random')
    custom_prompt = request.form.get('custom_prompt', '')
    game_type = request.form.get('game_type', 'doubles')
    image_mode = _normalize_image_mode(request.form.get('image_mode'))
    image_details = (request.form.get('image_details') or '').strip()
    
    if not selected_game_ids:
        flash('Please select at least one game.', 'error')
        return redirect(url_for('ai_summary'))

    def stay_on_prompt(error):
        return _render_select_ai_prompt(
            selected_game_ids,
            game_type,
            prompt_style=prompt_style,
            custom_prompt=custom_prompt,
            image_details=image_details,
            error=error,
        )

    # Prefer background generation so Menu navigation doesn't cancel the work.
    if ai_jobs.daemon_is_alive():
        username = session.get('username') or 'unknown'
        job_id = ai_jobs.enqueue_job(
            username,
            selected_game_ids,
            game_type,
            prompt_style,
            custom_prompt,
            image_mode=image_mode,
            image_details=image_details,
        )
        log_activity(
            'Queued AI recap publish',
            summary=(
                f'job #{job_id}: {game_type} for {len(selected_game_ids)} game(s), '
                f'style "{prompt_style}"'
            ),
        )
        return redirect(url_for('ai_summary_job_status', job_id=job_id))

    try:
        if game_type == 'vollis':
            payload = build_vollis_email_payload(
                selected_game_ids, prompt_style=prompt_style, custom_prompt=custom_prompt,
                image_mode=image_mode, image_details=image_details,
            )
        elif game_type == 'other':
            payload = build_other_email_payload(
                selected_game_ids, prompt_style=prompt_style, custom_prompt=custom_prompt,
                image_mode=image_mode, image_details=image_details,
            )
        else:
            payload = build_doubles_email_payload(
                selected_game_ids, prompt_style=prompt_style, custom_prompt=custom_prompt,
                image_mode=image_mode, image_details=image_details,
            )
    except ValueError as ve:
        log_activity('AI summary failed', summary=f'{game_type} summary for {len(selected_game_ids)} game(s): {str(ve)[:200]}')
        return stay_on_prompt(ve)
    except Exception as e:
        app.logger.exception('AI summary payload failed')
        log_activity('AI summary failed', summary=f'{game_type} summary for {len(selected_game_ids)} game(s): {str(e)[:200]}')
        return stay_on_prompt(f'Failed to prepare summary preview: {str(e)}')

    _save_ai_prompt_log(payload, prompt_style, custom_prompt, selected_game_ids)

    img_note = _ai_image_log_note(payload)
    log_activity('Generated AI summary', summary=(
        f'{game_type} summary for {len(selected_game_ids)} game(s), style "{prompt_style}"'
        + img_note
    ))

    try:
        share_id = _publish_ai_recap(
            payload, prompt_style, custom_prompt, selected_game_ids,
        )
        log_activity(
            'Published AI recap',
            summary=f'{game_type} recap published at /recap/{share_id}',
        )
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))
    except Exception as e:
        app.logger.exception('AI recap publish failed')
        return stay_on_prompt(f'Failed to publish recap: {str(e)}')


@app.route('/ai_summary/job/<int:job_id>/')
@login_required
def ai_summary_job_status(job_id):
    """Waiting page while a background AI recap job runs — menu stays available."""
    job = ai_jobs.get_job(job_id)
    if not job:
        abort(404)
    if job.get('username') != session.get('username'):
        abort(403)
    if job.get('status') == 'completed' and job.get('share_id'):
        return redirect(url_for('view_ai_recap', share_id=job['share_id'], published=1))
    return render_template('ai_summary_job.html', job=job, job_id=job_id)


@app.route('/api/ai_summary_job/<int:job_id>/')
@login_required
def api_ai_summary_job_status(job_id):
    """JSON status for background AI recap jobs."""
    job = ai_jobs.get_job(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found.'}), 404
    if job.get('username') != session.get('username'):
        return jsonify({'success': False, 'error': 'Not allowed.'}), 403
    share_id = job.get('share_id') or ''
    return jsonify({
        'success': True,
        'job_id': job_id,
        'status': job.get('status') or 'pending',
        'error': job.get('error') or '',
        'share_id': share_id,
        'result_summary': job.get('result_summary') or '',
        'recap_url': (
            url_for('view_ai_recap', share_id=share_id, published=1)
            if share_id else ''
        ),
    })


@app.route('/recap/<share_id>/')
def view_ai_recap(share_id):
    """Public shareable AI recap page."""
    from email_content import cleanup_expired_solo_images, filter_existing_solo_images

    row = adminfx.get_ai_recap_page(share_id)
    if not row:
        abort(404)

    # Drop expired temporary solo caricatures (creator-only previews).
    cleanup_expired_solo_images()

    solo_images = []
    try:
        solo_images = json.loads(row.get('solo_images_json') or '[]')
    except (json.JSONDecodeError, TypeError):
        solo_images = []

    show_creator_view = request.args.get('published') == '1'
    # Solos are never shown on the public shareable link — only the creator
    # view (?published=1), and only while the temp files still exist.
    if show_creator_view and solo_images:
        kept = filter_existing_solo_images(solo_images)
        if len(kept) != len(solo_images):
            adminfx.update_ai_recap_page(
                share_id,
                solo_images_json=json.dumps(kept) if kept else '[]',
            )
        solo_images = kept
    else:
        solo_images = []

    created_at = row.get('created_at') or ''
    if isinstance(created_at, str) and len(created_at) >= 16:
        created_at_fmt = created_at[:16].replace('T', ' ')
    else:
        created_at_fmt = str(created_at)

    can_remake = bool(
        show_creator_view
        and session.get('logged_in')
        and row.get('username')
        and row.get('username') == session.get('username')
    )

    remake_summary_prompt = ''
    remake_image_details = ''
    game_type = row.get('game_type') or 'doubles'
    if can_remake:
        remake_summary_prompt = (
            (row.get('style_instructions') or '').strip()
            or (row.get('custom_prompt') or '').strip()
        )
        remake_image_details = (row.get('image_details') or '').strip()

    # Ensure each solo card has an editable prompt (stored, or rebuilt as fallback).
    if can_remake and solo_images:
        from email_content import build_solo_caricature_prompt

        game_name = None
        try:
            game_ids = json.loads(row.get('game_ids_json') or '[]')
        except (json.JSONDecodeError, TypeError):
            game_ids = []
        if game_ids and game_type == 'other':
            try:
                _games, _players, game_name = _load_games_and_players_for_recap(
                    game_type, game_ids,
                )
            except Exception:
                game_name = None
        enriched = []
        for item in solo_images:
            entry = dict(item)
            if not (entry.get('prompt') or '').strip():
                entry['prompt'] = build_solo_caricature_prompt(
                    entry.get('name') or '',
                    game_type=game_type,
                    game_name=game_name,
                )
            enriched.append(entry)
        solo_images = enriched

    from email_content import ensure_recap_og_image

    site_base = (app.config.get('SITE_BASE_URL') or EMAIL_SITE_BASE_URL).rstrip('/')
    hero_image_url = adminfx.absolutize_hero_image_url(
        adminfx.ensure_recap_hero_image_url(share_id, row),
        site_base,
    )
    # Warm the on-disk OG JPEG cache when possible (WhatsApp requires <600KB).
    og_preview = ensure_recap_og_image(hero_image_url) if hero_image_url else {}
    og_image_width = og_preview.get('width') or ''
    og_image_height = og_preview.get('height') or ''

    # Share link includes image token + t= version so WhatsApp re-scrapes after OG fixes.
    share_query = adminfx.recap_share_query_args(hero_image_url)
    share_url = url_for(
        'view_ai_recap',
        share_id=share_id,
        _external=True,
        **share_query,
    )
    # WhatsApp wants an undecorated canonical og:url (no cache-bust query params).
    og_url = url_for('view_ai_recap', share_id=share_id, _external=True)
    # Always point crawlers at our compressed JPEG endpoint, not the full PNG.
    og_image_url = (
        url_for(
            'recap_og_image',
            share_id=share_id,
            v=f"{share_query['m']}-{share_query['t']}",
            _external=True,
        )
        if hero_image_url
        else ''
    )

    og_description = (row.get('plain_text_body') or '').strip()
    if og_description:
        # One short line for link previews (WhatsApp/iMessage/etc.).
        og_description = ' '.join(og_description.split())
        # WhatsApp shows roughly 1-2 short description lines.
        if len(og_description) > 120:
            og_description = og_description[:117].rstrip() + '…'
    else:
        og_description = 'Game recap'

    # Instagram carousel slides (creator view): generate on demand if missing.
    instagram_slides = []
    if show_creator_view:
        from email_content import IG_SLIDE_FILES, list_instagram_slide_paths

        slide_paths = list_instagram_slide_paths(share_id)
        if not slide_paths:
            slide_paths = _refresh_instagram_slides(
                share_id,
                html_body=row.get('html_body') or '',
                plain_text_body=row.get('plain_text_body') or '',
                subject=row.get('subject') or '',
                hero_image_url=hero_image_url or '',
                force=True,
            )
        if slide_paths:
            labels = {
                'photo': 'Photo',
                'summary': 'Summary',
                'stats': 'Stats',
                'games': 'Games',
            }
            for filename, kind in IG_SLIDE_FILES:
                instagram_slides.append({
                    'kind': kind,
                    'label': labels.get(kind, kind.title()),
                    'filename': filename,
                    'url': url_for(
                        'recap_instagram_slide',
                        share_id=share_id,
                        filename=filename,
                    ),
                })

    return render_template(
        'recap.html',
        subject=row.get('subject') or 'Game Recap',
        recap_html=recap_html_for_page(row.get('html_body') or ''),
        share_url=share_url,
        og_url=og_url,
        share_id=share_id,
        show_creator_view=show_creator_view,
        can_remake=can_remake,
        solo_images=solo_images,
        hero_image_url=hero_image_url,
        og_image_url=og_image_url,
        og_image_type='image/jpeg' if og_image_url else '',
        og_image_width=og_image_width,
        og_image_height=og_image_height,
        hero_image_error=row.get('hero_image_error') or '' if show_creator_view else '',
        created_at_fmt=created_at_fmt if show_creator_view else '',
        game_type=game_type,
        remake_summary_prompt=remake_summary_prompt,
        remake_image_details=remake_image_details,
        og_description=og_description,
        instagram_slides=instagram_slides,
    )


@app.route('/recap/<share_id>/og.jpg')
def recap_og_image(share_id):
    """Public WhatsApp/Open Graph thumbnail (JPEG under 600KB)."""
    import io
    from flask import send_file
    from email_content import build_recap_og_jpeg

    row = adminfx.get_ai_recap_page(share_id)
    if not row:
        abort(404)

    site_base = (app.config.get('SITE_BASE_URL') or EMAIL_SITE_BASE_URL).rstrip('/')
    hero_image_url = adminfx.absolutize_hero_image_url(
        adminfx.ensure_recap_hero_image_url(share_id, row),
        site_base,
    )
    if not hero_image_url:
        abort(404)

    try:
        data, _width, _height, cache_path = build_recap_og_jpeg(hero_image_url)
    except Exception:
        app.logger.exception('Failed to build OG image for /recap/%s/', share_id)
        abort(404)

    if cache_path and os.path.isfile(cache_path):
        return send_file(
            cache_path,
            mimetype='image/jpeg',
            conditional=True,
            max_age=86400,
            download_name=f'{share_id}-og.jpg',
        )
    return send_file(
        io.BytesIO(data),
        mimetype='image/jpeg',
        max_age=86400,
        download_name=f'{share_id}-og.jpg',
    )


@app.route('/recap/<share_id>/instagram/<filename>')
def recap_instagram_slide(share_id, filename):
    """Serve one Instagram carousel slide JPEG (creator download / preview)."""
    from flask import send_file
    from email_content import IG_SLIDE_FILES, instagram_slides_dir

    row = adminfx.get_ai_recap_page(share_id)
    if not row:
        abort(404)

    allowed = {name for name, _kind in IG_SLIDE_FILES}
    if filename not in allowed:
        abort(404)

    path = os.path.join(instagram_slides_dir(share_id), filename)
    if not os.path.isfile(path):
        # Rebuild once if missing (older recaps, or first request after remake race).
        site_base = (app.config.get('SITE_BASE_URL') or EMAIL_SITE_BASE_URL).rstrip('/')
        hero_image_url = adminfx.absolutize_hero_image_url(
            adminfx.ensure_recap_hero_image_url(share_id, row),
            site_base,
        )
        _refresh_instagram_slides(
            share_id,
            html_body=row.get('html_body') or '',
            plain_text_body=row.get('plain_text_body') or '',
            subject=row.get('subject') or '',
            hero_image_url=hero_image_url or '',
            force=True,
        )
    if not os.path.isfile(path):
        abort(404)

    return send_file(
        path,
        mimetype='image/jpeg',
        conditional=True,
        max_age=3600,
        download_name=f'{share_id}-{filename}',
        as_attachment=bool(request.args.get('download')),
    )


@app.route('/recap/<share_id>/instagram.zip')
@login_required
def recap_instagram_zip(share_id):
    """Download all 4 Instagram slides as a zip (creator only)."""
    import io
    from flask import send_file
    from email_content import build_instagram_slides_zip_bytes, list_instagram_slide_paths

    row, early = _require_recap_creator(share_id)
    if early:
        return early

    if not list_instagram_slide_paths(share_id):
        site_base = (app.config.get('SITE_BASE_URL') or EMAIL_SITE_BASE_URL).rstrip('/')
        hero_image_url = adminfx.absolutize_hero_image_url(
            adminfx.ensure_recap_hero_image_url(share_id, row),
            site_base,
        )
        _refresh_instagram_slides(
            share_id,
            html_body=row.get('html_body') or '',
            plain_text_body=row.get('plain_text_body') or '',
            subject=row.get('subject') or '',
            hero_image_url=hero_image_url or '',
            force=True,
        )

    data = build_instagram_slides_zip_bytes(share_id)
    if not data:
        flash('Could not build Instagram slides for this recap.', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    return send_file(
        io.BytesIO(data),
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'{share_id}-instagram.zip',
    )


@app.route('/recap/<share_id>/remake-image/', methods=['POST'])
@login_required
def remake_ai_recap_image(share_id):
    """Regenerate the hero illustration for a published AI recap page."""
    row = adminfx.get_ai_recap_page(share_id)
    if not row:
        abort(404)

    if row.get('username') != session.get('username'):
        flash('Only the creator can remake this picture.', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        flash('Gemini API key not configured.', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    try:
        game_ids = json.loads(row.get('game_ids_json') or '[]')
    except (json.JSONDecodeError, TypeError):
        game_ids = []
    if not game_ids:
        flash('This recap has no saved games to remake the picture from.', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    from email_content import delete_solo_image_files, filter_existing_solo_images

    game_type = row.get('game_type') or 'doubles'
    # Prefer freshly edited details from the remake form; fall back to saved ones.
    if 'image_details' in request.form:
        image_details = (request.form.get('image_details') or '').strip()
    else:
        image_details = (row.get('image_details') or '').strip()
    # Remake always generates an image, even if the original mode was "none".
    image_mode = 'image'

    try:
        old_solos = json.loads(row.get('solo_images_json') or '[]')
    except (json.JSONDecodeError, TypeError):
        old_solos = []
    reuse_solos = filter_existing_solo_images(old_solos)

    try:
        games, players, game_name = _load_games_and_players_for_recap(game_type, game_ids)
        if not games:
            raise ValueError('None of the saved games were found.')
        if not players:
            raise ValueError('No players found for the saved games.')

        new_url, _new_path, hero_err, _image_prompt, illustration_meta = (
            _try_generate_email_hero_image(
                api_key,
                game_type,
                games,
                players,
                game_name=game_name,
                image_mode=image_mode,
                image_details=image_details,
                existing_solo_images=reuse_solos,
                reuse_existing_solos=bool(reuse_solos),
            )
        )
    except Exception as e:
        app.logger.exception('AI recap remake image failed')
        flash(f'Failed to remake picture: {str(e)}', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    if not new_url:
        flash(hero_err or 'Failed to remake picture.', 'error')
        adminfx.update_ai_recap_page(
            share_id,
            hero_image_error=hero_err or 'Failed to remake picture.',
            image_details=image_details,
        )
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    old_url = row.get('hero_image_url') or ''
    updated_html = replace_recap_hero_image(row.get('html_body') or '', new_url)
    solo_images = (illustration_meta or {}).get('solo_images') or reuse_solos

    # Drop any old solo files that were replaced (not reused).
    reused_paths = {item.get('path') for item in solo_images if item.get('path')}
    stale = [item for item in old_solos if _solo_path_for_item(item) not in reused_paths]
    delete_solo_image_files(stale)

    from email_content import delete_recap_og_image_for_hero, ensure_recap_og_image

    adminfx.update_ai_recap_page(
        share_id,
        html_body=updated_html,
        hero_image_url=new_url,
        hero_image_error='',
        image_mode=image_mode,
        image_details=image_details,
        solo_images_json=json.dumps(solo_images) if solo_images else '[]',
    )
    ensure_recap_og_image(new_url)
    _refresh_instagram_slides(
        share_id,
        html_body=updated_html,
        plain_text_body=row.get('plain_text_body') or '',
        subject=row.get('subject') or '',
        hero_image_url=new_url,
        force=True,
    )

    if old_url and old_url != new_url:
        delete_recap_og_image_for_hero(old_url)
        old_path = _hero_image_path_from_url(old_url)
        if old_path:
            try:
                os.remove(old_path)
            except OSError:
                pass

    log_activity(
        'Remade AI recap picture',
        summary=f'Regenerated illustration for /recap/{share_id}',
    )
    flash(
        'Picture remade. Copy the share link again so WhatsApp shows the new thumbnail.',
        'success',
    )
    return redirect(url_for('view_ai_recap', share_id=share_id, published=1))


def _solo_path_for_item(item):
    """Best-effort absolute path for a solo image dict (for remake cleanup)."""
    if not item:
        return None
    path = item.get('path')
    if path and os.path.isfile(path):
        return path
    url = item.get('url') or ''
    marker = '/static/email_images/'
    if marker not in url:
        return None
    filename = url.split(marker, 1)[1].split('?', 1)[0]
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, 'static', 'email_images', os.path.basename(filename))
    return path if os.path.isfile(path) else None


def _require_recap_creator(share_id):
    """Load a recap row or abort; ensure the current user is the creator."""
    row = adminfx.get_ai_recap_page(share_id)
    if not row:
        abort(404)
    if row.get('username') != session.get('username'):
        flash('Only the creator can change this recap.', 'error')
        return None, redirect(url_for('view_ai_recap', share_id=share_id, published=1))
    return row, None


@app.route('/recap/<share_id>/upload-image/', methods=['POST'])
@login_required
def upload_ai_recap_image(share_id):
    """Replace the group hero illustration with a user-uploaded image."""
    from email_content import save_uploaded_email_image

    row, early = _require_recap_creator(share_id)
    if early:
        return early

    try:
        new_url, _new_path = save_uploaded_email_image(request.files.get('image'))
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))
    except Exception as e:
        app.logger.exception('AI recap group image upload failed')
        flash(f'Failed to upload picture: {e}', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    from email_content import delete_recap_og_image_for_hero, ensure_recap_og_image

    old_url = row.get('hero_image_url') or ''
    updated_html = replace_recap_hero_image(row.get('html_body') or '', new_url)
    adminfx.update_ai_recap_page(
        share_id,
        html_body=updated_html,
        hero_image_url=new_url,
        hero_image_error='',
        image_mode='image',
    )
    ensure_recap_og_image(new_url)
    _refresh_instagram_slides(
        share_id,
        html_body=updated_html,
        plain_text_body=row.get('plain_text_body') or '',
        subject=row.get('subject') or '',
        hero_image_url=new_url,
        force=True,
    )
    if old_url and old_url != new_url:
        delete_recap_og_image_for_hero(old_url)
        old_path = _hero_image_path_from_url(old_url)
        if old_path:
            try:
                os.remove(old_path)
            except OSError:
                pass

    log_activity(
        'Uploaded AI recap picture',
        summary=f'Replaced group illustration for /recap/{share_id}',
    )
    flash(
        'Group picture uploaded. Copy the share link again so WhatsApp shows the new thumbnail.',
        'success',
    )
    return redirect(url_for('view_ai_recap', share_id=share_id, published=1))


@app.route('/recap/<share_id>/upload-solo/', methods=['POST'])
@login_required
def upload_ai_recap_solo(share_id):
    """Replace one temporary solo caricature with a user-uploaded image."""
    from email_content import (
        SOLO_IMAGE_PREFIX,
        delete_solo_image_files,
        filter_existing_solo_images,
        save_uploaded_email_image,
    )

    row, early = _require_recap_creator(share_id)
    if early:
        return early

    player_name = (request.form.get('player_name') or '').strip()
    if not player_name:
        flash('Which player picture should be replaced?', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    try:
        solo_images = json.loads(row.get('solo_images_json') or '[]')
    except (json.JSONDecodeError, TypeError):
        solo_images = []
    solo_images = filter_existing_solo_images(solo_images)

    match_idx = None
    for index, item in enumerate(solo_images):
        if (item.get('name') or '').strip().lower() == player_name.lower():
            match_idx = index
            player_name = item.get('name') or player_name
            break
    if match_idx is None:
        flash(f'No caricature slot found for {player_name}.', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    try:
        new_url, new_path = save_uploaded_email_image(
            request.files.get('image'), prefix=SOLO_IMAGE_PREFIX,
        )
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))
    except Exception as e:
        app.logger.exception('AI recap solo image upload failed')
        flash(f'Failed to upload picture: {e}', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    old_item = solo_images[match_idx]
    solo_images[match_idx] = {'name': player_name, 'url': new_url, 'path': new_path}
    delete_solo_image_files([old_item])
    adminfx.update_ai_recap_page(
        share_id,
        solo_images_json=json.dumps(solo_images),
    )

    log_activity(
        'Uploaded AI solo caricature',
        summary=f'Replaced {player_name} portrait for /recap/{share_id}',
    )
    flash(
        f'Uploaded picture for {player_name}. Remake the group picture to use it in the final image.',
        'success',
    )
    return redirect(url_for('view_ai_recap', share_id=share_id, published=1))


@app.route('/recap/<share_id>/remake-solo/', methods=['POST'])
@login_required
def remake_ai_recap_solo(share_id):
    """Regenerate one temporary solo caricature for the creator preview gallery."""
    from email_content import (
        ImageGenerationError,
        delete_solo_image_files,
        filter_existing_solo_images,
        generate_solo_caricature,
    )

    row = adminfx.get_ai_recap_page(share_id)
    if not row:
        abort(404)

    if row.get('username') != session.get('username'):
        flash('Only the creator can remake this caricature.', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    player_name = (request.form.get('player_name') or '').strip()
    if not player_name:
        flash('Which player caricature should be remade?', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    custom_prompt = (request.form.get('solo_prompt') or '').strip()

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        flash('Gemini API key not configured.', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    try:
        solo_images = json.loads(row.get('solo_images_json') or '[]')
    except (json.JSONDecodeError, TypeError):
        solo_images = []
    solo_images = filter_existing_solo_images(solo_images)

    match_idx = None
    for index, item in enumerate(solo_images):
        if (item.get('name') or '').strip().lower() == player_name.lower():
            match_idx = index
            player_name = item.get('name') or player_name
            break
    if match_idx is None:
        flash(f'No caricature found for {player_name}.', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    game_type = row.get('game_type') or 'doubles'
    game_name = None
    try:
        game_ids = json.loads(row.get('game_ids_json') or '[]')
    except (json.JSONDecodeError, TypeError):
        game_ids = []
    if game_ids and game_type == 'other':
        try:
            _games, _players, game_name = _load_games_and_players_for_recap(game_type, game_ids)
        except Exception:
            game_name = None

    old_item = solo_images[match_idx]
    try:
        new_item = generate_solo_caricature(
            api_key,
            player_name,
            game_type=game_type,
            game_name=game_name,
            custom_prompt=custom_prompt or None,
        )
    except ImageGenerationError as e:
        app.logger.exception('AI recap remake solo failed')
        flash(f'Failed to remake caricature for {player_name}: {e}', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))
    except Exception as e:
        app.logger.exception('AI recap remake solo failed')
        flash(f'Failed to remake caricature for {player_name}: {e}', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    solo_images[match_idx] = new_item
    delete_solo_image_files([old_item])
    adminfx.update_ai_recap_page(
        share_id,
        solo_images_json=json.dumps(solo_images),
    )

    log_activity(
        'Remade AI solo caricature',
        summary=f'Regenerated {player_name} portrait for /recap/{share_id}',
    )
    flash(f'Remade caricature for {player_name}. Remake the group picture to use it in the final image.', 'success')
    return redirect(url_for('view_ai_recap', share_id=share_id, published=1))


@app.route('/recap/<share_id>/remake-summary/', methods=['POST'])
@login_required
def remake_ai_recap_summary(share_id):
    """Regenerate the written summary for a published AI recap page (keeps existing picture)."""
    row = adminfx.get_ai_recap_page(share_id)
    if not row:
        abort(404)

    if row.get('username') != session.get('username'):
        flash('Only the creator can remake this summary.', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    try:
        game_ids = json.loads(row.get('game_ids_json') or '[]')
    except (json.JSONDecodeError, TypeError):
        game_ids = []
    if not game_ids:
        flash('This recap has no saved games to remake the summary from.', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    game_type = row.get('game_type') or 'doubles'
    if 'custom_prompt' in request.form:
        custom_prompt = (request.form.get('custom_prompt') or '').strip()
    else:
        custom_prompt = (
            (row.get('style_instructions') or '').strip()
            or (row.get('custom_prompt') or '').strip()
        )

    if custom_prompt:
        prompt_style = 'custom'
    else:
        # Empty prompt → invent a fresh random style (same as original "random").
        prompt_style = 'random'

    try:
        payload = _build_ai_summary_payload(
            game_type,
            game_ids,
            prompt_style,
            custom_prompt,
            image_mode='none',
            image_details='',
        )
    except Exception as e:
        app.logger.exception('AI recap remake summary failed')
        flash(f'Failed to remake summary: {str(e)}', 'error')
        return redirect(url_for('view_ai_recap', share_id=share_id, published=1))

    html_body = payload.get('html_body') or ''
    old_hero = (row.get('hero_image_url') or '').strip()
    if old_hero:
        html_body = replace_recap_hero_image(html_body, old_hero)

    style_instructions = (payload.get('style_instructions') or '').strip()
    saved_custom = style_instructions or custom_prompt

    new_subject = payload.get('subject') or row.get('subject') or ''
    new_plain = payload.get('plain_text_body') or ''
    adminfx.update_ai_recap_page(
        share_id,
        html_body=html_body,
        plain_text_body=new_plain,
        subject=new_subject,
        prompt_style=prompt_style,
        custom_prompt=saved_custom,
        style_instructions=style_instructions,
        hero_image_url=old_hero,
        hero_image_error=row.get('hero_image_error') or '',
    )
    _refresh_instagram_slides(
        share_id,
        html_body=html_body,
        plain_text_body=new_plain,
        subject=new_subject,
        hero_image_url=old_hero,
        force=True,
    )

    log_activity(
        'Remade AI recap summary',
        summary=f'Regenerated summary for /recap/{share_id} (style "{prompt_style}")',
    )
    flash('Summary remade.', 'success')
    return redirect(url_for('view_ai_recap', share_id=share_id, published=1))


@app.route('/api/generate_and_send_ai_summary/', methods=['POST'])
@login_required
def api_generate_and_send_ai_summary():
    """Queue AI summary generation; an Always-on daemon publishes a share link in the background."""
    game_type = request.form.get('game_type', 'doubles')
    prompt_style = request.form.get('prompt_style', 'random')
    custom_prompt = request.form.get('custom_prompt', '')
    game_ids = request.form.getlist('game_ids')
    if not game_ids:
        return jsonify({'success': False, 'error': 'No games selected.'}), 400

    username = session.get('username', 'unknown')
    image_mode = _normalize_image_mode(request.form.get('image_mode'))
    image_details = (request.form.get('image_details') or '').strip()
    job_id = ai_jobs.enqueue_job(
        username, game_ids, game_type, prompt_style, custom_prompt,
        image_mode=image_mode, image_details=image_details,
    )
    worker_alive = ai_jobs.daemon_is_alive()
    log_activity(
        'Queued AI recap publish',
        summary=f'job #{job_id}: {game_type} for {len(game_ids)} game(s), style "{prompt_style}"',
        username=username,
    )

    if worker_alive:
        message = (
            f'Queued (job #{job_id}). Generating your recap page in the background — '
            'you can close this page. Check /admin/ activity for the share link in a few minutes.'
        )
    else:
        message = (
            f'Queued (job #{job_id}), but the background worker is not running. '
            'Enable the Always-on task on PythonAnywhere (see wsgi_config.py), '
            'or generate from the style page and wait for the recap link.'
        )
    return jsonify({
        'success': True,
        'job_id': job_id,
        'worker_alive': worker_alive,
        'message': message,
    })


def _add_doubles_game_view(redirect_to):
    """Shared logic for add_game and add_game_voice (same page, different URLs)."""
    year = str(date.today().year)
    if request.method == 'POST':
        winner1 = request.form['winner1'].strip()
        winner2 = request.form['winner2'].strip()
        loser1 = request.form['loser1'].strip()
        loser2 = request.form['loser2'].strip()
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']
        comments = request.form.get('comments', '').strip()

        if not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        elif int(winner_score) <= int(loser_score):
            flash("Winner's score must be higher than loser's score!")
        elif winner1 == winner2 or winner1 == loser1 or winner1 == loser2 or winner2 == loser1 or winner2 == loser2 or loser1 == loser2:
            flash('Two names are the same!')
        elif any(len(n) > 80 for n in (winner1, winner2, loser1, loser2)):
            flash('Each player name must be a single name (max 80 characters). Please use the dropdown to pick one player per field.')
        else:
            from player_functions import get_player_by_name, add_new_player
            for player_name in [winner1, winner2, loser1, loser2]:
                if player_name and not get_player_by_name(player_name):
                    add_new_player(player_name)
            # Use browser's local date/time when provided so games are stored in the timezone they were added (e.g. 7am PST)
            client_date = request.form.get('client_date', '').strip()
            client_time = request.form.get('client_time', '').strip()
            game_dt = parse_client_datetime_for_game(client_date, client_time)
            if game_dt is None:
                now = get_user_now_only()
                if now is None:
                    flash('Could not determine your timezone. Please refresh the page and try again.')
                    return redirect(url_for(redirect_to))
                game_dt = now.strftime('%Y-%m-%d %H:%M:%S')
            tz = request.form.get('entered_timezone', '').strip() or session.get('timezone') or None
            supabase_ok = add_game_stats([game_dt, winner1.strip(), winner2.strip(), loser1.strip(), loser2.strip(),
                winner_score, loser_score, game_dt, comments, tz], updated_by=session.get('username'))
            clear_stats_cache()
            user = session.get('username', 'unknown')
            details = f"Winners: {winner1} & {winner2}; Losers: {loser1} & {loser2}; Score: {winner_score}-{loser_score}"
            log_user_action(user, 'Added doubles game', details)
            new_row = adminfx.snapshot_last_row('doubles_game')
            log_activity('Added doubles game', target='doubles_game',
                         target_id=new_row['id'] if new_row else None,
                         summary=details, after=new_row)
            update_kobs()
            flash('Game saved to database.' + _supabase_flash_suffix(supabase_ok), 'success')
        return redirect(url_for(redirect_to))
    
    current_user = session.get('username')
    players = all_players_ordered_for_doubles(current_username=current_user)
    games = todays_games()
    todays_stats_data = todays_stats()
    l_scores = list(range(0, 21))
    is_voice_page = (redirect_to == 'add_game_voice')
    added = request.args.get('added')
    saved = request.args.get('saved')
    deleted = request.args.get('deleted')
    return render_template('add_game.html', players=players, games=games, year=year,
        l_scores=l_scores, todays_stats=todays_stats_data, form_action=url_for(redirect_to),
        is_voice_page=is_voice_page, added=added, saved=saved, deleted=deleted)


@app.route('/add_game/', methods=['GET', 'POST'])
@login_required
def add_game():
    """Add doubles game page."""
    return _add_doubles_game_view('add_game')


@app.route('/add_game_voice/', methods=['GET', 'POST'])
@login_required
def add_game_voice():
    """Add doubles game page (same as add_game, linked from hamburger for Kyle only)."""
    return _add_doubles_game_view('add_game_voice')


@app.route('/api/parse_voice_doubles', methods=['POST'])
@login_required
def api_parse_voice_doubles():
    """Parse a spoken doubles game transcript into structured fields using Gemini."""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401

    data = request.get_json() or {}
    transcript = (data.get('transcript') or '').strip()
    if not transcript:
        return jsonify({'success': False, 'error': 'No transcript provided.'}), 400

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return jsonify({
            'success': False,
            'error': 'Gemini API key not configured. Please set GEMINI_API_KEY environment variable.'
        }), 400

    all_games = year_games('All years')
    recent_players = []
    seen = set()
    for game in all_games:
        for idx in (2, 3, 5, 6):
            p = (game[idx] or '').strip()
            if p and p not in seen:
                seen.add(p)
                recent_players.append(p)
                if len(recent_players) >= 30:
                    break
        if len(recent_players) >= 30:
            break
    players_str = ', '.join(recent_players) if recent_players else '(no players yet)'

    try:
        prompt = f"""You are parsing a spoken doubles volleyball game result into structured data.

Known players (use EXACT full names from this list): {players_str}

Transcript from the user: "{transcript}"

Rules:
- Identify the two winners and two losers, and the final score (winner score, loser score).
- Map each spoken name (first name, nickname, or partial name) to the EXACT full name from the known players list above. If only one person matches, use that full name.
- If a name cannot be matched to the list, leave that field as empty string "".
- Common phrases: "X and Y beat Z and W 21 13", "X and Y won 21-13 against Z and W", "X and Y over Z and W 21-13".
- winner_score must be greater than loser_score (e.g. 21 and 13).

Respond with ONLY a JSON object, no other text, with these exact keys: winner1, winner2, loser1, loser2, winner_score, loser_score. Use strings for names (empty string "" if no match) and integers for scores.
Example: {{"winner1": "Kyle Thomson", "winner2": "Aaron Plumb", "loser1": "Dan Ferris", "loser2": "Zac Prost", "winner_score": 21, "loser_score": 13}}"""

        text = generate_ai_text(prompt)
        # Strip markdown code fence if present
        if text.startswith('```'):
            lines = text.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            text = '\n'.join(lines)
        parsed = json.loads(text)

        for key in ('winner1', 'winner2', 'loser1', 'loser2'):
            if key not in parsed or not isinstance(parsed.get(key), str):
                return jsonify({'success': False, 'error': f'Missing or invalid field: {key}'}), 400
            parsed[key] = parsed[key].strip()
        for key in ('winner_score', 'loser_score'):
            if key not in parsed:
                return jsonify({'success': False, 'error': f'Missing field: {key}'}), 400
            try:
                parsed[key] = int(parsed[key])
            except (TypeError, ValueError):
                return jsonify({'success': False, 'error': f'Invalid score: {key}'}), 400
        if parsed['winner_score'] <= parsed['loser_score']:
            return jsonify({'success': False, 'error': "Winner's score must be higher than loser's score."}), 400

        return jsonify({
            'success': True,
            'winner1': parsed['winner1'],
            'winner2': parsed['winner2'],
            'loser1': parsed['loser1'],
            'loser2': parsed['loser2'],
            'winner_score': parsed['winner_score'],
            'loser_score': parsed['loser_score'],
        })
    except json.JSONDecodeError as e:
        return jsonify({'success': False, 'error': 'Could not parse the result. Try speaking more clearly or rephrasing.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/add_vollis_game/', methods=['GET', 'POST'])
@login_required
def add_vollis_game():
    """Add vollis game page."""
    year = str(date.today().year)
    if request.method == 'POST':
        winner = request.form['winner'].strip()
        loser = request.form['loser'].strip()
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not winner or not loser or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            client_date = request.form.get('client_date', '').strip()
            client_time = request.form.get('client_time', '').strip()
            game_dt = parse_client_datetime_for_game(client_date, client_time)
            if game_dt is None:
                now = get_user_now_only()
                if now is None:
                    flash('Could not determine your timezone. Please refresh the page and try again.')
                    return redirect(url_for('add_vollis_game'))
                game_dt = now.strftime('%Y-%m-%d %H:%M:%S')
            tz = request.form.get('entered_timezone', '').strip() or session.get('timezone') or None
            add_vollis_stats([game_dt, winner, loser, winner_score, loser_score, game_dt, tz])
            user = session.get('username', 'unknown')
            details = f"Winner: {winner}; Loser: {loser}; Score: {winner_score}-{loser_score}"
            log_user_action(user, 'Added vollis game', details)
            new_row = adminfx.snapshot_last_row('vollis_game')
            log_activity('Added vollis game', target='vollis_game',
                         target_id=new_row['id'] if new_row else None,
                         summary=details, after=new_row)
        return redirect(url_for('add_vollis_game'))
    
    all_games = vollis_year_games('All years')
    players = all_vollis_players(all_games)
    games = todays_vollis_games()
    todays_stats_data = todays_vollis_stats()
    winning_scores = list(range(11, 27))
    losing_scores = list(range(0, 26))
    return render_template('add_vollis_game.html', players=players, games=games, year=year,
        winning_scores=winning_scores, losing_scores=losing_scores, todays_stats=todays_stats_data)

@app.route('/add_other_game/', methods=['GET', 'POST'])
@login_required
def add_other_game():
    """Add other game page."""
    from other_functions import all_combined_players
    year = str(date.today().year)
    
    if request.method == 'POST':
        game_type = request.form.get('game_type', '')
        game_name = request.form.get('game_name', '')
        score_type = request.form.get('score_type', 'individual') or 'individual'
        winners = []
        winner_scores = []
        losers = []
        loser_scores = []
        team_winner_score = None
        team_loser_score = None

        for i in range(1, 16):
            winner_name = request.form.get(f'winner{i}', '').strip()
            if winner_name:
                winners.append(winner_name)
                if score_type == 'individual':
                    winner_scores.append(request.form.get(f'winner{i}_score', '').strip())
                else:
                    winner_scores.append('')

        for i in range(1, 16):
            loser_name = request.form.get(f'loser{i}', '').strip()
            if loser_name:
                losers.append(loser_name)
                if score_type == 'individual':
                    loser_scores.append(request.form.get(f'loser{i}_score', '').strip())
                else:
                    loser_scores.append('')

        if score_type == 'team':
            team_winner_score = request.form.get('winner_score', '').strip()
            team_loser_score = request.form.get('loser_score', '').strip()
        elif score_type == 'none':
            team_winner_score = None
            team_loser_score = None

        comment = request.form.get('comment', '')

        # Games that have had scores before (by game_name) must have scores on this entry too (unless user chose "No Scores")
        from other_functions import game_name_requires_scores
        requires_scores = game_name_requires_scores(game_name)
        if score_type == 'none':
            has_scores = True  # no scores option: never require scores
        elif requires_scores:
            if score_type == 'team':
                has_scores = bool(team_winner_score and team_loser_score)
            else:
                has_scores = bool(
                    any(s for s in winner_scores if s not in ('', None)) and
                    any(s for s in loser_scores if s not in ('', None))
                )
        else:
            has_scores = True  # not required, so pass

        if not game_type or not game_name or not winners or not losers:
            flash('Some fields missing!')
        elif requires_scores and not has_scores:
            if score_type == 'team':
                flash('This game type uses team scores. Please enter both Winner and Loser team scores.')
            else:
                flash('This game type uses scores. Please enter at least one score for winners and one for losers.')
        else:
            client_date = request.form.get('client_date', '').strip()
            client_time = request.form.get('client_time', '').strip()
            game_dt = parse_client_datetime_for_game(client_date, client_time)
            if game_dt is None:
                now = get_user_now_only()
                if now is None:
                    flash('Could not determine your timezone. Please refresh the page and try again.')
                    return redirect(url_for('add_other_game'))
                game_dt = now.strftime('%Y-%m-%d %H:%M:%S')
            tz = request.form.get('entered_timezone', '').strip() or session.get('timezone') or None
            add_other_stats(
                game_dt, game_type, game_name, winners, winner_scores,
                losers, loser_scores, comment, game_dt,
                team_winner_score, team_loser_score, tz,
                entered_by=session.get('username', '')
            )
            user = session.get('username', 'unknown')
            details = f"Game: {game_type} - {game_name}; Winners: {', '.join(winners)}; Losers: {', '.join(losers)}"
            log_user_action(user, 'Added other game', details)
            new_row = adminfx.snapshot_last_row('other_game')
            log_activity('Added other game', target='other_game',
                         target_id=new_row['id'] if new_row else None,
                         summary=details, after=new_row)
        return redirect(url_for('add_other_game'))
    
    players = all_combined_players()
    games_dict = other_year_games('All years')
    game_names = other_game_names(games_dict)
    game_types = other_game_types(games_dict)
    games = todays_other_games()
    todays_stats_data = todays_other_stats()
    from other_functions import game_name_requires_scores
    game_names_requiring_scores = [n for n in game_names if game_name_requires_scores(n)]
    return render_template('add_other_game.html', players=players, games=games, year=year,
        game_names=game_names, game_types=game_types, todays_stats=todays_stats_data,
        game_names_requiring_scores=game_names_requiring_scores)


# ============================================
# PLAYER LIST ROUTE
# ============================================

@app.route('/player_list/')
@login_required
def player_list():
    """Player list page."""
    from player_functions import get_all_players
    players = get_all_players()
    all_unique_players = sorted(player_row[1] for player_row in players)
    player_cards = build_player_list_cards(players)
    return render_template(
        'player_list.html',
        players=players,
        player_cards=player_cards,
        all_unique_players=all_unique_players,
    )


# ============================================
# PLAYER STATS ROUTES
# ============================================

@app.route('/player/<year>/<name>/')
def player_stats(year, name):
    """Doubles player stats page."""
    games = games_from_player_by_year(year, name)
    all_years = all_years_player(name)
    stats = total_stats(games, name)
    # ~5% of this player's games that year (see player_matchup_min_games).
    winpct_min_games = player_matchup_min_games(len(games) if games else 0)
    partner_stats = partner_stats_by_year(name, games, winpct_min_games)
    opponent_stats = opponent_stats_by_year(name, games, winpct_min_games)

    # TrueSkill rating + rank for this year
    player_rating = None
    player_rank = None
    total_ranked = 0
    try:
        rankings = calculate_trueskill_rankings(year)
        total_ranked = len(rankings)
        for i, entry in enumerate(rankings):
            if entry['player'] == name:
                player_rating = entry['rating']
                player_rank = i + 1
                break
    except Exception:
        pass

    # Current streak and recent form (games list is chronological ascending)
    current_streak = None
    if games:
        streak_type, streak_len = None, 0
        for game in reversed(games):
            result = 'W' if name in (game[2], game[3]) else 'L'
            if streak_type is None:
                streak_type, streak_len = result, 1
            elif result == streak_type:
                streak_len += 1
            else:
                break
        current_streak = {'type': streak_type, 'length': streak_len}
    recent_form = ['W' if name in (g[2], g[3]) else 'L' for g in games[-10:]]

    return render_template('player.html', opponent_stats=opponent_stats,
        partner_stats=partner_stats, year=year, player=name,
        all_years=all_years, stats=stats, games=games,
        player_rating=player_rating, player_rank=player_rank, total_ranked=total_ranked,
        current_streak=current_streak, recent_form=recent_form,
        winpct_min_games=winpct_min_games,
        **player_avatar_context(name))

@app.route('/vollis_player/<year>/<name>/')
def vollis_player_stats(year, name):
    """Vollis player stats page."""
    all_years = all_years_vollis_player(name)
    games = games_from_vollis_player_by_year(year, name)
    stats = total_vollis_stats(name, games)
    winpct_min_games = player_matchup_min_games(len(games) if games else 0)
    opponent_stats = vollis_opponent_stats_by_year(name, games, winpct_min_games)
    return render_template('vollis_player.html', opponent_stats=opponent_stats,
        year=year, player=name, all_years=all_years, stats=stats, games=games,
        winpct_min_games=winpct_min_games,
        **player_avatar_context(name))

@app.route('/other_player/<year>/<name>/')
def other_player_stats(year, name):
    """Other player stats page."""
    all_years = all_years_other_player(name)
    games = games_from_other_player_by_year(year, name)
    stats = total_other_stats(name, games)
    winpct_min_games = player_matchup_min_games(len(games) if games else 0)
    opponent_stats = other_opponent_stats_by_year(name, games, winpct_min_games)
    return render_template('other_player.html', opponent_stats=opponent_stats,
        year=year, player=name, all_years=all_years, stats=stats, games=games,
        winpct_min_games=winpct_min_games,
        **player_avatar_context(name))


def calculate_tile_stats(year, stats, games):
    """Calculate stats for the tile cards."""
    tiles = {
        'games': len(games) if games else 0,
        'players': len(stats) if stats else 0,
        'top_rating': 0,
        'top_rating_player': '—',
        'most_games_count': 0,
        'most_games_player': '—',
        'avg_win_pct': 0,
        'highest_win_pct_value': '—',
        'highest_win_pct_player': '—'
    }
    
    if stats:
        # Top rating (stats is sorted by rating, index 4 is rating)
        tiles['top_rating'] = stats[0][4] if stats[0][4] else 0
        tiles['top_rating_player'] = stats[0][0]
        
        # Most games played
        most_games = max(stats, key=lambda x: x[1] + x[2])
        tiles['most_games_count'] = most_games[1] + most_games[2]
        tiles['most_games_player'] = most_games[0]
        
        # Average win percentage
        total_win_pct = sum(s[3] for s in stats)
        tiles['avg_win_pct'] = total_win_pct / len(stats) if stats else 0
        
        # Highest win percentage (minimum 5 games)
        qualified = [s for s in stats if (s[1] + s[2]) >= 5]
        if qualified:
            best = max(qualified, key=lambda x: x[3])
            tiles['highest_win_pct_value'] = f"{best[3]*100:.0f}%"
            tiles['highest_win_pct_player'] = best[0]
    
    return tiles


@app.route('/edit/<int:id>/',methods = ['GET','POST'])
@login_required
def update(id):
    game_id = id
    x = find_game(id)
    if not x:
        flash('Game not found.')
        return redirect(url_for('edit_games', year=str(date.today().year)))
    raw_game = x[0]
    existing_comment = ''
    if len(raw_game) > 9 and raw_game[9]:
        existing_comment = raw_game[9]
    game = [
        raw_game[0],  # id
        raw_game[1],  # game_date
        raw_game[2],  # winner1
        raw_game[3],  # winner2
        raw_game[4],  # winner_score
        raw_game[5],  # loser1
        raw_game[6],  # loser2
        raw_game[7],  # loser_score
        raw_game[8],  # updated_at
        existing_comment
    ]
    w_scores = winners_scores()
    l_scores = losers_scores()
    games = year_games(str(date.today().year))
    players = all_players(games)
    if request.method == 'POST':
        game_date = request.form['game_date']
        game_time = request.form['game_time']
        winner1 = request.form['winner1']
        winner2 = request.form['winner2']
        loser1 = request.form['loser1']
        loser2 = request.form['loser2']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']
        comment = request.form.get('comment', '').strip()
        game[9] = comment

        if not game_date or not game_time or not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            # Combine date and time into the format expected by the database
            combined_datetime = f"{game_date} {game_time}:00"
            before_row = adminfx.snapshot_row('doubles_game', game_id)
            supabase_ok = update_game(game_id, combined_datetime, winner1, winner2, winner_score, loser1, loser2, loser_score, get_user_now(), comment, game_id, updated_by=session.get('username'))
            
            # Clear stats cache after editing a game
            clear_stats_cache()
            
            # Log the action for the activity feed
            user = session.get('username', 'unknown')
            details = f"Game ID {game_id}: {winner1}/{winner2} vs {loser1}/{loser2} ({winner_score}-{loser_score})"
            log_user_action(user, 'Edited doubles game', details)
            log_activity('Edited doubles game', target='doubles_game', target_id=game_id,
                         summary=details, before=before_row,
                         after=adminfx.snapshot_row('doubles_game', game_id))
            
            # Update KOBs after editing game
            update_kobs()
            flash('Game updated in database.' + _supabase_flash_suffix(supabase_ok), 'success')
            
            # Check if user came from add game page
            from_add_game = request.form.get('from_add_game')
            if from_add_game == 'true':
                return redirect(url_for('add_game'))
            else:
                return redirect(url_for('edit_games', year=str(date.today().year)))
 
    return render_template('edit_game.html', game=game, players=players, 
        w_scores=w_scores, l_scores=l_scores, year=str(date.today().year),
        from_add_game=request.args.get('from_add_game'))

@app.route('/delete/<int:id>/',methods = ['GET','POST'])
@login_required
def delete_game(id):
    game_id = id
    game = find_game(id)
    from_add_game = request.args.get('from_add_game', 'false')
    from_redesign = request.args.get('from_redesign', 'false')
    if request.method == 'POST':
        # Log the action for the activity feed before deleting
        details = f"Game ID {game_id}"
        if game and len(game) > 0 and len(game[0]) >= 8:
            user = session.get('username', 'unknown')
            game_data = game[0]  # Get the first (and only) row
            details = f"Game ID {game_id}: {game_data[2]}/{game_data[3]} vs {game_data[5]}/{game_data[6]} ({game_data[4]}-{game_data[7]})"
            log_user_action(user, 'Deleted doubles game', details)
        before_row = adminfx.snapshot_row('doubles_game', game_id)
        supabase_ok = remove_game(game_id)
        log_activity('Deleted doubles game', target='doubles_game', target_id=game_id,
                     summary=details, before=before_row)
        
        # Clear stats cache after deleting a game
        clear_stats_cache()
        
        # Update KOBs after deleting game
        update_kobs()
        flash('Game deleted from database.' + _supabase_flash_suffix(supabase_ok), 'success')
        
        # Redirect back to appropriate page
        if request.form.get('from_redesign') == 'true':
            return redirect(url_for('add_game'))
        if request.form.get('from_add_game') == 'true':
            return redirect(url_for('add_game'))
        return redirect(url_for('edit_games', year=str(date.today().year)))
 
    year = str(date.today().year)
    return render_template('delete_game.html', game=game, from_add_game=from_add_game, from_redesign=from_redesign, year=year)

## VOLLIS ROUTES


@app.route('/edit_vollis_game/<int:id>/',methods = ['GET','POST'])
@login_required
def update_vollis_game(id):
    game_id = id
    x = find_vollis_game(game_id)
    game = [x[0][0], x[0][1], x[0][2], x[0][3], x[0][4], x[0][5], x[0][6]]
    games = vollis_year_games(str(date.today().year))
    players = all_vollis_players(games)
    if request.method == 'POST':
        winner = request.form['winner']
        loser = request.form['loser']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not winner or not loser or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            before_row = adminfx.snapshot_row('vollis_game', game_id)
            edit_vollis_game(game_id, game[1], winner, winner_score, loser, loser_score, get_user_now(), game_id)
            
            # Log the action for the activity feed
            user = session.get('username', 'unknown')
            details = f"Game ID {game_id}: {winner} vs {loser} ({winner_score}-{loser_score})"
            log_user_action(user, 'Edited vollis game', details)
            log_activity('Edited vollis game', target='vollis_game', target_id=game_id,
                         summary=details, before=before_row,
                         after=adminfx.snapshot_row('vollis_game', game_id))
            
            return redirect(url_for('edit_vollis_games', year=str(date.today().year)))
 
    return render_template('edit_vollis_game.html', game=game, players=players, year=str(date.today().year))


@app.route('/delete_vollis_game/<int:id>/',methods = ['GET','POST'])
@login_required
def delete_vollis_game(id):
    game_id = id
    game = find_vollis_game(id)
    from_add_game = request.args.get('from_add_game', 'false')
    from_redesign = request.args.get('from_redesign', 'false')
    if request.method == 'POST':
        # Log the action for the activity feed before deleting
        user = session.get('username', 'unknown')
        details = f"Game ID {game_id}: {game[0][2]} vs {game[0][3]} ({game[0][4]}-{game[0][5]})"
        log_user_action(user, 'Deleted vollis game', details)
        before_row = adminfx.snapshot_row('vollis_game', game_id)
        remove_vollis_game(game_id)
        log_activity('Deleted vollis game', target='vollis_game', target_id=game_id,
                     summary=details, before=before_row)
        
        # Redirect back to appropriate page
        if request.form.get('from_redesign') == 'true':
            return redirect(url_for('add_vollis_game'))
        if request.form.get('from_add_game') == 'true':
            return redirect(url_for('add_vollis_game'))
        return redirect(url_for('edit_vollis_games', year=str(date.today().year)))
 
    return render_template('delete_vollis_game.html', game=game, from_add_game=from_add_game, from_redesign=from_redesign)

@app.route('/single_game_stats/<game_name>/')
def single_game_stats(game_name):
    return redirect(url_for('index'))

@app.route('/single_game_stats/<game_name>/<year>/')
def single_game_stats_with_year(game_name, year):
    return redirect(url_for('index'))






## OTHER ROUTES




def build_other_game_cards(year, exclude_volleyball=True, minimum_games=1):
    """Build per-game cards for other games.
    
    If exclude_volleyball is True, consolidates all Volleyball games into a single summary card.
    minimum_games is used to filter players in the consolidated volleyball card.
    """
    from other_functions import other_year_games, other_game_names, total_game_name_stats, other_game_type_for_name
    
    games = other_year_games(year)
    game_cards = []
    volleyball_games = []
    
    if games:
        game_names = other_game_names(games)
        for game_name in game_names:
            game_specific = [game for game in games if game.get('game_name') == game_name]
            if not game_specific:
                continue
            
            # Check if this is a volleyball game
            game_type = other_game_type_for_name(games, game_name)
            if exclude_volleyball and game_type == 'Volleyball':
                volleyball_games.extend(game_specific)
                continue
            
            stats_for_game = total_game_name_stats(game_specific)
            if not stats_for_game:
                continue
            
            # Calculate minimum games for this game type using same formula as doubles
            num_games = len(game_specific)
            if num_games < 30:
                card_minimum_games = 1
            else:
                card_minimum_games = num_games // 30
            
            # Split stats into qualified and rare
            qualified_stats = [s for s in stats_for_game if (s[1] + s[2]) >= card_minimum_games]
            rare_stats = [s for s in stats_for_game if (s[1] + s[2]) < card_minimum_games]
            
            game_cards.append({
                'game_name': game_name,
                'stats': qualified_stats,
                'rare_stats': rare_stats,
                'minimum_games': card_minimum_games,
                'total_games': len(game_specific)  # Count actual games, not player participations
            })
        
        # Add consolidated volleyball card if we have volleyball games
        if exclude_volleyball and volleyball_games:
            volleyball_stats = total_game_name_stats(volleyball_games)
            if volleyball_stats:
                total_vb_games = len(volleyball_games)  # Count actual games, not player participations
                # Count unique volleyball game types
                vb_game_names = set(g.get('game_name') for g in volleyball_games)
                
                # Calculate minimum games for volleyball based on total volleyball games
                if len(volleyball_games) < 30:
                    vb_minimum_games = 1
                else:
                    vb_minimum_games = len(volleyball_games) // 30
                
                # Split stats by minimum games requirement
                qualified_stats = [s for s in volleyball_stats if (s[1] + s[2]) >= vb_minimum_games]
                rare_stats = [s for s in volleyball_stats if (s[1] + s[2]) < vb_minimum_games]
                
                game_cards.append({
                    'game_name': 'Volleyball',
                    'game_type': 'Volleyball',
                    'is_consolidated': True,
                    'num_game_types': len(vb_game_names),
                    'stats': qualified_stats,
                    'rare_stats': rare_stats,
                    'total_games': total_vb_games,
                    'minimum_games': vb_minimum_games
                })
    
    # Sort all cards by total games descending
    game_cards.sort(key=lambda x: x['total_games'], reverse=True)
    
    return game_cards


def build_volleyball_game_cards(year):
    """Build per-game cards for volleyball games only."""
    from other_functions import other_year_games, other_game_names, total_game_name_stats, other_game_type_for_name
    
    games = other_year_games(year)
    game_cards = []
    
    if games:
        game_names = other_game_names(games)
        for game_name in game_names:
            game_specific = [game for game in games if game.get('game_name') == game_name]
            if not game_specific:
                continue
            
            # Only include volleyball games
            game_type = other_game_type_for_name(games, game_name)
            if game_type != 'Volleyball':
                continue
            
            stats_for_game = total_game_name_stats(game_specific)
            if not stats_for_game:
                continue
            game_cards.append({
                'game_name': game_name,
                'stats': stats_for_game,  # Pass all stats, template handles display limit
                'total_games': len(game_specific)  # Count actual games, not player participations
            })
        
        # Sort by total games descending
        game_cards.sort(key=lambda x: x['total_games'], reverse=True)
    
    return game_cards


def _other_game_card_for_year(year, game_name):
    """Build stats card data for one other game type in a given year."""
    from other_functions import other_year_games, total_game_name_stats

    all_games = other_year_games(year)
    game_specific = [g for g in all_games if g.get('game_name') == game_name]
    if not game_specific:
        return None

    stats_for_game = total_game_name_stats(game_specific)
    num_games = len(game_specific)
    minimum_games = 1 if num_games < 30 else num_games // 30
    qualified_stats = [s for s in stats_for_game if (s[1] + s[2]) >= minimum_games]
    rare_stats = [s for s in stats_for_game if (s[1] + s[2]) < minimum_games]
    return {
        'game_name': game_name,
        'stats': qualified_stats,
        'rare_stats': rare_stats,
        'minimum_games': minimum_games,
        'total_games': num_games,
    }


@app.route('/volleyball_stats/')
def volleyball_stats_default():
    return redirect(url_for('volleyball_stats', year=str(date.today().year)))

@app.route('/volleyball_stats/<year>/')
def volleyball_stats(year):
    """Volleyball stats page: one card per volleyball game type (Beach, Indoor, etc.)."""
    all_years = all_other_years()
    game_cards = build_volleyball_game_cards_styled(year)
    return render_template('volleyball_stats.html', game_cards=game_cards, year=year, all_years=all_years)


def build_volleyball_game_cards_styled(year):
    """Build per-game cards for volleyball games (from other games)."""
    from other_functions import other_year_games, other_game_names, total_game_name_stats
    
    games = other_year_games(year)
    game_cards = []
    
    if games:
        volleyball_games = [g for g in games if g.get('game_type') == 'Volleyball']
        game_names = other_game_names(volleyball_games)
        for game_name in game_names:
            game_specific = [g for g in volleyball_games if g.get('game_name') == game_name]
            stats_for_game = total_game_name_stats(game_specific)
            if not stats_for_game:
                continue
            num_games = len(game_specific)
            card_minimum_games = 1 if num_games < 30 else num_games // 30
            qualified_stats = [s for s in stats_for_game if (s[1] + s[2]) >= card_minimum_games]
            rare_stats = [s for s in stats_for_game if (s[1] + s[2]) < card_minimum_games]
            game_cards.append({
                'game_name': game_name,
                'stats': qualified_stats,
                'rare_stats': rare_stats,
                'total_games': num_games,
                'minimum_games': card_minimum_games,
                'is_consolidated': False
            })
        game_cards.sort(key=lambda x: x['total_games'], reverse=True)
    
    return game_cards


@app.route('/volleyball_player/<year>/<name>')
def volleyball_player_stats(year, name):
    """Volleyball stats page for a specific player."""
    from other_functions import other_year_games, total_game_name_stats, other_game_names, _is_valid_player_name
    
    all_years = all_other_years()
    games = other_year_games(year)
    
    # Filter to only volleyball games where this player participated
    player_volleyball_games = []
    for game in games:
        if game.get('game_type') != 'Volleyball':
            continue
        for i in range(1, 16):
            winner = game.get(f'winner{i}')
            loser = game.get(f'loser{i}')
            if (winner and _is_valid_player_name(winner) and winner == name) or \
               (loser and _is_valid_player_name(loser) and loser == name):
                player_volleyball_games.append(game)
                break
    
    # Calculate overall stats for this player
    wins, losses = 0, 0
    for game in player_volleyball_games:
        for i in range(1, 16):
            winner = game.get(f'winner{i}')
            loser = game.get(f'loser{i}')
            if winner and _is_valid_player_name(winner) and winner == name:
                wins += 1
                break
            if loser and _is_valid_player_name(loser) and loser == name:
                losses += 1
                break
    
    total_games = wins + losses
    win_percentage = wins / total_games if total_games > 0 else 0
    overall_stats = [[name, wins, losses, win_percentage, total_games]]
    
    # Build game cards for each volleyball game type this player has played
    game_cards = []
    game_names = other_game_names(player_volleyball_games)
    for game_name in game_names:
        game_specific = [g for g in player_volleyball_games if g.get('game_name') == game_name]
        if not game_specific:
            continue
        
        type_wins, type_losses = 0, 0
        for game in game_specific:
            for i in range(1, 16):
                winner = game.get(f'winner{i}')
                loser = game.get(f'loser{i}')
                if winner and _is_valid_player_name(winner) and winner == name:
                    type_wins += 1
                    break
                if loser and _is_valid_player_name(loser) and loser == name:
                    type_losses += 1
                    break
        
        type_total = type_wins + type_losses
        type_win_pct = type_wins / type_total if type_total > 0 else 0
        
        game_cards.append({
            'game_name': game_name,
            'wins': type_wins,
            'losses': type_losses,
            'win_percentage': type_win_pct,
            'total_games': type_total
        })
    
    game_cards.sort(key=lambda x: x['total_games'], reverse=True)
    
    return render_template('volleyball_player.html',
        player=name,
        year=year,
        all_years=all_years,
        stats=overall_stats,
        game_cards=game_cards,
        total_games=total_games,
        **player_avatar_context(name))


@app.route('/edit_other_game/<int:id>/',methods = ['GET','POST'])
@login_required
def update_other_game(id):
    game_id = id
    x = find_other_game(game_id)
    if not x:
        flash('Game not found!')
        return redirect(url_for('edit_other_games', year=str(date.today().year)))
    
    # Get the full game data (all 20 fields); Row needs zip(keys, row) for column-name keys
    game_row = x[0]
    game_data_dict = dict(zip(game_row.keys(), game_row)) if hasattr(game_row, 'keys') else dict(game_row)
    games = other_year_games(str(date.today().year))
    games_all = other_year_games('All years')
    players = all_other_players(games)
    game_names = other_game_names(games_all)
    game_types = other_game_types(games_all)
    winner_count = next((i for i in range(15, 0, -1) if game_data_dict.get(f'winner{i}')), 1)
    loser_count = next((i for i in range(15, 0, -1) if game_data_dict.get(f'loser{i}')), 1)
    
    if request.method == 'POST':
        game_type = request.form.get('game_type', '')
        game_name = request.form.get('game_name', '')
        score_type = request.form.get('score_type', 'individual')
        winners = []
        winner_scores = []
        losers = []
        loser_scores = []

        for i in range(1, 16):
            winner_name = request.form.get(f'winner{i}', '').strip()
            winner_score_value = request.form.get(f'winner{i}_score', '').strip()
            if winner_name:
                winners.append(winner_name)
                winner_scores.append(winner_score_value if score_type == 'individual' else '')

        for i in range(1, 16):
            loser_name = request.form.get(f'loser{i}', '').strip()
            loser_score_value = request.form.get(f'loser{i}_score', '').strip()
            if loser_name:
                losers.append(loser_name)
                loser_scores.append(loser_score_value if score_type == 'individual' else '')

        comment = request.form.get('comment', '')
        
        # Get team scores (for team scoring mode)
        team_winner_score = request.form.get('winner_score', '').strip()
        team_loser_score = request.form.get('loser_score', '').strip()

        # Games that have had scores before (by game_name) must have scores on this entry too (unless "No Scores")
        from other_functions import game_name_requires_scores
        requires_scores = game_name_requires_scores(game_name)
        if score_type == 'none':
            has_scores = True
        elif requires_scores:
            if score_type == 'team':
                has_scores = bool(team_winner_score and team_loser_score)
            else:
                has_scores = bool(
                    any(s for s in winner_scores if s not in ('', None)) and
                    any(s for s in loser_scores if s not in ('', None))
                )
        else:
            has_scores = True

        if not game_type or not game_name or not winners or not losers:
            flash('Required fields missing!')
        elif requires_scores and not has_scores:
            if score_type == 'team':
                flash('This game type uses team scores. Please enter both Winner and Loser team scores.')
            else:
                flash('This game type uses scores. Please enter at least one score for winners and one for losers.')
        else:
            # Update the game using the database function
            from other_functions import database_update_other_game
            from database_functions import create_connection
            
            database = '/home/Idynkydnk/stats/stats.db'
            conn = create_connection(database)
            if conn is None:
                database = r'stats.db'
                conn = create_connection(database)
            
            # Determine aggregate scores based on score type
            if score_type == 'team':
                aggregate_winner_score = int(team_winner_score) if team_winner_score else None
                aggregate_loser_score = int(team_loser_score) if team_loser_score else None
            elif score_type == 'none':
                aggregate_winner_score = None
                aggregate_loser_score = None
            else:
                aggregate_winner_score = next((int(score) for score in winner_scores if score not in ("", None)), None)
                aggregate_loser_score = next((int(score) for score in loser_scores if score not in ("", None)), None)
            
            before_row = adminfx.snapshot_row('other_game', game_id)
            with conn:
                game_data = tuple(
                    [game_row[1], game_type, game_name]
                    + (winners + [""] * 15)[:15]
                    + [(int(score) if score not in ("", None) else None) for score in (winner_scores + [None] * 15)[:15]]
                    + [aggregate_winner_score]
                    + (losers + [""] * 15)[:15]
                    + [(int(score) if score not in ("", None) else None) for score in (loser_scores + [None] * 15)[:15]]
                    + [aggregate_loser_score, comment, get_user_now(), game_id]
                )
                database_update_other_game(conn, game_data)
            
            # Log the action for the activity feed
            user = session.get('username', 'unknown')
            details = f"Game ID {game_id}: {game_type} - {game_name}; Winners: {', '.join(winners)}; Losers: {', '.join(losers)}"
            log_user_action(user, 'Edited other game', details)
            log_activity('Edited other game', target='other_game', target_id=game_id,
                         summary=details, before=before_row,
                         after=adminfx.snapshot_row('other_game', game_id))
            
            return redirect(url_for('edit_other_games', year=str(date.today().year)))
 
    return render_template('edit_other_game.html', game=game_data_dict, players=players, year=str(date.today().year),
        game_names=game_names, game_types=game_types, winner_count=winner_count, loser_count=loser_count)


@app.route('/delete_other_game/<int:id>/',methods = ['GET','POST'])
@login_required
def delete_other_game(id):
    game_id = id
    game = find_other_game(id)
    from_add_game = request.args.get('from_add_game', 'false')
    from_redesign = request.args.get('from_redesign', 'false')
    if not game:
        flash('Game not found!')
        return redirect(url_for('edit_other_games', year=str(date.today().year)))
    
    if request.method == 'POST':
        # Log the action for the activity feed before deleting
        user = session.get('username', 'unknown')
        # Raw database structure: [id, game_date, game_type, game_name, winner1, winner2, ..., winner_score, loser1, ..., loser_score, comment, updated_at]
        details = f"Game ID {game_id}: {game[0][2]} - {game[0][3]} ({game[0][4]} vs {game[0][11]})"
        log_user_action(user, 'Deleted other game', details)
        before_row = adminfx.snapshot_row('other_game', game_id)
        remove_other_game(game_id)
        log_activity('Deleted other game', target='other_game', target_id=game_id,
                     summary=details, before=before_row)
        
        # Redirect back to appropriate page
        if request.form.get('from_redesign') == 'true':
            return redirect(url_for('add_other_game'))
        if request.form.get('from_add_game') == 'true':
            return redirect(url_for('add_other_game'))
        return redirect(url_for('edit_other_games', year=str(date.today().year)))
 
    return render_template('delete_other_game.html', game=game[0], from_add_game=from_add_game, from_redesign=from_redesign)

@app.route('/game_name_stats/<path:game_name>/')
def game_name_stats(game_name):
    return redirect(url_for('game_name_stats_with_year', game_name=game_name, year=str(date.today().year)))

@app.route('/game_name_stats/<path:game_name>/<year>/')
def game_name_stats_with_year(game_name, year):
    """Stats page for a single other game type."""
    from other_functions import game_name_years

    all_years = game_name_years(game_name)
    card = _other_game_card_for_year(year, game_name)
    return render_template(
        'other_game_stats.html',
        game_name=game_name,
        year=year,
        all_years=all_years,
        card=card,
    )

@app.route('/player_game_stats/<year>/<game_name>/<player_name>/')
def player_game_stats(year, game_name, player_name):
    """Player game stats page for specific game types."""
    from other_functions import player_game_name_games, player_game_name_stats, game_name_years
    
    all_years = game_name_years(game_name)
    games = player_game_name_games(year, game_name, player_name)
    stats = player_game_name_stats(games, player_name)
    
    return render_template('player_game_stats.html',
        player_name=player_name,
        game_name=game_name,
        year=year,
        all_years=all_years,
        stats=stats,
        games=games,
        **player_avatar_context(player_name))


# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Get the 'next' parameter for redirect after login
    next_url = request.args.get('next')
    
    # Check if user is already logged in via remember me cookie
    if not session.get('logged_in'):
        auth_token = request.cookies.get('remember_token')
        if auth_token:
            username = validate_auth_token(auth_token)
            if username:
                # Auto-login the user
                session['logged_in'] = True
                session['username'] = username
                flash(f'Welcome back, {username}!', 'success')
                # Redirect to next_url if provided, otherwise index
                return redirect(next_url if next_url else url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember_me = request.form.get('remember_me') == 'on'
        next_url = request.form.get('next')  # Get from hidden form field

        ip = _client_ip()
        if login_rate_limited(ip):
            flash('Too many failed login attempts. Please wait a few minutes and try again.', 'error')
            return render_template('login.html'), 429

        if verify_password(username, password):
            clear_login_failures(ip)
            session.permanent = True  # Use PERMANENT_SESSION_LIFETIME so session cookie persists
            session['logged_in'] = True
            session['username'] = username
            log_activity('Logged in', summary=f'Web login from {ip}', username=username)
            flash(f'Successfully logged in as {username}!', 'success')
            
            # Redirect to next_url if provided, otherwise index
            redirect_url = next_url if next_url else url_for('index')
            response = make_response(redirect(redirect_url))
            
            # Set remember me cookie if requested (default on so phone stays recognized)
            if remember_me:
                auth_token = create_auth_token(username)
                cookie_days = 90
                response.set_cookie('remember_token', auth_token,
                                  max_age=cookie_days*24*60*60,
                                  secure=request.is_secure,  # HTTPS-only cookie in production, still works on local http
                                  httponly=True,
                                  samesite='Lax')
                flash(f'You will stay logged in on this device for {cookie_days} days.', 'info')
            
            return response
        else:
            record_login_failure(ip)
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    # Get the current user before clearing session
    username = session.get('username')
    
    # Clear session
    session.pop('logged_in', None)
    session.pop('username', None)
    
    # Clear remember me cookie
    auth_token = request.cookies.get('remember_token')
    if auth_token:
        revoke_auth_token(auth_token)
    
    # Revoke all tokens for this user (optional - for security)
    if username:
        revoke_all_user_tokens(username)
    
    response = make_response(redirect(url_for('index')))
    response.set_cookie('remember_token', '', expires=0)
    
    flash('You have been logged out.', 'info')
    return response

# --- API for iPhone app: auth + doubles CRUD and sync ---

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """API login: POST JSON {username, password}. Returns {token, username} for use in Authorization: Bearer <token>."""
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    ip = _client_ip()
    if login_rate_limited(ip):
        return jsonify({'error': 'Too many failed login attempts. Try again in a few minutes.'}), 429
    if not verify_password(username, password):
        record_login_failure(ip)
        return jsonify({'error': 'Invalid username or password'}), 401
    clear_login_failures(ip)
    token = create_auth_token(username)
    log_activity('Logged in', summary=f'iPhone app login from {ip}', username=username)
    return jsonify({'token': token, 'username': username})

@app.route('/api/doubles/games', methods=['GET'])
@api_login_required
def api_doubles_list():
    """List doubles games. Query: year=YYYY (optional), since=ISO8601 (optional, for sync - games with updated_at >= since)."""
    database = _api_get_db()
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    year = request.args.get('year', '').strip()
    since = request.args.get('since', '').strip()
    if since:
        try:
            # Parse ISO8601 and compare; SQLite stores as text
            dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            since_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            since_str = None
    else:
        since_str = None
    if since_str:
        cur.execute("SELECT * FROM games WHERE updated_at >= ? ORDER BY game_date DESC", (since_str,))
    elif year and year != 'All years':
        cur.execute("SELECT * FROM games WHERE strftime('%Y', game_date) = ? ORDER BY game_date DESC", (year,))
    else:
        cur.execute("SELECT * FROM games ORDER BY game_date DESC")
    rows = cur.fetchall()
    conn.close()
    games = [_api_game_row_to_dict(r) for r in rows]
    return jsonify({'games': games})

@app.route('/api/doubles/games/<int:game_id>', methods=['GET'])
@api_login_required
def api_doubles_get(game_id):
    """Get one doubles game by id."""
    x = find_game(game_id)
    if not x or not x[0]:
        return jsonify({'error': 'Game not found'}), 404
    return jsonify(_api_game_row_to_dict(x[0]))

@app.route('/api/doubles/games', methods=['POST'])
@api_login_required
def api_doubles_create():
    """Create a doubles game. JSON: game_date, winner1, winner2, loser1, loser2, winner_score, loser_score, comments?, entered_timezone?."""
    data = request.get_json(force=True, silent=True) or {}
    game_date = (data.get('game_date') or '').strip()
    winner1 = (data.get('winner1') or '').strip()
    winner2 = (data.get('winner2') or '').strip()
    loser1 = (data.get('loser1') or '').strip()
    loser2 = (data.get('loser2') or '').strip()
    try:
        winner_score = int(data.get('winner_score', 0))
        loser_score = int(data.get('loser_score', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'winner_score and loser_score must be integers'}), 400
    comments = (data.get('comments') or '').strip()
    entered_timezone = (data.get('entered_timezone') or '').strip() or None
    if not all([game_date, winner1, winner2, loser1, loser2]):
        return jsonify({'error': 'game_date, winner1, winner2, loser1, loser2 required'}), 400
    if winner_score <= loser_score:
        return jsonify({'error': "winner_score must be greater than loser_score"}), 400
    if winner1 == winner2 or winner1 == loser1 or winner1 == loser2 or winner2 == loser1 or winner2 == loser2 or loser1 == loser2:
        return jsonify({'error': 'All four player names must be unique'}), 400
    from player_functions import get_player_by_name, add_new_player
    for name in (winner1, winner2, loser1, loser2):
        if name and not get_player_by_name(name):
            add_new_player(name)
    # Normalize game_date to YYYY-MM-DD HH:MM:SS if needed
    try:
        if 'T' in game_date:
            game_date = datetime.fromisoformat(game_date.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
        elif len(game_date) == 10:
            game_date = game_date + ' 12:00:00'
    except (ValueError, TypeError):
        pass
    updated_by = session.get('username', 'unknown')
    add_game_stats([game_date, winner1, winner2, loser1, loser2, winner_score, loser_score, game_date, comments, entered_timezone], updated_by=updated_by)
    clear_stats_cache()
    update_kobs()
    # Return the created game (we don't have id easily; fetch last inserted or by unique key)
    conn = sqlite3.connect(_api_get_db())
    cur = conn.execute("SELECT * FROM games ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    new_row = adminfx.snapshot_last_row('doubles_game')
    log_activity('Added doubles game (iPhone)', target='doubles_game',
                 target_id=new_row['id'] if new_row else None,
                 summary=f"{winner1} & {winner2} beat {loser1} & {loser2} {winner_score}-{loser_score}",
                 after=new_row)
    if row:
        game = _api_game_row_to_dict(row)
        return jsonify(game), 201
    return jsonify({'message': 'Game created'}), 201

@app.route('/api/doubles/games/<int:game_id>', methods=['PUT'])
@api_login_required
def api_doubles_update(game_id):
    """Update a doubles game. JSON: game_date?, winner1?, winner2?, loser1?, loser2?, winner_score?, loser_score?, comments?."""
    x = find_game(game_id)
    if not x or not x[0]:
        return jsonify({'error': 'Game not found'}), 404
    row = x[0]
    # row is tuple: id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, entered_timezone?, updated_by?
    def get(i, default=''):
        return (row[i] if i < len(row) else default) or default
    data = request.get_json(force=True, silent=True) or {}
    game_date = (data.get('game_date') or get(1)).strip() if data.get('game_date') is not None else str(get(1)).strip()
    winner1 = (data.get('winner1') or get(2)).strip()
    winner2 = (data.get('winner2') or get(3)).strip()
    loser1 = (data.get('loser1') or get(5)).strip()
    loser2 = (data.get('loser2') or get(6)).strip()
    winner_score = int(data.get('winner_score', get(4)))
    loser_score = int(data.get('loser_score', get(7)))
    comments = (data.get('comments') or get(9)).strip() if data.get('comments') is not None else str(get(9)).strip()
    if winner_score <= loser_score:
        return jsonify({'error': "winner_score must be greater than loser_score"}), 400
    if winner1 == winner2 or winner1 == loser1 or winner1 == loser2 or winner2 == loser1 or winner2 == loser2 or loser1 == loser2:
        return jsonify({'error': 'All four player names must be unique'}), 400
    try:
        if 'T' in game_date:
            game_date = datetime.fromisoformat(game_date.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
        elif len(game_date) == 10:
            game_date = game_date + ' 12:00:00'
    except (ValueError, TypeError):
        pass
    updated_at = get_user_now()
    updated_by = session.get('username', 'unknown')
    before_row = adminfx.snapshot_row('doubles_game', game_id)
    update_game(game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, game_id, updated_by=updated_by)
    clear_stats_cache()
    update_kobs()
    log_activity('Edited doubles game (iPhone)', target='doubles_game', target_id=game_id,
                 summary=f"Game ID {game_id}: {winner1}/{winner2} vs {loser1}/{loser2} ({winner_score}-{loser_score})",
                 before=before_row, after=adminfx.snapshot_row('doubles_game', game_id))
    x = find_game(game_id)
    if x and x[0]:
        return jsonify(_api_game_row_to_dict(x[0]))
    return jsonify({'id': game_id, 'message': 'Updated'})

@app.route('/api/doubles/games/<int:game_id>', methods=['DELETE'])
@api_login_required
def api_doubles_delete(game_id):
    """Delete a doubles game."""
    x = find_game(game_id)
    if not x or not x[0]:
        return jsonify({'error': 'Game not found'}), 404
    before_row = adminfx.snapshot_row('doubles_game', game_id)
    remove_game(game_id)
    clear_stats_cache()
    update_kobs()
    log_activity('Deleted doubles game (iPhone)', target='doubles_game', target_id=game_id,
                 summary=f"Game ID {game_id}", before=before_row)
    return jsonify({'message': 'Deleted', 'id': game_id}), 200

@app.route('/notifications')
@admin_required
def notifications():
    """Notifications were removed; activity lives on the admin dashboard."""
    return redirect(url_for('admin_dashboard'))

@app.route('/mark_notifications_read', methods=['POST'])
@admin_required
def mark_notifications_read_route():
    """Notifications were removed; activity lives on the admin dashboard."""
    return redirect(url_for('admin_dashboard'))

@app.route('/api/notifications/count')
@login_required
def get_notification_count():
    """Legacy endpoint; notifications badge is retired."""
    return jsonify({'count': 0})

@app.route('/deploy', methods=['POST'])
def deploy():
    """Webhook endpoint for automated deployment. Requires X-Deploy-Token header
    matching the DEPLOY_TOKEN env var (set in the WSGI file on PythonAnywhere)."""
    expected_token = os.environ.get('DEPLOY_TOKEN', '')
    if not expected_token:
        return 'Deployment disabled: DEPLOY_TOKEN is not configured on the server', 503
    provided_token = request.headers.get('X-Deploy-Token', '')
    if not secrets.compare_digest(provided_token, expected_token):
        return 'Unauthorized', 403
    try:
        # Change to the stats directory
        os.chdir('/home/Idynkydnk/stats')
        
        # Pull latest changes
        subprocess.run(['git', 'fetch', 'origin'], check=True)
        subprocess.run(['git', 'reset', '--hard', 'origin/main'], check=True)
        
        # Reload the web app
        subprocess.run(['touch', '/var/www/idynkydnk_pythonanywhere_com_wsgi.py'], check=True)
        
        log_activity('Deployed site', summary='Auto-deploy from GitHub push', username='github')
        return 'Deployment successful', 200
    except Exception as e:
        return f'Deployment failed: {str(e)}', 500

@app.route('/api/set_timezone', methods=['POST'])
def set_timezone():
    """Store the user's timezone in the session (detected from browser)"""
    data = request.get_json()
    if data and 'timezone' in data:
        session['timezone'] = data['timezone']
        return jsonify({'status': 'ok', 'timezone': data['timezone']})
    return jsonify({'status': 'error', 'message': 'No timezone provided'}), 400

@app.route('/api/other_game_type/<game_name>')
def get_other_game_type(game_name):
    """API endpoint to get game type for a given game name"""
    games = other_year_games('All years')
    game_type = other_game_type_for_name(games, game_name)
    return {'game_type': game_type} if game_type else {'game_type': None}

@app.route('/api/other_game_common_scores/<game_name>')
def get_other_game_common_scores(game_name):
    """API endpoint to get most common winner/loser scores for a game name (for Coed score dropdowns)."""
    from other_functions import get_common_scores_for_game
    data = get_common_scores_for_game(game_name)
    return jsonify(data)


@app.route('/api/doubles_players')
@login_required
def api_doubles_players():
    """Fresh doubles player list for add-game autocomplete after AJAX submit (no full reload)."""
    current_user = session.get('username')
    players = all_players_ordered_for_doubles(current_username=current_user)
    return jsonify(players)


@app.route('/api/todays_doubles_dashboard')
@login_required
def api_todays_doubles_dashboard():
    """Today's stats + games for add doubles page (updates after AJAX submit)."""
    return jsonify(todays_doubles_dashboard_payload())


@app.route('/api/other_game_players/<game_name>')
@login_required
def get_other_game_players(game_name):
    """API endpoint to get players ordered for a game: by current user's last-entered first."""
    from other_functions import get_players_ordered_for_game
    current_username = session.get('username') or None
    players = get_players_ordered_for_game(game_name, current_username=current_username)
    return jsonify(players)


@app.route('/api/other_game_info/<game_name>')
def get_other_game_info(game_name):
    """API endpoint to get game type, score type, and player counts for a given game name"""
    from other_functions import get_score_type_for_game, get_players_per_side_for_game
    games = other_year_games('All years')
    game_type = other_game_type_for_name(games, game_name)
    score_type = get_score_type_for_game(game_name)
    players_per_side = get_players_per_side_for_game(game_name)
    # Coed with no previous data: default 2v2 team
    if game_type and game_type.lower() == 'coed' and players_per_side is None:
        players_per_side = {'winner_count': 2, 'loser_count': 2}
        score_type = 'team'
    elif players_per_side is None:
        players_per_side = {'winner_count': 1, 'loser_count': 1}
    return {
        'game_type': game_type,
        'score_type': score_type,
        'winner_count': players_per_side['winner_count'],
        'loser_count': players_per_side['loser_count']
    }

@app.route('/api/search_all_players')
def api_search_all_players():
    """Search for players across all years and game types"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    
    try:
        all_players = get_all_unique_players()
        query_lower = query.lower()
        
        # Filter players matching the search query
        matching_players = [p for p in all_players if query_lower in p.lower()]
        
        # For each matching player, get their years and game counts
        results = []
        for player_name in matching_players[:20]:  # Limit to 20 results
            try:
                years_doubles = all_years_player(player_name) or []
            except:
                years_doubles = []
            
            try:
                years_vollis = all_years_vollis_player(player_name) or []
            except:
                years_vollis = []
            
            try:
                years_other = all_years_other_player(player_name) or []
            except:
                years_other = []
            
            # Get most recent year they played (excluding 'All years')
            all_years_list = []
            for y in years_doubles:
                if y != 'All years' and y not in all_years_list:
                    all_years_list.append(y)
            for y in years_vollis:
                if y != 'All years' and y not in all_years_list:
                    all_years_list.append(y)
            for y in years_other:
                if y != 'All years' and y not in all_years_list:
                    all_years_list.append(y)
            
            most_recent_year = max(all_years_list) if all_years_list else None
            
            results.append({
                'name': player_name,
                'years': sorted(all_years_list, reverse=True),
                'most_recent_year': most_recent_year,
                'has_doubles': len(years_doubles) > 0,
                'has_vollis': len(years_vollis) > 0,
                'has_other': len(years_other) > 0
            })
        
        return jsonify(results)
    except Exception as e:
        # Log error and return empty results
        print(f"Error in search_all_players: {e}")
        return jsonify([])

@app.route('/api/search_email_recipients')
@login_required
def api_search_email_recipients():
    """Search known players/emails for AI summary recipient autocomplete."""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])

    try:
        from player_functions import search_email_recipients
        return jsonify(search_email_recipients(query))
    except Exception as e:
        app.logger.exception('Error in search_email_recipients')
        return jsonify([])

@app.route('/api/clear_stats_cache', methods=['POST'])
@login_required
def api_clear_stats_cache():
    """Clear in-memory stats cache (e.g. after running DB migrations)."""
    clear_stats_cache()
    return jsonify({'status': 'ok', 'message': 'Stats cache cleared'})


@app.route('/api/delete_games', methods=['POST'])
@login_required
def api_delete_games():
    """API endpoint to delete multiple games at once"""
    data = request.get_json()
    game_ids = data.get('game_ids', [])
    game_type = data.get('game_type', 'doubles')  # doubles, vollis, or other
    
    if not game_ids:
        return {'success': False, 'error': 'No game IDs provided'}, 400
    
    deleted = 0
    user = session.get('username', 'unknown')
    
    for game_id in game_ids:
        try:
            if game_type == 'doubles':
                game = find_game(game_id)
                if game and len(game) > 0:
                    game_data = game[0]
                    details = f"Game ID {game_id}: {game_data[2]}/{game_data[3]} vs {game_data[5]}/{game_data[6]}"
                    log_user_action(user, 'Deleted doubles game (bulk)', details)
                    before_row = adminfx.snapshot_row('doubles_game', game_id)
                    remove_game(game_id)
                    log_activity('Deleted doubles game (bulk)', target='doubles_game',
                                 target_id=game_id, summary=details, before=before_row)
                    deleted += 1
            elif game_type == 'vollis':
                game = find_vollis_game(game_id)
                if game and len(game) > 0:
                    details = f"Game ID {game_id}: {game[0][2]} vs {game[0][3]}"
                    log_user_action(user, 'Deleted vollis game (bulk)', details)
                    before_row = adminfx.snapshot_row('vollis_game', game_id)
                    remove_vollis_game(game_id)
                    log_activity('Deleted vollis game (bulk)', target='vollis_game',
                                 target_id=game_id, summary=details, before=before_row)
                    deleted += 1
            elif game_type == 'other':
                game = find_other_game(game_id)
                if game:
                    details = f"Game ID {game_id}"
                    log_user_action(user, 'Deleted other game (bulk)', details)
                    before_row = adminfx.snapshot_row('other_game', game_id)
                    remove_other_game(game_id)
                    log_activity('Deleted other game (bulk)', target='other_game',
                                 target_id=game_id, summary=details, before=before_row)
                    deleted += 1
        except Exception as e:
            print(f"Error deleting game {game_id}: {e}")
    
    # Clear caches and update KOBs
    if deleted > 0:
        clear_stats_cache()
        if game_type == 'doubles':
            update_kobs()
    
    return {'success': True, 'deleted': deleted}

def _ensure_tournaments_table(conn):
    """Create tournaments table if it doesn't exist."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tournaments (
            id integer PRIMARY KEY AUTOINCREMENT,
            tournament_date DATE NOT NULL,
            place text NOT NULL,
            team text NOT NULL,
            location text NOT NULL,
            tournament_name text NOT NULL
        )
    ''')
    conn.commit()

@app.route('/tournaments/')
@login_required
def tournaments():
    """Tournaments list page (Kyle-only in menu; any logged-in user can open URL)."""
    conn = sqlite3.connect(_stats_db_path())
    cur = conn.cursor()
    try:
        _ensure_tournaments_table(conn)
        cur.execute('''
            SELECT id, tournament_date, place, team, location, tournament_name
            FROM tournaments
            ORDER BY tournament_date DESC
        ''')
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return render_template('tournaments.html', tournaments=rows)

@app.route('/add_tournament/', methods=('GET', 'POST'))
@login_required
def add_tournament():
    """Add a tournament - form POST or show form."""
    if request.method == 'POST':
        tournament_date = request.form.get('tournament_date', '').strip()
        place = request.form.get('place', '').strip()
        team = request.form.get('team', '').strip()
        location = request.form.get('location', '').strip()
        tournament_name = request.form.get('tournament_name', '').strip()
        if tournament_date and place and team and location and tournament_name:
            conn = sqlite3.connect(_stats_db_path())
            cur = conn.cursor()
            try:
                _ensure_tournaments_table(conn)
                cur.execute('''
                    INSERT INTO tournaments (tournament_date, place, team, location, tournament_name)
                    VALUES (?, ?, ?, ?, ?)
                ''', (tournament_date, place, team, location, tournament_name))
                conn.commit()
                log_activity('Added tournament', summary=f'{tournament_name} ({tournament_date}) - {place} place')
                flash('Tournament added.', 'success')
            except Exception as e:
                flash(f'Error saving: {e}', 'error')
            finally:
                conn.close()
            return redirect(url_for('tournaments'))
        flash('All fields are required.', 'error')
    return render_template('add_tournament.html')

@app.route('/edit_player/<int:player_id>/', methods=['GET', 'POST'])
@login_required
def edit_player(player_id):
    """Edit player information page"""
    from player_functions import (
        get_player_by_id, update_player_info,
        save_player_photo_upload, remove_player_photo,
        save_player_full_body_photo_upload, remove_player_full_body_photo,
    )

    player = get_player_by_id(player_id)

    if not player:
        flash('Player not found')
        return redirect(url_for('player_list'))

    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email'] if request.form['email'] else None
        date_of_birth = request.form['date_of_birth'] if request.form['date_of_birth'] else None
        height = request.form['height'] if request.form['height'] else None
        notes = request.form['notes'] if request.form['notes'] else None

        if not full_name:
            flash('Full name is required!')
        else:
            old_name = player[1]
            update_player_info(player_id, full_name, email, date_of_birth, height, notes)

            photo_msg = ''
            try:
                if request.form.get('remove_photo') == '1':
                    remove_player_photo(player_id)
                    photo_msg = ' Photo removed.'
                elif request.files.get('photo') and request.files['photo'].filename:
                    save_player_photo_upload(player_id, request.files['photo'])
                    photo_msg = ' Photo updated.'
                if request.form.get('remove_full_body_photo') == '1':
                    remove_player_full_body_photo(player_id)
                    photo_msg += ' Full-body photos removed.'
                elif request.files.getlist('full_body_photo'):
                    for f in request.files.getlist('full_body_photo'):
                        if f and f.filename:
                            save_player_full_body_photo_upload(player_id, f)
                    photo_msg += ' Full-body photo(s) updated.'
            except ValueError as e:
                flash(str(e), 'error')
                return render_template(
                    'edit_player.html',
                    player=get_player_by_id(player_id),
                    player_photo_url=player_photo_url_for(player[1]),
                    player_full_body_photos=player_full_body_photos_for(player[1]),
                    player_ai_image_traits=player_ai_image_traits_for(player[1]),
                    player_face_photo_focus=player_face_photo_focus_for(player[1]),
                )

            user = session.get('username', 'unknown')
            if old_name != full_name:
                log_user_action(user, 'Edited player', f'Renamed "{old_name}" to "{full_name}"')
                log_activity('Edited player', summary=f'Renamed "{old_name}" to "{full_name}"{photo_msg}')
                flash(f'Player updated successfully! Name changed from "{old_name}" to "{full_name}" across all games.{photo_msg}')
            else:
                log_user_action(user, 'Edited player', f'Updated info for "{full_name}"')
                log_activity('Edited player', summary=f'Updated info for "{full_name}"{photo_msg}')
                flash(f'Player updated successfully!{photo_msg}')
            return redirect(url_for('player_list'))

    return render_template(
        'edit_player.html',
        player=player,
        player_photo_url=player_photo_url_for(player[1]),
        player_full_body_photos=player_full_body_photos_for(player[1]),
        player_ai_image_traits=player_ai_image_traits_for(player[1]),
    )


@app.route('/api/player_photo/<path:name>/', methods=['POST'])
@login_required
def api_upload_player_photo(name):
    """Upload or remove a player photo from a player stats page."""
    from player_functions import (
        save_player_photo_upload,
        remove_player_photo,
        set_player_face_photo_focus,
        get_player_face_photo_focus,
    )

    name = name.strip()
    if not name:
        return jsonify({'success': False, 'error': 'Player name is required.'}), 400

    player = _ensure_player_record(name)
    if not player or not player[0]:
        return jsonify({'success': False, 'error': 'Could not find or create player record.'}), 400

    player_id = player[0]

    try:
        if request.form.get('focus_x') is not None and request.form.get('focus_y') is not None:
            z = request.form.get('focus_z')
            x, y, z = set_player_face_photo_focus(
                player_id,
                request.form.get('focus_x', 50),
                request.form.get('focus_y', 50),
                z if z is not None else None,
            )
            log_activity('Updated player photo', summary=f'Adjusted face crop for {name}')
            clear_stats_cache()
            return jsonify({'success': True, 'focus': {'x': x, 'y': y, 'z': z}})

        if request.form.get('remove') == '1':
            remove_player_photo(player_id)
            log_activity('Updated player photo', summary=f'Removed photo for {name}')
            clear_stats_cache()
            return jsonify({'success': True, 'photo_url': None, 'focus': {'x': 50, 'y': 50, 'z': 1}})

        file_storage = request.files.get('photo')
        if not file_storage or not file_storage.filename:
            return jsonify({'success': False, 'error': 'No photo file provided.'}), 400

        rel_path = save_player_photo_upload(player_id, file_storage)
        photo_url = url_for('static', filename=rel_path)
        fx, fy, fz = get_player_face_photo_focus(name)
        user = session.get('username', 'unknown')
        log_user_action(user, 'Uploaded player photo', name)
        log_activity('Updated player photo', summary=f'Uploaded photo for {name}')
        clear_stats_cache()
        return jsonify({
            'success': True,
            'photo_url': photo_url,
            'focus': {'x': fx, 'y': fy, 'z': fz},
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        app.logger.exception('Player photo upload failed')
        return jsonify({'success': False, 'error': f'Upload failed: {e}'}), 500


@app.route('/api/player_full_body_photo/<path:name>/', methods=['POST'])
@login_required
def api_upload_player_full_body_photo(name):
    """Upload or remove a player's full-body photo(s) from a player stats page."""
    from player_functions import (
        save_player_full_body_photo_upload,
        remove_player_full_body_photo,
        get_player_full_body_photo_paths,
        get_full_body_photo_crop,
        set_player_full_body_photo_crop,
    )

    name = name.strip()
    if not name:
        return jsonify({'success': False, 'error': 'Player name is required.'}), 400

    player = _ensure_player_record(name)
    if not player or not player[0]:
        return jsonify({'success': False, 'error': 'Could not find or create player record.'}), 400

    player_id = player[0]

    def _photo_payload():
        paths = get_player_full_body_photo_paths(name)
        urls = [url_for('static', filename=p) for p in paths]
        focuses = [
            {
                'x': get_full_body_photo_crop(name, p)['x'],
                'y': get_full_body_photo_crop(name, p)['y'],
                'z': get_full_body_photo_crop(name, p).get('z'),
                'aspect': get_full_body_photo_crop(name, p).get('aspect'),
                'w': get_full_body_photo_crop(name, p).get('w'),
                'h': get_full_body_photo_crop(name, p).get('h'),
            }
            for p in paths
        ]
        return {'photo_urls': urls, 'photo_paths': paths, 'photo_focuses': focuses}

    try:
        crop_path = (request.form.get('crop_path') or '').strip()
        if crop_path and request.form.get('focus_x') is not None and request.form.get('focus_y') is not None:
            w = request.form.get('focus_w')
            h = request.form.get('focus_h')
            if w is not None and h is not None:
                x, y, w, h = set_player_full_body_photo_crop(
                    player_id,
                    crop_path,
                    request.form.get('focus_x', 50),
                    request.form.get('focus_y', 50),
                    w=w,
                    h=h,
                )
                log_activity('Updated player photo', summary=f'Adjusted full-body crop for {name}')
                clear_stats_cache()
                payload = _photo_payload()
                payload.update({'success': True, 'focus': {'x': x, 'y': y, 'w': w, 'h': h}})
                return jsonify(payload)
            z = request.form.get('focus_z')
            aspect = request.form.get('focus_aspect')
            x, y, z, aspect = set_player_full_body_photo_crop(
                player_id,
                crop_path,
                request.form.get('focus_x', 50),
                request.form.get('focus_y', 50),
                z if z is not None else None,
                aspect if aspect is not None else None,
            )
            log_activity('Updated player photo', summary=f'Adjusted full-body crop for {name}')
            clear_stats_cache()
            payload = _photo_payload()
            payload.update({'success': True, 'focus': {'x': x, 'y': y, 'z': z, 'aspect': aspect}})
            return jsonify(payload)

        if request.form.get('remove') == '1':
            remove_player_full_body_photo(player_id)
            log_activity('Updated player photo', summary=f'Removed all full-body photos for {name}')
            clear_stats_cache()
            payload = _photo_payload()
            payload.update({'success': True, 'added_url': None})
            return jsonify(payload)

        remove_path = (request.form.get('remove_path') or '').strip()
        if remove_path:
            remove_player_full_body_photo(player_id, remove_path)
            log_activity('Updated player photo', summary=f'Removed a full-body photo for {name}')
            clear_stats_cache()
            payload = _photo_payload()
            payload.update({'success': True, 'added_url': None})
            return jsonify(payload)

        file_storage = request.files.get('photo')
        if not file_storage or not file_storage.filename:
            return jsonify({'success': False, 'error': 'No photo file provided.'}), 400

        rel_path = save_player_full_body_photo_upload(player_id, file_storage)
        photo_url = url_for('static', filename=rel_path)
        user = session.get('username', 'unknown')
        log_user_action(user, 'Uploaded player full-body photo', name)
        log_activity('Updated player photo', summary=f'Uploaded full-body photo for {name}')
        clear_stats_cache()
        payload = _photo_payload()
        payload.update({'success': True, 'added_url': photo_url})
        return jsonify(payload)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        app.logger.exception('Player full-body photo upload failed')
        return jsonify({'success': False, 'error': f'Upload failed: {e}'}), 500


@app.route('/api/player_ai_image_traits/<path:name>/', methods=['POST'])
@login_required
def api_save_player_ai_image_traits(name):
    """Save a player's signature-look phrase list for AI email images."""
    from player_functions import set_player_ai_image_traits

    name = name.strip()
    if not name:
        return jsonify({'success': False, 'error': 'Player name is required.'}), 400

    player = _ensure_player_record(name)
    if not player or not player[0]:
        return jsonify({'success': False, 'error': 'Could not find or create player record.'}), 400

    data = request.get_json(silent=True) or {}
    if isinstance(data, dict) and 'phrases' in data:
        traits = data.get('phrases')
        if not isinstance(traits, list):
            return jsonify({'success': False, 'error': 'Phrases must be a list.'}), 400
    elif request.form.get('phrases') is not None:
        try:
            traits = json.loads(request.form.get('phrases', '[]'))
        except json.JSONDecodeError:
            return jsonify({'success': False, 'error': 'Invalid phrase list.'}), 400
    elif request.form.get('traits') is not None:
        traits = request.form.get('traits', '')
    else:
        traits = data.get('traits', '') if isinstance(data, dict) else ''

    try:
        phrases = set_player_ai_image_traits(player[0], traits)
        log_activity('Updated signature look', summary=f'Updated AI image traits for {name}')
        clear_stats_cache()
        return jsonify({
            'success': True,
            'phrases': phrases,
            'traits': '; '.join(phrases),
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        app.logger.exception('Player AI image traits save failed')
        return jsonify({'success': False, 'error': f'Save failed: {e}'}), 500

@app.route('/benchmarks')
def benchmarks():
    """Performance benchmarks page - admin only"""
    if not is_admin():
        flash('Access denied. This page is only available to administrators.', 'error')
        return redirect(url_for('index'))
    
    # Load all benchmark files from benchmarks folder
    benchmarks_dir = os.path.join(os.path.dirname(__file__), 'benchmarks')
    benchmark_list = []
    
    if os.path.exists(benchmarks_dir):
        for filename in sorted(os.listdir(benchmarks_dir), reverse=True):
            if filename.endswith('.json'):
                filepath = os.path.join(benchmarks_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        data['filename'] = filename
                        benchmark_list.append(data)
                except Exception as e:
                    print(f"Error loading benchmark {filename}: {e}")
    
    return render_template('benchmarks.html', benchmarks=benchmark_list)

@app.route('/run_benchmark', methods=['POST'])
def run_benchmark():
    """Run a new benchmark - admin only"""
    if not is_admin():
        return jsonify({'success': False, 'error': 'Access denied'})
    
    import time
    from statistics import mean, stdev
    
    # Routes to benchmark
    routes = [
        ('/', 'Homepage'),
        ('/stats/2025/', 'Stats 2025'),
        ('/stats/2026/', 'Stats 2026'),
        ('/player_list/', 'Player List'),
        ('/games/', 'Games List'),
        ('/vollis_games/', 'Vollis Games'),
        ('/other_games/', 'Other Games'),
        ('/vollis_stats/', 'Vollis Stats'),
        ('/other_stats/', 'Other Stats'),
        ('/volleyball_stats/', 'Volleyball Stats'),
        ('/tournaments/', 'Tournaments'),
    ]
    
    results = []
    runs = 3
    
    with app.test_client() as client:
        # Login first to access protected pages
        client.post('/login', data={'username': 'kyle', 'password': 'stats2025'})
        
        for route, name in routes:
            times = []
            errors = []
            
            for _ in range(runs):
                try:
                    start = time.perf_counter()
                    response = client.get(route)
                    elapsed = time.perf_counter() - start
                    
                    if response.status_code == 200:
                        times.append(elapsed)
                    else:
                        errors.append(f"HTTP {response.status_code}")
                except Exception as e:
                    errors.append(str(e))
            
            results.append({
                'route': route,
                'name': name,
                'times': times,
                'avg': mean(times) if times else None,
                'min': min(times) if times else None,
                'max': max(times) if times else None,
                'stdev': stdev(times) if len(times) > 1 else 0,
                'errors': errors,
                'runs': runs,
                'successful_runs': len(times),
            })
    
    # Save results
    benchmarks_dir = os.path.join(os.path.dirname(__file__), 'benchmarks')
    os.makedirs(benchmarks_dir, exist_ok=True)
    
    timestamp = datetime.now().isoformat()
    filename = f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(benchmarks_dir, filename)
    
    data = {
        'timestamp': timestamp,
        'results': results,
    }
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    
    return jsonify({'success': True, 'filename': filename})

@app.route('/delete_benchmark/<filename>', methods=['POST'])
def delete_benchmark(filename):
    """Delete a benchmark file - admin only"""
    if not is_admin():
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    # Sanitize filename to prevent directory traversal
    if '..' in filename or '/' in filename:
        flash('Invalid filename.', 'error')
        return redirect(url_for('benchmarks'))
    
    benchmarks_dir = os.path.join(os.path.dirname(__file__), 'benchmarks')
    filepath = os.path.join(benchmarks_dir, filename)
    
    if os.path.exists(filepath):
        os.remove(filepath)
        flash('Benchmark deleted.', 'success')
    else:
        flash('Benchmark not found.', 'error')
    
    return redirect(url_for('benchmarks'))

@app.route('/testing_lab')
def testing_lab():
    """Testing lab for email and AI features"""
    if 'username' not in session:
        flash('Please login to access the testing lab', 'error')
        return redirect(url_for('login'))
    
    # Try to list available models for debugging
    available_models = None
    try:
        import google.generativeai as genai
        import os
        api_key = os.environ.get('GEMINI_API_KEY')
        if api_key:
            genai.configure(api_key=api_key)
            models = genai.list_models()
            available_models = [model.name for model in models if 'generateContent' in model.supported_generation_methods]
    except Exception as e:
        available_models = f"Error listing models: {str(e)}"
    
    return render_template('testing_lab.html', available_models=available_models)

@app.route('/generate_ai_summary', methods=['POST'])
def generate_ai_summary():
    """Generate AI summary for a specific date"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    import google.generativeai as genai
    import os
    
    # Check if Gemini API key is configured
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return jsonify({
            'success': False,
            'error': 'Gemini API key not configured. Please set GEMINI_API_KEY environment variable.'
        }), 400
    
    # Get the date from the request
    target_date = request.form.get('date', None)
    if not target_date:
        yesterday = datetime.now().date() - timedelta(days=1)
        target_date = yesterday.strftime('%Y-%m-%d')
    
    try:
        # Get stats for the date
        stats, games = specific_date_stats(target_date)
        
        if not games:
            return jsonify({
                'success': False,
                'error': f'No games found for {target_date}'
            }), 404
        
        # Build context for AI
        context = f"Date: {target_date}\n"
        context += f"Total Games: {len(games)}\n\n"
        context += "Player Stats:\n"
        for stat in stats[:10]:
            player_name = stat[0]
            wins = stat[1]
            losses = stat[2]
            win_pct = stat[3] * 100
            differential = stat[4]
            context += f"- {player_name}: {wins}-{losses} ({win_pct:.1f}%), Point Diff: {differential:+d}\n"
        
        context += f"\nGames Played:\n"
        for game in games[:5]:
            winners = f"{game[2]} & {game[3]}"
            losers = f"{game[5]} & {game[6]}"
            score = f"{game[4]}-{game[7]}"
            context += f"- {winners} def. {losers} ({score})\n"
        
        # Generate summary (falls back to alternate models on quota errors)
        prompt = f"""Write a fun, engaging 1-2 paragraph summary of these volleyball games. 
        Each paragraph must be 2-3 sentences only. Total under 100 words.
        Highlight top performers and notable matches. Be concise—quick hit, not a long read.

{context}

Write the summary:"""
        
        summary = generate_ai_text(prompt)
        
        return jsonify({
            'success': True,
            'summary': summary,
            'date': target_date,
            'games_count': len(games)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to generate summary: {str(e)}'
        }), 500

@app.route('/api/add_player', methods=['POST'])
@login_required
def api_add_player():
    """Add a new player via AJAX and ensure they appear in future dropdowns."""
    data = request.get_json() or {}
    full_name = (data.get('full_name') or '').strip()
    email = (data.get('email') or '').strip() or None
    date_of_birth = (data.get('date_of_birth') or '').strip() or None
    height = (data.get('height') or '').strip() or None
    notes = (data.get('notes') or '').strip() or None

    if not full_name:
        return jsonify({'success': False, 'error': 'Full name is required.'}), 400

    if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'success': False, 'error': 'Invalid email address.'}), 400

    from player_functions import get_player_by_name, add_new_player

    existing = get_player_by_name(full_name)
    if existing:
        return jsonify({'success': False, 'error': 'Player already exists.'}), 400

    player_id = add_new_player(full_name, email=email, date_of_birth=date_of_birth, height=height, notes=notes)

    user = session.get('username', 'unknown')
    log_user_action(user, 'Added new player', f'{full_name} ({email or "no email"})')
    log_activity('Added new player', summary=f'{full_name} ({email or "no email"})')
    clear_stats_cache()

    return jsonify({'success': True, 'player_id': player_id})


@app.route('/api/rename_player', methods=['POST'])
@login_required
def api_rename_player():
    """Rename a player across all game types via AJAX."""
    data = request.get_json() or {}
    old_name = (data.get('old_name') or '').strip()
    new_name = (data.get('new_name') or '').strip()

    if not old_name or not new_name:
        return jsonify({'success': False, 'error': 'Both old name and new name are required.'}), 400

    if old_name == new_name:
        return jsonify({'success': False, 'error': 'New name must be different from the old name.'}), 400

    try:
        updates_made = update_player_name(old_name, new_name)
        user = session.get('username', 'unknown')
        log_user_action(user, 'Renamed player', f'"{old_name}" to "{new_name}" ({updates_made} records)')
        log_activity('Renamed player', summary=f'"{old_name}" to "{new_name}" ({updates_made} records)')
        
        # Clear caches so stats reflect the new name
        clear_stats_cache()
        
        return jsonify({'success': True, 'updates_made': updates_made, 'message': f'Successfully renamed "{old_name}" to "{new_name}" in {updates_made} records.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/add_player_email', methods=['POST'])
@login_required
def add_player_email():
    """Add or update a player's email address from the AI summary preview."""
    data = request.get_json() or {}
    player_name = (data.get('player_name') or '').strip()
    email = (data.get('email') or '').strip()

    if not player_name or not email:
        return jsonify({'success': False, 'error': 'Player name and email are required.'}), 400

    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'success': False, 'error': 'Invalid email address.'}), 400

    from player_functions import get_player_by_name, add_new_player, update_player_info

    player_record = get_player_by_name(player_name)
    if player_record:
        player_id = player_record[0]
        # Preserve existing metadata when updating
        existing_full_name = player_record[1]
        date_of_birth = player_record[3]
        height = player_record[4]
        notes = player_record[5]
        update_player_info(player_id, existing_full_name, email=email,
                           date_of_birth=date_of_birth, height=height, notes=notes)
    else:
        add_new_player(player_name, email=email)

    user = session.get('username', 'unknown')
    log_user_action(user, 'Updated player email', f'{player_name} -> {email}')
    log_activity('Updated player email', summary=f'{player_name} -> {email}')
    clear_stats_cache()

    return jsonify({'success': True, 'email': email})


@app.route('/api/update_player_info', methods=['POST'])
@login_required
def api_update_player_info():
    """Update player info (email, birthday, height) from AI summary preview."""
    data = request.get_json() or {}
    player_name = (data.get('player_name') or '').strip()
    email = (data.get('email') or '').strip() or None
    birthday = (data.get('birthday') or '').strip() or None
    height = (data.get('height') or '').strip() or None

    if not player_name:
        return jsonify({'success': False, 'error': 'Player name is required.'}), 400

    if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'success': False, 'error': 'Invalid email address.'}), 400

    from player_functions import get_player_by_name, add_new_player, update_player_info

    player_record = get_player_by_name(player_name)
    if player_record:
        player_id = player_record[0]
        existing_full_name = player_record[1]
        # Use new values if provided, otherwise keep existing
        new_email = email if email else player_record[2]
        new_birthday = birthday if birthday else player_record[3]
        new_height = height if height else player_record[4]
        notes = player_record[5]
        update_player_info(player_id, existing_full_name, email=new_email,
                           date_of_birth=new_birthday, height=new_height, notes=notes)
    else:
        add_new_player(player_name, email=email)
        # If we just created the player, update with birthday/height if provided
        if birthday or height:
            player_record = get_player_by_name(player_name)
            if player_record:
                update_player_info(player_record[0], player_record[1], 
                                   email=email, date_of_birth=birthday, height=height, notes=None)

    user = session.get('username', 'unknown')
    updates = []
    if email: updates.append(f'email={email}')
    if birthday: updates.append(f'birthday={birthday}')
    if height: updates.append(f'height={height}')
    log_user_action(user, 'Updated player info', f'{player_name}: {", ".join(updates)}')
    log_activity('Updated player info', summary=f'{player_name}: {", ".join(updates)}')
    clear_stats_cache()

    return jsonify({'success': True})


@app.route('/opt_in_ai_emails')
def opt_in_ai_emails():
    """Handle opt-in link from AI summary emails"""
    email = request.args.get('email', '').strip()
    
    # Handle case where user clicked link in preview (placeholder not replaced)
    if not email or email == EMAIL_PLACEHOLDER or 'EMAIL_PLACEHOLDER' in email:
        return render_template('opt_in_error.html', error='This link only works from the actual email. When you receive the AI summary email, the link will be personalized for you.')
    
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return render_template('opt_in_error.html', error='Invalid email address.')
    
    # Store opt-in preference - add note to player with this email
    from player_functions import get_player_by_name, update_player_info
    from database_functions import set_cur
    
    cur = set_cur()
    
    # Check if there's a player with this email
    cur.execute("SELECT id, full_name, email, notes FROM players WHERE email = ?", (email,))
    player = cur.fetchone()
    
    if player:
        # Update player's notes to include opt-in flag
        player_id = player[0]
        full_name = player[1]
        existing_email = player[2]
        existing_notes = player[3] or ""
        
        # Add opt-in flag if not already present
        if "AI_EMAILS_OPT_IN" not in existing_notes:
            new_notes = existing_notes + ("\n" if existing_notes else "") + "AI_EMAILS_OPT_IN"
            update_player_info(player_id, full_name, email=existing_email, notes=new_notes)
            success = True
        else:
            success = True  # Already opted in
    else:
        # No player found with this email - still show success
        success = True
    
    return render_template('opt_in_success.html', email=email, success=success)


def _apply_ai_email_opt_out(email):
    from player_functions import update_player_info

    cur = set_cur()
    cur.execute("SELECT id, full_name, email, notes FROM players WHERE email = ?", (email,))
    player = cur.fetchone()
    if not player:
        return True

    player_id, full_name, existing_email, existing_notes = player
    notes = existing_notes or ''
    if 'AI_EMAILS_OPT_IN' in notes:
        notes = notes.replace('AI_EMAILS_OPT_IN', '').strip()
    if 'AI_EMAILS_OPT_OUT' not in notes:
        notes = notes + ("\n" if notes else "") + "AI_EMAILS_OPT_OUT"
    update_player_info(player_id, full_name, email=existing_email, notes=notes.strip())
    return True


@app.route('/opt_out_ai_emails', methods=['GET', 'POST'])
def opt_out_ai_emails():
    """One-click unsubscribe from AI summary emails (List-Unsubscribe)."""
    email = (request.args.get('email') or request.form.get('email') or '').strip()

    if not email or email == EMAIL_PLACEHOLDER or 'EMAIL_PLACEHOLDER' in email:
        if request.method == 'POST':
            return 'Invalid unsubscribe link.', 400
        return render_template('opt_in_error.html', error='This unsubscribe link only works from the actual email.')

    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        if request.method == 'POST':
            return 'Invalid email address.', 400
        return render_template('opt_in_error.html', error='Invalid email address.')

    _apply_ai_email_opt_out(email)

    if request.method == 'POST':
        return 'You have been unsubscribed from AI summary emails.', 200

    return render_template('opt_out_success.html', email=email)


@app.route('/cleanup_tokens')
def cleanup_tokens():
    """Clean up expired authentication tokens (can be called periodically)"""
    from email_content import cleanup_expired_solo_images

    cleanup_expired_tokens()
    solos_removed = cleanup_expired_solo_images()
    return f'Expired tokens cleaned up successfully; removed {solos_removed} expired solo image(s)', 200

def get_players_who_played_on_date(target_date):
    """Get all players who played on a specific date with their email addresses"""
    from player_functions import get_player_by_name
    
    # Get database connection
    cur = set_cur()
    
    # Get all games from that date across all game types
    players_set = set()
    
    # Doubles games
    cur.execute("SELECT winner1, winner2, loser1, loser2 FROM games WHERE date(game_date) = ?", (target_date,))
    doubles_games = cur.fetchall()
    for game in doubles_games:
        for player in game:
            if player and player.strip():
                players_set.add(player)
    
    # Vollis games
    cur.execute("SELECT winner, loser FROM vollis_games WHERE date(game_date) = ?", (target_date,))
    vollis_games = cur.fetchall()
    for game in vollis_games:
        for player in game:
            if player and player.strip():
                players_set.add(player)
    
    # Other games - get all player columns
    cur.execute("""SELECT winner1, winner2, winner3, winner4, winner5, winner6, 
                   loser1, loser2, loser3, loser4, loser5, loser6 
                   FROM other_games WHERE date(game_date) = ?""", (target_date,))
    other_games = cur.fetchall()
    for game in other_games:
        for player in game:
            if player and player.strip():
                players_set.add(player)
    
    # Get player emails
    players_with_emails = []
    for player_name in players_set:
        player_info = get_player_by_name(player_name)
        if player_info:
            # player_info format: (id, full_name, email, date_of_birth, height, notes, created_at, updated_at)
            email = player_info[2] if len(player_info) > 2 else None
            if email and email.strip():
                players_with_emails.append({
                    'name': player_name,
                    'email': email
                })
    
    return players_with_emails

@app.route('/test_email', methods=['POST'])
def test_email():
    """Send a test email to verify email configuration"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    # Check if email is configured
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        return jsonify({
            'success': False, 
            'error': 'Email not configured. Please set MAIL_USERNAME and MAIL_PASSWORD environment variables.'
        }), 400
    
    try:
        # Create test email
        msg = Message(
            subject="Test Email from Stats Site",
            recipients=["acwodzinski@gmail.com"]
        )
        
        msg.body = "I love you"
        
        # Send the email (with retry for flaky outbound network)
        sent, errors = send_messages_with_retry([msg])
        if errors:
            raise Exception(errors[0])
        
        log_activity('Sent email', summary='Test email to acwodzinski@gmail.com')
        flash('Test email sent successfully to acwodzinski@gmail.com!', 'success')
        return jsonify({
            'success': True,
            'message': 'Test email sent to acwodzinski@gmail.com'
        })
        
    except Exception as e:
        error_msg = f"Failed to send test email: {str(e)}"
        flash(error_msg, 'error')
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500

@app.route('/generate_and_email_today', methods=['POST'])
@login_required
def generate_and_email_today():
    """Send the AI summary email to selected recipients (from preview page)."""
    if not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
        return jsonify({'success': False, 'error': 'Email not configured.'}), 400
    data = request.get_json() or {}
    selected_emails = data.get('selected_emails') or []
    additional_emails = data.get('additional_emails') or []
    email_html = data.get('email_html') or ''
    plain_text_body = data.get('plain_text_body') or ''
    hero_image_url = data.get('hero_image_url') or ''
    hero_image_path = data.get('hero_image_path') or ''
    subject = data.get('subject') or 'Vball Summary'
    recipients = [e.strip() for e in selected_emails if e and str(e).strip()]
    for raw in additional_emails:
        for e in str(raw).replace(',', ' ').replace(';', ' ').split():
            e = e.strip()
            if e and '@' in e and e not in recipients:
                recipients.append(e)
    if not recipients:
        return jsonify({'success': False, 'error': 'No recipients selected.'}), 400
    emails_sent, errors = send_ai_summary_messages(
        subject,
        email_html,
        plain_text_body,
        recipients,
        hero_image_url=hero_image_url or None,
        hero_image_path=hero_image_path or None,
    )
    if errors:
        log_activity('Email send failed', summary=f'AI summary "{subject}": sent to {emails_sent}, {len(errors)} failed: {"; ".join(errors)[:200]}')
    else:
        log_activity('Sent email', summary=f'AI summary "{subject}" to {emails_sent} recipient(s)')
    return jsonify({
        'success': True,
        'emails_sent': emails_sent,
        'errors': errors
    })


@app.route('/send_ai_email_form', methods=['POST'])
@login_required
def send_ai_email_form():
    """Send the AI summary email via plain HTML form (no JS needed)."""
    preview_ctx = _ai_summary_preview_from_form(request.form)

    if not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
        flash('Email not configured.', 'error')
        return _render_ai_summary_preview_page(**preview_ctx)

    email_html = preview_ctx['email_html']
    plain_text_body = preview_ctx['plain_text_body']
    hero_image_url = preview_ctx['hero_image_url']
    hero_image_path = preview_ctx['hero_image_path']
    subject = preview_ctx['subject']
    additional_raw = preview_ctx['additional_emails_value']

    recipients = [e.strip() for e in preview_ctx['checked_emails'] if e and e.strip()]
    for e in additional_raw.replace(',', ' ').replace(';', ' ').replace('\n', ' ').split():
        e = e.strip()
        if e and '@' in e and e not in recipients:
            recipients.append(e)

    if not recipients:
        flash('No recipients selected.', 'error')
        return _render_ai_summary_preview_page(**preview_ctx)

    emails_sent, errors = send_ai_summary_messages(
        subject,
        email_html,
        plain_text_body,
        recipients,
        hero_image_url=hero_image_url or None,
        hero_image_path=hero_image_path or None,
    )

    if errors:
        log_activity('Email send failed', summary=f'AI summary "{subject}": sent to {emails_sent}, {len(errors)} failed: {"; ".join(errors)[:200]}')
        flash(f'Sent to {emails_sent} recipient(s), but {len(errors)} failed: {"; ".join(errors)}', 'error')
        return _render_ai_summary_preview_page(**preview_ctx)
    else:
        log_activity('Sent email', summary=f'AI summary "{subject}" to {emails_sent} recipient(s)')
        flash(f'Email sent to {emails_sent} recipient(s)!', 'success')
        return redirect(url_for('ai_summary'))


@app.route('/send_daily_emails', methods=['POST'])
def send_daily_emails():
    """Send emails to all players who played on a specific date"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    # Get the date to send emails for (default to yesterday)
    target_date = request.form.get('date', None)
    if not target_date:
        yesterday = datetime.now().date() - timedelta(days=1)
        target_date = yesterday.strftime('%Y-%m-%d')
    
    # Check if email is configured
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        flash('Email not configured. Please set MAIL_USERNAME and MAIL_PASSWORD environment variables.', 'error')
        return jsonify({
            'success': False, 
            'error': 'Email not configured. Please contact administrator.'
        }), 400
    
    # Get players who played on that date
    players = get_players_who_played_on_date(target_date)
    
    if not players:
        flash(f'No players with email addresses found for {target_date}', 'warning')
        return jsonify({
            'success': False, 
            'error': f'No players with email addresses found for {target_date}'
        }), 404
    
    # Get stats for that date
    stats, games = specific_date_stats(target_date)
    
    # Build one message per player, then send them over a single connection with retries
    messages = []
    for player in players:
        # Find player's stats for that day
        player_stats = None
        for stat in stats:
            if stat[0] == player['name']:
                player_stats = stat
                break
        
        msg = Message(
            subject=f"Your Stats for {target_date}",
            recipients=[player['email']]
        )
        
        email_body = f"Hi {player['name']},\n\n"
        email_body += f"Here are your stats for {target_date}:\n\n"
        
        if player_stats:
            wins = player_stats[1]
            losses = player_stats[2]
            win_pct = player_stats[3] * 100
            differential = player_stats[4]
            
            email_body += f"Record: {wins}-{losses} ({win_pct:.1f}%)\n"
            email_body += f"Point Differential: {differential:+d}\n\n"
        else:
            email_body += "You played on this date!\n\n"
        
        email_body += f"Total games played on {target_date}: {len(games)}\n\n"
        email_body += "Thanks for playing!\n\n"
        email_body += "— Your Stats Team"
        
        msg.body = email_body
        messages.append(msg)
    
    emails_sent, errors = send_messages_with_retry(messages)
    
    # Flash success/error messages
    if emails_sent > 0:
        flash(f'Successfully sent {emails_sent} email(s) for {target_date}!', 'success')
        log_activity('Sent email', summary=f'Daily emails for {target_date} to {emails_sent} player(s)')
    
    if errors:
        for error in errors:
            flash(error, 'error')
    
    return jsonify({
        'success': True,
        'emails_sent': emails_sent,
        'errors': errors
    })


# ============================================
# ADMIN DASHBOARD
# ============================================

@app.route('/admin/')
@admin_required
def admin_dashboard():
    """Admin dashboard: overview cards, activity feed, user management, quick actions."""
    today = date.today()
    counts = adminfx.games_counts(today.strftime('%Y-%m-%d'), (today - timedelta(days=6)).strftime('%Y-%m-%d'))
    recent_game = adminfx.most_recent_game()

    page = max(int(request.args.get('page', 1) or 1), 1)
    per_page = 25
    entries, total_entries = adminfx.get_activity_page(page=page, per_page=per_page)
    total_pages = max((total_entries + per_page - 1) // per_page, 1)
    entries = _format_activity_times(entries)

    users = adminfx.list_site_users()
    users = [dict(u, last_seen_fmt=_format_utc_str(u.get('last_seen')),
                  last_login_fmt=_format_utc_str(u.get('last_login'))) for u in users]

    try:
        db_size_mb = round(os.path.getsize(adminfx.stats_db_path()) / (1024 * 1024), 1)
    except OSError:
        db_size_mb = None

    return render_template('admin.html',
        counts=counts, recent_game=recent_game,
        entries=entries, page=page, total_pages=total_pages, total_entries=total_entries,
        users=users, db_size_mb=db_size_mb,
        email_configured=bool(app.config.get('MAIL_USERNAME') and app.config.get('MAIL_PASSWORD')))


@app.route('/admin/activity/')
@admin_required
def admin_activity():
    """Full site activity log with optional search and user filter."""
    page = max(int(request.args.get('page', 1) or 1), 1)
    search_q = (request.args.get('q') or '').strip()
    filter_username = (request.args.get('username') or '').strip()
    per_page = 50
    entries, total_entries = adminfx.get_activity_page(
        page=page, per_page=per_page, username=filter_username or None, q=search_q or None,
    )
    total_pages = max((total_entries + per_page - 1) // per_page, 1)
    entries = _format_activity_times(entries)

    user_meta = None
    if filter_username:
        users = [u for u in adminfx.list_site_users() if u['username'].lower() == filter_username.lower()]
        if users:
            u = users[0]
            user_meta = dict(
                u,
                last_seen_fmt=_format_utc_str(u.get('last_seen')),
                last_login_fmt=_format_utc_str(u.get('last_login')),
            )
            filter_username = u['username']

    return render_template(
        'admin_activity.html',
        entries=entries,
        page=page,
        total_pages=total_pages,
        total_entries=total_entries,
        search_q=search_q,
        filter_username=filter_username,
        user_meta=user_meta,
    )


@app.route('/admin/users/<username>/')
@admin_required
def admin_user_activity(username):
    """Everything one site user has done."""
    page = max(int(request.args.get('page', 1) or 1), 1)
    search_q = (request.args.get('q') or '').strip()
    per_page = 50
    entries, total_entries = adminfx.get_activity_page(
        page=page, per_page=per_page, username=username, q=search_q or None,
    )
    total_pages = max((total_entries + per_page - 1) // per_page, 1)
    entries = _format_activity_times(entries)

    users = [u for u in adminfx.list_site_users() if u['username'].lower() == username.lower()]
    user_meta = None
    if users:
        u = users[0]
        user_meta = dict(
            u,
            last_seen_fmt=_format_utc_str(u.get('last_seen')),
            last_login_fmt=_format_utc_str(u.get('last_login')),
        )
        username = u['username']

    return render_template(
        'admin_activity.html',
        entries=entries,
        page=page,
        total_pages=total_pages,
        total_entries=total_entries,
        search_q=search_q,
        filter_username=username,
        user_meta=user_meta,
    )


def _format_utc_str(ts):
    """Format a UTC timestamp string from SQLite into the session user's timezone."""
    if not ts:
        return None
    try:
        clean = str(ts).split('.')[0]
        dt_utc = datetime.strptime(clean, '%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo('UTC'))
        tz = ZoneInfo(session.get('timezone')) if session.get('timezone') else ZoneInfo('UTC')
        return dt_utc.astimezone(tz).strftime('%b %d, %Y at %I:%M %p')
    except Exception:
        return str(ts)


def _format_activity_times(entries):
    for e in entries:
        e['created_at_fmt'] = _format_utc_str(e.get('created_at'))
    return entries


@app.route('/admin/undo/<int:log_id>', methods=['POST'])
@admin_required
def admin_undo(log_id):
    """Reverse a logged game change (edit -> restore old values, delete -> re-insert, add -> remove)."""
    ok, message, target = adminfx.undo_entry(log_id)
    if ok:
        clear_stats_cache()
        if target == 'doubles_game':
            update_kobs()
        entry = adminfx.get_activity_entry(log_id)
        log_activity('Undid change', target=target, target_id=entry['target_id'] if entry else None,
                     summary=f"Undid log entry #{log_id}: {entry['summary'] if entry else ''}")
        flash(message, 'success')
    else:
        flash(message, 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/ai-prompts/')
@admin_required
def admin_ai_prompts():
    """Browse saved AI summary prompts and generated text."""
    page = max(int(request.args.get('page', 1) or 1), 1)
    per_page = 25
    entries, total_entries = adminfx.get_ai_prompt_log_page(page=page, per_page=per_page)
    total_pages = max((total_entries + per_page - 1) // per_page, 1)
    for entry in entries:
        entry['created_at_fmt'] = _format_utc_str(entry.get('created_at'))
        try:
            game_ids = json.loads(entry.get('game_ids_json') or '[]')
        except json.JSONDecodeError:
            game_ids = []
        entry['game_count'] = len(game_ids)
        summary = (entry.get('summary_text') or '').strip()
        entry['summary_preview'] = (
            summary[:180] + '...' if len(summary) > 180 else summary
        )
        try:
            entry['solo_images'] = json.loads(entry.get('solo_images_json') or '[]')
        except json.JSONDecodeError:
            entry['solo_images'] = []
    return render_template(
        'admin_ai_prompts.html',
        entries=entries,
        page=page,
        total_pages=total_pages,
        total_entries=total_entries,
    )


@app.route('/admin/ai-recaps/')
@admin_required
def admin_ai_recaps():
    """Browse all published shareable AI recap pages."""
    page = max(int(request.args.get('page', 1) or 1), 1)
    per_page = 25
    entries, total_entries = adminfx.list_ai_recap_pages(page=page, per_page=per_page)
    total_pages = max((total_entries + per_page - 1) // per_page, 1)
    site_base = (app.config.get('SITE_BASE_URL') or EMAIL_SITE_BASE_URL).rstrip('/')
    for entry in entries:
        entry['created_at_fmt'] = _format_utc_str(entry.get('created_at'))
        hero = adminfx.absolutize_hero_image_url(
            entry.get('hero_image_url') or '', site_base,
        )
        entry['hero_image_url'] = hero
        entry['share_url'] = url_for(
            'view_ai_recap',
            share_id=entry['share_id'],
            _external=True,
            **adminfx.recap_share_query_args(hero),
        )
    return render_template(
        'admin_ai_recaps.html',
        entries=entries,
        page=page,
        total_pages=total_pages,
        total_entries=total_entries,
    )


@app.route('/admin/ai-recaps/delete', methods=['POST'])
@admin_required
def admin_ai_recaps_delete():
    """Delete a published AI recap page."""
    share_id = (request.form.get('share_id') or '').strip()
    page = max(int(request.form.get('page', 1) or 1), 1)
    if not share_id:
        flash('No recap selected.', 'error')
        return redirect(url_for('admin_ai_recaps', page=page))

    row = adminfx.get_ai_recap_page(share_id)
    if adminfx.delete_ai_recap_page(share_id):
        subject = ((row or {}).get('subject') or 'Game Recap').strip()
        username = ((row or {}).get('username') or 'unknown').strip()
        log_activity(
            'Deleted AI recap',
            target=share_id,
            summary=f'{subject} by {username}',
        )
        flash(f'Deleted recap "{subject}".', 'success')
    else:
        flash('Recap not found.', 'error')
    return redirect(url_for('admin_ai_recaps', page=page))


@app.route('/admin/ai-images/')
@admin_required
def admin_ai_images():
    """Browse and delete AI illustration files taking up disk space."""
    image_stats = adminfx.list_ai_email_images()
    return render_template('admin_ai_images.html', image_stats=image_stats)


@app.route('/admin/ai-images/delete', methods=['POST'])
@admin_required
def admin_ai_images_delete():
    """Delete selected AI illustration files from disk."""
    action = (request.form.get('action') or 'delete_selected').strip()
    if action == 'delete_unused':
        image_stats = adminfx.list_ai_email_images()
        filenames = [img['filename'] for img in image_stats['images'] if not img['in_use']]
        deleted, missing, blocked = adminfx.delete_ai_email_images(filenames, allow_in_use=False)
    else:
        filenames = request.form.getlist('filenames')
        deleted, missing, blocked = adminfx.delete_ai_email_images(filenames, allow_in_use=True)

    if deleted:
        log_activity(
            'Deleted AI images',
            summary=f'Removed {len(deleted)} illustration file(s) from static/email_images/',
        )
        flash(f'Deleted {len(deleted)} image(s).', 'success')
    if blocked:
        flash(f'Skipped {len(blocked)} in-use image(s).', 'error')
    if missing and not deleted:
        flash('No matching image files found to delete.', 'error')
    if not deleted and not blocked and not missing:
        flash('No images selected.', 'error')
    return redirect(url_for('admin_ai_images'))


@app.route('/admin/users/add', methods=['POST'])
@admin_required
def admin_add_user():
    from werkzeug.security import generate_password_hash
    username = (request.form.get('username') or '').strip().lower()
    password = request.form.get('password') or ''
    make_admin = request.form.get('is_admin') == 'on'
    if not username or not password:
        flash('Username and password are required.', 'error')
    elif len(password) < 8:
        flash('Password must be at least 8 characters.', 'error')
    elif adminfx.get_site_user(username):
        flash(f'User "{username}" already exists.', 'error')
    else:
        adminfx.create_site_user(username, generate_password_hash(password, method='pbkdf2:sha256'), is_admin=make_admin)
        log_activity('Added site user', summary=f'{username}{" (admin)" if make_admin else ""}')
        flash(f'User "{username}" created.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/users/reset_password', methods=['POST'])
@admin_required
def admin_reset_password():
    from werkzeug.security import generate_password_hash
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    if not username or not password:
        flash('Username and new password are required.', 'error')
    elif len(password) < 8:
        flash('Password must be at least 8 characters.', 'error')
    elif adminfx.update_site_user(username, password_hash=generate_password_hash(password, method='pbkdf2:sha256')):
        log_activity('Reset user password', summary=username)
        flash(f'Password updated for "{username}".', 'success')
    else:
        flash(f'User "{username}" not found.', 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/users/toggle_active', methods=['POST'])
@admin_required
def admin_toggle_active():
    username = (request.form.get('username') or '').strip()
    activate = request.form.get('activate') == '1'
    if username.lower() == (session.get('username') or '').lower():
        flash('You cannot deactivate your own account.', 'error')
    elif adminfx.update_site_user(username, active=activate):
        # Kick a deactivated user off any device immediately
        if not activate:
            revoke_all_user_tokens(username)
        log_activity('Reactivated site user' if activate else 'Deactivated site user', summary=username)
        flash(f'User "{username}" {"reactivated" if activate else "deactivated"}.', 'success')
    else:
        flash(f'User "{username}" not found.', 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/backup', methods=['POST'])
@admin_required
def admin_backup():
    """Copy stats.db into backups/ with a timestamp."""
    import shutil
    src = adminfx.stats_db_path()
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(src)) or '.', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    dest = os.path.join(backup_dir, f"stats_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    try:
        shutil.copy2(src, dest)
        log_activity('Backed up database', summary=os.path.basename(dest))
        flash(f'Database backed up to {os.path.basename(dest)}.', 'success')
    except Exception as e:
        flash(f'Backup failed: {e}', 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/clear_cache', methods=['POST'])
@admin_required
def admin_clear_cache():
    clear_stats_cache()
    log_activity('Cleared stats cache')
    flash('Stats cache cleared.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/test_email', methods=['POST'])
@admin_required
def admin_test_email():
    """Send a test email and redirect back to the dashboard (form-friendly)."""
    if not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
        flash('Email not configured.', 'error')
        return redirect(url_for('admin_dashboard'))
    to_addr = app.config.get('MAIL_USERNAME')
    try:
        msg = Message(subject='Test email from Stats admin dashboard', recipients=[to_addr])
        msg.body = 'Email sending works. Sent from the admin dashboard.'
        mail.send(msg)
        log_activity('Sent email', summary=f'Test email to {to_addr}')
        flash(f'Test email sent to {to_addr}.', 'success')
    except Exception as e:
        flash(f'Test email failed: {e}', 'error')
    return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    # host='127.0.0.1' = local only (avoids HTTPS probes from browser/network)
    app.run(debug=True, host='127.0.0.1', port=5000)
