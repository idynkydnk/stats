"""JSON API for the native iOS app. Shares the same SQLite DB as the website.

Registered from stats.py after the Flask app and auth helpers exist.
HTML pages are unchanged; these routes wrap existing domain functions.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import jsonify, request, session, url_for
from werkzeug.security import generate_password_hash


def _S():
    import stats as S
    return S


def _abs(path):
    if not path:
        return None
    if str(path).startswith('http'):
        return path
    base = (
        os.environ.get('SITE_BASE_URL')
        or getattr(_S(), 'EMAIL_SITE_BASE_URL', None)
        or 'https://idynkydnk.pythonanywhere.com'
    ).rstrip('/')
    if not str(path).startswith('/'):
        path = '/' + str(path)
    return base + path


def _json_val(v):
    if v is None:
        return None
    if hasattr(v, 'isoformat'):
        return v.isoformat(sep=' ')
    return v


def api_login_required(f):
    """Same as stats.api_login_required (Bearer, API key, session, cookie)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        S = _S()
        username = None
        api_key = request.headers.get('X-API-Key')
        expected = os.environ.get('STATS_API_TOKEN', '')
        if api_key and expected and __import__('secrets').compare_digest(api_key, expected):
            username = 'api_key'
            session['logged_in'] = True
            session['username'] = username
        if not username:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header[7:].strip()
                if token:
                    username = S.validate_auth_token(token)
                    if username:
                        session['logged_in'] = True
                        session['username'] = username
        if not username and session.get('logged_in'):
            username = session.get('username')
        if not username:
            auth_token = request.cookies.get('remember_token')
            if auth_token:
                username = S.validate_auth_token(auth_token)
                if username:
                    session['logged_in'] = True
                    session['username'] = username
        if not username:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated


def api_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        inner = api_login_required(lambda: None)

        @wraps(f)
        def gated(*a, **k):
            S = _S()
            if not S.is_admin():
                return jsonify({'error': 'Admin access required'}), 403
            return f(*a, **k)

        # Reuse Bearer/session check then admin check
        username = None
        S = _S()
        api_key = request.headers.get('X-API-Key')
        expected = os.environ.get('STATS_API_TOKEN', '')
        if api_key and expected and __import__('secrets').compare_digest(api_key, expected):
            username = 'api_key'
            session['logged_in'] = True
            session['username'] = username
        if not username:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header[7:].strip()
                if token:
                    username = S.validate_auth_token(token)
                    if username:
                        session['logged_in'] = True
                        session['username'] = username
        if not username and session.get('logged_in'):
            username = session.get('username')
        if not username:
            auth_token = request.cookies.get('remember_token')
            if auth_token:
                username = S.validate_auth_token(auth_token)
                if username:
                    session['logged_in'] = True
                    session['username'] = username
        if not username:
            return jsonify({'error': 'Authentication required'}), 401
        if not S.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


def _ensure_deleted_table():
    S = _S()
    conn = sqlite3.connect(S._stats_db_path())
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS deleted_records (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            deleted_at TEXT NOT NULL
        )'''
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_deleted_kind_at ON deleted_records(kind, deleted_at)'
    )
    conn.commit()
    conn.close()


def record_deletion(kind, record_id):
    _ensure_deleted_table()
    S = _S()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(S._stats_db_path())
    conn.execute(
        'INSERT INTO deleted_records (kind, record_id, deleted_at) VALUES (?, ?, ?)',
        (kind, int(record_id), now),
    )
    conn.commit()
    conn.close()


def deleted_ids_since(kind, since_str):
    _ensure_deleted_table()
    S = _S()
    conn = sqlite3.connect(S._stats_db_path())
    cur = conn.cursor()
    if since_str:
        cur.execute(
            'SELECT record_id FROM deleted_records WHERE kind = ? AND deleted_at >= ?',
            (kind, since_str),
        )
    else:
        cur.execute('SELECT record_id FROM deleted_records WHERE kind = ?', (kind,))
    ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return ids


def _year_arg(default=None):
    year = (request.args.get('year') or '').strip()
    if not year or year.lower() in ('all', 'all years'):
        return 'All years' if default is None else default
    return year


def _ranking(row, rating_key='rating'):
    games = (row[1] or 0) + (row[2] or 0)
    out = {
        'name': row[0],
        'wins': row[1],
        'losses': row[2],
        'win_pct': row[3],
        'games': games,
    }
    if len(row) > 4:
        out[rating_key] = row[4]
    return out


def _doubles_game_dict(row):
    S = _S()
    return S._api_game_row_to_dict(row)


def _vollis_game_dict(row):
    cols = ['id', 'game_date', 'winner', 'winner_score', 'loser', 'loser_score', 'updated_at', 'entered_timezone', 'location']
    if hasattr(row, 'keys'):
        d = {k: _json_val(row[k]) for k in row.keys()}
    else:
        d = {}
        for i, k in enumerate(cols):
            d[k] = _json_val(row[i]) if i < len(row) else None
    return d


def _other_game_json(game):
    if not isinstance(game, dict):
        return game
    out = {}
    for k, v in game.items():
        out[k] = _json_val(v)
    if 'game_id' in out and 'id' not in out:
        out['id'] = out['game_id']
    return out


def _card_stats(card):
    def rows(items):
        return [_ranking(s) for s in (items or [])]
    return {
        'game_name': card.get('game_name'),
        'game_type': card.get('game_type'),
        'is_consolidated': bool(card.get('is_consolidated')),
        'total_games': card.get('total_games', 0),
        'minimum_games': card.get('minimum_games', 1),
        'stats': rows(card.get('stats')),
        'rare_stats': rows(card.get('rare_stats')),
    }


ADMIN_TOPICS = (
    {
        'id': 'everything',
        'label': 'Everything',
        'description': 'Full activity log of every action on the site',
        'path': '/api/admin/activity',
    },
    {
        'id': 'games',
        'label': 'Recent games',
        'description': 'Doubles, vollis, and other games, newest first',
        'path': '/api/admin/games',
    },
    {
        'id': 'logins',
        'label': 'Logins',
        'description': 'Who signed in on the website or iPhone app',
        'path': '/api/admin/logins',
    },
    {
        'id': 'summaries',
        'label': 'AI summary links',
        'description': 'Published recap pages with shareable URLs',
        'path': '/api/admin/recaps',
    },
    {
        'id': 'flyers',
        'label': 'Flyers',
        'description': 'Generated flyer pages and download links',
        'path': '/api/admin/flyers',
    },
    {
        'id': 'jobs',
        'label': 'AI jobs',
        'description': 'Recap, flyer, and player-image jobs',
        'path': '/api/admin/jobs',
    },
    {
        'id': 'users',
        'label': 'Users',
        'description': 'Site accounts, last login, and last seen',
        'path': '/api/admin/users',
    },
    {
        'id': 'overview',
        'label': 'Overview',
        'description': 'Counts, latest game, and recent shares',
        'path': '/api/admin/overview',
    },
)


def admin_topic_catalog():
    """Menu of Kyle-only activity topics the client can ask for."""
    return {
        'ask': 'What do you want to see?',
        'topics': [dict(topic) for topic in ADMIN_TOPICS],
        'hint': (
            'Pass topic=games, topic=logins, topic=summaries, or topic=everything '
            'to fetch that list in this response.'
        ),
    }


def _page_args(default_per_page=40, max_per_page=100):
    try:
        page = int(request.args.get('page', 1) or 1)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get('per_page', default_per_page) or default_per_page)
    except (TypeError, ValueError):
        per_page = default_per_page
    return max(page, 1), min(max(per_page, 1), max_per_page)


def _paged(entries, total, page, per_page, key):
    total_pages = max((total + per_page - 1) // per_page, 1) if total else 1
    return {
        key: entries,
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': total_pages,
    }


def _normalize_game_date(game_date):
    game_date = (game_date or '').strip()
    if not game_date:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        if 'T' in game_date:
            return datetime.fromisoformat(game_date.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
        if len(game_date) == 10:
            return game_date + ' 12:00:00'
    except (ValueError, TypeError):
        pass
    return game_date


def register_ios_api(app):
    """Attach iOS JSON routes to the Flask app."""
    _ensure_deleted_table()

    @app.route('/api/me')
    @api_login_required
    def api_me():
        S = _S()
        username = session.get('username')
        return jsonify({
            'username': username,
            'is_admin': bool(S.is_admin(username)),
            'logged_in': True,
        })

    @app.route('/api/auth/logout', methods=['POST'])
    @api_login_required
    def api_logout():
        S = _S()
        username = session.get('username')
        auth_header = request.headers.get('Authorization') or ''
        if auth_header.startswith('Bearer '):
            S.revoke_auth_token(auth_header[7:].strip())
        cookie = request.cookies.get('remember_token')
        if cookie:
            S.revoke_auth_token(cookie)
        session.pop('logged_in', None)
        session.pop('username', None)
        resp = jsonify({'ok': True, 'username': username})
        resp.set_cookie('remember_token', '', expires=0)
        return resp

    @app.route('/api/years')
    def api_years():
        from stat_functions import grab_all_years
        from vollis_functions import all_vollis_years
        from other_functions import all_other_years
        return jsonify({
            'doubles': grab_all_years(),
            'vollis': all_vollis_years(),
            'other': all_other_years(),
        })

    # ----- Doubles stats (public) -----

    @app.route('/api/doubles/stats')
    def api_doubles_stats():
        from stat_functions import (
            year_games, grab_all_years, stats_per_year, rare_stats_per_year,
            todays_stats, todays_games,
        )
        year = _year_arg(str(date.today().year))
        current_year = str(date.today().year)
        display_year = year
        showing_previous_year = False
        games = year_games(year)
        minimum_games = 1 if not games or len(games) < 30 else len(games) // 30
        all_years = grab_all_years()
        stats = stats_per_year(year, minimum_games)
        if not stats and year == current_year and all_years:
            previous_year = str(int(current_year) - 1)
            if previous_year in all_years:
                games = year_games(previous_year)
                minimum_games = max(1, (len(games) // 30) if games else 1)
                stats = stats_per_year(previous_year, minimum_games)
                display_year = previous_year
                showing_previous_year = True
        rare = rare_stats_per_year(display_year, minimum_games)
        today = todays_stats()
        today_games = todays_games()
        return jsonify({
            'year': year,
            'display_year': display_year,
            'showing_previous_year': showing_previous_year,
            'minimum_games': minimum_games,
            'all_years': all_years,
            'stats': [_ranking(r) for r in (stats or [])],
            'rare_stats': [_ranking(r) for r in (rare or [])],
            'today_stats': [_ranking(r, rating_key='plus_minus') for r in (today or [])],
            'today_game_count': len(today_games or []),
        })

    @app.route('/api/doubles/players/<path:name>')
    def api_doubles_player(name):
        from stat_functions import (
            games_from_player_by_year, all_years_player, total_stats,
            player_matchup_min_games, partner_stats_by_year, opponent_stats_by_year,
            calculate_trueskill_rankings,
        )
        S = _S()
        year = _year_arg(str(date.today().year))
        name = name.strip()
        games = games_from_player_by_year(year, name)
        all_years = all_years_player(name)
        stats = total_stats(games, name) if games else []
        n_games = len(games) if games else 0
        min_games = player_matchup_min_games(n_games)
        partners = partner_stats_by_year(name, games, min_games) if games else []
        opponents = opponent_stats_by_year(name, games, min_games) if games else []
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
        recent_form = ['W' if name in (g[2], g[3]) else 'L' for g in (games or [])[-10:]]
        avatar = S.player_avatar_context(name)
        return jsonify({
            'name': name,
            'year': year,
            'all_years': all_years,
            'stats': _ranking(stats[0]) if stats else None,
            'rating': player_rating,
            'rank': player_rank,
            'total_ranked': total_ranked,
            'current_streak': current_streak,
            'recent_form': recent_form,
            'partner_min_games': min_games,
            'partners': partners,
            'opponents': opponents,
            'games': [_doubles_game_dict(g) for g in (games or [])],
            'photo_url': _abs(avatar.get('player_photo_url')),
            'nickname': avatar.get('player_nickname') or '',
            'height': avatar.get('player_height') or '',
            'date_of_birth': avatar.get('player_date_of_birth') or '',
            'email': avatar.get('player_email') or '',
        })

    @app.route('/api/network')
    def api_network():
        from stat_functions import build_player_network_data, grab_all_years, year_games
        year = _year_arg(str(date.today().year))
        current_year = str(date.today().year)
        display_year = year
        all_years = grab_all_years()
        games = year_games(year)
        if not games and year == current_year and all_years:
            previous_year = str(int(current_year) - 1)
            if previous_year in all_years and year_games(previous_year):
                display_year = previous_year
        data = build_player_network_data(display_year)
        return jsonify({
            'year': year,
            'display_year': display_year,
            'all_years': all_years,
            'network': data,
        })

    # ----- Vollis -----

    @app.route('/api/vollis/stats')
    def api_vollis_stats():
        from vollis_functions import (
            vollis_stats_per_year, all_vollis_years,
            todays_vollis_stats, todays_vollis_games,
        )
        year = _year_arg(str(date.today().year))
        current_year = str(date.today().year)
        display_year = year
        showing_previous_year = False
        all_years = all_vollis_years()
        stats = vollis_stats_per_year(year, 0)
        if not stats and year == current_year and all_years:
            previous_year = str(int(current_year) - 1)
            if previous_year in all_years:
                stats = vollis_stats_per_year(previous_year, 0)
                display_year = previous_year
                showing_previous_year = True
        today = todays_vollis_stats()
        today_games = todays_vollis_games()
        return jsonify({
            'year': year,
            'display_year': display_year,
            'showing_previous_year': showing_previous_year,
            'all_years': all_years,
            'stats': [_ranking(r) for r in (stats or [])],
            'today_stats': [_ranking(r, rating_key='plus_minus') for r in (today or [])],
            'today_game_count': len(today_games or []),
        })

    @app.route('/api/vollis/games', methods=['GET'])
    def api_vollis_list():
        from vollis_functions import vollis_year_games, all_vollis_years
        year = _year_arg('All years')
        since = (request.args.get('since') or '').strip()
        games = vollis_year_games(year)
        if since:
            try:
                dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
                since_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                since_str = since
            filtered = []
            for g in games:
                updated = str(g[6]) if len(g) > 6 and g[6] else str(g[1])
                if updated >= since_str:
                    filtered.append(g)
            games = filtered
        else:
            since_str = None
        return jsonify({
            'games': [_vollis_game_dict(g) for g in games],
            'all_years': all_vollis_years(),
            'deleted_ids': deleted_ids_since('vollis_game', since_str),
        })

    @app.route('/api/vollis/games/<int:game_id>', methods=['GET'])
    def api_vollis_get(game_id):
        from vollis_functions import find_vollis_game
        rows = find_vollis_game(game_id)
        if not rows:
            return jsonify({'error': 'Game not found'}), 404
        return jsonify(_vollis_game_dict(rows[0]))

    @app.route('/api/vollis/games', methods=['POST'])
    @api_login_required
    def api_vollis_create():
        from vollis_functions import add_vollis_stats, find_vollis_game
        S = _S()
        data = request.get_json(force=True, silent=True) or {}
        winner = (data.get('winner') or '').strip()
        loser = (data.get('loser') or '').strip()
        try:
            winner_score = int(data.get('winner_score'))
            loser_score = int(data.get('loser_score'))
        except (TypeError, ValueError):
            return jsonify({'error': 'Scores must be integers'}), 400
        if not winner or not loser:
            return jsonify({'error': 'winner and loser required'}), 400
        if winner == loser:
            return jsonify({'error': 'Winner and loser must be different'}), 400
        if winner_score <= loser_score:
            return jsonify({'error': 'winner_score must be greater than loser_score'}), 400
        game_date = _normalize_game_date(data.get('game_date'))
        tz = (data.get('entered_timezone') or '').strip() or session.get('timezone') or None
        location = (data.get('location') or '').strip()
        add_vollis_stats([game_date, winner, loser, winner_score, loser_score, game_date, tz, location])
        S._remember_game_location(location)
        S.clear_stats_cache()
        new_row = S.adminfx.snapshot_last_row('vollis_game')
        S.log_activity(
            'Added vollis game (iPhone)',
            target='vollis_game',
            target_id=new_row['id'] if new_row else None,
            summary=f'{winner} beat {loser} {winner_score}-{loser_score}',
            after=new_row,
        )
        if new_row and new_row.get('id'):
            found = find_vollis_game(new_row['id'])
            if found:
                return jsonify(_vollis_game_dict(found[0])), 201
        return jsonify({'message': 'Game created'}), 201

    @app.route('/api/vollis/games/<int:game_id>', methods=['PUT'])
    @api_login_required
    def api_vollis_update(game_id):
        from vollis_functions import find_vollis_game, edit_vollis_game
        S = _S()
        rows = find_vollis_game(game_id)
        if not rows:
            return jsonify({'error': 'Game not found'}), 404
        row = rows[0]
        data = request.get_json(force=True, silent=True) or {}

        def col(i, default=''):
            return row[i] if i < len(row) and row[i] is not None else default

        game_date = _normalize_game_date(data.get('game_date') or col(1))
        winner = (data.get('winner') or col(2)).strip()
        winner_score = int(data.get('winner_score', col(3)))
        loser = (data.get('loser') or col(4)).strip()
        loser_score = int(data.get('loser_score', col(5)))
        location = (data.get('location') or '').strip() if data.get('location') is not None else str(col(8)).strip()
        if winner_score <= loser_score:
            return jsonify({'error': 'winner_score must be greater than loser_score'}), 400
        before = S.adminfx.snapshot_row('vollis_game', game_id)
        edit_vollis_game(game_id, game_date, winner, winner_score, loser, loser_score, S.get_user_now(), game_id)
        conn = sqlite3.connect(S._api_get_db())
        conn.execute('UPDATE vollis_games SET location = ? WHERE id = ?', (location, game_id))
        conn.commit()
        conn.close()
        S._remember_game_location(location)
        S.clear_stats_cache()
        S.log_activity(
            'Edited vollis game (iPhone)',
            target='vollis_game',
            target_id=game_id,
            summary=f'{winner} vs {loser} ({winner_score}-{loser_score})',
            before=before,
            after=S.adminfx.snapshot_row('vollis_game', game_id),
        )
        found = find_vollis_game(game_id)
        return jsonify(_vollis_game_dict(found[0]))

    @app.route('/api/vollis/games/<int:game_id>', methods=['DELETE'])
    @api_login_required
    def api_vollis_delete(game_id):
        from vollis_functions import find_vollis_game, remove_vollis_game
        S = _S()
        rows = find_vollis_game(game_id)
        if not rows:
            return jsonify({'error': 'Game not found'}), 404
        before = S.adminfx.snapshot_row('vollis_game', game_id)
        remove_vollis_game(game_id)
        record_deletion('vollis_game', game_id)
        S.clear_stats_cache()
        S.log_activity(
            'Deleted vollis game (iPhone)',
            target='vollis_game',
            target_id=game_id,
            summary=f'Game ID {game_id}',
            before=before,
        )
        return jsonify({'message': 'Deleted', 'id': game_id})

    @app.route('/api/vollis_players')
    @api_login_required
    def api_vollis_players():
        from vollis_functions import vollis_year_games, all_vollis_players
        from player_functions import merge_roster_into_player_names
        games = vollis_year_games('All years')
        return jsonify(merge_roster_into_player_names(all_vollis_players(games)))

    @app.route('/api/vollis/players/<path:name>')
    def api_vollis_player(name):
        from vollis_functions import (
            all_years_vollis_player, games_from_vollis_player_by_year,
            total_vollis_stats, vollis_opponent_stats_by_year,
        )
        from stat_functions import player_matchup_min_games
        S = _S()
        year = _year_arg(str(date.today().year))
        name = name.strip()
        games = games_from_vollis_player_by_year(year, name)
        stats = total_vollis_stats(name, games)
        min_games = player_matchup_min_games(len(games) if games else 0)
        opponents = vollis_opponent_stats_by_year(name, games, min_games)
        avatar = S.player_avatar_context(name)
        stat_row = None
        if stats:
            if isinstance(stats[0], (list, tuple)):
                stat_row = _ranking(stats[0])
            else:
                stat_row = stats
        return jsonify({
            'name': name,
            'year': year,
            'all_years': all_years_vollis_player(name),
            'stats': stat_row,
            'opponents': opponents,
            'winpct_min_games': min_games,
            'games': [_vollis_game_dict(g) for g in (games or [])],
            'photo_url': _abs(avatar.get('player_photo_url')),
        })

    # ----- Other / volleyball -----

    @app.route('/api/other/stats')
    def api_other_stats():
        from other_functions import (
            all_other_years, other_year_games, other_stats_per_year,
            rare_other_stats_per_year, todays_other_stats_by_game, todays_other_games,
        )
        S = _S()
        year = _year_arg(str(date.today().year))
        current_year = str(date.today().year)
        display_year = year
        showing_previous_year = False
        all_years = all_other_years()
        games = other_year_games(year)
        minimum_games = 1 if not games or len(games) < 30 else len(games) // 30
        stats = other_stats_per_year(year, minimum_games)
        if not stats and year == current_year and all_years:
            previous_year = str(int(current_year) - 1)
            if previous_year in all_years:
                games = other_year_games(previous_year)
                minimum_games = max(1, (len(games) // 30) if games else 1)
                stats = other_stats_per_year(previous_year, minimum_games)
                display_year = previous_year
                showing_previous_year = True
        rare = rare_other_stats_per_year(display_year, minimum_games)
        cards = S.build_other_game_cards(display_year)
        today_by_game = todays_other_stats_by_game()
        today_json = []
        for block in (today_by_game or []):
            today_json.append({
                'game_name': block.get('game_name'),
                'game_count': block.get('game_count'),
                'stats': [_ranking(r, rating_key='plus_minus') for r in (block.get('stats') or [])],
            })
        return jsonify({
            'year': year,
            'display_year': display_year,
            'showing_previous_year': showing_previous_year,
            'minimum_games': minimum_games,
            'all_years': all_years,
            'stats': [_ranking(r) for r in (stats or [])],
            'rare_stats': [_ranking(r) for r in (rare or [])],
            'game_cards': [_card_stats(c) for c in (cards or [])],
            'today_stats_by_game': today_json,
            'today_games': [_other_game_json(g) for g in (todays_other_games() or [])],
        })

    @app.route('/api/other/game-types')
    def api_other_game_types():
        from other_functions import other_year_games, other_game_names, other_game_types, other_game_type_for_name
        games = other_year_games('All years')
        names = other_game_names(games)
        types = other_game_types(games)
        mapping = {n: other_game_type_for_name(games, n) for n in names}
        return jsonify({'game_names': names, 'game_types': types, 'type_for_name': mapping})

    @app.route('/api/volleyball/stats')
    def api_volleyball_stats():
        S = _S()
        year = _year_arg(str(date.today().year))
        from other_functions import all_other_years
        cards = S.build_volleyball_game_cards_styled(year)
        return jsonify({
            'year': year,
            'all_years': all_other_years(),
            'game_cards': [_card_stats(c) for c in (cards or [])],
        })

    @app.route('/api/other/games', methods=['GET'])
    def api_other_list():
        from other_functions import other_year_games, all_other_years
        year = _year_arg('All years')
        game_name = (request.args.get('game_name') or '').strip()
        since = (request.args.get('since') or '').strip()
        games = other_year_games(year)
        if game_name:
            games = [g for g in games if g.get('game_name') == game_name]
        since_str = None
        if since:
            try:
                dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
                since_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                since_str = since
            games = [g for g in games if str(g.get('updated_at') or '') >= since_str]
        return jsonify({
            'games': [_other_game_json(g) for g in games],
            'all_years': all_other_years(),
            'deleted_ids': deleted_ids_since('other_game', since_str),
        })

    @app.route('/api/other/games/<int:game_id>', methods=['GET'])
    def api_other_get(game_id):
        from other_functions import find_other_game, readable_games_data
        rows = find_other_game(game_id)
        if not rows:
            return jsonify({'error': 'Game not found'}), 404
        parsed = readable_games_data(rows)
        return jsonify(_other_game_json(parsed[0] if parsed else {}))

    def _other_payload_from_json(data):
        game_type = (data.get('game_type') or '').strip()
        game_name = (data.get('game_name') or '').strip()
        score_type = (data.get('score_type') or 'individual') or 'individual'
        winners = [n.strip() for n in (data.get('winners') or []) if n and str(n).strip()]
        losers = [n.strip() for n in (data.get('losers') or []) if n and str(n).strip()]
        winner_scores = list(data.get('winner_scores') or [])
        loser_scores = list(data.get('loser_scores') or [])
        while len(winner_scores) < len(winners):
            winner_scores.append('')
        while len(loser_scores) < len(losers):
            loser_scores.append('')
        comment = data.get('comment') or data.get('comments') or ''
        team_winner_score = data.get('winner_score')
        team_loser_score = data.get('loser_score')
        return {
            'game_type': game_type,
            'game_name': game_name,
            'score_type': score_type,
            'winners': winners,
            'losers': losers,
            'winner_scores': winner_scores,
            'loser_scores': loser_scores,
            'comment': comment,
            'team_winner_score': team_winner_score,
            'team_loser_score': team_loser_score,
            'game_date': _normalize_game_date(data.get('game_date')),
            'entered_timezone': (data.get('entered_timezone') or '').strip() or session.get('timezone') or None,
            'location': (data.get('location') or '').strip(),
        }

    @app.route('/api/other/games', methods=['POST'])
    @api_login_required
    def api_other_create():
        from other_functions import add_other_stats
        S = _S()
        data = request.get_json(force=True, silent=True) or {}
        p = _other_payload_from_json(data)
        if not p['game_type'] or not p['game_name'] or not p['winners'] or not p['losers']:
            return jsonify({'error': 'game_type, game_name, winners, and losers required'}), 400
        add_other_stats(
            p['game_date'], p['game_type'], p['game_name'], p['winners'], p['winner_scores'],
            p['losers'], p['loser_scores'], p['comment'], p['game_date'],
            p['team_winner_score'], p['team_loser_score'], p['entered_timezone'],
            entered_by=session.get('username', ''), location=p['location'],
        )
        S._remember_game_location(p['location'])
        S.clear_stats_cache()
        new_row = S.adminfx.snapshot_last_row('other_game')
        S.log_activity(
            'Added other game (iPhone)',
            target='other_game',
            target_id=new_row['id'] if new_row else None,
            summary=f"{p['game_type']} - {p['game_name']}",
            after=new_row,
        )
        return jsonify({'message': 'Game created', 'id': new_row['id'] if new_row else None}), 201

    @app.route('/api/other/games/<int:game_id>', methods=['PUT'])
    @api_login_required
    def api_other_update(game_id):
        from other_functions import find_other_game, database_update_other_game
        from database_functions import create_connection
        S = _S()
        rows = find_other_game(game_id)
        if not rows:
            return jsonify({'error': 'Game not found'}), 404
        game_row = rows[0]
        data = request.get_json(force=True, silent=True) or {}
        p = _other_payload_from_json(data)
        if not p['game_type'] or not p['game_name'] or not p['winners'] or not p['losers']:
            return jsonify({'error': 'game_type, game_name, winners, and losers required'}), 400
        score_type = p['score_type']
        if score_type == 'team':
            aggregate_winner_score = int(p['team_winner_score']) if p['team_winner_score'] not in (None, '') else None
            aggregate_loser_score = int(p['team_loser_score']) if p['team_loser_score'] not in (None, '') else None
        elif score_type == 'none':
            aggregate_winner_score = None
            aggregate_loser_score = None
        else:
            aggregate_winner_score = next((int(s) for s in p['winner_scores'] if s not in ('', None)), None)
            aggregate_loser_score = next((int(s) for s in p['loser_scores'] if s not in ('', None)), None)
        database = '/home/Idynkydnk/stats/stats.db'
        conn = create_connection(database)
        if conn is None:
            conn = create_connection('stats.db')
        before = S.adminfx.snapshot_row('other_game', game_id)
        date_val = game_row[1] if not hasattr(game_row, 'keys') else game_row['game_date']
        if data.get('game_date'):
            date_val = p['game_date']
        with conn:
            game_data = tuple(
                [date_val, p['game_type'], p['game_name']]
                + (p['winners'] + [''] * 15)[:15]
                + [(int(s) if s not in ('', None) else None) for s in (p['winner_scores'] + [None] * 15)[:15]]
                + [aggregate_winner_score]
                + (p['losers'] + [''] * 15)[:15]
                + [(int(s) if s not in ('', None) else None) for s in (p['loser_scores'] + [None] * 15)[:15]]
                + [aggregate_loser_score, p['comment'], S.get_user_now(), game_id]
            )
            database_update_other_game(conn, game_data)
            conn.execute('UPDATE other_games SET location = ? WHERE id = ?', (p['location'], game_id))
        S._remember_game_location(p['location'])
        S.clear_stats_cache()
        S.log_activity(
            'Edited other game (iPhone)',
            target='other_game',
            target_id=game_id,
            summary=f"{p['game_type']} - {p['game_name']}",
            before=before,
            after=S.adminfx.snapshot_row('other_game', game_id),
        )
        return jsonify({'message': 'Updated', 'id': game_id})

    @app.route('/api/other/games/<int:game_id>', methods=['DELETE'])
    @api_login_required
    def api_other_delete(game_id):
        from other_functions import find_other_game, remove_other_game
        S = _S()
        rows = find_other_game(game_id)
        if not rows:
            return jsonify({'error': 'Game not found'}), 404
        before = S.adminfx.snapshot_row('other_game', game_id)
        remove_other_game(game_id)
        record_deletion('other_game', game_id)
        S.clear_stats_cache()
        S.log_activity(
            'Deleted other game (iPhone)',
            target='other_game',
            target_id=game_id,
            summary=f'Game ID {game_id}',
            before=before,
        )
        return jsonify({'message': 'Deleted', 'id': game_id})

    @app.route('/api/other/players/<path:name>')
    def api_other_player(name):
        from other_functions import (
            all_years_other_player, games_from_other_player_by_year,
            total_other_stats, other_opponent_stats_by_year,
        )
        from stat_functions import player_matchup_min_games
        S = _S()
        year = _year_arg(str(date.today().year))
        name = name.strip()
        games = games_from_other_player_by_year(year, name)
        stats = total_other_stats(name, games)
        min_games = player_matchup_min_games(len(games) if games else 0)
        opponents = other_opponent_stats_by_year(name, games, min_games)
        avatar = S.player_avatar_context(name)
        stat_row = _ranking(stats[0]) if stats and isinstance(stats[0], (list, tuple)) else stats
        return jsonify({
            'name': name,
            'year': year,
            'all_years': all_years_other_player(name),
            'stats': stat_row,
            'opponents': opponents,
            'winpct_min_games': min_games,
            'games': [_other_game_json(g) for g in (games or [])],
            'photo_url': _abs(avatar.get('player_photo_url')),
        })

    # ----- Players / tournaments -----

    @app.route('/api/players')
    def api_players():
        from player_functions import get_all_players
        S = _S()
        players = get_all_players()
        cards = S.build_player_list_cards(players)
        for card in cards:
            if card.get('photoUrl'):
                card['photoUrl'] = _abs(card['photoUrl'])
            if card.get('aiImageUrl'):
                card['aiImageUrl'] = _abs(card['aiImageUrl'])
        return jsonify({'players': cards})

    @app.route('/api/tournaments', methods=['GET'])
    @api_login_required
    def api_tournaments_list():
        S = _S()
        conn = sqlite3.connect(S._stats_db_path())
        cur = conn.cursor()
        try:
            S._ensure_tournaments_table(conn)
            cur.execute(
                '''SELECT id, tournament_date, place, team, location, tournament_name
                   FROM tournaments ORDER BY tournament_date DESC'''
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            rows = []
        finally:
            conn.close()
        items = [
            {
                'id': r[0],
                'tournament_date': r[1],
                'place': r[2],
                'team': r[3],
                'location': r[4],
                'tournament_name': r[5],
            }
            for r in rows
        ]
        return jsonify({'tournaments': items})

    @app.route('/api/tournaments', methods=['POST'])
    @api_login_required
    def api_tournaments_create():
        S = _S()
        data = request.get_json(force=True, silent=True) or {}
        tournament_date = (data.get('tournament_date') or '').strip()
        place = (data.get('place') or '').strip()
        team = (data.get('team') or '').strip()
        location = (data.get('location') or '').strip()
        tournament_name = (data.get('tournament_name') or '').strip()
        if not all([tournament_date, place, team, location, tournament_name]):
            return jsonify({'error': 'All fields are required'}), 400
        conn = sqlite3.connect(S._stats_db_path())
        cur = conn.cursor()
        S._ensure_tournaments_table(conn)
        cur.execute(
            '''INSERT INTO tournaments (tournament_date, place, team, location, tournament_name)
               VALUES (?, ?, ?, ?, ?)''',
            (tournament_date, place, team, location, tournament_name),
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        S.log_activity('Added tournament', summary=f'{tournament_name} ({tournament_date}) - {place} place')
        return jsonify({
            'id': new_id,
            'tournament_date': tournament_date,
            'place': place,
            'team': team,
            'location': location,
            'tournament_name': tournament_name,
        }), 201

    # ----- AI -----

    @app.route('/api/ai/recaps')
    @api_login_required
    def api_my_recaps():
        S = _S()
        username = S._browse_username_filter()
        page = max(int(request.args.get('page', 1) or 1), 1)
        per_page = 25
        entries, total = S.adminfx.list_ai_recap_pages(page=page, per_page=per_page, username=username)
        site_base = (S.app.config.get('SITE_BASE_URL') or S.EMAIL_SITE_BASE_URL).rstrip('/')
        out = [S.serialize_recap_list_entry(entry, site_base) for entry in entries]
        return jsonify({
            'recaps': out,
            'page': page,
            'total': total,
            'showing_all': username is None,
        })

    @app.route('/api/flyers', methods=['GET'])
    @api_login_required
    def api_my_flyers():
        S = _S()
        import flyer_functions as flyerfx
        username = S._browse_username_filter()
        page = max(int(request.args.get('page', 1) or 1), 1)
        per_page = 25
        entries, total = flyerfx.list_flyer_pages(page=page, per_page=per_page, username=username)
        site_base = (S.app.config.get('SITE_BASE_URL') or S.EMAIL_SITE_BASE_URL).rstrip('/')
        out = [S.serialize_flyer_list_entry(entry, site_base) for entry in entries]
        return jsonify({
            'flyers': out,
            'page': page,
            'total': total,
            'showing_all': username is None,
        })

    @app.route('/api/flyers/<share_id>', methods=['DELETE'])
    @api_login_required
    def api_delete_flyer(share_id):
        S = _S()
        import flyer_functions as flyerfx
        share_id = (share_id or '').strip()
        row = flyerfx.get_flyer_page(share_id)
        if not row:
            return jsonify({'error': 'Flyer not found'}), 404
        if not S._is_owner_or_admin(row.get('username')):
            return jsonify({'error': 'You can only delete flyers you created.'}), 403
        if not flyerfx.delete_flyer_page(share_id):
            return jsonify({'error': 'Flyer not found'}), 404
        S.log_activity('Deleted flyer', target=share_id, summary=S._flyer_sport_label(
            row.get('game_type'), row.get('game_name'),
        ))
        return jsonify({'ok': True})

    @app.route('/api/ai/roster', methods=['POST'])
    @api_login_required
    def api_ai_roster():
        """Player cards for the recap/flyer roster review step."""
        S = _S()
        data = request.get_json(force=True, silent=True) or {}
        names = [
            str(n).strip() for n in (data.get('players') or [])
            if n and str(n).strip()
        ]
        if not names:
            game_ids = [str(g) for g in (data.get('game_ids') or []) if g]
            game_type = (data.get('game_type') or 'doubles').strip().lower()
            if not game_ids:
                return jsonify({'error': 'No games or players selected.'}), 400
            names = S._roster_players_for_games(game_ids, game_type)
        cards = S.build_ai_recap_roster_cards(names)
        for card in cards:
            if card.get('photoUrl'):
                card['photoUrl'] = _abs(card['photoUrl'])
            if card.get('aiImageUrl'):
                card['aiImageUrl'] = _abs(card['aiImageUrl'])
        return jsonify({'players': cards})

    @app.route('/api/ai/summary', methods=['POST'])
    @api_login_required
    def api_ai_summary_json():
        """JSON wrapper around the existing form-based generate endpoint."""
        S = _S()
        data = request.get_json(force=True, silent=True) or {}
        game_type = data.get('game_type', 'doubles')
        prompt_style = data.get('prompt_style', 'default')
        custom_prompt = data.get('custom_prompt', '')
        game_ids = data.get('game_ids') or []
        if not game_ids:
            return jsonify({'success': False, 'error': 'No games selected.'}), 400
        username = session.get('username', 'unknown')
        image_mode = S._normalize_image_mode(data.get('image_mode'))
        image_details = (data.get('image_details') or '').strip()
        job_id = S.ai_jobs.enqueue_job(
            username, [str(g) for g in game_ids], game_type, prompt_style, custom_prompt,
            image_mode=image_mode, image_details=image_details,
            illustration_players=[],
        )
        worker_alive = S.ai_jobs.daemon_is_alive()
        S.log_activity(
            'Queued AI recap publish',
            summary=f'job #{job_id}: {game_type} for {len(game_ids)} game(s)',
            username=username,
        )
        return jsonify({
            'success': True,
            'job_id': job_id,
            'worker_alive': worker_alive,
        })

    @app.route('/api/flyers', methods=['POST'])
    @api_login_required
    def api_create_flyer():
        S = _S()
        data = request.get_json(force=True, silent=True) or {}
        players = [n.strip() for n in (data.get('players') or []) if n and str(n).strip()]
        payload = {
            'players': players,
            'game_type': (data.get('game_type') or 'doubles').strip().lower(),
            'game_name': (data.get('game_name') or '').strip(),
            'event_date': (data.get('event_date') or '').strip(),
            'event_time': (data.get('event_time') or '').strip(),
            'location': (data.get('location') or '').strip(),
            'image_details': (data.get('image_details') or '').strip(),
            'scene_prompt': (data.get('scene_prompt') or '').strip(),
            'custom_solo_prompts': data.get('custom_solo_prompts') or {},
        }
        error = S._validate_flyer_payload(payload)
        if error:
            return jsonify({'error': error}), 400
        username = session.get('username') or 'unknown'
        job_id = S.ai_jobs.enqueue_flyer_job(username, payload)
        S.log_activity('Queued flyer', summary=f'job #{job_id}', username=username)
        return jsonify({'success': True, 'job_id': job_id}), 201

    @app.route('/api/ai/jobs/<int:job_id>')
    @api_login_required
    def api_ai_job(job_id):
        S = _S()
        job = S.ai_jobs.get_job(job_id) if hasattr(S.ai_jobs, 'get_job') else None
        if job is None:
            # Fall back to existing HTML/JSON job route internals if present
            try:
                from ai_auto_send_jobs import get_job
                job = get_job(job_id)
            except Exception:
                job = None
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        if not S._can_access_job(job):
            return jsonify({'error': 'Not allowed'}), 403
        if not isinstance(job, dict):
            job = dict(job)
        payload = {}
        raw_payload = job.get('payload_json')
        if isinstance(raw_payload, str) and raw_payload.strip():
            try:
                parsed = json.loads(raw_payload)
                if isinstance(parsed, dict):
                    payload = parsed
            except (json.JSONDecodeError, TypeError):
                payload = {}
        ai_image_url = None
        if (job.get('job_type') or '') == 'player_ai_image' and (job.get('status') or '') == 'completed':
            summary = (job.get('result_summary') or '').strip()
            if summary.startswith('/') or summary.startswith('http'):
                ai_image_url = _abs(summary) if summary.startswith('/') else summary
        job['ai_image_url'] = ai_image_url
        job['player_name'] = payload.get('player_name') or job.get('custom_prompt') or ''
        share_id = (job.get('share_id') or '').strip()
        if (job.get('job_type') or '') == 'flyer' and share_id:
            import flyer_functions as flyerfx
            row = flyerfx.get_flyer_page(share_id) or {}
            job['flyer_image_url'] = _abs(row.get('flyer_image_url') or '')
            job['download_url'] = _abs(f'/flyer/{share_id}/download.jpg')
        return jsonify(job)

    # ----- Admin -----

    def _admin_user_payload(u):
        return {
            'username': u.get('username'),
            'is_admin': bool(u.get('is_admin')),
            'active': bool(u.get('active')),
            'created_at': u.get('created_at'),
            'last_seen': u.get('last_seen'),
            'last_login': u.get('last_login'),
        }

    def _admin_activity_payload():
        S = _S()
        page, per_page = _page_args(40)
        q = (request.args.get('q') or '').strip() or None
        username = (request.args.get('username') or '').strip() or None
        action = (request.args.get('action') or '').strip() or None
        entries, total = S.adminfx.get_activity_page(
            page=page, per_page=per_page, username=username, q=q, action=action,
        )
        return _paged(
            [S.adminfx.serialize_activity_entry(e) for e in entries],
            total, page, per_page, 'entries',
        )

    def _admin_games_payload():
        S = _S()
        page, per_page = _page_args(40)
        kind = (request.args.get('kind') or '').strip() or None
        games, total = S.adminfx.list_recent_games(page=page, per_page=per_page, kind=kind)
        payload = _paged(games, total, page, per_page, 'games')
        payload['kind'] = kind or 'all'
        return payload

    def _admin_logins_payload():
        S = _S()
        page, per_page = _page_args(40)
        username = (request.args.get('username') or '').strip() or None
        entries, total = S.adminfx.list_logins(page=page, per_page=per_page, username=username)
        return _paged(
            [S.adminfx.serialize_login_entry(e) for e in entries],
            total, page, per_page, 'logins',
        )

    def _admin_recaps_payload():
        S = _S()
        page, per_page = _page_args(25)
        username = (request.args.get('username') or '').strip() or None
        entries, total = S.adminfx.list_ai_recap_pages(
            page=page, per_page=per_page, username=username,
        )
        site_base = (S.app.config.get('SITE_BASE_URL') or S.EMAIL_SITE_BASE_URL).rstrip('/')
        payload = _paged(
            [S.serialize_recap_list_entry(entry, site_base) for entry in entries],
            total, page, per_page, 'recaps',
        )
        payload['showing_all'] = username is None
        return payload

    def _admin_flyers_payload():
        S = _S()
        import flyer_functions as flyerfx
        page, per_page = _page_args(25)
        username = (request.args.get('username') or '').strip() or None
        entries, total = flyerfx.list_flyer_pages(
            page=page, per_page=per_page, username=username,
        )
        site_base = (S.app.config.get('SITE_BASE_URL') or S.EMAIL_SITE_BASE_URL).rstrip('/')
        payload = _paged(
            [S.serialize_flyer_list_entry(entry, site_base) for entry in entries],
            total, page, per_page, 'flyers',
        )
        payload['showing_all'] = username is None
        return payload

    def _admin_jobs_payload():
        S = _S()
        page, per_page = _page_args(25)
        job_type = (request.args.get('job_type') or '').strip() or None
        username = (request.args.get('username') or '').strip() or None
        status = (request.args.get('status') or '').strip() or None
        jobs, total = S.ai_jobs.list_jobs(
            page=page, per_page=per_page, job_type=job_type,
            username=username, status=status,
        )
        return _paged(jobs, total, page, per_page, 'jobs')

    def _admin_users_payload():
        S = _S()
        return {'users': [_admin_user_payload(u) for u in S.adminfx.list_site_users()]}

    def _admin_overview_payload():
        S = _S()
        today = date.today()
        counts = S.adminfx.games_counts(today.strftime('%Y-%m-%d'), (today - timedelta(days=6)).strftime('%Y-%m-%d'))
        recent = S.adminfx.most_recent_game()
        activity = S.adminfx.activity_overview()
        shares = S._admin_share_previews()
        try:
            db_size_mb = round(os.path.getsize(S.adminfx.stats_db_path()) / (1024 * 1024), 1)
        except OSError:
            db_size_mb = None
        catalog = admin_topic_catalog()
        return {
            'ask': catalog['ask'],
            'topics': catalog['topics'],
            'counts': counts,
            'recent_game': recent,
            'db_size_mb': db_size_mb,
            'users': _admin_users_payload()['users'],
            'email_configured': bool(S.app.config.get('MAIL_USERNAME') and S.app.config.get('MAIL_PASSWORD')),
            'activity': activity,
            'recent_recaps': shares['recent_recaps'],
            'recap_count': shares['recap_total'],
            'recent_flyers': shares['recent_flyers'],
            'flyer_count': shares['flyer_total'],
            'recent_jobs': shares['recent_jobs'],
            'job_count': shares['job_total'],
        }

    def _admin_topic_payload(topic):
        builders = {
            'everything': _admin_activity_payload,
            'activity': _admin_activity_payload,
            'games': _admin_games_payload,
            'logins': _admin_logins_payload,
            'summaries': _admin_recaps_payload,
            'recaps': _admin_recaps_payload,
            'flyers': _admin_flyers_payload,
            'jobs': _admin_jobs_payload,
            'users': _admin_users_payload,
            'overview': _admin_overview_payload,
        }
        builder = builders.get(topic)
        if not builder:
            return None
        return builder()

    @app.route('/api/admin')
    @app.route('/api/admin/')
    @api_admin_required
    def api_admin_index():
        catalog = admin_topic_catalog()
        topic = (request.args.get('topic') or '').strip().lower()
        if not topic:
            return jsonify(catalog)
        payload = _admin_topic_payload(topic)
        if payload is None:
            known = [t['id'] for t in catalog['topics']]
            return jsonify({
                **catalog,
                'error': f'Unknown topic "{topic}"',
                'known_topics': known,
            }), 400
        return jsonify({**catalog, 'topic': topic, **payload})

    @app.route('/api/admin/overview')
    @api_admin_required
    def api_admin_overview():
        return jsonify(_admin_overview_payload())

    @app.route('/api/admin/games')
    @api_admin_required
    def api_admin_games():
        return jsonify(_admin_games_payload())

    @app.route('/api/admin/logins')
    @api_admin_required
    def api_admin_logins():
        return jsonify(_admin_logins_payload())

    @app.route('/api/admin/users', methods=['GET'])
    @api_admin_required
    def api_admin_list_users():
        return jsonify(_admin_users_payload())

    @app.route('/api/admin/activity')
    @api_admin_required
    def api_admin_activity():
        return jsonify(_admin_activity_payload())

    @app.route('/api/admin/recaps')
    @api_admin_required
    def api_admin_recaps():
        return jsonify(_admin_recaps_payload())

    @app.route('/api/admin/flyers')
    @api_admin_required
    def api_admin_flyers():
        return jsonify(_admin_flyers_payload())

    @app.route('/api/admin/jobs')
    @api_admin_required
    def api_admin_jobs():
        return jsonify(_admin_jobs_payload())

    @app.route('/api/admin/activity/<int:log_id>')
    @api_admin_required
    def api_admin_activity_entry(log_id):
        S = _S()
        entry = S.adminfx.get_activity_entry(log_id)
        if not entry:
            return jsonify({'error': 'Log entry not found'}), 404
        return jsonify({'entry': S.adminfx.serialize_activity_entry(entry, include_snapshots=True)})

    @app.route('/api/admin/undo/<int:log_id>', methods=['POST'])
    @api_admin_required
    def api_admin_undo(log_id):
        S = _S()
        ok, message, target = S.adminfx.undo_entry(log_id)
        if ok:
            S.clear_stats_cache()
            if target == 'doubles_game':
                from kob_functions import update_kobs
                update_kobs()
            entry = S.adminfx.get_activity_entry(log_id)
            S.log_activity(
                'Undid change',
                target=target,
                target_id=entry['target_id'] if entry else None,
                summary=f'Undid log entry #{log_id}',
            )
            return jsonify({'ok': True, 'message': message})
        return jsonify({'ok': False, 'error': message}), 400

    @app.route('/api/admin/users', methods=['POST'])
    @api_admin_required
    def api_admin_add_user():
        S = _S()
        data = request.get_json(force=True, silent=True) or {}
        username = (data.get('username') or '').strip().lower()
        password = data.get('password') or ''
        make_admin = bool(data.get('is_admin'))
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        if S.adminfx.get_site_user(username):
            return jsonify({'error': f'User "{username}" already exists'}), 400
        ok = S.adminfx.create_site_user(
            username, generate_password_hash(password, method='pbkdf2:sha256'), is_admin=make_admin,
        )
        if not ok:
            return jsonify({'error': 'Could not create user'}), 400
        S.log_activity('Added site user', summary=f'{username}{" (admin)" if make_admin else ""}')
        return jsonify({'ok': True, 'username': username}), 201

    @app.route('/api/admin/users/reset_password', methods=['POST'])
    @api_admin_required
    def api_admin_reset_password():
        S = _S()
        data = request.get_json(force=True, silent=True) or {}
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        if not S.adminfx.update_site_user(
            username, password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
        ):
            return jsonify({'error': f'User "{username}" not found'}), 404
        S.log_activity('Reset user password', summary=username)
        return jsonify({'ok': True})

    @app.route('/api/admin/users/toggle_active', methods=['POST'])
    @api_admin_required
    def api_admin_toggle_active():
        S = _S()
        data = request.get_json(force=True, silent=True) or {}
        username = (data.get('username') or '').strip()
        active = data.get('active')
        if not username or active is None:
            return jsonify({'error': 'Username and active are required'}), 400
        if username.lower() == (session.get('username') or '').lower():
            return jsonify({'error': 'You cannot deactivate your own account'}), 400
        activate = bool(active)
        if not S.adminfx.update_site_user(username, active=1 if activate else 0):
            return jsonify({'error': f'User "{username}" not found'}), 404
        if not activate:
            S.revoke_all_user_tokens(username)
        S.log_activity(
            'Reactivated site user' if activate else 'Deactivated site user',
            summary=username,
        )
        return jsonify({'ok': True})

    @app.route('/api/admin/backup', methods=['POST'])
    @api_admin_required
    def api_admin_backup():
        import shutil
        S = _S()
        src = S.adminfx.stats_db_path()
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(src)) or '.', 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        dest = os.path.join(backup_dir, f"stats_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        try:
            shutil.copy2(src, dest)
        except OSError as e:
            return jsonify({'ok': False, 'error': f'Backup failed: {e}'}), 500
        S.log_activity('Backed up database', summary=os.path.basename(dest))
        return jsonify({'ok': True, 'filename': os.path.basename(dest)})

    @app.route('/api/admin/clear_cache', methods=['POST'])
    @api_admin_required
    def api_admin_clear_cache():
        S = _S()
        S.clear_stats_cache()
        S.log_activity('Cleared stats cache')
        return jsonify({'ok': True})

    @app.route('/api/admin/test_email', methods=['POST'])
    @api_admin_required
    def api_admin_test_email():
        S = _S()
        if not S.app.config.get('MAIL_USERNAME') or not S.app.config.get('MAIL_PASSWORD'):
            return jsonify({'error': 'Email not configured'}), 400
        to_addr = S.app.config.get('MAIL_USERNAME')
        from flask_mail import Message
        msg = Message(subject='Test email from Stats admin dashboard', recipients=[to_addr])
        msg.body = 'Email sending works. Sent from the iOS admin API.'
        S.mail.send(msg)
        S.log_activity('Sent email', summary=f'Test email to {to_addr}')
        return jsonify({'ok': True, 'to': to_addr})

    @app.route('/api/admin/site-updates', methods=['GET', 'POST'])
    @api_admin_required
    def api_admin_site_updates():
        S = _S()
        if request.method == 'GET':
            changes, git_error = S.adminfx.list_recent_site_changes()
            return jsonify({
                'changes': changes,
                'git_error': git_error,
                'recipients': S.adminfx.list_site_update_recipients(),
                'email_configured': bool(S.app.config.get('MAIL_USERNAME') and S.app.config.get('MAIL_PASSWORD')),
                'default_subject': "What's new on the stats site",
            })
        data = request.get_json(silent=True) or {}
        shas = [str(sha) for sha in (data.get('shas') or []) if sha]
        extra_notes = (data.get('extra_notes') or '').strip()
        usernames = [str(name) for name in (data.get('usernames') or []) if name]
        subject = data.get('subject')
        body = data.get('body')
        changes, _err = S.adminfx.list_recent_site_changes()
        by_sha = {item['sha']: item for item in changes}
        selected = [by_sha[sha] for sha in shas if sha in by_sha]
        if body is None:
            bullets = S.adminfx.site_update_bullets(selected, extra_notes)
        else:
            bullets = [line.strip() for line in str(body).splitlines() if line.strip()]
        sent, errors, chosen = S.send_site_update_email(
            subject, bullets, usernames, shas=shas,
            sent_by=session.get('username'),
        )
        if not chosen:
            return jsonify({'success': False, 'error': (errors or ['Could not send that update.'])[0]}), 400
        names = [person['username'] for person in chosen]
        return jsonify({
            'success': True,
            'sent': sent,
            'errors': errors,
            'usernames': names,
        })
