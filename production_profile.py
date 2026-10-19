"""Opt-in profiling of public GETs, signed by deployment CI; no user data output."""
import cProfile
import hashlib
import hmac
import os
from pathlib import Path
import pstats
import time

from flask import g, jsonify, request

PROFILE_ENDPOINTS = {'stats', 'player_stats', 'games', 'vollis_stats',
                     'other_stats', 'volleyball_stats', 'add_game', 'add_vollis_game',
                     'add_other_game', 'player_list', 'stats_sources_page', 'admin_dashboard'}


def profile_target(path, query='', cookie='', authorization=''):
    target = path + ('?' + query if query else '')
    if cookie or authorization:
        # A public diagnostic signature cannot be replayed against a signed-in
        # browser. Bind the diagnostic to the exact existing credentials too.
        target += '\nauth:' + hashlib.sha256((cookie + '\n' + authorization).encode()).hexdigest()
    return target


def signature(secret, timestamp, target):
    return hmac.new(secret.encode(), (timestamp + '\n' + target).encode(), hashlib.sha256).hexdigest()


def start_profile():
    header = request.headers.get('X-Stats-Profile', '')
    secret = os.environ.get('DEPLOY_TOKEN', '')
    if not header or not secret or request.method != 'GET' or request.endpoint not in PROFILE_ENDPOINTS:
        return
    timestamp, separator, supplied = header.partition(':')
    try:
        fresh = abs(time.time() - int(timestamp)) <= 60
    except ValueError:
        return
    target = profile_target(request.path, request.query_string.decode('ascii'),
                            request.headers.get('Cookie', ''), request.headers.get('Authorization', ''))
    if not separator or not fresh or not hmac.compare_digest(supplied, signature(secret, timestamp, target)):
        return
    profile = g.production_profile = cProfile.Profile()
    profile.enable()


def finish_profile(response, duration):
    profile = g.pop('production_profile', None)
    if profile is None:
        return response
    profile.disable()
    stats = pstats.Stats(profile)
    root = Path(__file__).resolve().parent
    rows = []
    for (filename, line, function), (primitive, calls, own, cumulative, _) in stats.stats.items():
        # Only code locations and aggregate times; never arguments, SQL, URLs,
        # response contents, or local variables from the request.
        try:
            location = str(Path(filename).relative_to(root))
        except ValueError:
            location = Path(filename).name
        rows.append(dict(file=location, line=line, function=function, calls=calls,
                         self_ms=round(own * 1000, 3), total_ms=round(cumulative * 1000, 3)))
    result = jsonify(endpoint=request.endpoint, status=response.status_code,
                     page_cache='hit' if getattr(g, 'stats_page_hit', False) else 'miss',
                     elapsed_ms=round(duration, 1), html_bytes=len(response.get_data()),
                     worker=hashlib.sha256(str(os.getpid()).encode()).hexdigest()[:8],
                     cumulative=sorted(rows, key=lambda row: row['total_ms'], reverse=True)[:65],
                     self_time=sorted(rows, key=lambda row: row['self_ms'], reverse=True)[:35])
    result.headers['Cache-Control'] = 'no-store'
    return result


def stop_profile(error=None):
    profile = g.pop('production_profile', None)
    if profile is not None:
        profile.disable()
