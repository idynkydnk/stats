"""Durable mobile write receipts, committed atomically with each new game."""
from contextlib import closing
from functools import wraps
import hashlib
import json
import sqlite3
import uuid

from flask import g, has_request_context, jsonify, make_response, request, session
from private_accounts import connect_data, data_path


class ReceiptConflict(ValueError):
    pass


def ensure_receipts(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS mobile_game_receipts (
        owner TEXT NOT NULL COLLATE NOCASE, client_id TEXT NOT NULL,
        kind TEXT NOT NULL, payload_hash TEXT NOT NULL, game_id INTEGER NOT NULL,
        PRIMARY KEY(owner, client_id))''')


def _lookup(conn, owner, client_id):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='mobile_game_receipts'").fetchone():
        return None
    return conn.execute('SELECT kind, payload_hash, game_id FROM mobile_game_receipts WHERE owner=? AND client_id=?',
                        (owner, client_id)).fetchone()


def commit_insert(conn, kind, insert):
    """Schema preparation may precede this, but receipt and game share one commit.

    BEGIN IMMEDIATE also serializes simultaneous retries in different workers.
    Receipts survive game deletion: a delayed retry cannot resurrect a game.
    """
    context = getattr(g, 'mobile_game_write', None) if has_request_context() else None
    if context is None:
        game_id = insert()
        conn.commit()
        return game_id
    owner, client_id, expected_kind, payload_hash = context
    if kind != expected_kind:
        raise ReceiptConflict('Game type does not match the saved request.')
    conn.commit()  # Existing schema/format setup is independent of the game write.
    conn.execute('BEGIN IMMEDIATE')
    try:
        ensure_receipts(conn)
        previous = _lookup(conn, owner, client_id)
        if previous:
            if previous[:2] != (kind, payload_hash):
                raise ReceiptConflict('This saved game ID was already used for different game details.')
            game_id = previous[2]
        else:
            game_id = insert()
            conn.execute('INSERT INTO mobile_game_receipts VALUES (?, ?, ?, ?, ?)',
                         (owner, client_id, kind, payload_hash, game_id))
        conn.commit()
        g.mobile_game_result = game_id
        return game_id
    except BaseException:
        conn.rollback()
        raise


def idempotent_game(kind):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            payload = request.get_json(silent=True) or {}
            client_id = payload.get('client_game_id')
            if client_id is None:
                return view(*args, **kwargs)  # Website and older clients.
            try:
                client_id = str(uuid.UUID(client_id))
            except (ValueError, TypeError, AttributeError):
                return jsonify(error='client_game_id must be a UUID.'), 400
            owner = session.get('username')
            if not owner:
                return jsonify(error='Authentication required'), 401
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            import stats as S
            with closing(connect_data(S._stats_db_path())) as conn:
                previous = _lookup(conn, owner, client_id)
            if previous:
                if previous[:2] != (kind, digest):
                    return jsonify(error='This saved game ID was already used for different game details.'), 409
                return jsonify(id=previous[2], client_game_id=client_id, synced=True), 200
            g.mobile_game_write = (owner, client_id, kind, digest)
            try:
                response = make_response(view(*args, **kwargs))
            except ReceiptConflict as error:
                return jsonify(error=str(error)), 409
            finally:
                g.pop('mobile_game_write', None)
            game_id = g.pop('mobile_game_result', None)
            if 200 <= response.status_code < 300 and game_id is not None:
                return jsonify(id=game_id, client_game_id=client_id, synced=True), 201
            return response
        return wrapped
    return decorate


def local_game_snapshot(view):
    """Tell the app exactly which local saves a stats/games snapshot includes.

    Selected-source views contain receipts copied in the same read transaction
    as their owned games. For live databases reject a racing read instead of
    returning mismatched totals and receipts.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.headers.get('X-Stats-Local-Snapshot') != '1':
            return view(*args, **kwargs)
        import stats as S
        from stats_response_cache import database_revisions
        path = data_path(S._stats_db_path())
        before = database_revisions([path], fresh=True)
        with closing(sqlite3.connect(path)) as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='mobile_game_receipts'").fetchone()
            ids = [row[0] for row in conn.execute(
                'SELECT client_id FROM mobile_game_receipts WHERE owner=? ORDER BY client_id',
                (session.get('username') or '',))] if exists else []
        response = make_response(view(*args, **kwargs))
        if before != database_revisions([path], fresh=True):
            return jsonify(error='Games changed while loading. Please retry.'), 503
        if response.status_code == 200 and response.is_json:
            body = response.get_json()
            body['synced_local_game_ids'] = ids
            response.set_data(json.dumps(body))
            response.headers['Cache-Control'] = 'no-store'
        return response
    return wrapped
