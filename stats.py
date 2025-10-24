from flask import Flask, render_template, request, url_for, flash, redirect, session, jsonify, make_response
from database_functions import *
from stat_functions import *
from datetime import datetime, date, timedelta
from vollis_functions import *
from one_v_one_functions import *
from other_functions import *
import os
import subprocess
import sqlite3
import secrets
import hashlib

app = Flask(__name__)
app.config['SECRET_KEY'] = 'b83880e869f054bfc465a6f46125ac715e7286ed25e88537'

# User authentication - you can add more users here
USERS = {
    'kyle': 'stats2025',
    'aaron': 'aaron2025',
    'dan': 'dan2025',
    'ryan': 'ryan2025',
    'arbel': 'arbel2025',
    'mark': 'mark2025'
}

def init_notifications_db():
    """Initialize the notifications table"""
    conn = sqlite3.connect('stats.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            read_status INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def init_auth_tokens_db():
    """Initialize the auth_tokens table for remember me functionality"""
    conn = sqlite3.connect('stats.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS auth_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def generate_auth_token():
    """Generate a secure random token"""
    return secrets.token_urlsafe(32)

def hash_token(token):
    """Hash a token for secure storage"""
    return hashlib.sha256(token.encode()).hexdigest()

def create_auth_token(username):
    """Create a new authentication token for a user"""
    token = generate_auth_token()
    token_hash = hash_token(token)
    expires_at = datetime.now() + timedelta(days=30)  # Token expires in 30 days
    
    conn = sqlite3.connect('stats.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO auth_tokens (username, token_hash, expires_at)
        VALUES (?, ?, ?)
    ''', (username, token_hash, expires_at))
    conn.commit()
    conn.close()
    
    return token

def validate_auth_token(token):
    """Validate an authentication token and return username if valid"""
    if not token:
        return None
    
    token_hash = hash_token(token)
    conn = sqlite3.connect('stats.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT username FROM auth_tokens 
        WHERE token_hash = ? AND expires_at > ?
    ''', (token_hash, datetime.now()))
    
    result = cur.fetchone()
    conn.close()
    
    return result[0] if result else None

def revoke_auth_token(token):
    """Revoke a specific authentication token"""
    if not token:
        return
    
    token_hash = hash_token(token)
    conn = sqlite3.connect('stats.db')
    cur = conn.cursor()
    cur.execute('DELETE FROM auth_tokens WHERE token_hash = ?', (token_hash,))
    conn.commit()
    conn.close()

def revoke_all_user_tokens(username):
    """Revoke all authentication tokens for a user"""
    conn = sqlite3.connect('stats.db')
    cur = conn.cursor()
    cur.execute('DELETE FROM auth_tokens WHERE username = ?', (username,))
    conn.commit()
    conn.close()

def cleanup_expired_tokens():
    """Remove expired authentication tokens"""
    conn = sqlite3.connect('stats.db')
    cur = conn.cursor()
    cur.execute('DELETE FROM auth_tokens WHERE expires_at <= ?', (datetime.now(),))
    conn.commit()
    conn.close()

def log_user_action(user, action, details=None):
    """Log a user action for notification purposes"""
    if user != 'kyle':  # Only log actions by non-Kyle users
        conn = sqlite3.connect('stats.db')
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO notifications (user, action, details)
            VALUES (?, ?, ?)
        ''', (user, action, details))
        conn.commit()
        conn.close()

def get_unread_notifications():
    """Get all unread notifications"""
    conn = sqlite3.connect('stats.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT id, user, action, details, timestamp
        FROM notifications 
        WHERE read_status = 0
        ORDER BY timestamp DESC
    ''')
    notifications = cur.fetchall()
    conn.close()
    return notifications

def mark_notifications_read(notification_ids):
    """Mark specific notifications as read"""
    if notification_ids:
        conn = sqlite3.connect('stats.db')
        cur = conn.cursor()
        placeholders = ','.join('?' * len(notification_ids))
        cur.execute(f'''
            UPDATE notifications 
            SET read_status = 1 
            WHERE id IN ({placeholders})
        ''', notification_ids)
        conn.commit()
        conn.close()

# Initialize database tables
init_notifications_db()
init_auth_tokens_db()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in via session
        if session.get('logged_in'):
            return f(*args, **kwargs)
        
        # Check if user is logged in via remember me cookie
        auth_token = request.cookies.get('remember_token')
        if auth_token:
            username = validate_auth_token(auth_token)
            if username:
                # Auto-login the user
                session['logged_in'] = True
                session['username'] = username
                flash(f'Welcome back, {username}!', 'success')
                return f(*args, **kwargs)
            else:
                # Invalid or expired token, clear the cookie
                response = make_response(redirect(url_for('login')))
                response.set_cookie('remember_token', '', expires=0)
                flash('Please log in to access this page.', 'error')
                return response
        
        flash('Please log in to access this page.', 'error')
        return redirect(url_for('login'))
    return decorated_function

@app.route('/')
def index():
    from datetime import datetime
    
    games = year_games(str(date.today().year))
    if games:
        if len(games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(games) // 30
    else:
        minimum_games = 1
    all_years = grab_all_years()
    t_stats = todays_stats()
    games = todays_games()
    stats = stats_per_year(str(date.today().year), minimum_games)
    rare_stats = rare_stats_per_year(str(date.today().year), minimum_games)
    
    # Add navigation data for today
    today = datetime.now().strftime('%Y-%m-%d')
    previous_date = get_previous_date(today)
    next_date = get_next_date(today)
    has_previous = has_games_on_date(previous_date)
    has_next = has_games_on_date(next_date)
    
    return render_template('stats.html', todays_stats=t_stats, stats=stats, games=games, rare_stats=rare_stats, 
        minimum_games=minimum_games, year=str(date.today().year), all_years=all_years,
        current_date=today, display_date="Today", previous_date=previous_date, next_date=next_date,
        has_previous=has_previous, has_next=has_next)

@app.route('/stats/<year>/')
def stats(year):
    games = year_games(year)
    if games:
        if len(games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(games) // 30
    else:
        minimum_games = 1
    all_years = grab_all_years()
    stats = stats_per_year(year, minimum_games)
    rare_stats = rare_stats_per_year(year, minimum_games)
    return render_template('stats.html', all_years=all_years, stats=stats, rare_stats=rare_stats, minimum_games=minimum_games, year=year)

@app.route('/stats/<year>/<date>/')
def stats_by_date(year, date):
    """Stats page for a specific date with navigation"""
    from datetime import datetime
    
    # Get stats for the specific date
    date_stats, date_games = specific_date_stats(date)
    
    # Get year stats
    games = year_games(year)
    if games:
        if len(games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(games) // 30
    else:
        minimum_games = 1
    all_years = grab_all_years()
    stats = stats_per_year(year, minimum_games)
    rare_stats = rare_stats_per_year(year, minimum_games)
    
    # Navigation dates
    previous_date = get_previous_date(date)
    next_date = get_next_date(date)
    
    # Check if there are games on adjacent dates
    has_previous = has_games_on_date(previous_date)
    has_next = has_games_on_date(next_date)
    
    # Format date for display
    try:
        display_date = datetime.strptime(date, '%Y-%m-%d').strftime('%m/%d/%y')
    except:
        display_date = date
    
    return render_template('stats.html', 
                         all_years=all_years, 
                         stats=stats, 
                         rare_stats=rare_stats, 
                         minimum_games=minimum_games, 
                         year=year,
                         todays_stats=date_stats,
                         games=date_games,
                         current_date=date,
                         display_date=display_date,
                         previous_date=previous_date,
                         next_date=next_date,
                         has_previous=has_previous,
                         has_next=has_next)

@app.route('/top_teams/')
def top_teams():
    all_years = grab_all_years()
    games = year_games(str(date.today().year))
    year = str(date.today().year)
    if games:
        if len(games) < 70:
            minimum_games = 1
        else:
            minimum_games = len(games) // 70
    else:
        minimum_games = 1
    stats = team_stats_per_year(year, minimum_games, games)
    return render_template('top_teams.html', all_years=all_years, stats=stats, minimum_games=minimum_games, year=year)

@app.route('/top_teams/<year>/')
def top_teams_by_year(year):
    games = year_games(year)
    if games:
        if len(games) < 70:
            minimum_games = 1
        else:
            minimum_games = len(games) // 70
    else:
        minimum_games = 1
    all_years = grab_all_years()
    stats = team_stats_per_year(year, minimum_games, games)
    return render_template('top_teams.html', all_years=all_years, stats=stats, minimum_games=minimum_games, year=year)

@app.route('/player/<year>/<name>')
def player_stats(year, name):
    games = games_from_player_by_year(year, name)
    if games:
        if len(games) < 40:
            minimum_games = 1
        else:
            minimum_games = len(games) // 40
    else:
        minimum_games = 1
    all_years = all_years_player(name)
    games = games_from_player_by_year(year, name)
    stats = total_stats(games, name)
    partner_stats = partner_stats_by_year(name, games, minimum_games)
    opponent_stats = opponent_stats_by_year(name, games, minimum_games)
    rare_partner_stats = rare_partner_stats_by_year(name, games, minimum_games)
    rare_opponent_stats = rare_opponent_stats_by_year(name, games, minimum_games)
    return render_template('player.html', opponent_stats=opponent_stats, rare_opponent_stats=rare_opponent_stats,
        partner_stats=partner_stats, rare_partner_stats=rare_partner_stats, 
        year=year, player=name, minimum_games=minimum_games, all_years=all_years, stats=stats, games=games)

@app.route('/games/')
def games():
    all_years = grab_all_years()
    games = year_games(str(date.today().year))
    year = str(date.today().year)
    return render_template('games.html', games=games, year=year, all_years=all_years)

@app.route('/games/<year>')
def games_by_year(year):
    all_years = grab_all_years()
    games = year_games(year)
    return render_template('games.html', games=games, year=year, all_years=all_years)

@app.route('/add_game/', methods=('GET', 'POST'))
@login_required
def add_game():
    games = year_games(str(date.today().year))
    if games:
        if len(games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(games) // 30
    else:
        minimum_games = 1
    stats = stats_per_year(str(date.today().year), minimum_games)
    rare_stats = rare_stats_per_year(str(date.today().year), minimum_games)

    w_scores = winners_scores()
    l_scores = losers_scores()
    games = year_games('All years')
    players = all_players(games)
    t_stats = todays_stats()
    games = todays_games()
    year = str(date.today().year)
    if request.method == 'POST':
        winner1 = request.form['winner1']
        winner2 = request.form['winner2']
        loser1 = request.form['loser1']
        loser2 = request.form['loser2']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        elif int(winner_score) <= int(loser_score):
            flash('Winner score is less than loser score!')
        elif winner1 == winner2 or winner1 == loser1 or winner1 == loser2 or winner2 == loser1 or winner2 == loser2 or loser1 == loser2:
            flash('Two names are the same!')
        else:
            add_game_stats([datetime.now(), winner1.strip(), winner2.strip(), loser1.strip(), loser2.strip(), 
                winner_score, loser_score, datetime.now()])
            
            # Log the action for notifications
            user = session.get('username', 'unknown')
            details = f"Winners: {winner1.strip()}, {winner2.strip()}; Losers: {loser1.strip()}, {loser2.strip()}; Score: {winner_score}-{loser_score}"
            log_user_action(user, 'Added doubles game', details)
            
            return redirect(url_for('add_game'))

    return render_template('add_game.html', todays_stats=t_stats, games=games, players=players, 
        w_scores=w_scores, l_scores=l_scores, year=year, stats=stats, rare_stats=rare_stats, minimum_games=minimum_games)


@app.route('/edit_games/')
def edit_games():
    all_years = grab_all_years()
    games = year_games(str(date.today().year))
    return render_template('edit_games.html', games=games, year=str(date.today().year), all_years=all_years)

@app.route('/edit_games/<year>')
def edit_games_by_year(year):
    all_years = grab_all_years()
    games = year_games(year)
    return render_template('edit_games.html', games=games, year=year, all_years=all_years)


@app.route('/edit/<int:id>/',methods = ['GET','POST'])
@login_required
def update(id):
    game_id = id
    x = find_game(id)
    game = [x[0][0], x[0][1], x[0][2], x[0][3], x[0][4], x[0][5], x[0][6], x[0][7], x[0][8]]
    w_scores = winners_scores()
    l_scores = losers_scores()
    games = year_games(str(date.today().year))
    players = all_players(games)
    if request.method == 'POST':
        game_date = request.form['game_date']
        game_time = request.form['game_time']
        winner1 = request.form['winner1']
        winner2 = request.form['winner2']
        loser1 = request.form['loser1']
        loser2 = request.form['loser2']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not game_date or not game_time or not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            # Combine date and time into the format expected by the database
            combined_datetime = f"{game_date} {game_time}:00"
            update_game(game_id, combined_datetime, winner1, winner2, winner_score, loser1, loser2, loser_score, datetime.now(), game_id)
            
            # Log the action for notifications
            user = session.get('username', 'unknown')
            details = f"Game ID {game_id}: {winner1}/{winner2} vs {loser1}/{loser2} ({winner_score}-{loser_score})"
            log_user_action(user, 'Edited doubles game', details)
            
            # Check if user came from add game page
            from_add_game = request.form.get('from_add_game')
            if from_add_game == 'true':
                return redirect(url_for('add_game'))
            else:
                return redirect(url_for('edit_games'))
 
    return render_template('edit_game.html', game=game, players=players, 
        w_scores=w_scores, l_scores=l_scores, year=str(date.today().year),
        from_add_game=request.args.get('from_add_game'))

@app.route('/player_trends/')
def player_trends():
    """Player trends page showing win/loss statistics for doubles games"""
    all_players = get_all_players_for_trends()
    player_name = request.args.get('player_name')
    
    if player_name:
        trends_data = get_player_trends_data(player_name)
        return render_template('player_trends.html', 
                             player_name=player_name,
                             all_players=all_players,
                             **trends_data)
    else:
        return render_template('player_trends.html', 
                             player_name=None,
                             all_players=all_players)


@app.route('/delete/<int:id>/',methods = ['GET','POST'])
@login_required
def delete_game(id):
    game_id = id
    game = find_game(id)
    if request.method == 'POST':
        # Log the action for notifications before deleting
        if game and len(game) > 0 and len(game[0]) >= 8:
            user = session.get('username', 'unknown')
            game_data = game[0]  # Get the first (and only) row
            details = f"Game ID {game_id}: {game_data[2]}/{game_data[3]} vs {game_data[5]}/{game_data[6]} ({game_data[4]}-{game_data[7]})"
            log_user_action(user, 'Deleted doubles game', details)
        
        remove_game(game_id)
        return redirect(url_for('edit_games'))
 
    return render_template('delete_game.html', game=game)

@app.route('/advanced_stats/')
def advanced_stats():
    return render_template('advanced_stats.html')



## VOLLIS ROUTES



@app.route('/vollis_stats/<year>/')
def vollis_stats(year):
    all_years = all_vollis_years()
    minimum_games = 2
    stats = vollis_stats_per_year(year, minimum_games)
    return render_template('vollis_stats.html', stats=stats,
        all_years=all_years, minimum_games=minimum_games, year=year)

@app.route('/vollis_stats/')
def vollis():
    all_years = all_vollis_years()
    year = str(date.today().year)
    t_stats = todays_vollis_stats()
    games = todays_vollis_games()
    minimum_games = 0
    stats = vollis_stats_per_year(year, minimum_games)
    return render_template('vollis_stats.html', stats=stats, todays_stats=t_stats, games=games,
        all_years=all_years, minimum_games=minimum_games, year=year)


@app.route('/add_vollis_game/', methods=('GET', 'POST'))
@login_required
def add_vollis_game():
    games = vollis_year_games('All years')
    players = all_vollis_players(games)
    stats = todays_vollis_stats()
    games = todays_vollis_games()
    year = str(date.today().year)
    winning_scores = vollis_winning_scores()
    losing_scores = vollis_losing_scores()
    if request.method == 'POST':
        winner = request.form['winner']
        loser = request.form['loser']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not winner or not loser or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            add_vollis_stats([datetime.now(), winner, loser, winner_score, loser_score, datetime.now()])
            
            # Log the action for notifications
            user = session.get('username', 'unknown')
            details = f"Winner: {winner}; Loser: {loser}; Score: {winner_score}-{loser_score}"
            log_user_action(user, 'Added vollis game', details)
            
            return redirect(url_for('add_vollis_game'))

    return render_template('add_vollis_game.html', year=year, players=players, todays_stats=stats, games=games,
        winning_scores=winning_scores, losing_scores=losing_scores)


@app.route('/edit_vollis_games/')
def edit_vollis_games():
    all_years = all_vollis_years()
    games = vollis_year_games(str(date.today().year))
    return render_template('edit_vollis_games.html', games=games, all_years=all_years, year=str(date.today().year))

@app.route('/edit_past_year_vollis_games/<year>')
def edit_vollis_games_by_year(year):
    all_years = all_vollis_years()
    games = vollis_year_games(year)
    return render_template('edit_vollis_games.html', all_years=all_years, games=games, year=year)

@app.route('/vollis_games/')
def vollis_games():
    all_years = all_vollis_years()
    games = vollis_year_games(str(date.today().year))
    return render_template('vollis_games.html', games=games, all_years=all_years, year=str(date.today().year))

@app.route('/vollis_games/<year>')
def vollis_games_by_year(year):
    all_years = all_vollis_years()
    games = vollis_year_games(year)
    return render_template('vollis_games.html', all_years=all_years, games=games, year=year)


@app.route('/edit_vollis_game/<int:id>/',methods = ['GET','POST'])
def update_vollis_game(id):
    game_id = id
    x = find_vollis_game(game_id)
    game = [x[0][0], x[0][1], x[0][2], x[0][3], x[0][4], x[0][5], x[0][6]]
    games = vollis_year_games(str(date.today().year))
    players = all_vollis_players(games)
    if request.method == 'POST':
        winner = request.form['winner']
        loser = request.form['loser']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not winner or not loser or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            edit_vollis_game(game_id, game[1], winner, winner_score, loser, loser_score, datetime.now(), game_id)
            
            # Log the action for notifications
            user = session.get('username', 'unknown')
            details = f"Game ID {game_id}: {winner} vs {loser} ({winner_score}-{loser_score})"
            log_user_action(user, 'Edited vollis game', details)
            
            return redirect(url_for('edit_vollis_games'))
 
    return render_template('edit_vollis_game.html', game=game, players=players, year=str(date.today().year))


@app.route('/delete_vollis_game/<int:id>/',methods = ['GET','POST'])
def delete_vollis_game(id):
    game_id = id
    game = find_vollis_game(id)
    if request.method == 'POST':
        # Log the action for notifications before deleting
        user = session.get('username', 'unknown')
        details = f"Game ID {game_id}: {game[0][2]} vs {game[0][3]} ({game[0][4]}-{game[0][5]})"
        log_user_action(user, 'Deleted vollis game', details)
        
        remove_vollis_game(game_id)
        return redirect(url_for('edit_vollis_games'))
 
    return render_template('delete_vollis_game.html', game=game)

@app.route('/vollis_player/<year>/<name>')
def vollis_player_stats(year, name):
    all_years = all_years_vollis_player(name)
    games = games_from_vollis_player_by_year(year, name)
    stats = total_vollis_stats(name, games)
    opponent_stats = vollis_opponent_stats_by_year(name, games)
    return render_template('vollis_player.html', opponent_stats=opponent_stats, 
        year=year, player=name, all_years=all_years, stats=stats)



## ONE V ONE ROUTES


@app.route('/one_v_one_stats/<year>/')
def one_v_one_stats(year):
    all_years = all_one_v_one_years()
    minimum_games = 1
    stats = one_v_one_stats_per_year(year, minimum_games)
    return render_template('one_v_one_stats.html', stats=stats,
        all_years=all_years, minimum_games=minimum_games, year=year)

@app.route('/one_v_one_stats/')
def one_v_one():
    all_years = all_one_v_one_years()
    year = str(date.today().year)
    t_stats = todays_one_v_one_stats()
    games = todays_one_v_one_games()
    minimum_games = 0
    stats = one_v_one_stats_per_year(year, minimum_games)
    return render_template('one_v_one_stats.html', stats=stats, todays_stats=t_stats, games=games,
        all_years=all_years, minimum_games=minimum_games, year=year)


@app.route('/add_one_v_one_game/', methods=('GET', 'POST'))
@login_required
def add_one_v_one_game():
    games = one_v_one_year_games('All years')
    game_types = one_v_one_game_types(games)
    game_names = one_v_one_game_names(games)
    players = all_one_v_one_players(games)
    stats = todays_one_v_one_stats()
    year = str(date.today().year)
    winning_scores = one_v_one_winning_scores()
    losing_scores = one_v_one_losing_scores()
    if request.method == 'POST':
        game_type = request.form['game_type']
        game_name = request.form['game_name']
        winner = request.form['winner']
        loser = request.form['loser']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not game_type or not game_name or not winner or not loser or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            add_one_v_one_stats([datetime.now(), game_type, game_name, winner, loser, winner_score, loser_score, datetime.now()])
            
            # Log the action for notifications
            user = session.get('username', 'unknown')
            details = f"Game: {game_type} - {game_name}; Winner: {winner}; Loser: {loser}; Score: {winner_score}-{loser_score}"
            log_user_action(user, 'Added 1v1 game', details)
            
            return redirect(url_for('add_one_v_one_game'))

    return render_template('add_one_v_one_game.html', year=year, players=players, game_types=game_types, game_names=game_names, todays_stats=stats, games=games,
        winning_scores=winning_scores, losing_scores=losing_scores)


@app.route('/edit_one_v_one_games/')
def edit_one_v_one_games():
    all_years = all_one_v_one_years()
    games = one_v_one_year_games(str(date.today().year))
    return render_template('edit_one_v_one_games.html', games=games, all_years=all_years, year=str(date.today().year))

@app.route('/edit_past_year_one_v_one_games/<year>')
def edit_one_v_one_games_by_year(year):
    all_years = all_one_v_one_years()
    games = one_v_one_year_games(year)
    return render_template('edit_one_v_one_games.html', all_years=all_years, games=games, year=year)

@app.route('/one_v_one_games/')
def one_v_one_games():
    all_years = all_one_v_one_years()
    games = one_v_one_year_games(str(date.today().year))
    all_games = one_v_one_year_games('All years')
    game_types = one_v_one_game_types(all_games)
    return render_template('one_v_one_games.html', games=games, all_years=all_years, year=str(date.today().year), game_types=game_types)

@app.route('/one_v_one_games/<year>')
def one_v_one_games_by_year(year):
    all_years = all_one_v_one_years()
    games = one_v_one_year_games(year)
    all_games = one_v_one_year_games('All years')
    game_types = one_v_one_game_types(all_games)
    return render_template('one_v_one_games.html', all_years=all_years, games=games, year=year, game_types=game_types)

@app.route('/one_v_one_games/<year>/<game_type>')
def one_v_one_games_by_year_and_type(year, game_type):
    all_years = all_one_v_one_years()
    games = one_v_one_year_and_game_type_games(year, game_type)
    all_games = one_v_one_year_games('All years')
    game_types = one_v_one_game_types(all_games)
    return render_template('one_v_one_games.html', all_years=all_years, games=games, year=year, game_types=game_types, selected_game_type=game_type)

@app.route('/one_v_one_games_by_type/<game_type>')
def one_v_one_games_by_type(game_type):
    all_years = all_one_v_one_years()
    games = one_v_one_game_type_games(game_type)
    all_games = one_v_one_year_games('All years')
    game_types = one_v_one_game_types(all_games)
    return render_template('one_v_one_games.html', all_years=all_years, games=games, year='All years', game_types=game_types, selected_game_type=game_type)


@app.route('/edit_one_v_one_game/<int:id>/',methods = ['GET','POST'])
def update_one_v_one_game(id):
    game_id = id
    x = find_one_v_one_game(game_id)
    game = [x[0][0], x[0][1], x[0][2], x[0][3], x[0][4], x[0][5], x[0][6], x[0][7], x[0][8]]
    games = one_v_one_year_games(str(date.today().year))
    players = all_one_v_one_players(games)
    if request.method == 'POST':
        winner = request.form['winner']
        loser = request.form['loser']
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not winner or not loser or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            edit_one_v_one_game(game_id, game[1], game[2], game[3], winner, winner_score, loser, loser_score, datetime.now(), game_id)
            
            # Log the action for notifications
            user = session.get('username', 'unknown')
            details = f"Game ID {game_id}: {winner} vs {loser} ({winner_score}-{loser_score})"
            log_user_action(user, 'Edited 1v1 game', details)
            
            return redirect(url_for('edit_one_v_one_games'))
 
    return render_template('edit_one_v_one_game.html', game=game, players=players, year=str(date.today().year))


@app.route('/delete_one_v_one_game/<int:id>/',methods = ['GET','POST'])
def delete_one_v_one_game(id):
    game_id = id
    game = find_one_v_one_game(id)
    if request.method == 'POST':
        # Log the action for notifications before deleting
        user = session.get('username', 'unknown')
        details = f"Game ID {game_id}: {game[0][2]} vs {game[0][3]} ({game[0][4]}-{game[0][5]})"
        log_user_action(user, 'Deleted 1v1 game', details)
        
        remove_one_v_one_game(game_id)
        return redirect(url_for('edit_one_v_one_games'))
 
    return render_template('delete_one_v_one_game.html', game=game)

@app.route('/one_v_one_player/<year>/<name>')
def one_v_one_player_stats(year, name):
    all_years = all_years_one_v_one_player(name)
    games = games_from_one_v_one_player_by_year(year, name)
    stats = total_one_v_one_stats(name, games)
    opponent_stats = one_v_one_opponent_stats_by_year(name, games)
    return render_template('one_v_one_player.html', opponent_stats=opponent_stats, 
        year=year, player=name, all_years=all_years, stats=stats)



@app.route('/single_game_stats/<game_name>/')
def single_game_stats(game_name):
    all_years = single_game_years(game_name)
    year = str(date.today().year)
    games = single_game_games(year, game_name)
    minimum_games = 0
    stats = total_single_game_stats(games)
    return render_template('single_game_stats.html', stats=stats, game_name=game_name,
        all_years=all_years, minimum_games=minimum_games, year=year)

@app.route('/single_game_stats/<game_name>/<year>/')
def single_game_stats_with_year(game_name, year):
    all_years = single_game_years(game_name)
    games = single_game_games(year, game_name)
    minimum_games = 0
    stats = total_single_game_stats(games)
    return render_template('single_game_stats.html', stats=stats, game_name=game_name,
        all_years=all_years, minimum_games=minimum_games, year=year)






## OTHER ROUTES




@app.route('/other_stats/<year>/')
def other_stats(year):
    all_years = all_other_years()
    minimum_games = 1
    stats = other_stats_per_year(year, minimum_games)
    return render_template('other_stats.html', stats=stats,
        all_years=all_years, minimum_games=minimum_games, year=year)

@app.route('/other_stats/')
def other():
    all_years = all_other_years()
    year = str(date.today().year)
    t_stats = todays_other_stats()
    games = todays_other_games()
    minimum_games = 0
    stats = other_stats_per_year(year, minimum_games)
    return render_template('other_stats.html', stats=stats, todays_stats=t_stats, games=games,
        all_years=all_years, minimum_games=minimum_games, year=year)


@app.route('/add_other_game/', methods=('GET', 'POST'))
@login_required
def add_other_game():
    from other_functions import convert_other_ampm, all_combined_players
    games_raw = other_year_games_raw('All years')
    games = convert_other_ampm(games_raw)
    
    # Get helper data using the old format
    games_dict = other_year_games('All years')
    game_types = other_game_types(games_dict)
    game_names = other_game_names(games_dict)
    players = all_combined_players()
    stats = todays_other_stats()
    year = str(date.today().year)
    winning_scores = other_winning_scores()
    losing_scores = other_losing_scores()
    if request.method == 'POST':
        game_type = request.form.get('game_type', '')
        game_name = request.form.get('game_name', '')
        winner1 = request.form.get('winner1', '')
        winner2 = request.form.get('winner2', '')
        winner3 = request.form.get('winner3', '')
        winner4 = request.form.get('winner4', '')
        winner5 = request.form.get('winner5', '')
        winner6 = request.form.get('winner6', '')
        loser1 = request.form.get('loser1', '')
        loser2 = request.form.get('loser2', '')
        loser3 = request.form.get('loser3', '')
        loser4 = request.form.get('loser4', '')
        loser5 = request.form.get('loser5', '')
        loser6 = request.form.get('loser6', '')
        winner_score = request.form.get('winner_score', '')
        loser_score = request.form.get('loser_score', '')
        comment = request.form.get('comment', '')

        if not game_type or not game_name or not winner1 or not loser1:
            flash('Some fields missing!')
        else:
            add_other_stats(datetime.now(), game_type, game_name, winner1, winner2, winner3, winner4, winner5, winner6, 
                            winner_score, loser1, loser2, loser3, loser4, loser5, loser6, loser_score, comment, datetime.now())
            
            # Log the action for notifications
            user = session.get('username', 'unknown')
            winners = [winner1, winner2, winner3, winner4, winner5, winner6]
            losers = [loser1, loser2, loser3, loser4, loser5, loser6]
            winners_str = ', '.join([w for w in winners if w])
            losers_str = ', '.join([l for l in losers if l])
            details = f"Game: {game_type} - {game_name}; Winners: {winners_str}; Losers: {losers_str}; Score: {winner_score}-{loser_score}"
            log_user_action(user, 'Added other game', details)
            
            return redirect(url_for('add_other_game'))

    return render_template('add_other_game.html', year=year, players=players, game_types=game_types, game_names=game_names, todays_stats=stats, games=games,
        winning_scores=winning_scores, losing_scores=losing_scores)


@app.route('/edit_other_games/')
def edit_other_games():
    all_years = all_other_years()
    games = other_year_games(str(date.today().year))
    return render_template('edit_other_games.html', games=games, all_years=all_years, year=str(date.today().year))

@app.route('/edit_past_year_other_games/<year>')
def edit_other_games_by_year(year):
    all_years = all_other_years()
    games = other_year_games(year)
    return render_template('edit_other_games.html', all_years=all_years, games=games, year=year)

@app.route('/other_games/')
def other_games():
    all_years = all_other_years()
    games = other_year_games(str(date.today().year))
    return render_template('other_games.html', games=games, all_years=all_years, year=str(date.today().year))

@app.route('/other_games/<year>')
def other_games_by_year(year):
    all_years = all_other_years()
    games = other_year_games(year)
    return render_template('other_games.html', all_years=all_years, games=games, year=year)


@app.route('/edit_other_game/<int:id>/',methods = ['GET','POST'])
def update_other_game(id):
    game_id = id
    x = find_other_game(game_id)
    if not x:
        flash('Game not found!')
        return redirect(url_for('edit_other_games'))
    
    # Get the full game data (all 20 fields)
    game = x[0]
    games = other_year_games(str(date.today().year))
    players = all_other_players(games)
    
    if request.method == 'POST':
        game_type = request.form.get('game_type', '')
        game_name = request.form.get('game_name', '')
        winner1 = request.form.get('winner1', '')
        winner2 = request.form.get('winner2', '')
        winner3 = request.form.get('winner3', '')
        winner4 = request.form.get('winner4', '')
        winner5 = request.form.get('winner5', '')
        winner6 = request.form.get('winner6', '')
        loser1 = request.form.get('loser1', '')
        loser2 = request.form.get('loser2', '')
        loser3 = request.form.get('loser3', '')
        loser4 = request.form.get('loser4', '')
        loser5 = request.form.get('loser5', '')
        loser6 = request.form.get('loser6', '')
        winner_score = request.form.get('winner_score', '')
        loser_score = request.form.get('loser_score', '')
        comment = request.form.get('comment', '')

        if not game_type or not game_name or not winner1 or not loser1 or not winner_score or not loser_score:
            flash('Required fields missing!')
        else:
            # Update the game using the database function
            from other_functions import database_update_other_game
            from database_functions import create_connection
            
            database = '/home/Idynkydnk/stats/stats.db'
            conn = create_connection(database)
            if conn is None:
                database = r'stats.db'
                conn = create_connection(database)
            
            with conn:
                game_data = (game_id, game[1], game_type, game_name, winner1, winner2, winner3, winner4, winner5, winner6,
                           winner_score, loser1, loser2, loser3, loser4, loser5, loser6, loser_score, comment, datetime.now(), game_id)
                database_update_other_game(conn, game_data)
            
            # Log the action for notifications
            user = session.get('username', 'unknown')
            details = f"Game ID {game_id}: {game_type} - {game_name}; {winner1} vs {loser1} ({winner_score}-{loser_score})"
            log_user_action(user, 'Edited other game', details)
            
            return redirect(url_for('edit_other_games'))
 
    return render_template('edit_other_game.html', game=game, players=players, year=str(date.today().year))


@app.route('/delete_other_game/<int:id>/',methods = ['GET','POST'])
def delete_other_game(id):
    game_id = id
    game = find_other_game(id)
    if not game:
        flash('Game not found!')
        return redirect(url_for('edit_other_games'))
    
    if request.method == 'POST':
        # Log the action for notifications before deleting
        user = session.get('username', 'unknown')
        # Raw database structure: [id, game_date, game_type, game_name, winner1, winner2, ..., winner_score, loser1, ..., loser_score, comment, updated_at]
        details = f"Game ID {game_id}: {game[0][2]} - {game[0][3]} ({game[0][4]} vs {game[0][11]})"
        log_user_action(user, 'Deleted other game', details)
        
        remove_other_game(game_id)
        return redirect(url_for('edit_other_games'))
 
    return render_template('delete_other_game.html', game=game[0])

@app.route('/other_player/<year>/<name>')
def other_player_stats(year, name):
    all_years = all_years_other_player(name)
    games = games_from_other_player_by_year(year, name)
    stats = total_other_stats(name, games)
    opponent_stats = other_opponent_stats_by_year(name, games)
    return render_template('other_player.html', opponent_stats=opponent_stats, 
        year=year, player=name, all_years=all_years, stats=stats)


@app.route('/game_name_stats/<game_name>/')
def game_name_stats(game_name):
    all_years = game_name_years(game_name)
    year = str(date.today().year)
    games = game_name_games(year, game_name)
    minimum_games = 0
    stats = total_game_name_stats(games)
    return render_template('game_name_stats.html', stats=stats, game_name=game_name,
        all_years=all_years, minimum_games=minimum_games, year=year)

@app.route('/game_name_stats/<game_name>/<year>/')
def game_name_stats_with_year(game_name, year):
    all_years = game_name_years(game_name)
    games = game_name_games(year, game_name)
    minimum_games = 0
    stats = total_game_name_stats(games)
    return render_template('game_name_stats.html', stats=stats, game_name=game_name,
        all_years=all_years, minimum_games=minimum_games, year=year)

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Check if user is already logged in via remember me cookie
    if not session.get('logged_in'):
        auth_token = request.cookies.get('remember_token')
        if auth_token:
            username = validate_auth_token(auth_token)
            if username:
                # Auto-login the user
                session['logged_in'] = True
                session['username'] = username
                flash(f'Welcome back, {username}!', 'success')
                return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember_me = request.form.get('remember_me') == 'on'
        
        if username in USERS and USERS[username] == password:
            session['logged_in'] = True
            session['username'] = username
            flash(f'Successfully logged in as {username}!', 'success')
            
            # Show notifications to Kyle if there are any unread ones
            if username == 'kyle':
                notifications = get_unread_notifications()
                if notifications:
                    flash(f'You have {len(notifications)} unread notification(s) from other users. Check the notifications menu.', 'info')
            
            response = make_response(redirect(url_for('index')))
            
            # Set remember me cookie if requested
            if remember_me:
                auth_token = create_auth_token(username)
                response.set_cookie('remember_token', auth_token, 
                                  max_age=30*24*60*60,  # 30 days
                                  secure=False,  # Set to True in production with HTTPS
                                  httponly=True,  # Prevent XSS attacks
                                  samesite='Lax')  # CSRF protection
                flash('You will stay logged in on this device for 30 days.', 'info')
            
            return response
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    # Get the current user before clearing session
    username = session.get('username')
    
    # Clear session
    session.pop('logged_in', None)
    session.pop('username', None)
    
    # Clear remember me cookie
    auth_token = request.cookies.get('remember_token')
    if auth_token:
        revoke_auth_token(auth_token)
    
    # Revoke all tokens for this user (optional - for security)
    if username:
        revoke_all_user_tokens(username)
    
    response = make_response(redirect(url_for('index')))
    response.set_cookie('remember_token', '', expires=0)
    
    flash('You have been logged out.', 'info')
    return response

@app.route('/notifications')
@login_required
def notifications():
    """View and manage notifications (Kyle only)"""
    if session.get('username') != 'kyle':
        flash('Access denied. Only Kyle can view notifications.', 'error')
        return redirect(url_for('index'))
    
    all_notifications = get_unread_notifications()
    return render_template('notifications.html', notifications=all_notifications)

@app.route('/mark_notifications_read', methods=['POST'])
@login_required
def mark_notifications_read_route():
    """Mark selected notifications as read"""
    if session.get('username') != 'kyle':
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    notification_ids = request.form.getlist('notification_ids')
    if notification_ids:
        mark_notifications_read(notification_ids)
        flash(f'Marked {len(notification_ids)} notification(s) as read.', 'success')
    
    return redirect(url_for('notifications'))

@app.route('/api/notifications/count')
@login_required
def get_notification_count():
    """API endpoint to get notification count for Kyle"""
    if session.get('username') != 'kyle':
        return jsonify({'count': 0})
    
    notifications = get_unread_notifications()
    return jsonify({'count': len(notifications)})

@app.route('/deploy', methods=['POST'])
def deploy():
    """Webhook endpoint for automated deployment"""
    try:
        # Change to the stats directory
        os.chdir('/home/Idynkydnk/stats')
        
        # Pull latest changes
        subprocess.run(['git', 'fetch', 'origin'], check=True)
        subprocess.run(['git', 'reset', '--hard', 'origin/main'], check=True)
        
        # Reload the web app
        subprocess.run(['touch', '/var/www/idynkydnk_pythonanywhere_com_wsgi.py'], check=True)
        
        return 'Deployment successful', 200
    except Exception as e:
        return f'Deployment failed: {str(e)}', 500

@app.route('/api/one_v_one_game_type/<game_name>')
def get_one_v_one_game_type(game_name):
    """API endpoint to get game type for a given game name"""
    games = one_v_one_year_games('All years')
    game_type = one_v_one_game_type_for_name(games, game_name)
    return {'game_type': game_type} if game_type else {'game_type': None}

@app.route('/api/other_game_type/<game_name>')
def get_other_game_type(game_name):
    """API endpoint to get game type for a given game name"""
    games = other_year_games('All years')
    game_type = other_game_type_for_name(games, game_name)
    return {'game_type': game_type} if game_type else {'game_type': None}

@app.route('/manage_player_names/', methods=['GET', 'POST'])
@login_required
def manage_player_names():
    """Page for managing player names across all game types"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'search':
            search_term = request.form.get('search_term', '').strip()
            if search_term:
                search_results = search_player_names(search_term)
                all_players = get_all_unique_players()
                return render_template('manage_player_names.html', 
                                     search_results=search_results, 
                                     search_term=search_term,
                                     all_players=all_players)
        
        elif action == 'update':
            old_name = request.form.get('old_name', '').strip()
            new_name = request.form.get('new_name', '').strip()
            
            if old_name and new_name and old_name != new_name:
                try:
                    updates_made = update_player_name(old_name, new_name)
                    flash(f'Successfully updated "{old_name}" to "{new_name}" in {updates_made} records.', 'success')
                except Exception as e:
                    flash(f'Error updating player name: {str(e)}', 'error')
            else:
                flash('Please provide both old and new names, and ensure they are different.', 'error')
    
    all_players = get_all_unique_players()
    return render_template('manage_player_names.html', all_players=all_players)

@app.route('/date_range_stats/')
@app.route('/date_range_stats/<start_date>/<end_date>/')
def date_range_stats(start_date=None, end_date=None):
    """Page for viewing stats and games within a custom date range"""
    # Get dates from URL parameters or form
    if not start_date or not end_date:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        start_time = request.args.get('start_time', '00:00')
        end_time = request.args.get('end_time', '23:59')
    else:
        # For URL path parameters, default times
        start_time = '00:00'
        end_time = '23:59'
    
    if start_date and end_date:
        # Use the provided times
        start_datetime = f"{start_date} {start_time}:00"
        end_datetime = f"{end_date} {end_time}:00"
        
        # Convert times to 12-hour format for display
        def format_time_12h(time_24h):
            hour, minute = time_24h.split(':')
            hour = int(hour)
            ampm = 'AM' if hour < 12 else 'PM'
            hour_12 = hour % 12 or 12
            return f"{hour_12}:{minute} {ampm}"
        
        start_time_display = format_time_12h(start_time)
        end_time_display = format_time_12h(end_time)
        
        stats = get_date_range_stats(start_datetime, end_datetime)
        games = date_range_games(start_datetime, end_datetime)
        
        return render_template('date_range_stats.html', 
                             stats=stats, 
                             games=games,
                             start_date=start_date,
                             end_date=end_date,
                             start_time=start_time,
                             end_time=end_time,
                             start_time_display=start_time_display,
                             end_time_display=end_time_display,
                             has_results=True)
    
    return render_template('date_range_stats.html', has_results=False)

@app.route('/dashboard/')
def dashboard():
    """Visual dashboard showing key doubles statistics"""
    from stat_functions import get_dashboard_data, grab_all_years, specific_date_stats, get_previous_date_with_games, get_next_date_with_games, get_most_recent_date_with_games, has_games_on_date, calculate_glicko_rankings
    from datetime import datetime
    
    # Get selected year from query parameter, default to current year
    selected_year = request.args.get('year')
    if not selected_year:
        selected_year = str(datetime.now().year)
    
    # Get date from query parameter, default to today
    target_date = request.args.get('date')
    if not target_date:
        target_date = datetime.now().strftime('%Y-%m-%d')
    
    # Get available years
    available_years = grab_all_years()
    
    # Get dashboard data for selected year
    dashboard_data = get_dashboard_data(selected_year)
    dashboard_data['selected_year'] = selected_year
    dashboard_data['available_years'] = available_years
    dashboard_data['current_year'] = datetime.now().year
    
    # If no games on target date, find the most recent date with games
    if not has_games_on_date(target_date):
        most_recent_date = get_most_recent_date_with_games()
        if most_recent_date:
            target_date = most_recent_date
    
    # Get stats for the specific date
    date_stats, date_games = specific_date_stats(target_date)
    
    # Navigation dates - skip days without games
    previous_date = get_previous_date_with_games(target_date)
    next_date = get_next_date_with_games(target_date)
    
    # Check if there are previous/next dates with games
    has_previous = previous_date is not None
    has_next = next_date is not None
    
    # Format date for display
    try:
        display_date = datetime.strptime(target_date, '%Y-%m-%d').strftime('%m/%d/%y')
    except:
        display_date = target_date
    
    # Get trueskill rankings for the selected year
    from stat_functions import calculate_trueskill_rankings
    trueskill_rankings = calculate_trueskill_rankings(selected_year)
    
    # Get top teams data for the selected year
    from stat_functions import team_stats_per_year, year_games
    games = year_games(selected_year)
    if games:
        if len(games) < 70:
            minimum_games_teams = 1
        else:
            minimum_games_teams = len(games) // 70
    else:
        minimum_games_teams = 1
    top_teams = team_stats_per_year(selected_year, minimum_games_teams, games)
    
    # Add date navigation data
    dashboard_data['today_stats'] = date_stats
    dashboard_data['current_date'] = target_date
    dashboard_data['display_date'] = display_date
    dashboard_data['previous_date'] = previous_date
    dashboard_data['next_date'] = next_date
    dashboard_data['has_previous'] = has_previous
    dashboard_data['has_next'] = has_next
    dashboard_data['trueskill_rankings'] = trueskill_rankings
    dashboard_data['current_month'] = datetime.now().month
    dashboard_data['top_teams'] = top_teams
    
    return render_template('dashboard.html', **dashboard_data)

@app.route('/api/dashboard/today-activity/')
def dashboard_today_activity():
    """API endpoint to get just the Today's Activity card content"""
    from stat_functions import specific_date_stats, get_previous_date_with_games, get_next_date_with_games, get_most_recent_date_with_games, has_games_on_date
    from datetime import datetime
    from flask import jsonify
    
    # Get date from query parameter, default to today
    target_date = request.args.get('date')
    if not target_date:
        target_date = datetime.now().strftime('%Y-%m-%d')
    
    # If no games on target date, find the most recent date with games
    if not has_games_on_date(target_date):
        most_recent_date = get_most_recent_date_with_games()
        if most_recent_date:
            target_date = most_recent_date
    
    # Get stats for the specific date
    date_stats, date_games = specific_date_stats(target_date)
    
    # Navigation dates - skip days without games
    previous_date = get_previous_date_with_games(target_date)
    next_date = get_next_date_with_games(target_date)
    
    # Check if there are previous/next dates with games
    has_previous = previous_date is not None
    has_next = next_date is not None
    
    # Format date for display
    try:
        display_date = datetime.strptime(target_date, '%Y-%m-%d').strftime('%m/%d/%y')
    except:
        display_date = target_date
    
    return jsonify({
        'date_stats': date_stats,
        'date_games': date_games,
        'current_date': target_date,
        'display_date': display_date,
        'previous_date': previous_date,
        'next_date': next_date,
        'has_previous': has_previous,
        'has_next': has_next
    })

@app.route('/streak_details/<player_name>/<streak_type>/<int:streak_length>/')
@app.route('/streak_details/<player_name>/<streak_type>/<int:streak_length>/<year>/')
def streak_details(player_name, streak_type, streak_length, year=None):
    """Show the games that made up a specific streak"""
    from stat_functions import get_streak_games
    
    # Get the games that made up this streak
    streak_games = get_streak_games(player_name, streak_type, streak_length, year)
    
    return render_template('streak_details.html', 
                         player_name=player_name,
                         streak_type=streak_type,
                         streak_length=streak_length,
                         year=year,
                         streak_games=streak_games)

@app.route('/tournaments/')
def tournaments():
    """Tournament results page"""
    return render_template('tournaments.html')

@app.route('/glicko_rankings/')
def glicko_rankings():
    """Glicko-2 rankings page"""
    from stat_functions import calculate_glicko_rankings, grab_all_years
    from datetime import datetime
    
    # Get selected year from query parameter, default to current year
    selected_year = request.args.get('year')
    if not selected_year:
        selected_year = str(datetime.now().year)
    
    # Get available years
    available_years = grab_all_years()
    
    rankings = calculate_glicko_rankings(selected_year)
    return render_template('glicko_rankings.html', rankings=rankings, selected_year=selected_year, available_years=available_years)

@app.route('/trueskill_rankings/')
def trueskill_rankings():
    """TrueSkill rankings page"""
    from stat_functions import calculate_trueskill_rankings, grab_all_years, year_games
    from datetime import datetime
    
    # Get selected year from query parameter, default to current year
    selected_year = request.args.get('year')
    if not selected_year:
        selected_year = str(datetime.now().year)
    
    # Get available years
    available_years = grab_all_years()
    
    # Calculate minimum games requirement
    if selected_year == 'All years':
        from stat_functions import all_games
        games = all_games()
    else:
        games = year_games(selected_year)
    
    if len(games) < 30:
        minimum_games = 1
    else:
        minimum_games = len(games) // 30
    
    # Get all rankings and filter by minimum games
    all_rankings = calculate_trueskill_rankings(selected_year)
    rankings = [r for r in all_rankings if r['games_played'] >= minimum_games]
    
    return render_template('trueskill_rankings.html', rankings=rankings, selected_year=selected_year, available_years=available_years)

@app.route('/player_list/')
def player_list():
    """Player list page showing all players in the database"""
    from player_functions import get_all_players
    
    players = get_all_players()
    return render_template('player_list.html', players=players)

@app.route('/kobs/')
def kobs():
    """KOBs page showing all volleyball KOBs with their games"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    cur = conn.cursor()
    
    # Get KOBs
    cur.execute("""
        SELECT session_number, start_time, end_time, total_games, 
               doubles_games, vollis_games, one_v_one_games, other_games
        FROM sessions 
        ORDER BY start_time DESC
    """)
    kobs = cur.fetchall()
    
    # Get games for each KOB
    kobs_with_games = []
    for kob in kobs:
        session_num, start_time, end_time, total_games, doubles, vollis, one_v_one, other = kob
        
        # Get all games for this KOB (only from games table since KOBs are created from doubles games)
        all_games = []
        
        # Get doubles games
        try:
            cur.execute("""
                SELECT id, game_date, 'doubles' as game_type, winner1, winner2, loser1, loser2, winner_score, loser_score 
                FROM games 
                WHERE game_date BETWEEN ? AND ? 
                ORDER BY game_date
            """, (start_time, end_time))
            doubles_games = cur.fetchall()
            all_games.extend(doubles_games)
        except:
            pass
        
        # Sort games by date
        all_games.sort(key=lambda x: x[1])
        
        # Get unique players from the games
        players = set()
        for game in all_games:
            players.add(game[3])  # winner1
            players.add(game[4])  # winner2
            players.add(game[5])  # loser1
            players.add(game[6])  # loser2
        
        kobs_with_games.append({
            'kob': kob,
            'games': all_games,
            'players': sorted(list(players))
        })
    
    conn.close()
    
    return render_template('kobs.html', kobs_with_games=kobs_with_games)

@app.route('/kob/<int:session_number>/')
def kob_detail(session_number):
    """Individual KOB detail page with player stats and games"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    cur = conn.cursor()
    
    # Get KOB details
    cur.execute("""
        SELECT session_number, start_time, end_time, total_games, 
               doubles_games, vollis_games, one_v_one_games, other_games
        FROM sessions 
        WHERE session_number = ?
    """, (session_number,))
    kob = cur.fetchone()
    
    if not kob:
        conn.close()
        return "KOB not found", 404
    
    session_num, start_time, end_time, total_games, doubles, vollis, one_v_one, other = kob
    
    # Get all games for this KOB
    all_games = []
    
    # Get doubles games
    try:
        cur.execute("""
            SELECT id, game_date, 'doubles' as game_type, winner1, winner2, loser1, loser2, winner_score, loser_score 
            FROM games 
            WHERE game_date BETWEEN ? AND ? 
            ORDER BY game_date
        """, (start_time, end_time))
        doubles_games = cur.fetchall()
        all_games.extend(doubles_games)
    except:
        pass
    
    # Sort games by date
    all_games.sort(key=lambda x: x[1])
    
    # Format games with proper time display
    from datetime import datetime
    formatted_games = []
    for game in all_games:
        game_list = list(game)
        # Convert time to 12-hour format with AM/PM
        if game[1] and len(game[1]) > 10:
            try:
                dt = datetime.fromisoformat(game[1])
                # Format as HH:MMAM/PM
                time_12hr = dt.strftime('%I:%M%p').lstrip('0')
                game_list.append(time_12hr)
            except:
                game_list.append('')
        else:
            game_list.append('')
        formatted_games.append(game_list)
    all_games = formatted_games
    
    # Get unique players from the games
    players = set()
    for game in all_games:
        players.add(game[3])  # winner1
        players.add(game[4])  # winner2
        players.add(game[5])  # loser1
        players.add(game[6])  # loser2
    
    # Calculate player stats for this session
    player_stats = []
    for player in sorted(players):
        wins = 0
        losses = 0
        plus_minus = 0
        
        for game in all_games:
            if player in [game[3], game[4]]:  # winner
                wins += 1
                plus_minus += game[7] - game[8]  # winner_score - loser_score
            elif player in [game[5], game[6]]:  # loser
                losses += 1
                plus_minus += game[8] - game[7]  # loser_score - winner_score
        
        total_games = wins + losses
        win_percentage = (wins / total_games * 100) if total_games > 0 else 0
        
        player_stats.append({
            'player': player,
            'wins': wins,
            'losses': losses,
            'win_percentage': win_percentage,
            'plus_minus': plus_minus
        })
    
    # Sort by win percentage, then by plus/minus
    player_stats.sort(key=lambda x: (-x['win_percentage'], -x['plus_minus']))
    
    # Determine KOB winner (highest win percentage, then highest plus/minus)
    kob_winner = player_stats[0] if player_stats else None
    
    conn.close()
    
    return render_template('kob_detail.html', 
                         kob=kob,
                         games=all_games,
                         players=sorted(players),
                         player_stats=player_stats,
                         kob_winner=kob_winner)

@app.route('/edit_player/<int:player_id>/', methods=['GET', 'POST'])
def edit_player(player_id):
    """Edit player information page"""
    from player_functions import get_player_by_id, update_player_info
    
    player = get_player_by_id(player_id)
    
    if not player:
        flash('Player not found')
        return redirect(url_for('player_list'))
    
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email'] if request.form['email'] else None
        date_of_birth = request.form['date_of_birth'] if request.form['date_of_birth'] else None
        height = request.form['height'] if request.form['height'] else None
        phone = request.form['phone'] if request.form['phone'] else None
        notes = request.form['notes'] if request.form['notes'] else None
        
        if not full_name:
            flash('Full name is required!')
        else:
            old_name = player[1]
            update_player_info(player_id, full_name, email, date_of_birth, height, phone, notes)
            if old_name != full_name:
                flash(f'Player updated successfully! Name changed from "{old_name}" to "{full_name}" across all games.')
            else:
                flash('Player updated successfully!')
            return redirect(url_for('player_list'))
    
    return render_template('edit_player.html', player=player)

@app.route('/game_hub')
def game_hub():
    """Game Hub dashboard showing vollis, 1v1, and other game statistics"""
    from stat_functions import grab_all_years
    from vollis_functions import get_vollis_dashboard_data
    from one_v_one_functions import get_one_v_one_dashboard_data
    from other_functions import get_other_dashboard_data
    from datetime import datetime
    
    # Get selected year from query parameter, default to All years
    selected_year = request.args.get('year')
    if not selected_year:
        selected_year = 'All years'
    
    # Get available years
    available_years = grab_all_years()
    
    # Get dashboard data for each game type
    vollis_data = get_vollis_dashboard_data(selected_year)
    one_v_one_data = get_one_v_one_dashboard_data(selected_year)
    other_data = get_other_dashboard_data(selected_year)
    
    return render_template('game_hub.html', 
                          selected_year=selected_year,
                          available_years=available_years,
                          vollis_data=vollis_data,
                          one_v_one_data=one_v_one_data,
                          other_data=other_data)

@app.route('/work_in_progress')
def work_in_progress():
    """Work in Progress page with links to various features"""
    return render_template('work_in_progress.html')

@app.route('/cleanup_tokens')
def cleanup_tokens():
    """Clean up expired authentication tokens (can be called periodically)"""
    cleanup_expired_tokens()
    return 'Expired tokens cleaned up successfully', 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
