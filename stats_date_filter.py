"""Calendar-day filters carried in stats links, including shared links."""
from datetime import date
from urllib.parse import parse_qsl, urlsplit

from flask import abort, has_request_context, redirect, render_template, request, url_for


def validate_date_range(start, end):
    if not start and not end:
        return None
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first.isoformat() != start or last.isoformat() != end:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('Choose both a valid start day and end day.') from None
    if first > last:
        raise ValueError('The end day must be on or after the start day.')
    return start, end


def active_date_range():
    from stats_location_filter import STATS_ENDPOINTS
    if not has_request_context() or request.method != 'GET' or request.endpoint not in STATS_ENDPOINTS:
        return None
    try:
        return validate_date_range(request.args.get('start_date', ''), request.args.get('end_date', ''))
    except ValueError as error:
        abort(400, description=str(error))


def register_stats_date_filter(app):
    from stats_location_filter import STATS_ENDPOINTS

    def destination(raw):
        """Accept only local stats routes, preserving their other filters."""
        parts = urlsplit(raw)
        if parts.scheme or parts.netloc:
            return 'stats', {'year': 'All years'}
        try:
            endpoint, values = app.url_map.bind('').match(parts.path, method='GET')
        except Exception:
            return 'stats', {'year': 'All years'}
        if endpoint not in STATS_ENDPOINTS:
            return 'stats', {'year': 'All years'}
        values.update({k: v for k, v in parse_qsl(parts.query)
                       if k not in {'start_date', 'end_date', 'page'} and k not in values})
        return endpoint, values

    @app.before_request
    def normalize_stats_date_range():
        if active_date_range() and request.endpoint.startswith('api_') and request.args.get('year') != 'All years':
            values = dict(request.args)
            values.update(request.view_args or {})
            values['year'] = 'All years'
            return redirect(url_for(request.endpoint, **values))
        if active_date_range() and request.view_args and 'year' in request.view_args:
            if request.view_args['year'] != 'All years':
                values = dict(request.args)
                values.update(request.view_args, year='All years')
                return redirect(url_for(request.endpoint, **values))

    @app.url_defaults
    def preserve_stats_date_range(endpoint, values):
        selected = active_date_range()
        if endpoint in STATS_ENDPOINTS and selected:
            values.setdefault('start_date', selected[0])
            values.setdefault('end_date', selected[1])
            if values.get('start_date') and values.get('end_date') and 'year' in values:
                values['year'] = 'All years'

    @app.context_processor
    def date_range_context():
        selected = active_date_range()
        endpoint, values = destination(request.full_path)
        values.update(start_date=None, end_date=None)
        clear_dates_url = url_for(endpoint, **values)
        values.update(location=None, missing=None)
        return dict(stats_date_range=selected,
                    stats_date_range_url=url_for('stats_time_frame', next=request.full_path),
                    stats_date_range_clear_url=clear_dates_url,
                    stats_filters_clear_url=url_for(endpoint, **values))

    @app.route('/stats-time-frame/')
    def stats_time_frame():
        next_url = request.args.get('next', '/stats/All%20years/')
        start = request.args.get('start_date', '')
        end = request.args.get('end_date', '')
        error = None
        if 'apply' in request.args:
            try:
                selected = validate_date_range(start, end)
                if not selected:
                    raise ValueError('Choose a start day and end day.')
            except ValueError as exc:
                error = str(exc)
            else:
                endpoint, values = destination(next_url)
                if 'year' in values:
                    values['year'] = 'All years'
                values.update(start_date=start, end_date=end)
                return redirect(url_for(endpoint, **values))
        else:
            previous = dict(parse_qsl(urlsplit(next_url).query))
            start, end = previous.get('start_date', ''), previous.get('end_date', '')
        return render_template('stats_time_frame.html', start=start, end=end,
                               next_url=next_url, error=error), 400 if error else 200
