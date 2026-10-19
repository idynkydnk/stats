"""Bounded, anonymous action timings. No URLs, queries, player names or account IDs."""
from collections import deque
import threading
import time

from flask import g, jsonify, request
from production_profile import start_profile, finish_profile, stop_profile


def register_performance(app, can_view):
    samples = deque(maxlen=256)
    lock = threading.Lock()

    def record(kind, action, duration):
        sample = dict(kind=kind, action=action, milliseconds=round(duration, 1))
        with lock:
            samples.append(sample)
        if duration >= 1000:
            app.logger.warning('slow_action kind=%s action=%s milliseconds=%.1f', kind, action, duration)

    @app.before_request
    def start_timing():
        g.performance_started = time.perf_counter()
        start_profile()

    app.teardown_request(stop_profile)

    @app.after_request
    def finish_timing(response):
        started = getattr(g, 'performance_started', None)
        if started is not None and request.endpoint not in {'static', 'performance_sample', 'performance_report'}:
            duration = (time.perf_counter() - started) * 1000
            response = finish_profile(response, duration)
            response.headers.add('Server-Timing', f'app;dur={duration:.1f}')
            record('server', request.endpoint or 'unknown', duration)
        return response

    @app.post('/performance-sample')
    def performance_sample():
        # Telemetry cannot trigger work or store user supplied labels. Bound both
        # the request and retained values, including anonymous browser samples.
        if request.content_length is None or request.content_length > 4096:
            return '', 413
        if request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin'):
            return '', 403
        payload = request.get_json(silent=True)
        if not isinstance(payload, list) or len(payload) > 12:
            return '', 400
        allowed = {'navigation', 'tap', 'save', 'filter', 'long-task', 'server-wait', 'download', 'render'}
        for item in payload:
            if not isinstance(item, dict):
                continue
            value = item.get('milliseconds')
            if item.get('action') in allowed and isinstance(value, (float, int)) and 0 <= value <= 120000:
                record('browser', item['action'], value)
        return '', 204

    @app.get('/api/admin/performance')
    def performance_report():
        if not can_view():
            return jsonify(error='Admin access required'), 403
        with lock:
            result = list(samples)
        response = jsonify(samples=result, scope='This server worker; slow actions also appear in server logs.')
        response.headers['Cache-Control'] = 'no-store'
        return response
