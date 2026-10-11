"""Bounded game browsing; legacy and incremental-sync requests retain their format."""
import re
from flask import request


def game_page(conn, table):
    if table not in {'games', 'vollis_games', 'other_games'}:
        raise ValueError('Unknown game table')
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
    clauses, values = [], []
    year = request.args.get('year', 'All years')
    if year != 'All years' and year:
        clauses.append("strftime('%Y', game_date)=?")
        values.append(year)
    if table == 'other_games' and request.args.get('game_name'):
        clauses.append('game_name=?')
        values.append(request.args['game_name'])
    candidates = [f'{side}{number}' for side in ('winner', 'loser') for number in range(1, 16)]
    candidates += ['winner', 'loser', 'game_name', 'comment', 'comments']
    searchable = [column for column in candidates if column in columns]
    conn.create_function('browse_casefold', 1, lambda value: str(value or '').casefold(), deterministic=True)
    haystack = " || ' ' || ".join(f"COALESCE({c}, '')" for c in searchable) or "''"
    for token in re.split(r'[\s,]+', request.args.get('q', '').strip().casefold()):
        if token:
            clauses.append(f'instr(browse_casefold({haystack}), ?) > 0')
            values.append(token)
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    limit = min(100, max(1, request.args.get('limit', 50, type=int)))
    offset = max(0, request.args.get('offset', 0, type=int))
    total = conn.execute(f'SELECT COUNT(*) FROM {table}' + where, values).fetchone()[0]
    rows = conn.execute(f'SELECT * FROM {table}' + where + ' ORDER BY game_date DESC, id DESC LIMIT ? OFFSET ?',
                        values + [limit, offset]).fetchall()
    return rows, dict(total=total, next_offset=offset + len(rows) if offset + len(rows) < total else None)
