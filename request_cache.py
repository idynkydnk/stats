"""Reuse read-only calculations within one request, never between accounts."""
from functools import wraps

from flask import g, has_request_context, request


def request_cached(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if not has_request_context() or request.method != 'GET':
            return function(*args, **kwargs)
        from private_accounts import data_path
        from stats_location_filter import active_location_filter
        from doubles_division import active_doubles_division
        key = (function.__module__, function.__name__, args, tuple(sorted(kwargs.items())),
               data_path('stats.db'), active_location_filter(), active_doubles_division())
        memo = g.setdefault('read_calculations', {})
        if key not in memo:
            memo[key] = function(*args, **kwargs)
        return memo[key]
    return wrapped
