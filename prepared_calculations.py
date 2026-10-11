"""Bounded per-worker reuse of read-only calculations after source authorization."""
from collections import OrderedDict
import pickle
import threading
import time

from flask import g
from doubles_division import active_doubles_division
from stats_location_filter import active_location_filter

_values = OrderedDict()
_lock = threading.Lock()
MAX_BYTES = 16 * 1024 * 1024


def clear_prepared_calculations():
    with _lock:
        _values.clear()


def reuse_calculation(function, args, kwargs, ttl=300):
    revision = g.stats_data_revision
    databases = getattr(g, 'stats_source_databases', None)
    table = {'stat_functions': 'games', 'vollis_functions': 'vollis_games',
             'other_functions': 'other_games'}.get(function.__module__)
    if databases and table:
        from stats_snapshot_cache import source_revision
        revisions = g.setdefault('stats_calculation_revisions', {})
        if table not in revisions:
            revisions[table] = source_revision(databases, ('players', table))
        revision = revisions[table]
    key = (revision, function.__module__, function.__name__, repr(args),
           repr(sorted(kwargs.items())), active_doubles_division(), active_location_filter())
    now = time.monotonic()
    with _lock:
        found = _values.get(key)
        if found and found[0] > now:
            _values.move_to_end(key)
            # Only bytes we serialized in this process are decoded. Returning a
            # copy keeps sorting/decorating one response from changing another.
            return pickle.loads(found[1])
    result = function(*args, **kwargs)
    try:
        body = pickle.dumps(result)
    except (TypeError, pickle.PicklingError):
        return result
    if len(body) <= 2 * 1024 * 1024:
        with _lock:
            _values[key] = (now + ttl, body)
            while len(_values) > 128 or sum(len(v[1]) for v in _values.values()) > MAX_BYTES:
                _values.popitem(last=False)
    return result
