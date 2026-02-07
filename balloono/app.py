"""Balloono - Multiplayer Bomberman-style game (standalone Flask app)"""
from flask import Flask, render_template, request, jsonify, make_response
from datetime import datetime, timedelta
import os
import sqlite3
import secrets
import hashlib
import threading
import time
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'balloono-dev-secret-change-in-production')

DATABASE = os.environ.get('DATABASE_URL', '')
if DATABASE and DATABASE.startswith('sqlite:///'):
    DB_PATH = DATABASE.replace('sqlite:///', '')
else:
    DB_PATH = 'balloono.db'

# Game state (in-memory, room-based)
_balloono_rooms = {}
_balloono_lock = threading.Lock()
_ACTIVE_ROOM_SEC = 60
_ROOM_IDLE_DELETE_SEC = 300

GRID_W, GRID_H = 15, 11
CELL = 40


def get_db():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS balloono_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS balloono_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES balloono_users(id)
        )
    ''')
    conn.commit()
    conn.close()


def _balloono_lobby_game(players_list):
    blocks = set()
    for x in range(GRID_W):
        blocks.add((x, 0))
        blocks.add((x, GRID_H - 1))
    for y in range(GRID_H):
        blocks.add((0, y))
        blocks.add((GRID_W - 1, y))
    for x in range(2, GRID_W - 2, 2):
        for y in range(2, GRID_H - 2, 2):
            blocks.add((x, y))
    players_data = []
    for i, p in enumerate(players_list):
        x, y = (1, 1) if i == 0 else (GRID_W - 2, GRID_H - 2)
        players_data.append({
            'id': p['id'], 'user_id': p.get('user_id'), 'username': p['username'],
            'x': x, 'y': y, 'alive': True,
        })
    return {
        'grid_w': GRID_W, 'grid_h': GRID_H, 'cell': CELL,
        'players': players_data,
        'blocks': list(blocks),
    }


def _balloono_token_cookie():
    return request.cookies.get('balloono_token', '')


def _balloono_current_user():
    token = _balloono_token_cookie()
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT u.id, u.username FROM balloono_users u
        JOIN balloono_tokens t ON t.user_id = u.id
        WHERE t.token_hash = ? AND t.expires_at > ?
    ''', (token_hash, datetime.now()))
    row = cur.fetchone()
    conn.close()
    return (row[0], row[1]) if row else None


def _generate_room_code():
    return ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))


@app.route('/')
def index():
    return render_template('balloono.html')


@app.route('/api/balloono/me')
def api_balloono_me():
    user = _balloono_current_user()
    if not user:
        return jsonify({'logged_in': False})
    user_id, username = user
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT wins, losses FROM balloono_users WHERE id = ?', (user_id,))
    row = cur.fetchone()
    conn.close()
    return jsonify({
        'logged_in': True,
        'user_id': user_id,
        'username': username,
        'wins': row[0] if row else 0,
        'losses': row[1] if row else 0,
    })


@app.route('/api/balloono/register', methods=['POST'])
def api_balloono_register():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()[:20]
    password = data.get('password', '')
    if not username or len(username) < 2:
        return jsonify({'error': 'Username must be at least 2 characters'}), 400
    if not password or len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires = datetime.now() + timedelta(days=90)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO balloono_users (username, password_hash) VALUES (?, ?)', (username, pw_hash))
        user_id = cur.lastrowid
        cur.execute('INSERT INTO balloono_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)',
                    (user_id, token_hash, expires))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Username already taken'}), 400
    conn.close()
    resp = make_response(jsonify({'ok': True, 'username': username, 'user_id': user_id}))
    resp.set_cookie('balloono_token', token, max_age=90*24*3600, httponly=True, samesite='Lax')
    return resp


@app.route('/api/balloono/login', methods=['POST'])
def api_balloono_login():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()[:20]
    password = data.get('password', '')
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM balloono_users WHERE username = ? AND password_hash = ?', (username, pw_hash))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Invalid username or password'}), 401
    user_id = row[0]
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires = datetime.now() + timedelta(days=90)
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT INTO balloono_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)',
                (user_id, token_hash, expires))
    conn.commit()
    conn.close()
    resp = make_response(jsonify({'ok': True, 'username': username, 'user_id': user_id}))
    resp.set_cookie('balloono_token', token, max_age=90*24*3600, httponly=True, samesite='Lax')
    return resp


@app.route('/api/balloono/logout', methods=['POST'])
def api_balloono_logout():
    resp = make_response(jsonify({'ok': True}))
    resp.set_cookie('balloono_token', '', max_age=0, httponly=True, samesite='Lax')
    return resp


@app.route('/api/balloono/create_room', methods=['POST'])
def api_balloono_create_room():
    user = _balloono_current_user()
    if not user:
        return jsonify({'error': 'Must be logged in to create a room'}), 401
    user_id, username = user
    with _balloono_lock:
        room_code = _generate_room_code()
        while room_code in _balloono_rooms:
            room_code = _generate_room_code()
        player_id = secrets.token_hex(8)
        now = datetime.now()
        _balloono_rooms[room_code] = {
            'players': [{'id': player_id, 'user_id': user_id, 'username': username, 'ready': False, 'x': 1, 'y': 1}],
            'messages': [{'type': 'system', 'text': f'{username} created the room.'}],
            'game': None,
            'lobby_game': _balloono_lobby_game([{'id': player_id, 'user_id': user_id, 'username': username}]),
            'created': now.isoformat(),
            'last_activity': time.time(),
        }
    return jsonify({
        'room_code': room_code,
        'player_id': player_id,
        'username': username,
    })


@app.route('/api/balloono/leave_room', methods=['POST'])
def api_balloono_leave_room():
    data = request.get_json() or {}
    room_code = (data.get('room_code') or '').strip().upper()[:6]
    player_id = data.get('player_id', '')
    with _balloono_lock:
        if room_code not in _balloono_rooms:
            return jsonify({'ok': True})
        room = _balloono_rooms[room_code]
        room['players'] = [p for p in room['players'] if p['id'] != player_id]
        if len(room['players']) == 0:
            del _balloono_rooms[room_code]
        else:
            if room.get('lobby_game') and room['lobby_game'].get('players'):
                room['lobby_game']['players'] = [p for p in room['lobby_game']['players'] if p['id'] != player_id]
            room['messages'].append({'type': 'system', 'text': 'A player left.'})
            if room.get('game') is not None and 'game_over_message' not in room['game']:
                room['game']['game_over_title'] = 'Game Over'
                room['game']['game_over_message'] = 'A player left. No winner.'
    return jsonify({'ok': True})


@app.route('/api/balloono/rooms')
def api_balloono_list_rooms():
    now_ts = time.time()
    with _balloono_lock:
        to_del = [c for c, r in _balloono_rooms.items()
                  if now_ts - r.get('last_activity', 0) > _ROOM_IDLE_DELETE_SEC]
        for c in to_del:
            del _balloono_rooms[c]
        rooms = []
        for code, room in _balloono_rooms.items():
            if now_ts - room.get('last_activity', 0) > _ACTIVE_ROOM_SEC:
                continue
            if room.get('game') is not None:
                continue
            players = room.get('players', [])
            if len(players) >= 2:
                continue
            host = players[0]['username'] if players else 'Unknown'
            rooms.append({
                'room_code': code,
                'host': host,
                'player_count': len(players),
                'max_players': 2,
            })
    return jsonify({'rooms': rooms})


@app.route('/api/balloono/join_room', methods=['POST'])
def api_balloono_join_room():
    user = _balloono_current_user()
    if not user:
        return jsonify({'error': 'Must be logged in to join a room'}), 401
    user_id, username = user
    data = request.get_json() or {}
    room_code = (data.get('room_code') or '').strip().upper()[:6]
    with _balloono_lock:
        if room_code not in _balloono_rooms:
            return jsonify({'error': 'Room not found'}), 404
        room = _balloono_rooms[room_code]
        if time.time() - room.get('last_activity', 0) > _ACTIVE_ROOM_SEC:
            del _balloono_rooms[room_code]
            return jsonify({'error': 'Room expired'}), 404
        if room['game'] is not None:
            return jsonify({'error': 'Game already in progress'}), 400
        if len(room['players']) >= 2:
            return jsonify({'error': 'Room is full'}), 400
        player_id = secrets.token_hex(8)
        room['players'].append({'id': player_id, 'user_id': user_id, 'username': username, 'ready': False, 'x': GRID_W - 2, 'y': GRID_H - 2})
        room['lobby_game'] = _balloono_lobby_game(room['players'])
        room['messages'].append({'type': 'system', 'text': f'{username} joined the room.'})
        room['last_activity'] = time.time()
    return jsonify({
        'room_code': room_code,
        'player_id': player_id,
        'username': username,
    })


@app.route('/api/balloono/room/<room_code>')
def api_balloono_get_room(room_code):
    room_code = room_code.upper()
    with _balloono_lock:
        if room_code not in _balloono_rooms:
            return jsonify({'error': 'Room not found'}), 404
        room = _balloono_rooms[room_code]
        room['last_activity'] = time.time()
        room = room.copy()
        try:
            conn = get_db()
            cur = conn.cursor()
            out_players = []
            for p in room['players']:
                pl = dict(p)
                uid = p.get('user_id')
                if uid:
                    cur.execute('SELECT wins, losses FROM balloono_users WHERE id = ?', (uid,))
                    row = cur.fetchone()
                    if row:
                        pl['balloono_wins'] = row[0]
                        pl['balloono_losses'] = row[1]
                out_players.append(pl)
            conn.close()
            room['players'] = out_players
        except Exception:
            room['players'] = list(room['players'])
        room['messages'] = list(room['messages'])[-50:]
        if room.get('game') is None:
            blocks = set()
            for x in range(GRID_W):
                blocks.add((x, 0))
                blocks.add((x, GRID_H - 1))
            for y in range(GRID_H):
                blocks.add((0, y))
                blocks.add((GRID_W - 1, y))
            for x in range(2, GRID_W - 2, 2):
                for y in range(2, GRID_H - 2, 2):
                    blocks.add((x, y))
            lobby_players = [{'id': p['id'], 'username': p['username'], 'x': p.get('x', 1), 'y': p.get('y', 1), 'alive': True, 'balloono_wins': p.get('balloono_wins'), 'balloono_losses': p.get('balloono_losses')} for p in room['players']]
            room['lobby_game'] = {'grid_w': GRID_W, 'grid_h': GRID_H, 'cell': 40, 'blocks': [[a, b] for a, b in blocks], 'players': lobby_players}
        else:
            room['lobby_game'] = None
    return jsonify(room)


@app.route('/api/balloono/lobby_action', methods=['POST'])
def api_balloono_lobby_action():
    data = request.get_json() or {}
    room_code = (data.get('room_code') or '').strip().upper()[:6]
    player_id = data.get('player_id', '')
    action = data.get('action')
    if action not in ('up', 'down', 'left', 'right'):
        return jsonify({'error': 'Invalid action'}), 400
    blocks = set()
    for x in range(GRID_W):
        blocks.add((x, 0))
        blocks.add((x, GRID_H - 1))
    for y in range(GRID_H):
        blocks.add((0, y))
        blocks.add((GRID_W - 1, y))
    for x in range(2, GRID_W - 2, 2):
        for y in range(2, GRID_H - 2, 2):
            blocks.add((x, y))
    with _balloono_lock:
        if room_code not in _balloono_rooms:
            return jsonify({'error': 'Room not found'}), 404
        room = _balloono_rooms[room_code]
        if room.get('game') is not None:
            return jsonify({'error': 'Game already started'}), 400
        player = next((p for p in room['players'] if p['id'] == player_id), None)
        if not player:
            return jsonify({'error': 'Player not in room'}), 400
        dx, dy = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}[action]
        nx = player.get('x', 1) + dx
        ny = player.get('y', 1) + dy
        if 1 <= nx < GRID_W - 1 and 1 <= ny < GRID_H - 1 and (nx, ny) not in blocks:
            others_at = [(p.get('x'), p.get('y')) for p in room['players'] if p['id'] != player_id]
            if (nx, ny) not in others_at:
                player['x'], player['y'] = nx, ny
        if room.get('lobby_game') and room['lobby_game'].get('players'):
            lobby_player = next((p for p in room['lobby_game']['players'] if p['id'] == player_id), None)
            if lobby_player:
                lobby_player['x'], lobby_player['y'] = player['x'], player['y']
        room['last_activity'] = time.time()
    return jsonify({'ok': True})


@app.route('/api/balloono/send_message', methods=['POST'])
def api_balloono_send_message():
    data = request.get_json() or {}
    room_code = (data.get('room_code') or '').strip().upper()[:6]
    player_id = data.get('player_id', '')
    text = (data.get('text') or '').strip()[:200]
    if not text:
        return jsonify({'error': 'Empty message'}), 400
    with _balloono_lock:
        if room_code not in _balloono_rooms:
            return jsonify({'error': 'Room not found'}), 404
        room = _balloono_rooms[room_code]
        username = next((p['username'] for p in room['players'] if p['id'] == player_id), 'Unknown')
        room['messages'].append({'type': 'chat', 'username': username, 'text': text})
    return jsonify({'ok': True})


@app.route('/api/balloono/start_game', methods=['POST'])
def api_balloono_start_game():
    data = request.get_json() or {}
    room_code = (data.get('room_code') or '').strip().upper()[:6]
    player_id = data.get('player_id', '')
    with _balloono_lock:
        if room_code not in _balloono_rooms:
            return jsonify({'error': 'Room not found'}), 404
        room = _balloono_rooms[room_code]
        if room['game'] is not None:
            return jsonify({'error': 'Game already in progress'}), 400
        if len(room['players']) < 1:
            return jsonify({'error': 'Need at least 1 player to start'}), 400
        p0 = room['players'][0]
        x0, y0 = p0.get('x', 1), p0.get('y', 1)
        players_data = [
            {'id': p0['id'], 'user_id': p0.get('user_id'), 'username': p0['username'], 'x': x0, 'y': y0, 'alive': True, 'blast_level': 0, 'bombs_level': 0, 'speed_level': 0},
        ]
        if len(room['players']) >= 2:
            p1 = room['players'][1]
            x1, y1 = p1.get('x', GRID_W - 2), p1.get('y', GRID_H - 2)
            players_data.append({'id': p1['id'], 'user_id': p1.get('user_id'), 'username': p1['username'], 'x': x1, 'y': y1, 'alive': True, 'blast_level': 0, 'bombs_level': 0, 'speed_level': 0})
        room['game'] = {
            'grid_w': GRID_W, 'grid_h': GRID_H, 'cell': CELL,
            'players': players_data,
            'bombs': [],
            'explosions': [],
            'powerups': [],
            'walls': [],
            'blocks': [],
            'last_tick': datetime.now().isoformat(),
            'last_powerup_spawn': 0,
            'game_started_at': time.time(),
        }
        blocks = set()
        for x in range(GRID_W):
            blocks.add((x, 0))
            blocks.add((x, GRID_H - 1))
        for y in range(GRID_H):
            blocks.add((0, y))
            blocks.add((GRID_W - 1, y))
        for x in range(2, GRID_W - 2, 2):
            for y in range(2, GRID_H - 2, 2):
                blocks.add((x, y))
        room['game']['blocks'] = list(blocks)
        room['messages'].append({'type': 'system', 'text': 'Game started!'})
    return jsonify({'ok': True, 'game': room['game']})


@app.route('/api/balloono/game_action', methods=['POST'])
def api_balloono_game_action():
    data = request.get_json() or {}
    room_code = (data.get('room_code') or '').strip().upper()[:6]
    player_id = data.get('player_id', '')
    action = data.get('action')
    with _balloono_lock:
        if room_code not in _balloono_rooms:
            return jsonify({'error': 'Room not found'}), 404
        room = _balloono_rooms[room_code]
        if room['game'] is None:
            return jsonify({'error': 'No game in progress'}), 400
        game = room['game']
        player = next((p for p in game['players'] if p['id'] == player_id), None)
        if not player or not player.get('alive', True):
            return jsonify({'error': 'Invalid player'}), 400
        blocks_set = set((b[0], b[1]) for b in game.get('blocks', []))
        bombs_list = game.get('bombs', [])
        powerups_list = game.get('powerups', [])

        if action in ('up', 'down', 'left', 'right'):
            speed = player.get('speed_level', 0)
            cooldown = max(0.04, 0.15 - speed * 0.03)
            last_move = player.get('_last_move_at', 0)
            if time.time() - last_move < cooldown:
                return jsonify({'ok': True})
            player['_last_move_at'] = time.time()
            dx, dy = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}[action]
            nx, ny = player['x'] + dx, player['y'] + dy
            if 1 <= nx < game['grid_w'] - 1 and 1 <= ny < game['grid_h'] - 1:
                if (nx, ny) not in blocks_set and not any(b['x'] == nx and b['y'] == ny for b in bombs_list):
                    other = next((p for p in game['players'] if p['id'] != player_id and p.get('alive')), None)
                    if not (other and other['x'] == nx and other['y'] == ny):
                        player['x'], player['y'] = nx, ny
                        for i, pu in enumerate(powerups_list):
                            if pu['x'] == nx and pu['y'] == ny:
                                powerups_list.pop(i)
                                pu_type = pu.get('type', 'blast')
                                if pu_type == 'blast':
                                    player['blast_level'] = player.get('blast_level', 0) + 1
                                elif pu_type == 'bombs':
                                    player['bombs_level'] = player.get('bombs_level', 0) + 1
                                elif pu_type == 'speed':
                                    player['speed_level'] = player.get('speed_level', 0) + 1
                                break
        elif action == 'bomb':
            placed = sum(1 for b in bombs_list if b.get('owner') == player_id)
            max_bombs = 1 + player.get('bombs_level', 0)
            if placed < max_bombs:
                bomb_range = 2 + player.get('blast_level', 0)
                game.setdefault('bombs', []).append({
                    'x': player['x'], 'y': player['y'], 'owner': player_id,
                    'range': bomb_range, 'placed_at': datetime.now().isoformat(),
                })
    return jsonify({'ok': True})


def _balloono_tick(game):
    blocks_set = set((b[0], b[1]) for b in game.get('blocks', []))
    now = datetime.now()
    now_ts = time.time()
    bombs = game.get('bombs', [])
    explosions = game.get('explosions', [])
    powerups = game.setdefault('powerups', [])

    game_start = game.get('game_started_at', now_ts)
    elapsed = now_ts - game_start
    interval = max(5.0, 10.0 - (elapsed // 45))
    last_spawn = game.get('last_powerup_spawn', 0)
    if now_ts - last_spawn >= interval:
        game['last_powerup_spawn'] = now_ts
        occupied = blocks_set | {(b['x'], b['y']) for b in bombs}
        occupied |= {(p['x'], p['y']) for p in game['players'] if p.get('alive')}
        occupied |= {(pu['x'], pu['y']) for pu in powerups}
        empty = []
        for x in range(1, game['grid_w'] - 1):
            for y in range(1, game['grid_h'] - 1):
                if (x, y) not in occupied:
                    empty.append((x, y))
        if empty:
            x, y = random.choice(empty)
            pu_type = random.choice(['blast', 'bombs', 'speed'])
            powerups.append({'x': x, 'y': y, 'type': pu_type})

    explosions[:] = [e for e in explosions if (now - datetime.fromisoformat(e['at'])).total_seconds() < 0.4]

    TAUNTS = [
        lambda w, l: f'{w} wins! {l} got absolutely destroyed.',
        lambda w, l: f'GG EZ. {l} never stood a chance against {w}.',
        lambda w, l: f'{w} dominates! {l} might as well uninstall.',
        lambda w, l: f'Pathetic. {l} is no match for {w}.',
        lambda w, l: f'{w} crushed it! {l} should stick to single player.',
        lambda w, l: f'Too easy. {l} got owned by {w}.',
        lambda w, l: f'{w} reigns supreme! {l} folded like a cheap lawn chair.',
    ]
    to_explode = [(b, datetime.fromisoformat(b['placed_at'])) for b in list(bombs)]
    queued_for_explosion = set()
    while to_explode:
        b, placed = to_explode.pop(0)
        if (now - placed).total_seconds() < 2.5:
            continue
        if b in bombs:
            bombs.remove(b)
        r = b.get('range', 2)
        cx, cy = b['x'], b['y']
        cells = [(cx, cy)]
        for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            for d in range(1, r + 1):
                nx, ny = cx + dx * d, cy + dy * d
                if (nx, ny) in blocks_set:
                    break
                cells.append((nx, ny))
        for x, y in cells:
            explosions.append({'x': x, 'y': y, 'at': now.isoformat()})
            for p in game['players']:
                if p.get('alive') and p['x'] == x and p['y'] == y:
                    p['alive'] = False
            for b2 in list(bombs):
                b2pos = (b2['x'], b2['y'])
                if b2['x'] == x and b2['y'] == y and b2pos not in queued_for_explosion:
                    queued_for_explosion.add(b2pos)
                    to_explode.append((b2, now - timedelta(seconds=5)))
    alive = [p for p in game['players'] if p.get('alive')]
    if len(alive) == 1 and 'game_over_message' not in game:
        winner = alive[0]
        loser = next((p for p in game['players'] if not p.get('alive')), None)
        w_name, l_name = winner['username'], loser['username'] if loser else ''
        idx = hash(w_name + l_name) % len(TAUNTS)
        game['game_over_title'] = winner['username'] + ' Wins!'
        game['game_over_message'] = TAUNTS[idx](w_name, l_name) if l_name else game['game_over_title']
        try:
            conn = get_db()
            cur = conn.cursor()
            if loser and winner.get('user_id'):
                cur.execute('UPDATE balloono_users SET wins = wins + 1 WHERE id = ?', (winner['user_id'],))
            if loser and loser.get('user_id'):
                cur.execute('UPDATE balloono_users SET losses = losses + 1 WHERE id = ?', (loser['user_id'],))
            conn.commit()
            conn.close()
        except Exception:
            pass
    elif len(alive) == 0 and 'game_over_message' not in game:
        game['game_over_title'] = 'Draw!'
        game['game_over_message'] = 'Everyone exploded. What a mess.'


@app.route('/api/balloono/reset_game', methods=['POST'])
def api_balloono_reset_game():
    data = request.get_json() or {}
    room_code = (data.get('room_code') or '').strip().upper()[:6]
    with _balloono_lock:
        if room_code not in _balloono_rooms:
            return jsonify({'error': 'Room not found'}), 404
        room = _balloono_rooms[room_code]
        room['game'] = None
        room['messages'].append({'type': 'system', 'text': 'Game reset. Ready for a new round!'})
    return jsonify({'ok': True})


@app.route('/api/balloono/game_state/<room_code>')
def api_balloono_game_state(room_code):
    room_code = room_code.upper()
    with _balloono_lock:
        if room_code in _balloono_rooms:
            _balloono_rooms[room_code]['last_activity'] = time.time()
        if room_code not in _balloono_rooms:
            return jsonify({'error': 'Room not found'}), 404
        room = _balloono_rooms[room_code]
        if room['game'] is None:
            return jsonify({'game': None, 'players': room['players']})
        _balloono_tick(room['game'])
        g = room['game'].copy()
        try:
            conn = get_db()
            cur = conn.cursor()
            out_players = []
            for p in g['players']:
                pl = {k: v for k, v in p.items() if not k.startswith('_')}
                uid = p.get('user_id')
                if uid:
                    cur.execute('SELECT wins, losses FROM balloono_users WHERE id = ?', (uid,))
                    row = cur.fetchone()
                    if row:
                        pl['balloono_wins'] = row[0]
                        pl['balloono_losses'] = row[1]
                out_players.append(pl)
            conn.close()
            g['players'] = out_players
        except Exception:
            g['players'] = [{k: v for k, v in p.items() if not k.startswith('_')} for p in g['players']]
        g['bombs'] = list(g.get('bombs', []))
        g['explosions'] = list(g.get('explosions', []))
        g['powerups'] = list(g.get('powerups', []))
        g['messages'] = list(room.get('messages', []))[-50:]
    return jsonify({'game': g})


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=os.environ.get('FLASK_DEBUG', '0') == '1')
