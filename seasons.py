"""Private, cross-device seasons and revocable, read-only links."""
from contextlib import closing
from functools import wraps
import re
import secrets
import sqlite3
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for

from season_stats import AWARDS_EXPLANATION, MINIMUM_EXPLANATION, season_results, season_status
from stats_date_filter import validate_date_range

ENDPOINTS = {'seasons_list', 'season_create', 'season_detail', 'season_edit', 'season_delete',
             'season_share', 'season_public', 'api_seasons', 'api_season', 'api_season_share'}


def validate_season(body):
    if not isinstance(body, dict):
        raise ValueError('Enter the season details.')
    name = body.get('name')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError('Give the season a name of 1–80 characters.')
    start, end = body.get('start_date', ''), body.get('end_date', '')
    if not validate_date_range(start, end):
        raise ValueError('Choose both a start day and an end day.')
    mode = body.get('minimum_mode', 'automatic')
    if not isinstance(mode, str) or mode not in {'automatic', 'fixed'}:
        raise ValueError('Choose automatic or fixed minimum games.')
    minimum = None
    if mode == 'fixed':
        raw = body.get('minimum_games')
        if isinstance(raw, bool) or not re.fullmatch(r'[0-9]{1,6}', str(raw)) or not 1 <= int(raw) <= 100000:
            raise ValueError('Minimum games must be a whole number from 1 to 100,000.')
        minimum = int(raw)
    timezone = body.get('timezone') or 'America/Los_Angeles'
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError('Choose a valid time zone.') from None
    return dict(name=name.strip(), start_date=start, end_date=end, minimum_games=minimum, timezone=timezone)


def register_seasons(app, service):
    site_path = service._stats_db_path()
    with sqlite3.connect(site_path) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS seasons (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL COLLATE NOCASE,
            name TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
            minimum_games INTEGER, timezone TEXT NOT NULL,
            share_token TEXT UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK(minimum_games IS NULL OR minimum_games >= 1), CHECK(start_date <= end_date)
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS seasons_owner ON seasons(owner, start_date)')

    def username():
        return session.get('username') if session.get('logged_in') else None

    def csrf_token():
        if not session.get('season_csrf'):
            session['season_csrf'] = secrets.token_urlsafe(32)
        return session['season_csrf']

    def require_csrf():
        # Bearer identity is validated by the existing account middleware.
        if request.headers.get('Authorization', '').startswith('Bearer '):
            return
        supplied = request.headers.get('X-Season-CSRF') or request.form.get('csrf_token', '')
        if not supplied or not secrets.compare_digest(supplied, session.get('season_csrf', '')):
            abort(400, description='This form expired. Reload the page and try again.')

    def authenticated(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not username():
                if request.path.startswith('/api/'):
                    return jsonify(error='Sign in to manage your seasons.'), 401
                return redirect(url_for('login', next=request.path))
            if request.method != 'GET':
                require_csrf()
            return fn(*args, **kwargs)
        return wrapped

    def rows(query, params=()):
        with closing(sqlite3.connect(site_path)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(query, params)]

    def owned(season_id):
        result = rows('SELECT * FROM seasons WHERE id=? AND owner=? COLLATE NOCASE', (season_id, username()))
        if not result:
            abort(404)
        return result[0]

    def public_data(season, owner=False):
        data = {key: season[key] for key in ('id', 'name', 'start_date', 'end_date', 'minimum_games', 'timezone')}
        data.update(status=season_status(season), minimum_mode='automatic' if season['minimum_games'] is None else 'fixed')
        if owner:
            data['share_url'] = url_for('season_public', token=season['share_token'], _external=True) if season['share_token'] else None
        return data

    def payload(season, owner=False, with_player=False):
        results = season_results(site_path, season,
                                 request.args.get('player') if with_player else None,
                                 request.args.get('group') if with_player else None)
        if results is None:
            abort(404)
        return dict(season=public_data(season, owner), **results,
                    minimum_explanation=MINIMUM_EXPLANATION, awards_explanation=AWARDS_EXPLANATION)

    def library():
        entries = rows('SELECT * FROM seasons WHERE owner=? COLLATE NOCASE ORDER BY start_date DESC, created_at DESC', (username(),))
        champions = []
        for season in entries:
            if season_status(season) == 'Completed':
                for group in season_results(site_path, season)['groups']:
                    for champion in group['champions']:
                        champions.append(dict(season_id=season['id'], season_name=season['name'],
                                              start_date=season['start_date'], end_date=season['end_date'],
                                              group_id=group['id'], group_title=group['title'], **champion))
        return dict(seasons=[public_data(s, True) for s in entries], champions=champions)

    def save(body, existing=None):
        # Editing dates or minimums does not change the account, link, or time zone.
        body = dict(body) if isinstance(body, dict) else body
        if existing and isinstance(body, dict):
            body['timezone'] = existing['timezone']
        values = validate_season(body)
        season_id = existing['id'] if existing else secrets.token_hex(16)
        with sqlite3.connect(site_path) as conn:
            if existing:
                conn.execute('''UPDATE seasons SET name=:name, start_date=:start_date, end_date=:end_date,
                    minimum_games=:minimum_games, updated_at=CURRENT_TIMESTAMP WHERE id=:id AND owner=:owner''',
                    dict(values, id=season_id, owner=username()))
            else:
                conn.execute('''INSERT INTO seasons (id,owner,name,start_date,end_date,minimum_games,timezone)
                    VALUES (:id,:owner,:name,:start_date,:end_date,:minimum_games,:timezone)''',
                    dict(values, id=season_id, owner=username()))
        return owned(season_id)

    def delete(season):
        with sqlite3.connect(site_path) as conn:
            conn.execute('DELETE FROM seasons WHERE id=? AND owner=? COLLATE NOCASE', (season['id'], username()))

    def share(season, enabled):
        token = (season['share_token'] or secrets.token_urlsafe(32)) if enabled else None
        with sqlite3.connect(site_path) as conn:
            conn.execute('UPDATE seasons SET share_token=? WHERE id=? AND owner=? COLLATE NOCASE', (token, season['id'], username()))
        return owned(season['id'])

    @app.after_request
    def season_headers(response):
        if request.endpoint in ENDPOINTS:
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
            response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    @app.route('/api/seasons', methods=['GET', 'POST'])
    @authenticated
    def api_seasons():
        if request.method == 'GET':
            return jsonify(library())
        try:
            season = save(request.get_json(silent=True))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(payload(season, owner=True)), 201

    @app.route('/api/seasons/<season_id>', methods=['GET', 'PUT', 'DELETE'])
    @authenticated
    def api_season(season_id):
        season = owned(season_id)
        if request.method == 'DELETE':
            delete(season)
            return jsonify(ok=True)
        if request.method == 'PUT':
            try:
                season = save(request.get_json(silent=True), season)
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
        return jsonify(payload(season, owner=True, with_player=True))

    @app.route('/api/seasons/<season_id>/share', methods=['POST', 'DELETE'])
    @authenticated
    def api_season_share(season_id):
        return jsonify(season=public_data(share(owned(season_id), request.method == 'POST'), True))

    @app.get('/seasons/')
    @authenticated
    def seasons_list():
        return render_template('seasons.html', **library())

    def editor(existing=None):
        values = public_data(existing, True) if existing else dict(name='', start_date='', end_date='', minimum_mode='automatic', minimum_games=1)
        error = None
        if request.method == 'POST':
            values = request.form.to_dict()
            values.setdefault('timezone', session.get('timezone') or 'America/Los_Angeles')
            try:
                saved = save(values, existing)
            except ValueError as exc:
                error = str(exc)
            else:
                return redirect(url_for('season_detail', season_id=saved['id'],
                                        group=request.form.get('group') or None))
        cancel_url = (url_for('season_detail', season_id=existing['id'], group=request.values.get('group') or None)
                      if existing else url_for('seasons_list'))
        return render_template('season_form.html', values=values, editing=bool(existing), error=error,
                               cancel_url=cancel_url, season_back_url=cancel_url,
                               season_back_label='Back to season' if existing else 'Seasons',
                               csrf_token=csrf_token(), minimum_explanation=MINIMUM_EXPLANATION), 400 if error else 200

    @app.route('/seasons/new/', methods=['GET', 'POST'])
    @authenticated
    def season_create():
        return editor()

    @app.route('/seasons/<season_id>/edit/', methods=['GET', 'POST'])
    @authenticated
    def season_edit(season_id):
        return editor(owned(season_id))

    @app.post('/seasons/<season_id>/delete/')
    @authenticated
    def season_delete(season_id):
        delete(owned(season_id))
        flash('Season deleted. Your game records are unchanged.', 'success')
        return redirect(url_for('seasons_list'))

    @app.post('/seasons/<season_id>/share/')
    @authenticated
    def season_share(season_id):
        share(owned(season_id), request.form.get('action') != 'stop')
        return redirect(url_for('season_detail', season_id=season_id,
                                group=request.form.get('group') or None, sharing='1'))

    def show(season, is_owner):
        data = payload(season, owner=is_owner, with_player=True)
        selected = next((group['id'] for group in data['groups'] if group['id'] == request.args.get('group')),
                        data['groups'][0]['id'] if data['groups'] else '')
        player_back_url = request.path + '?' + urlencode({'group': selected})
        back_url = player_back_url if data.get('player') else url_for('seasons_list') if is_owner else None
        return render_template('season_detail.html', **data, is_owner=is_owner,
                               selected_group=selected, season_back_url=back_url,
                               season_back_label='Back to season' if data.get('player') else 'Seasons',
                               csrf_token=csrf_token() if is_owner else None,
                               detail_url=request.path)

    @app.get('/seasons/<season_id>/')
    @authenticated
    def season_detail(season_id):
        return show(owned(season_id), True)

    @app.get('/season/s/<token>/')
    def season_public(token):
        result = rows('''SELECT s.* FROM seasons s JOIN site_users u ON u.username=s.owner COLLATE NOCASE
                         WHERE s.share_token=? AND u.active=1''', (token,))
        if not result:
            abort(404)
        from account_lifecycle import AccountBusy, account_lock
        from content_safety import restricted_authors
        season = result[0]
        if season['owner'].casefold() in restricted_authors(username() or ''):
            abort(404)
        # Protect the owner's data during account deletion, independent of viewer identity.
        try:
            with account_lock(site_path, season['owner']):
                # A concurrent revocation or deletion must not resurrect a link.
                current = rows('''SELECT s.* FROM seasons s JOIN site_users u ON u.username=s.owner COLLATE NOCASE
                                  WHERE s.id=? AND s.share_token=? AND u.active=1''', (season['id'], token))
                if not current:
                    abort(404)
                return show(current[0], False)
        except AccountBusy:
            abort(409, description='This season is being updated. Please try again in a moment.')
