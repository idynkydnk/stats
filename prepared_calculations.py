"""Bounded per-worker reuse of read-only calculations after source authorization."""
from stats_date_filter import active_date_range
from collections import OrderedDict
import pickle
import threading
import time

from flask import current_app, g, session
from doubles_division import active_doubles_division
from stats_location_filter import active_location_filter

_values = OrderedDict()
_lock = threading.Lock()
MAX_BYTES = 16 * 1024 * 1024


def clear_prepared_calculations():
    with _lock:
        _values.clear()


def reuse_calculation(function, args, kwargs, ttl=300, revision=None):
    databases = getattr(g, 'stats_source_databases', None) if revision is None else None
    if revision is None:
        revision = g.stats_data_revision
    table = {'stat_functions': 'games', 'vollis_functions': 'vollis_games',
             'other_functions': 'other_games'}.get(function.__module__)
    if databases and table:
        from stats_snapshot_cache import source_revision
        revisions = g.setdefault('stats_calculation_revisions', {})
        if table not in revisions:
            revisions[table] = source_revision(databases, ('players', table))
        revision = revisions[table]
    key = (revision, function.__module__, function.__name__, repr(args),
           repr(sorted(kwargs.items())), active_doubles_division(), active_location_filter(), active_date_range(), session.get('timezone'))
    now = time.monotonic()
    with _lock:
        found = _values.get(key)
        if found and found[0] > now:
            _values.move_to_end(key)
            # These bytes were generated here or authenticated on shared load.
            # Return a copy so one response cannot change another's calculations.
            return pickle.loads(found[1])
    shared = current_app.extensions.get('stats_calculation_cache')
    found = shared.load(key) if shared else None
    if found is not None:
        body, expires = found
        try:
            result = pickle.loads(body)
        except (pickle.PickleError, EOFError, TypeError, ValueError, AttributeError, ImportError):
            body = None
        else:
            _remember(key, min(now + ttl, now + max(0, expires - time.time())), body)
            return result
    result = function(*args, **kwargs)
    try:
        body = pickle.dumps(result)
    except (TypeError, pickle.PicklingError):
        return result
    if len(body) <= 2 * 1024 * 1024:
        _remember(key, now + ttl, body)
        if shared:
            shared.save(key, body, ttl)
    return result


def _remember(key, expires, body):
    with _lock:
        _values[key] = (expires, body)
        _values.move_to_end(key)
        while len(_values) > 128 or sum(len(v[1]) for v in _values.values()) > MAX_BYTES:
            _values.popitem(last=False)
