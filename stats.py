from flask import Flask, render_template, request, url_for, flash, redirect, session, jsonify, make_response
# Flask-Caching is optional - the custom caching in stat_functions.py will still work
try:
    from flask_caching import Cache
    FLASK_CACHING_AVAILABLE = True
except ImportError:
    FLASK_CACHING_AVAILABLE = False
from flask_mail import Mail, Message
from database_functions import *
from stat_functions import *
from stat_functions import clear_stats_cache
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from vollis_functions import *
from one_v_one_functions import *
from other_functions import *
from kob_functions import update_kobs
import os
import subprocess
import sqlite3
import secrets
import hashlib
import json
import re
import threading
import time
import random

# Load environment variables from .env file if it exists (optional, for local development)
# Only load if dotenv is available - not required on PythonAnywhere where env vars are set in WSGI file
try:
    from dotenv import load_dotenv
    load_dotenv()
except (ImportError, ModuleNotFoundError):
    # dotenv not available (e.g., on PythonAnywhere) - that's fine, use environment variables directly
    pass

app = Flask(__name__)
app.config['SECRET_KEY'] = 'b83880e869f054bfc465a6f46125ac715e7286ed25e88537'

# Cache configuration - cache expensive calculations for 5 minutes
# Flask-Caching is optional - stat_functions.py has its own caching that works without it
if FLASK_CACHING_AVAILABLE:
    app.config['CACHE_TYPE'] = 'SimpleCache'
    app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutes
    cache = Cache(app)

# Email configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@stats.com')

mail = Mail(app)

# User authentication - you can add more users here
USERS = {
    'kyle': 'stats2025',
    'aaron': 'aaron2025',
    'dan': 'dan2025',
    'ryan': 'ryan2025',
    'arbel': 'arbel2025',
    'mark': 'mark2025',
    'troy': 'troy2025',
    'jason': 'jason2025'
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

def get_user_now():
    """Get the current datetime in the user's timezone (from session).
    Falls back to server local time if no timezone is set."""
    user_tz = session.get('timezone')
    if user_tz:
        try:
            tz = ZoneInfo(user_tz)
            return datetime.now(tz).replace(tzinfo=None)  # Return naive datetime for DB storage
        except Exception:
            pass
    return datetime.now()

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

def init_balloono_db():
    """Initialize Balloono users and stats tables"""
    conn = sqlite3.connect('stats.db')
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

# Initialize database tables
init_notifications_db()
init_auth_tokens_db()
init_balloono_db()

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
                response = make_response(redirect(url_for('login', next=request.url)))
                response.set_cookie('remember_token', '', expires=0)
                return response
        
        return redirect(url_for('login', next=request.url))
    return decorated_function

@app.route('/')
def index():
    """Redirect to the redesigned stats page."""
    return stats_redesign(str(date.today().year))

@app.route('/stats/<year>/')
def stats(year):
    """Redirect to the redesigned stats page for the given year."""
    return stats_redesign(year)

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


# ============================================
# REDESIGNED STATS PAGE (Steam Charts-inspired)
# ============================================

@app.route('/stats_redesign/')
def stats_redesign_default():
    return stats_redesign(str(date.today().year))


@app.route('/stats_redesign/<year>/')
def stats_redesign(year):
    """Steam Charts-inspired doubles stats page."""
    current_year = str(date.today().year)
    showing_previous_year = False
    display_year = year
    
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
    
    # If no stats for current year, fall back to previous year
    if not stats and year == current_year and all_years:
        previous_year = str(int(current_year) - 1)
        if previous_year in all_years:
            games = year_games(previous_year)
            if games:
                minimum_games = max(1, len(games) // 30)
            stats = stats_per_year(previous_year, minimum_games)
            display_year = previous_year
            showing_previous_year = True
    
    rare_stats = rare_stats_per_year(display_year, minimum_games)
    
    # Calculate tile stats
    tiles = calculate_tile_stats(display_year, stats, games)
    
    # Get today's stats
    today_stats = todays_stats()
    today_games = todays_games()
    
    return render_template('stats_redesign.html', 
        all_years=all_years, 
        stats=stats, 
        rare_stats=rare_stats, 
        minimum_games=minimum_games, 
        year=year,
        display_year=display_year,
        showing_previous_year=showing_previous_year,
        tiles=tiles,
        today_stats=today_stats,
        today_games=today_games)


@app.route('/games_redesign/')
def games_redesign_default():
    return games_redesign(str(date.today().year))


@app.route('/games_redesign/<year>/')
def games_redesign(year):
    """Steam Charts-inspired doubles games page."""
    all_years = grab_all_years()
    games = year_games(year)
    return render_template('games_redesign.html', games=games, year=year, all_years=all_years)


# ============================================
# REDESIGNED VOLLIS ROUTES
# ============================================

@app.route('/vollis_stats_redesign/')
def vollis_stats_redesign_default():
    return vollis_stats_redesign(str(date.today().year))

@app.route('/vollis_stats_redesign/<year>/')
def vollis_stats_redesign(year):
    """Redesigned vollis stats page."""
    current_year = str(date.today().year)
    showing_previous_year = False
    display_year = year
    
    all_years = all_vollis_years()
    stats = vollis_stats_per_year(year, 0)
    
    # If no stats for current year, fall back to previous year
    if not stats and year == current_year and all_years:
        previous_year = str(int(current_year) - 1)
        if previous_year in all_years:
            stats = vollis_stats_per_year(previous_year, 0)
            display_year = previous_year
            showing_previous_year = True
    
    return render_template('vollis_stats_redesign.html', stats=stats, all_years=all_years, year=year,
        display_year=display_year, showing_previous_year=showing_previous_year)

@app.route('/vollis_games_redesign/')
def vollis_games_redesign_default():
    return vollis_games_redesign(str(date.today().year))

@app.route('/vollis_games_redesign/<year>/')
def vollis_games_redesign(year):
    """Redesigned vollis games page."""
    all_years = all_vollis_years()
    games = vollis_year_games(year)
    return render_template('vollis_games_redesign.html', games=games, all_years=all_years, year=year)


# ============================================
# REDESIGNED OTHER ROUTES
# ============================================

@app.route('/other_stats_redesign/')
def other_stats_redesign_default():
    return other_stats_redesign(str(date.today().year))

@app.route('/other_stats_redesign/<year>/')
def other_stats_redesign(year):
    """Redesigned other stats page."""
    current_year = str(date.today().year)
    showing_previous_year = False
    display_year = year
    
    all_years = all_other_years()
    games = other_year_games(year)
    if games:
        if len(games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(games) // 30
    else:
        minimum_games = 1
    stats = other_stats_per_year(year, minimum_games)
    
    # If no stats for current year, fall back to previous year
    if not stats and year == current_year and all_years:
        previous_year = str(int(current_year) - 1)
        if previous_year in all_years:
            games = other_year_games(previous_year)
            if games:
                minimum_games = max(1, len(games) // 30)
            stats = other_stats_per_year(previous_year, minimum_games)
            display_year = previous_year
            showing_previous_year = True
    
    rare_stats = rare_other_stats_per_year(display_year, minimum_games)
    game_cards = build_other_game_cards(display_year)
    
    # Get today's stats grouped by game name
    today_stats_by_game = todays_other_stats_by_game()
    
    return render_template('other_stats_redesign.html', stats=stats, rare_stats=rare_stats,
        all_years=all_years, minimum_games=minimum_games, year=year,
        display_year=display_year, showing_previous_year=showing_previous_year, game_cards=game_cards,
        today_stats_by_game=today_stats_by_game)

@app.route('/other_games_redesign/')
def other_games_redesign_default():
    return other_games_redesign(str(date.today().year))

@app.route('/other_games_redesign/<year>/')
def other_games_redesign(year):
    """Redesigned other games page."""
    all_years = all_other_years()
    games = other_year_games(year)
    return render_template('other_games_redesign.html', games=games, all_years=all_years, year=year)


@app.route('/other_games_redesign/<year>/<game_name>/')
def other_games_by_name_redesign(year, game_name):
    """Redesigned other games page filtered by game name."""
    from other_functions import total_game_name_stats
    all_years = all_other_years()
    all_games = other_year_games(year)
    # Filter games by game_name
    games = [g for g in all_games if g.get('game_name') == game_name]
    stats = total_game_name_stats(games)
    return render_template('other_games_redesign.html', games=games, all_years=all_years, year=year, game_name=game_name, stats=stats)


# ============================================
# REDESIGNED EDIT ROUTES
# ============================================

@app.route('/edit_games_redesign/')
def edit_games_redesign_default():
    return edit_games_redesign(str(date.today().year))

@app.route('/edit_games_redesign/<year>/')
def edit_games_redesign(year):
    """Redesigned edit doubles games page."""
    all_years = grab_all_years()
    games = year_games(year)
    return render_template('edit_games_redesign.html', games=games, year=year, all_years=all_years)

@app.route('/edit_vollis_games_redesign/')
def edit_vollis_games_redesign_default():
    return edit_vollis_games_redesign(str(date.today().year))

@app.route('/edit_vollis_games_redesign/<year>/')
def edit_vollis_games_redesign(year):
    """Redesigned edit vollis games page."""
    all_years = all_vollis_years()
    games = vollis_year_games(year)
    return render_template('edit_vollis_games_redesign.html', games=games, year=year, all_years=all_years)

@app.route('/edit_other_games_redesign/')
def edit_other_games_redesign_default():
    return edit_other_games_redesign(str(date.today().year))

@app.route('/edit_other_games_redesign/<year>/')
def edit_other_games_redesign(year):
    """Redesigned edit other games page."""
    all_years = all_other_years()
    games = other_year_games(year)
    return render_template('edit_other_games_redesign.html', games=games, year=year, all_years=all_years)


# ============================================
# REDESIGNED ADD GAME ROUTES
# ============================================

@app.route('/ai_summary_redesign/')
@login_required
def ai_summary_redesign():
    """Redesigned AI summary page for selecting games to summarize."""
    games = recent_games(50)  # Get last 50 games
    return render_template('ai_summary_redesign.html', games=games)

@app.route('/select_ai_prompt/', methods=['POST'])
@login_required
def select_ai_prompt():
    """Show prompt selection page after selecting games."""
    selected_game_ids = request.form.getlist('game_ids')
    if not selected_game_ids:
        flash('Please select at least one game.', 'error')
        return redirect(url_for('ai_summary_redesign'))
    return render_template('select_prompt_redesign.html', game_ids=selected_game_ids)

@app.route('/preview_ai_summary_with_prompt/', methods=['POST'])
@login_required
def preview_ai_summary_with_prompt():
    """Generate AI summary with selected prompt style."""
    selected_game_ids = request.form.getlist('game_ids')
    prompt_style = request.form.get('prompt_style', 'announcer')
    custom_prompt = request.form.get('custom_prompt', '')
    
    if not selected_game_ids:
        flash('Please select at least one game.', 'error')
        return redirect(url_for('ai_summary_redesign'))

    try:
        payload = build_doubles_email_payload(selected_game_ids, prompt_style=prompt_style, custom_prompt=custom_prompt)
    except ValueError as ve:
        flash(str(ve), 'error')
        return redirect(url_for('ai_summary_redesign'))
    except Exception as e:
        flash(f'Failed to prepare summary preview: {str(e)}', 'error')
        return redirect(url_for('ai_summary_redesign'))

    selected_game_ids_json = json.dumps([str(gid) for gid in selected_game_ids])
    can_send = len(payload['players']) > 0 and len(payload['all_emails']) > 0

    return render_template(
        'preview_ai_summary_redesign.html',
        game_type='doubles',
        header_title="Doubles AI Summary Preview",
        subject=payload['subject'],
        email_html=payload['html_body'],
        players=payload['players'],
        players_without_email=payload['players_without_email'],
        selected_game_ids_json=selected_game_ids_json,
        selected_game_ids=selected_game_ids,
        send_url=url_for('generate_and_email_today'),
        back_url=url_for('ai_summary_redesign'),
        can_send=can_send
    )

@app.route('/add_game_redesign/', methods=['GET', 'POST'])
@login_required
def add_game_redesign():
    """Redesigned add doubles game page."""
    year = str(date.today().year)
    if request.method == 'POST':
        winner1 = request.form['winner1'].strip()
        winner2 = request.form['winner2'].strip()
        loser1 = request.form['loser1'].strip()
        loser2 = request.form['loser2'].strip()
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']
        comments = request.form.get('comments', '').strip()

        if not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        elif int(winner_score) <= int(loser_score):
            flash("Winner's score must be higher than loser's score!")
        elif winner1 == winner2 or winner1 == loser1 or winner1 == loser2 or winner2 == loser1 or winner2 == loser2 or loser1 == loser2:
            flash('Two names are the same!')
        else:
            from player_functions import get_player_by_name, add_new_player
            for player_name in [winner1, winner2, loser1, loser2]:
                if player_name and not get_player_by_name(player_name):
                    add_new_player(player_name)
            
            add_game_stats([get_user_now(), winner1.strip(), winner2.strip(), loser1.strip(), loser2.strip(), 
                winner_score, loser_score, get_user_now(), comments])
            clear_stats_cache()
            user = session.get('username', 'unknown')
            details = f"Winners: {winner1} & {winner2}; Losers: {loser1} & {loser2}; Score: {winner_score}-{loser_score}"
            log_user_action(user, 'Added doubles game', details)
            update_kobs()
        return redirect(url_for('add_game_redesign'))
    
    all_games = year_games('All years')
    players = all_players(all_games)
    games = todays_games()
    todays_stats_data = todays_stats()
    l_scores = list(range(0, 21))
    return render_template('add_game_redesign.html', players=players, games=games, year=year, 
        l_scores=l_scores, todays_stats=todays_stats_data)

@app.route('/add_vollis_game_redesign/', methods=['GET', 'POST'])
@login_required
def add_vollis_game_redesign():
    """Redesigned add vollis game page."""
    year = str(date.today().year)
    if request.method == 'POST':
        winner = request.form['winner'].strip()
        loser = request.form['loser'].strip()
        winner_score = request.form['winner_score']
        loser_score = request.form['loser_score']

        if not winner or not loser or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            add_vollis_stats([get_user_now(), winner, loser, winner_score, loser_score, get_user_now()])
            user = session.get('username', 'unknown')
            details = f"Winner: {winner}; Loser: {loser}; Score: {winner_score}-{loser_score}"
            log_user_action(user, 'Added vollis game', details)
        return redirect(url_for('add_vollis_game_redesign'))
    
    all_games = vollis_year_games('All years')
    players = all_vollis_players(all_games)
    games = todays_vollis_games()
    todays_stats_data = todays_vollis_stats()
    winning_scores = list(range(11, 27))
    losing_scores = list(range(0, 26))
    return render_template('add_vollis_game_redesign.html', players=players, games=games, year=year,
        winning_scores=winning_scores, losing_scores=losing_scores, todays_stats=todays_stats_data)

@app.route('/add_other_game_redesign/', methods=['GET', 'POST'])
@login_required
def add_other_game_redesign():
    """Redesigned add other game page."""
    from other_functions import all_combined_players
    year = str(date.today().year)
    
    if request.method == 'POST':
        game_type = request.form.get('game_type', '')
        game_name = request.form.get('game_name', '')
        score_type = request.form.get('score_type', 'individual') or 'individual'
        winners = []
        winner_scores = []
        losers = []
        loser_scores = []
        team_winner_score = None
        team_loser_score = None

        for i in range(1, 16):
            winner_name = request.form.get(f'winner{i}', '').strip()
            if winner_name:
                winners.append(winner_name)
                if score_type == 'individual':
                    winner_scores.append(request.form.get(f'winner{i}_score', '').strip())
                else:
                    winner_scores.append('')

        for i in range(1, 16):
            loser_name = request.form.get(f'loser{i}', '').strip()
            if loser_name:
                losers.append(loser_name)
                if score_type == 'individual':
                    loser_scores.append(request.form.get(f'loser{i}_score', '').strip())
                else:
                    loser_scores.append('')

        if score_type == 'team':
            team_winner_score = request.form.get('winner_score', '').strip()
            team_loser_score = request.form.get('loser_score', '').strip()

        comment = request.form.get('comment', '')

        if not game_type or not game_name or not winners or not losers:
            flash('Some fields missing!')
        else:
            add_other_stats(
                get_user_now(), game_type, game_name, winners, winner_scores,
                losers, loser_scores, comment, get_user_now(),
                team_winner_score, team_loser_score
            )
            user = session.get('username', 'unknown')
            details = f"Game: {game_type} - {game_name}; Winners: {', '.join(winners)}; Losers: {', '.join(losers)}"
            log_user_action(user, 'Added other game', details)
        return redirect(url_for('add_other_game_redesign'))
    
    players = all_combined_players()
    games_dict = other_year_games('All years')
    game_names = other_game_names(games_dict)
    game_types = other_game_types(games_dict)
    games = todays_other_games()
    todays_stats_data = todays_other_stats()
    return render_template('add_other_game_redesign.html', players=players, games=games, year=year,
        game_names=game_names, game_types=game_types, todays_stats=todays_stats_data)


# ============================================
# REDESIGNED PLAYER LIST ROUTE
# ============================================

@app.route('/player_list_redesign/')
@login_required
def player_list_redesign():
    """Redesigned player list page."""
    from player_functions import get_all_players
    players = get_all_players()
    all_unique_players = sorted(get_all_unique_players())
    return render_template('player_list_redesign.html', players=players, all_unique_players=all_unique_players)


# ============================================
# REDESIGNED PLAYER STATS ROUTES
# ============================================

@app.route('/player_redesign/<year>/<name>/')
def player_stats_redesign(year, name):
    """Redesigned doubles player stats page."""
    games = games_from_player_by_year(year, name)
    if games:
        minimum_games = max(1, len(games) // 40)
    else:
        minimum_games = 1
    all_years = all_years_player(name)
    stats = total_stats(games, name)
    partner_stats = partner_stats_by_year(name, games, minimum_games)
    opponent_stats = opponent_stats_by_year(name, games, minimum_games)
    return render_template('player_redesign.html', opponent_stats=opponent_stats,
        partner_stats=partner_stats, year=year, player=name, 
        minimum_games=minimum_games, all_years=all_years, stats=stats, games=games)

@app.route('/vollis_player_redesign/<year>/<name>/')
def vollis_player_stats_redesign(year, name):
    """Redesigned vollis player stats page."""
    all_years = all_years_vollis_player(name)
    games = games_from_vollis_player_by_year(year, name)
    stats = total_vollis_stats(name, games)
    opponent_stats = vollis_opponent_stats_by_year(name, games)
    return render_template('vollis_player_redesign.html', opponent_stats=opponent_stats, 
        year=year, player=name, all_years=all_years, stats=stats)

@app.route('/other_player_redesign/<year>/<name>/')
def other_player_stats_redesign(year, name):
    """Redesigned other player stats page."""
    all_years = all_years_other_player(name)
    games = games_from_other_player_by_year(year, name)
    stats = total_other_stats(name, games)
    opponent_stats = other_opponent_stats_by_year(name, games)
    return render_template('other_player_redesign.html', opponent_stats=opponent_stats, 
        year=year, player=name, all_years=all_years, stats=stats)


def calculate_tile_stats(year, stats, games):
    """Calculate stats for the tile cards."""
    tiles = {
        'games': len(games) if games else 0,
        'players': len(stats) if stats else 0,
        'top_rating': 0,
        'top_rating_player': '—',
        'most_games_count': 0,
        'most_games_player': '—',
        'avg_win_pct': 0,
        'highest_win_pct_value': '—',
        'highest_win_pct_player': '—'
    }
    
    if stats:
        # Top rating (stats is sorted by rating, index 4 is rating)
        tiles['top_rating'] = stats[0][4] if stats[0][4] else 0
        tiles['top_rating_player'] = stats[0][0]
        
        # Most games played
        most_games = max(stats, key=lambda x: x[1] + x[2])
        tiles['most_games_count'] = most_games[1] + most_games[2]
        tiles['most_games_player'] = most_games[0]
        
        # Average win percentage
        total_win_pct = sum(s[3] for s in stats)
        tiles['avg_win_pct'] = total_win_pct / len(stats) if stats else 0
        
        # Highest win percentage (minimum 5 games)
        qualified = [s for s in stats if (s[1] + s[2]) >= 5]
        if qualified:
            best = max(qualified, key=lambda x: x[3])
            tiles['highest_win_pct_value'] = f"{best[3]*100:.0f}%"
            tiles['highest_win_pct_player'] = best[0]
    
    return tiles


@app.route('/api/stats/hero')
def api_stats_hero():
    """JSON endpoint for hero chart data."""
    year = request.args.get('year', str(date.today().year))
    range_filter = request.args.get('range', 'all')
    
    games = year_games(year)
    if games:
        if len(games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(games) // 30
    else:
        minimum_games = 1
    
    stats = stats_per_year(year, minimum_games)
    
    # Limit based on range
    if range_filter == '10':
        stats = stats[:10]
    elif range_filter == '25':
        stats = stats[:25]
    # 'all' returns all stats
    
    # Format for chart (bar chart of top players by rating)
    series = []
    for player in stats:
        series.append({
            'name': player[0],
            'value': player[4] if player[4] else 0  # rating
        })
    
    return jsonify({
        'labels': [s['name'] for s in series],
        'series': series
    })


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
    return add_game_redesign()


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
    if not x:
        flash('Game not found.')
        return redirect(url_for('edit_games'))
    raw_game = x[0]
    existing_comment = ''
    if len(raw_game) > 9 and raw_game[9]:
        existing_comment = raw_game[9]
    game = [
        raw_game[0],  # id
        raw_game[1],  # game_date
        raw_game[2],  # winner1
        raw_game[3],  # winner2
        raw_game[4],  # winner_score
        raw_game[5],  # loser1
        raw_game[6],  # loser2
        raw_game[7],  # loser_score
        raw_game[8],  # updated_at
        existing_comment
    ]
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
        comment = request.form.get('comment', '').strip()
        game[9] = comment

        if not game_date or not game_time or not winner1 or not winner2 or not loser1 or not loser2 or not winner_score or not loser_score:
            flash('All fields required!')
        else:
            # Combine date and time into the format expected by the database
            combined_datetime = f"{game_date} {game_time}:00"
            update_game(game_id, combined_datetime, winner1, winner2, winner_score, loser1, loser2, loser_score, get_user_now(), comment, game_id)
            
            # Clear stats cache after editing a game
            clear_stats_cache()
            
            # Log the action for notifications
            user = session.get('username', 'unknown')
            details = f"Game ID {game_id}: {winner1}/{winner2} vs {loser1}/{loser2} ({winner_score}-{loser_score})"
            log_user_action(user, 'Edited doubles game', details)
            
            # Update KOBs after editing game
            update_kobs()
            
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
    from_add_game = request.args.get('from_add_game', 'false')
    from_redesign = request.args.get('from_redesign', 'false')
    if request.method == 'POST':
        # Log the action for notifications before deleting
        if game and len(game) > 0 and len(game[0]) >= 8:
            user = session.get('username', 'unknown')
            game_data = game[0]  # Get the first (and only) row
            details = f"Game ID {game_id}: {game_data[2]}/{game_data[3]} vs {game_data[5]}/{game_data[6]} ({game_data[4]}-{game_data[7]})"
            log_user_action(user, 'Deleted doubles game', details)
        
        remove_game(game_id)
        
        # Clear stats cache after deleting a game
        clear_stats_cache()
        
        # Update KOBs after deleting game
        update_kobs()
        
        # Redirect back to appropriate page
        if request.form.get('from_redesign') == 'true':
            return redirect(url_for('add_game_redesign'))
        if request.form.get('from_add_game') == 'true':
            return redirect(url_for('add_game'))
        return redirect(url_for('edit_games'))
 
    return render_template('delete_game.html', game=game, from_add_game=from_add_game, from_redesign=from_redesign)

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
    current_year = str(date.today().year)
    year = current_year
    t_stats = todays_vollis_stats()
    games = todays_vollis_games()
    minimum_games = 0
    stats = vollis_stats_per_year(year, minimum_games)
    
    # If no stats for current year, show previous year with a notice
    showing_previous_year = False
    if not stats and current_year in all_years:
        # Remove current year since it has no data, try previous
        pass
    if not stats:
        previous_year = str(int(current_year) - 1)
        if previous_year in all_years:
            year = previous_year
            stats = vollis_stats_per_year(year, minimum_games)
            showing_previous_year = True
    
    return render_template('vollis_stats.html', stats=stats, todays_stats=t_stats, games=games,
        all_years=all_years, minimum_games=minimum_games, year=year, 
        showing_previous_year=showing_previous_year, current_year=current_year)


@app.route('/add_vollis_game/', methods=('GET', 'POST'))
@login_required
def add_vollis_game():
    return add_vollis_game_redesign()


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
            edit_vollis_game(game_id, game[1], winner, winner_score, loser, loser_score, get_user_now(), game_id)
            
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
    from_add_game = request.args.get('from_add_game', 'false')
    from_redesign = request.args.get('from_redesign', 'false')
    if request.method == 'POST':
        # Log the action for notifications before deleting
        user = session.get('username', 'unknown')
        details = f"Game ID {game_id}: {game[0][2]} vs {game[0][3]} ({game[0][4]}-{game[0][5]})"
        log_user_action(user, 'Deleted vollis game', details)
        
        remove_vollis_game(game_id)
        
        # Redirect back to appropriate page
        if request.form.get('from_redesign') == 'true':
            return redirect(url_for('add_vollis_game_redesign'))
        if request.form.get('from_add_game') == 'true':
            return redirect(url_for('add_vollis_game'))
        return redirect(url_for('edit_vollis_games'))
 
    return render_template('delete_vollis_game.html', game=game, from_add_game=from_add_game, from_redesign=from_redesign)

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
    current_year = str(date.today().year)
    year = current_year
    t_stats = todays_one_v_one_stats()
    games = todays_one_v_one_games()
    minimum_games = 0
    stats = one_v_one_stats_per_year(year, minimum_games)
    
    # If no stats for current year, show previous year with a notice
    showing_previous_year = False
    if not stats:
        previous_year = str(int(current_year) - 1)
        if previous_year in all_years:
            year = previous_year
            stats = one_v_one_stats_per_year(year, minimum_games)
            showing_previous_year = True
    
    return render_template('one_v_one_stats.html', stats=stats, todays_stats=t_stats, games=games,
        all_years=all_years, minimum_games=minimum_games, year=year,
        showing_previous_year=showing_previous_year, current_year=current_year)


@app.route('/add_one_v_one_game/', methods=('GET', 'POST'))
@login_required
def add_one_v_one_game():
    all_games = one_v_one_year_games('All years')
    game_types = one_v_one_game_types(all_games)
    game_names = one_v_one_game_names(all_games)
    players = all_one_v_one_players(all_games)
    stats = todays_one_v_one_stats()
    games = todays_one_v_one_games()
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
            add_one_v_one_stats([get_user_now(), game_type, game_name, winner, loser, winner_score, loser_score, get_user_now()])
            
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
            edit_one_v_one_game(game_id, game[1], game[2], game[3], winner, winner_score, loser, loser_score, get_user_now(), game_id)
            
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




def build_other_game_cards(year, exclude_volleyball=True, minimum_games=1):
    """Build per-game cards for other games.
    
    If exclude_volleyball is True, consolidates all Volleyball games into a single summary card.
    minimum_games is used to filter players in the consolidated volleyball card.
    """
    from other_functions import other_year_games, other_game_names, total_game_name_stats, other_game_type_for_name
    
    games = other_year_games(year)
    game_cards = []
    volleyball_games = []
    
    if games:
        game_names = other_game_names(games)
        for game_name in game_names:
            game_specific = [game for game in games if game.get('game_name') == game_name]
            if not game_specific:
                continue
            
            # Check if this is a volleyball game
            game_type = other_game_type_for_name(games, game_name)
            if exclude_volleyball and game_type == 'Volleyball':
                volleyball_games.extend(game_specific)
                continue
            
            stats_for_game = total_game_name_stats(game_specific)
            if not stats_for_game:
                continue
            
            # Calculate minimum games for this game type using same formula as doubles
            num_games = len(game_specific)
            if num_games < 30:
                card_minimum_games = 1
            else:
                card_minimum_games = num_games // 30
            
            # Split stats into qualified and rare
            qualified_stats = [s for s in stats_for_game if (s[1] + s[2]) >= card_minimum_games]
            rare_stats = [s for s in stats_for_game if (s[1] + s[2]) < card_minimum_games]
            
            game_cards.append({
                'game_name': game_name,
                'stats': qualified_stats,
                'rare_stats': rare_stats,
                'minimum_games': card_minimum_games,
                'total_games': len(game_specific)  # Count actual games, not player participations
            })
        
        # Add consolidated volleyball card if we have volleyball games
        if exclude_volleyball and volleyball_games:
            volleyball_stats = total_game_name_stats(volleyball_games)
            if volleyball_stats:
                total_vb_games = len(volleyball_games)  # Count actual games, not player participations
                # Count unique volleyball game types
                vb_game_names = set(g.get('game_name') for g in volleyball_games)
                
                # Calculate minimum games for volleyball based on total volleyball games
                if len(volleyball_games) < 30:
                    vb_minimum_games = 1
                else:
                    vb_minimum_games = len(volleyball_games) // 30
                
                # Split stats by minimum games requirement
                qualified_stats = [s for s in volleyball_stats if (s[1] + s[2]) >= vb_minimum_games]
                rare_stats = [s for s in volleyball_stats if (s[1] + s[2]) < vb_minimum_games]
                
                game_cards.append({
                    'game_name': 'Volleyball',
                    'game_type': 'Volleyball',
                    'is_consolidated': True,
                    'num_game_types': len(vb_game_names),
                    'stats': qualified_stats,
                    'rare_stats': rare_stats,
                    'total_games': total_vb_games,
                    'minimum_games': vb_minimum_games
                })
    
    # Sort all cards by total games descending
    game_cards.sort(key=lambda x: x['total_games'], reverse=True)
    
    return game_cards


def build_volleyball_game_cards(year):
    """Build per-game cards for volleyball games only."""
    from other_functions import other_year_games, other_game_names, total_game_name_stats, other_game_type_for_name
    
    games = other_year_games(year)
    game_cards = []
    
    if games:
        game_names = other_game_names(games)
        for game_name in game_names:
            game_specific = [game for game in games if game.get('game_name') == game_name]
            if not game_specific:
                continue
            
            # Only include volleyball games
            game_type = other_game_type_for_name(games, game_name)
            if game_type != 'Volleyball':
                continue
            
            stats_for_game = total_game_name_stats(game_specific)
            if not stats_for_game:
                continue
            game_cards.append({
                'game_name': game_name,
                'stats': stats_for_game,  # Pass all stats, template handles display limit
                'total_games': len(game_specific)  # Count actual games, not player participations
            })
        
        # Sort by total games descending
        game_cards.sort(key=lambda x: x['total_games'], reverse=True)
    
    return game_cards


@app.route('/other_stats/<year>/')
def other_stats(year):
    all_years = all_other_years()
    # Calculate minimum games using same formula as doubles stats
    games = other_year_games(year)
    if games:
        if len(games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(games) // 30
    else:
        minimum_games = 1
    stats = other_stats_per_year(year, minimum_games)
    rare_stats = rare_other_stats_per_year(year, minimum_games)
    game_cards = build_other_game_cards(year)
    return render_template('other_stats.html', stats=stats, rare_stats=rare_stats,
        all_years=all_years, minimum_games=minimum_games, year=year, game_cards=game_cards)

@app.route('/other_stats/')
def other():
    all_years = all_other_years()
    current_year = str(date.today().year)
    year = current_year
    t_stats = todays_other_stats()
    todays_games = todays_other_games()
    
    # Calculate minimum games using same formula as doubles stats
    year_games = other_year_games(year)
    if year_games:
        if len(year_games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(year_games) // 30
    else:
        minimum_games = 1
    
    stats = other_stats_per_year(year, minimum_games)
    rare_stats = rare_other_stats_per_year(year, minimum_games)
    game_cards = build_other_game_cards(year)
    
    # If no stats for current year, show previous year with a notice
    showing_previous_year = False
    if not stats and not rare_stats:
        previous_year = str(int(current_year) - 1)
        if previous_year in all_years:
            year = previous_year
            # Recalculate minimum games for the previous year
            year_games = other_year_games(year)
            if year_games:
                if len(year_games) < 30:
                    minimum_games = 1
                else:
                    minimum_games = len(year_games) // 30
            else:
                minimum_games = 1
            stats = other_stats_per_year(year, minimum_games)
            rare_stats = rare_other_stats_per_year(year, minimum_games)
            game_cards = build_other_game_cards(year)
            showing_previous_year = True
    
    return render_template('other_stats.html', stats=stats, rare_stats=rare_stats, 
        todays_stats=t_stats, games=todays_games,
        all_years=all_years, minimum_games=minimum_games, year=year, game_cards=game_cards,
        showing_previous_year=showing_previous_year, current_year=current_year)


@app.route('/volleyball_stats/')
def volleyball_stats_default():
    return volleyball_stats(str(date.today().year))


@app.route('/volleyball_stats/<year>/')
def volleyball_stats(year):
    from other_functions import other_year_games, total_game_name_stats
    
    all_years = all_other_years()
    games = other_year_games(year)
    
    # Filter to only volleyball games
    volleyball_games = [g for g in games if g.get('game_type') == 'Volleyball']
    
    # Calculate overall volleyball stats
    overall_stats = total_game_name_stats(volleyball_games) if volleyball_games else []
    
    # Calculate minimum games for qualification
    if volleyball_games:
        if len(volleyball_games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(volleyball_games) // 30
    else:
        minimum_games = 1
    
    # Split into qualified and rare stats
    qualified_stats = [s for s in overall_stats if (s[1] + s[2]) >= minimum_games]
    rare_stats = [s for s in overall_stats if (s[1] + s[2]) < minimum_games]
    
    # Get individual game cards for each volleyball game type
    game_cards = build_volleyball_game_cards(year)
    
    return render_template('volleyball_stats.html', 
        stats=qualified_stats,
        rare_stats=rare_stats,
        all_years=all_years, 
        minimum_games=minimum_games, 
        year=year, 
        game_cards=game_cards,
        total_games=len(volleyball_games))


def is_1v1_game(game):
    """Check if a game is 1v1 (exactly 1 player per team)."""
    from other_functions import _is_valid_player_name
    
    # Count winners
    winner_count = 0
    for i in range(1, 16):
        winner = game.get(f'winner{i}')
        if winner and _is_valid_player_name(winner):
            winner_count += 1
    
    # Count losers
    loser_count = 0
    for i in range(1, 16):
        loser = game.get(f'loser{i}')
        if loser and _is_valid_player_name(loser):
            loser_count += 1
    
    return winner_count == 1 and loser_count == 1


def build_volleyball_game_cards_styled(year):
    """Build per-game cards for volleyball games, consolidating all 1v1 games into one card."""
    from other_functions import other_year_games, other_game_names, total_game_name_stats, other_game_type_for_name
    
    games = other_year_games(year)
    game_cards = []
    one_v_one_games = []
    one_v_one_game_names = set()
    
    if games:
        # First, identify all volleyball games and classify them as 1v1 or team
        volleyball_games = [g for g in games if g.get('game_type') == 'Volleyball']
        
        for game in volleyball_games:
            if is_1v1_game(game):
                one_v_one_games.append(game)
                one_v_one_game_names.add(game.get('game_name', 'Unknown'))
        
        # Get game names that are NOT 1v1 (team games)
        game_names = other_game_names(volleyball_games)
        for game_name in game_names:
            # Skip if all games of this type are 1v1
            game_specific = [g for g in volleyball_games if g.get('game_name') == game_name]
            non_1v1_games = [g for g in game_specific if not is_1v1_game(g)]
            
            if not non_1v1_games:
                # All games of this type are 1v1, skip (they'll be in consolidated card)
                continue
            
            stats_for_game = total_game_name_stats(non_1v1_games)
            if not stats_for_game:
                continue
            game_cards.append({
                'game_name': game_name,
                'stats': stats_for_game,
                'total_games': len(non_1v1_games),
                'is_consolidated': False
            })
        
        # Create consolidated 1v1 card if there are any 1v1 games
        if one_v_one_games:
            one_v_one_stats = total_game_name_stats(one_v_one_games)
            if one_v_one_stats:
                game_cards.append({
                    'game_name': '1v1 Volleyball',
                    'stats': one_v_one_stats,
                    'total_games': len(one_v_one_games),
                    'is_consolidated': True,
                    'included_games': sorted(list(one_v_one_game_names))
                })
        
        # Sort by total games descending
        game_cards.sort(key=lambda x: x['total_games'], reverse=True)
    
    return game_cards


@app.route('/volleyball_stats_styled/')
def volleyball_stats_styled_default():
    return volleyball_stats_styled(str(date.today().year))


@app.route('/volleyball_stats_styled/<year>/')
def volleyball_stats_styled(year):
    from other_functions import other_year_games, total_game_name_stats
    
    all_years = all_other_years()
    games = other_year_games(year)
    
    # Filter to only volleyball games
    volleyball_games = [g for g in games if g.get('game_type') == 'Volleyball']
    
    # Calculate overall volleyball stats
    overall_stats = total_game_name_stats(volleyball_games) if volleyball_games else []
    
    # Calculate minimum games for qualification
    if volleyball_games:
        if len(volleyball_games) < 30:
            minimum_games = 1
        else:
            minimum_games = len(volleyball_games) // 30
    else:
        minimum_games = 1
    
    # Split into qualified and rare stats
    qualified_stats = [s for s in overall_stats if (s[1] + s[2]) >= minimum_games]
    rare_stats = [s for s in overall_stats if (s[1] + s[2]) < minimum_games]
    
    # Get game cards with 1v1 consolidation
    game_cards = build_volleyball_game_cards_styled(year)
    
    return render_template('volleyball_stats_styled.html', 
        stats=qualified_stats,
        rare_stats=rare_stats,
        all_years=all_years, 
        minimum_games=minimum_games, 
        year=year, 
        game_cards=game_cards,
        total_games=len(volleyball_games))


@app.route('/volleyball_player/<year>/<name>')
def volleyball_player_stats(year, name):
    """Show volleyball stats for a specific player with cards for each game type."""
    from other_functions import other_year_games, total_game_name_stats, other_game_names, _is_valid_player_name
    
    all_years = all_other_years()
    games = other_year_games(year)
    
    # Filter to only volleyball games where this player participated
    player_volleyball_games = []
    for game in games:
        if game.get('game_type') != 'Volleyball':
            continue
        # Check if player is in this game
        for i in range(1, 16):
            winner = game.get(f'winner{i}')
            loser = game.get(f'loser{i}')
            if (winner and _is_valid_player_name(winner) and winner == name) or \
               (loser and _is_valid_player_name(loser) and loser == name):
                player_volleyball_games.append(game)
                break
    
    # Calculate overall stats for this player
    wins, losses = 0, 0
    for game in player_volleyball_games:
        for i in range(1, 16):
            winner = game.get(f'winner{i}')
            loser = game.get(f'loser{i}')
            if winner and _is_valid_player_name(winner) and winner == name:
                wins += 1
                break
            if loser and _is_valid_player_name(loser) and loser == name:
                losses += 1
                break
    
    total_games = wins + losses
    win_percentage = wins / total_games if total_games > 0 else 0
    overall_stats = [[name, wins, losses, win_percentage, total_games]]
    
    # Build game cards for each volleyball game type this player has played
    game_cards = []
    game_names = other_game_names(player_volleyball_games)
    for game_name in game_names:
        game_specific = [g for g in player_volleyball_games if g.get('game_name') == game_name]
        if not game_specific:
            continue
        
        # Calculate player's stats for this specific game type
        type_wins, type_losses = 0, 0
        for game in game_specific:
            for i in range(1, 16):
                winner = game.get(f'winner{i}')
                loser = game.get(f'loser{i}')
                if winner and _is_valid_player_name(winner) and winner == name:
                    type_wins += 1
                    break
                if loser and _is_valid_player_name(loser) and loser == name:
                    type_losses += 1
                    break
        
        type_total = type_wins + type_losses
        type_win_pct = type_wins / type_total if type_total > 0 else 0
        
        game_cards.append({
            'game_name': game_name,
            'wins': type_wins,
            'losses': type_losses,
            'win_percentage': type_win_pct,
            'total_games': type_total
        })
    
    # Sort by total games descending
    game_cards.sort(key=lambda x: x['total_games'], reverse=True)
    
    return render_template('volleyball_player.html',
        player=name,
        year=year,
        all_years=all_years,
        stats=overall_stats,
        game_cards=game_cards,
        total_games=total_games)


@app.route('/volleyball_player_redesign/<year>/<name>')
def volleyball_player_stats_redesign(year, name):
    """Redesigned volleyball stats page for a specific player."""
    from other_functions import other_year_games, total_game_name_stats, other_game_names, _is_valid_player_name
    
    all_years = all_other_years()
    games = other_year_games(year)
    
    # Filter to only volleyball games where this player participated
    player_volleyball_games = []
    for game in games:
        if game.get('game_type') != 'Volleyball':
            continue
        for i in range(1, 16):
            winner = game.get(f'winner{i}')
            loser = game.get(f'loser{i}')
            if (winner and _is_valid_player_name(winner) and winner == name) or \
               (loser and _is_valid_player_name(loser) and loser == name):
                player_volleyball_games.append(game)
                break
    
    # Calculate overall stats for this player
    wins, losses = 0, 0
    for game in player_volleyball_games:
        for i in range(1, 16):
            winner = game.get(f'winner{i}')
            loser = game.get(f'loser{i}')
            if winner and _is_valid_player_name(winner) and winner == name:
                wins += 1
                break
            if loser and _is_valid_player_name(loser) and loser == name:
                losses += 1
                break
    
    total_games = wins + losses
    win_percentage = wins / total_games if total_games > 0 else 0
    overall_stats = [[name, wins, losses, win_percentage, total_games]]
    
    # Build game cards for each volleyball game type this player has played
    game_cards = []
    game_names = other_game_names(player_volleyball_games)
    for game_name in game_names:
        game_specific = [g for g in player_volleyball_games if g.get('game_name') == game_name]
        if not game_specific:
            continue
        
        type_wins, type_losses = 0, 0
        for game in game_specific:
            for i in range(1, 16):
                winner = game.get(f'winner{i}')
                loser = game.get(f'loser{i}')
                if winner and _is_valid_player_name(winner) and winner == name:
                    type_wins += 1
                    break
                if loser and _is_valid_player_name(loser) and loser == name:
                    type_losses += 1
                    break
        
        type_total = type_wins + type_losses
        type_win_pct = type_wins / type_total if type_total > 0 else 0
        
        game_cards.append({
            'game_name': game_name,
            'wins': type_wins,
            'losses': type_losses,
            'win_percentage': type_win_pct,
            'total_games': type_total
        })
    
    game_cards.sort(key=lambda x: x['total_games'], reverse=True)
    
    return render_template('volleyball_player_redesign.html',
        player=name,
        year=year,
        all_years=all_years,
        stats=overall_stats,
        game_cards=game_cards,
        total_games=total_games)


@app.route('/add_other_game/', methods=('GET', 'POST'))
@login_required
def add_other_game():
    return add_other_game_redesign()


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

@app.route('/other_games/<year>/<game_name>')
def other_games_by_year_and_name(year, game_name):
    from other_functions import total_game_name_stats
    all_years = all_other_years()
    all_games = other_year_games(year)
    # Filter games by game_name
    games = [g for g in all_games if g.get('game_name') == game_name]
    # Calculate stats for this game type
    stats = total_game_name_stats(games)
    return render_template('other_games.html', all_years=all_years, games=games, year=year, game_name=game_name, stats=stats)


@app.route('/edit_other_game/<int:id>/',methods = ['GET','POST'])
def update_other_game(id):
    game_id = id
    x = find_other_game(game_id)
    if not x:
        flash('Game not found!')
        return redirect(url_for('edit_other_games'))
    
    # Get the full game data (all 20 fields)
    game_row = x[0]
    game_data_dict = dict(game_row)
    games = other_year_games(str(date.today().year))
    players = all_other_players(games)
    
    if request.method == 'POST':
        game_type = request.form.get('game_type', '')
        game_name = request.form.get('game_name', '')
        score_type = request.form.get('score_type', 'individual')
        winners = []
        winner_scores = []
        losers = []
        loser_scores = []

        for i in range(1, 16):
            winner_name = request.form.get(f'winner{i}', '').strip()
            winner_score_value = request.form.get(f'winner{i}_score', '').strip()
            if winner_name:
                winners.append(winner_name)
                winner_scores.append(winner_score_value if score_type == 'individual' else '')

        for i in range(1, 16):
            loser_name = request.form.get(f'loser{i}', '').strip()
            loser_score_value = request.form.get(f'loser{i}_score', '').strip()
            if loser_name:
                losers.append(loser_name)
                loser_scores.append(loser_score_value if score_type == 'individual' else '')

        comment = request.form.get('comment', '')
        
        # Get team scores (for team scoring mode)
        team_winner_score = request.form.get('winner_score', '').strip()
        team_loser_score = request.form.get('loser_score', '').strip()

        if not game_type or not game_name or not winners or not losers:
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
            
            # Determine aggregate scores based on score type
            if score_type == 'team':
                aggregate_winner_score = int(team_winner_score) if team_winner_score else None
                aggregate_loser_score = int(team_loser_score) if team_loser_score else None
            else:
                aggregate_winner_score = next((int(score) for score in winner_scores if score not in ("", None)), None)
                aggregate_loser_score = next((int(score) for score in loser_scores if score not in ("", None)), None)
            
            with conn:
                game_data = tuple(
                    [game_row[1], game_type, game_name]
                    + (winners + [""] * 15)[:15]
                    + [(int(score) if score not in ("", None) else None) for score in (winner_scores + [None] * 15)[:15]]
                    + [aggregate_winner_score]
                    + (losers + [""] * 15)[:15]
                    + [(int(score) if score not in ("", None) else None) for score in (loser_scores + [None] * 15)[:15]]
                    + [aggregate_loser_score, comment, get_user_now(), game_id]
                )
                database_update_other_game(conn, game_data)
            
            # Log the action for notifications
            user = session.get('username', 'unknown')
            details = f"Game ID {game_id}: {game_type} - {game_name}; Winners: {', '.join(winners)}; Losers: {', '.join(losers)}"
            log_user_action(user, 'Edited other game', details)
            
            return redirect(url_for('edit_other_games'))
 
    return render_template('edit_other_game.html', game=game_data_dict, players=players, year=str(date.today().year))


@app.route('/delete_other_game/<int:id>/',methods = ['GET','POST'])
def delete_other_game(id):
    game_id = id
    game = find_other_game(id)
    from_add_game = request.args.get('from_add_game', 'false')
    from_redesign = request.args.get('from_redesign', 'false')
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
        
        # Redirect back to appropriate page
        if request.form.get('from_redesign') == 'true':
            return redirect(url_for('add_other_game_redesign'))
        if request.form.get('from_add_game') == 'true':
            return redirect(url_for('add_other_game'))
        return redirect(url_for('edit_other_games'))
 
    return render_template('delete_other_game.html', game=game[0], from_add_game=from_add_game, from_redesign=from_redesign)

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
    
    # Get all stats (no minimum)
    all_stats = total_game_name_stats(games)
    
    # Calculate minimum games requirement (at least 5 games to qualify)
    minimum_games = 5
    
    # Filter stats to only include players with minimum games, sorted by win %
    qualified_stats = [s for s in all_stats if s[4] >= minimum_games]
    qualified_stats.sort(key=lambda x: x[3], reverse=True)
    
    return render_template('game_name_stats.html', 
        qualified_stats=qualified_stats,
        all_stats=all_stats, 
        game_name=game_name,
        all_years=all_years, 
        minimum_games=minimum_games, 
        year=year)

@app.route('/game_name_stats/<game_name>/<year>/')
def game_name_stats_with_year(game_name, year):
    all_years = game_name_years(game_name)
    games = game_name_games(year, game_name)
    
    # Get all stats (no minimum)
    all_stats = total_game_name_stats(games)
    
    # Calculate minimum games requirement (at least 5 games to qualify)
    minimum_games = 5
    
    # Filter stats to only include players with minimum games, sorted by win %
    qualified_stats = [s for s in all_stats if s[4] >= minimum_games]
    qualified_stats.sort(key=lambda x: x[3], reverse=True)
    
    return render_template('game_name_stats.html', 
        qualified_stats=qualified_stats,
        all_stats=all_stats, 
        game_name=game_name,
        all_years=all_years, 
        minimum_games=minimum_games, 
        year=year)

@app.route('/player_game_stats/<year>/<game_name>/<player_name>/')
def player_game_stats(year, game_name, player_name):
    from other_functions import player_game_name_games, player_game_name_stats, game_name_years
    
    all_years = game_name_years(game_name)
    games = player_game_name_games(year, game_name, player_name)
    stats = player_game_name_stats(games, player_name)
    
    return render_template('player_game_stats.html',
        player_name=player_name,
        game_name=game_name,
        year=year,
        all_years=all_years,
        stats=stats,
        games=games)


@app.route('/player_game_stats_redesign/<year>/<game_name>/<player_name>/')
def player_game_stats_redesign(year, game_name, player_name):
    """Redesigned player game stats page for specific game types."""
    from other_functions import player_game_name_games, player_game_name_stats, game_name_years
    
    all_years = game_name_years(game_name)
    games = player_game_name_games(year, game_name, player_name)
    stats = player_game_name_stats(games, player_name)
    
    return render_template('player_game_stats_redesign.html',
        player_name=player_name,
        game_name=game_name,
        year=year,
        all_years=all_years,
        stats=stats,
        games=games)


# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Get the 'next' parameter for redirect after login
    next_url = request.args.get('next')
    
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
                # Redirect to next_url if provided, otherwise index
                return redirect(next_url if next_url else url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember_me = request.form.get('remember_me') == 'on'
        next_url = request.form.get('next')  # Get from hidden form field
        
        if username in USERS and USERS[username] == password:
            session['logged_in'] = True
            session['username'] = username
            flash(f'Successfully logged in as {username}!', 'success')
            
            # Show notifications to Kyle if there are any unread ones
            if username == 'kyle':
                notifications = get_unread_notifications()
                if notifications:
                    flash(f'You have {len(notifications)} unread notification(s) from other users. Check the notifications menu.', 'info')
            
            # Redirect to next_url if provided, otherwise index
            redirect_url = next_url if next_url else url_for('index')
            response = make_response(redirect(redirect_url))
            
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
    
    return render_template('login_redesign.html')

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

@app.route('/api/set_timezone', methods=['POST'])
def set_timezone():
    """Store the user's timezone in the session (detected from browser)"""
    data = request.get_json()
    if data and 'timezone' in data:
        session['timezone'] = data['timezone']
        return jsonify({'status': 'ok', 'timezone': data['timezone']})
    return jsonify({'status': 'error', 'message': 'No timezone provided'}), 400

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

@app.route('/api/other_game_info/<game_name>')
def get_other_game_info(game_name):
    """API endpoint to get game type and score type for a given game name"""
    from other_functions import get_score_type_for_game
    games = other_year_games('All years')
    game_type = other_game_type_for_name(games, game_name)
    score_type = get_score_type_for_game(game_name)
    return {
        'game_type': game_type,
        'score_type': score_type
    }

@app.route('/api/delete_games', methods=['POST'])
@login_required
def api_delete_games():
    """API endpoint to delete multiple games at once"""
    data = request.get_json()
    game_ids = data.get('game_ids', [])
    game_type = data.get('game_type', 'doubles')  # doubles, vollis, or other
    
    if not game_ids:
        return {'success': False, 'error': 'No game IDs provided'}, 400
    
    deleted = 0
    user = session.get('username', 'unknown')
    
    for game_id in game_ids:
        try:
            if game_type == 'doubles':
                game = find_game(game_id)
                if game and len(game) > 0:
                    game_data = game[0]
                    details = f"Game ID {game_id}: {game_data[2]}/{game_data[3]} vs {game_data[5]}/{game_data[6]}"
                    log_user_action(user, 'Deleted doubles game (bulk)', details)
                    remove_game(game_id)
                    deleted += 1
            elif game_type == 'vollis':
                game = find_vollis_game(game_id)
                if game and len(game) > 0:
                    details = f"Game ID {game_id}: {game[0][2]} vs {game[0][3]}"
                    log_user_action(user, 'Deleted vollis game (bulk)', details)
                    remove_vollis_game(game_id)
                    deleted += 1
            elif game_type == 'other':
                game = find_other_game(game_id)
                if game:
                    details = f"Game ID {game_id}"
                    log_user_action(user, 'Deleted other game (bulk)', details)
                    remove_other_game(game_id)
                    deleted += 1
        except Exception as e:
            print(f"Error deleting game {game_id}: {e}")
    
    # Clear caches and update KOBs
    if deleted > 0:
        clear_stats_cache()
        if game_type == 'doubles':
            update_kobs()
    
    return {'success': True, 'deleted': deleted}

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
    """Visual dashboard showing key doubles statistics - optimized with lazy loading"""
    from stat_functions import get_dashboard_data, grab_all_years, specific_date_stats, get_previous_date_with_games, get_next_date_with_games, get_most_recent_date_with_games, has_games_on_date
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
    
    # Get dashboard data for selected year (fast - cached)
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
    
    # Add date navigation data
    dashboard_data['today_stats'] = date_stats
    dashboard_data['current_date'] = target_date
    dashboard_data['display_date'] = display_date
    dashboard_data['previous_date'] = previous_date
    dashboard_data['next_date'] = next_date
    dashboard_data['has_previous'] = has_previous
    dashboard_data['has_next'] = has_next
    dashboard_data['current_month'] = datetime.now().month
    
    # These will be lazy-loaded via AJAX - pass empty placeholders
    dashboard_data['trueskill_rankings'] = []
    dashboard_data['top_teams'] = []
    # Note: win_streaks, loss_streaks, best_win_streaks, best_loss_streaks are already in get_dashboard_data
    # but we'll lazy load them too for faster initial render
    dashboard_data['lazy_load_enabled'] = True
    
    return render_template('dashboard.html', **dashboard_data)

@app.route('/combined_dashboard/')
def combined_dashboard():
    """Visual dashboard showing key statistics from 1v1, vollis, and other games"""
    from stat_functions import get_combined_dashboard_data, get_combined_years
    from datetime import datetime
    
    # Get selected year from query parameter, default to current year
    selected_year = request.args.get('year')
    if not selected_year:
        selected_year = str(datetime.now().year)
    
    # Get available years
    available_years = get_combined_years()
    
    # Get dashboard data for selected year
    dashboard_data = get_combined_dashboard_data(selected_year)
    dashboard_data['selected_year'] = selected_year
    dashboard_data['available_years'] = available_years
    dashboard_data['current_year'] = datetime.now().year
    dashboard_data['current_month'] = datetime.now().month
    
    return render_template('combined_dashboard.html', **dashboard_data)

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

@app.route('/api/dashboard/trueskill/')
def dashboard_trueskill():
    """API endpoint for lazy-loading TrueSkill rankings"""
    from stat_functions import calculate_trueskill_rankings, get_player_wins_losses
    from flask import jsonify
    
    selected_year = request.args.get('year', str(datetime.now().year))
    
    trueskill_rankings = calculate_trueskill_rankings(selected_year)
    
    # Get player wins/losses if not already included
    if trueskill_rankings and 'wins' not in trueskill_rankings[0]:
        player_wins_losses = get_player_wins_losses(selected_year)
        for ranking in trueskill_rankings:
            player_name = ranking['player']
            if player_name in player_wins_losses:
                ranking['wins'] = player_wins_losses[player_name]['wins']
                ranking['losses'] = player_wins_losses[player_name]['losses']
            else:
                ranking['wins'] = 0
                ranking['losses'] = 0
    
    return jsonify({'rankings': trueskill_rankings[:20]})

@app.route('/api/dashboard/streaks/')
def dashboard_streaks():
    """API endpoint for lazy-loading current win/loss streaks"""
    from stat_functions import get_current_streaks_last_365_days
    from flask import jsonify
    
    current_streaks = get_current_streaks_last_365_days()
    
    win_streaks = [streak for streak in current_streaks if streak[2] == 'win']
    loss_streaks = [streak for streak in current_streaks if streak[2] == 'loss']
    
    return jsonify({
        'win_streaks': win_streaks[:20],
        'loss_streaks': loss_streaks[:20]
    })

@app.route('/api/dashboard/best-streaks/')
def dashboard_best_streaks():
    """API endpoint for lazy-loading best streaks for a year"""
    from stat_functions import get_best_streaks_for_year
    from flask import jsonify
    
    selected_year = request.args.get('year', str(datetime.now().year))
    
    year_best_streaks = get_best_streaks_for_year(selected_year)
    best_win_streaks = [streak for streak in year_best_streaks if streak[2] == 'win']
    best_loss_streaks = [streak for streak in year_best_streaks if streak[2] == 'loss']
    
    return jsonify({
        'best_win_streaks': best_win_streaks[:20],
        'best_loss_streaks': best_loss_streaks[:20]
    })

@app.route('/api/dashboard/top-teams/')
def dashboard_top_teams():
    """API endpoint for lazy-loading top teams"""
    from stat_functions import team_stats_per_year, year_games
    from flask import jsonify
    
    selected_year = request.args.get('year', str(datetime.now().year))
    
    games = year_games(selected_year)
    if games:
        if len(games) < 70:
            minimum_games_teams = 1
        else:
            minimum_games_teams = len(games) // 70
    else:
        minimum_games_teams = 1
    
    top_teams = team_stats_per_year(selected_year, minimum_games_teams, games)
    
    # Convert to JSON-serializable format
    teams_data = []
    for team in top_teams[:20]:
        teams_data.append({
            'player1': team['team']['player1'],
            'player2': team['team']['player2'],
            'wins': team['wins'],
            'losses': team['losses'],
            'win_percentage': team['win_percentage'],
            'total_games': team['total_games']
        })
    
    return jsonify({'top_teams': teams_data})

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
    from database_functions import create_connection
    from datetime import datetime
    
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    if conn is None:
        return "Database connection error", 500
    
    cur = conn.cursor()
    
    # Check if tournaments table exists, create it if it doesn't
    cur.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='tournaments'
    """)
    table_exists = cur.fetchone()
    
    if not table_exists:
        # Create tournaments table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id integer PRIMARY KEY,
                tournament_date DATE NOT NULL,
                place text NOT NULL,
                team text NOT NULL,
                location text NOT NULL,
                tournament_name text NOT NULL
            )
        """)
        conn.commit()
    
    # Get all tournaments ordered by date (most recent first)
    cur.execute("""
        SELECT tournament_date, place, team, location, tournament_name
        FROM tournaments
        ORDER BY tournament_date DESC
    """)
    
    tournaments = cur.fetchall()
    conn.close()
    
    # Format dates for display (YYYY-MM-DD -> MM/DD/YY)
    formatted_tournaments = []
    for tourn in tournaments:
        if len(tourn) >= 5:
            date_str, place, team, location, tournament_name = tourn
            try:
                # Parse YYYY-MM-DD format
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%m/%d/%y')
            except Exception as e:
                # If date parsing fails, use the original date string
                formatted_date = date_str
            
            formatted_tournaments.append({
                'date': formatted_date,
                'place': place or '',
                'team': team or '',
                'location': location or '',
                'tournament_name': tournament_name or ''
            })
    
    return render_template('tournaments.html', tournaments=formatted_tournaments)

@app.route('/add_tournament/', methods=('GET', 'POST'))
@login_required
def add_tournament():
    """Add a new tournament"""
    from database_functions import create_connection
    from datetime import datetime
    from player_functions import get_all_players
    
    # Get all players for the partner dropdown
    all_players_full = get_all_players()
    # Extract first and last name for display, but keep full name for storage
    all_players = []
    for player in all_players_full:
        full_name = player[1] if len(player) > 1 else player  # full_name is at index 1
        if isinstance(full_name, str):
            # Extract first and last name (assume format is "First Last" or "First Middle Last")
            name_parts = full_name.strip().split()
            if len(name_parts) >= 2:
                # Take first and last name
                display_name = f"{name_parts[0]} {name_parts[-1]}"
            else:
                # If only one part, use it as is
                display_name = full_name
            all_players.append((display_name, full_name))  # (display_name, full_name)
        else:
            all_players.append((str(full_name), str(full_name)))
    
    # Get unique values from existing tournaments for dropdowns
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    teams = []
    locations = []
    tournament_names = []
    
    if conn:
        cur = conn.cursor()
        # Get unique teams
        cur.execute("SELECT DISTINCT team FROM tournaments WHERE team IS NOT NULL AND team != '' ORDER BY team")
        teams = [row[0] for row in cur.fetchall()]
        
        # Get unique locations
        cur.execute("SELECT DISTINCT location FROM tournaments WHERE location IS NOT NULL AND location != '' ORDER BY location")
        locations = [row[0] for row in cur.fetchall()]
        
        # Get unique tournament names
        cur.execute("SELECT DISTINCT tournament_name FROM tournaments WHERE tournament_name IS NOT NULL AND tournament_name != '' ORDER BY tournament_name")
        tournament_names = [row[0] for row in cur.fetchall()]
        conn.close()
    
    if request.method == 'POST':
        tournament_date = request.form.get('tournament_date', '').strip()
        place = request.form.get('place', '').strip()
        team = request.form.get('team', '').strip()
        location = request.form.get('location', '').strip()
        tournament_name = request.form.get('tournament_name', '').strip()
        
        if not tournament_date or not place or not team or not location or not tournament_name:
            flash('All fields are required!', 'error')
            # Re-fetch players in case of error
            all_players_full = get_all_players()
            all_players = []
            for player in all_players_full:
                full_name = player[1] if len(player) > 1 else player
                if isinstance(full_name, str):
                    name_parts = full_name.strip().split()
                    if len(name_parts) >= 2:
                        display_name = f"{name_parts[0]} {name_parts[-1]}"
                    else:
                        display_name = full_name
                    all_players.append((display_name, full_name))
                else:
                    all_players.append((str(full_name), str(full_name)))
            return render_template('add_tournament.html',
                                 all_players=all_players,
                                 teams=teams,
                                 locations=locations,
                                 tournament_names=tournament_names)
        else:
            # Parse date - accept YYYY-MM-DD or MM/DD/YYYY format
            try:
                if '/' in tournament_date:
                    # MM/DD/YYYY format
                    date_obj = datetime.strptime(tournament_date, '%m/%d/%Y')
                else:
                    # YYYY-MM-DD format
                    date_obj = datetime.strptime(tournament_date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%Y-%m-%d')
            except ValueError:
                flash('Invalid date format. Please use YYYY-MM-DD or MM/DD/YYYY', 'error')
                # Re-fetch players in case of error
                all_players_full = get_all_players()
                all_players = []
                for player in all_players_full:
                    full_name = player[1] if len(player) > 1 else player
                    if isinstance(full_name, str):
                        name_parts = full_name.strip().split()
                        if len(name_parts) >= 2:
                            display_name = f"{name_parts[0]} {name_parts[-1]}"
                        else:
                            display_name = full_name
                        all_players.append((display_name, full_name))
                    else:
                        all_players.append((str(full_name), str(full_name)))
                return render_template('add_tournament.html',
                                     all_players=all_players,
                                     teams=teams,
                                     locations=locations,
                                     tournament_names=tournament_names)
            
            # Insert tournament into database
            database = '/home/Idynkydnk/stats/stats.db'
            conn = create_connection(database)
            if conn is None:
                database = r'stats.db'
                conn = create_connection(database)
            
            if conn is None:
                flash('Database connection error', 'error')
                # Re-fetch players in case of error
                all_players_full = get_all_players()
                all_players = []
                for player in all_players_full:
                    full_name = player[1] if len(player) > 1 else player
                    if isinstance(full_name, str):
                        name_parts = full_name.strip().split()
                        if len(name_parts) >= 2:
                            display_name = f"{name_parts[0]} {name_parts[-1]}"
                        else:
                            display_name = full_name
                        all_players.append((display_name, full_name))
                    else:
                        all_players.append((str(full_name), str(full_name)))
                return render_template('add_tournament.html',
                                     all_players=all_players,
                                     teams=teams,
                                     locations=locations,
                                     tournament_names=tournament_names)
            
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO tournaments(tournament_date, place, team, location, tournament_name)
                    VALUES(?, ?, ?, ?, ?)
                """, (formatted_date, place, team, location, tournament_name))
                conn.commit()
                conn.close()
                
                # Log the action
                user = session.get('username', 'unknown')
                details = f"Tournament: {tournament_name} - {team} ({place}) on {formatted_date}"
                log_user_action(user, 'Added tournament', details)
                
                flash(f'Tournament added successfully!', 'success')
                return redirect(url_for('tournaments'))
            except Exception as e:
                conn.close()
                flash(f'Error adding tournament: {str(e)}', 'error')
    
    return render_template('add_tournament.html', 
                         all_players=all_players,
                         teams=teams,
                         locations=locations,
                         tournament_names=tournament_names)

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
        notes = request.form['notes'] if request.form['notes'] else None
        
        if not full_name:
            flash('Full name is required!')
        else:
            old_name = player[1]
            update_player_info(player_id, full_name, email, date_of_birth, height, notes)
            
            # Log the action for notifications
            user = session.get('username', 'unknown')
            if old_name != full_name:
                log_user_action(user, 'Edited player', f'Renamed "{old_name}" to "{full_name}"')
                flash(f'Player updated successfully! Name changed from "{old_name}" to "{full_name}" across all games.')
            else:
                log_user_action(user, 'Edited player', f'Updated info for "{full_name}"')
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

# Balloono game state (in-memory, room-based)
_balloono_rooms = {}
_balloono_lock = threading.Lock()
_ACTIVE_ROOM_SEC = 60  # Rooms with no activity for this long are excluded from list
_ROOM_IDLE_DELETE_SEC = 300  # Delete rooms idle this long

def _balloono_token_cookie():
    return request.cookies.get('balloono_token', '')

def _balloono_current_user():
    """Return (user_id, username) if valid token, else None"""
    token = _balloono_token_cookie()
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = sqlite3.connect('stats.db')
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

@app.route('/balloono')
def balloono():
    """Balloono game page. Link in menu is Kyle-only, but page is public so friends can join via URL."""
    return render_template('balloono.html')

@app.route('/api/balloono/me')
def api_balloono_me():
    """Return current Balloono user if logged in"""
    user = _balloono_current_user()
    if not user:
        return jsonify({'logged_in': False})
    user_id, username = user
    conn = sqlite3.connect('stats.db')
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
    """Register a new Balloono user"""
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
    conn = sqlite3.connect('stats.db')
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
    """Login to Balloono"""
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()[:20]
    password = data.get('password', '')
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = sqlite3.connect('stats.db')
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
    conn = sqlite3.connect('stats.db')
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
    """Logout from Balloono"""
    resp = make_response(jsonify({'ok': True}))
    resp.set_cookie('balloono_token', '', max_age=0, httponly=True, samesite='Lax')
    return resp

@app.route('/api/balloono/create_room', methods=['POST'])
def api_balloono_create_room():
    """Create a new Balloono room"""
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
            'players': [{'id': player_id, 'user_id': user_id, 'username': username, 'ready': False}],
            'messages': [{'type': 'system', 'text': f'{username} created the room.'}],
            'game': None,
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
    """Leave a room; removes room if empty"""
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
            room['messages'].append({'type': 'system', 'text': 'A player left.'})
    return jsonify({'ok': True})

@app.route('/api/balloono/rooms')
def api_balloono_list_rooms():
    """List available rooms (active, not in game, not full)"""
    now_ts = time.time()
    with _balloono_lock:
        # Delete stale rooms
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
    """Join an existing Balloono room"""
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
        room['players'].append({'id': player_id, 'user_id': user_id, 'username': username, 'ready': False})
        room['messages'].append({'type': 'system', 'text': f'{username} joined the room.'})
        room['last_activity'] = time.time()
    return jsonify({
        'room_code': room_code,
        'player_id': player_id,
        'username': username,
    })

@app.route('/api/balloono/room/<room_code>')
def api_balloono_get_room(room_code):
    """Get room state (polling)"""
    room_code = room_code.upper()
    with _balloono_lock:
        if room_code not in _balloono_rooms:
            return jsonify({'error': 'Room not found'}), 404
        room = _balloono_rooms[room_code]
        room['last_activity'] = time.time()
        room = room.copy()
        room['players'] = list(room['players'])
        room['messages'] = list(room['messages'])[-50:]
    return jsonify(room)

@app.route('/api/balloono/send_message', methods=['POST'])
def api_balloono_send_message():
    """Send a chat message"""
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
    """Start the Balloono game (both players must be in room)"""
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
        # Initialize game state (Bomberman-style)
        GRID_W, GRID_H = 15, 11
        CELL = 40
        p0 = room['players'][0]
        players_data = [
            {'id': p0['id'], 'user_id': p0.get('user_id'), 'username': p0['username'], 'x': 1, 'y': 1, 'alive': True, 'blast_level': 0, 'bombs_level': 0, 'speed_level': 0},
        ]
        if len(room['players']) >= 2:
            p1 = room['players'][1]
            players_data.append({'id': p1['id'], 'user_id': p1.get('user_id'), 'username': p1['username'], 'x': GRID_W - 2, 'y': GRID_H - 2, 'alive': True, 'blast_level': 0, 'bombs_level': 0, 'speed_level': 0})
        room['game'] = {
            'grid_w': GRID_W, 'grid_h': GRID_H, 'cell': CELL,
            'players': players_data,
            'bombs': [],
            'explosions': [],
            'powerups': [],
            'walls': [],
            'blocks': set(),
            'last_tick': datetime.now().isoformat(),
            'last_powerup_spawn': 0,
        }
        # Add indestructible blocks (border + grid pattern)
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
    """Player action: move or place bomb"""
    data = request.get_json() or {}
    room_code = (data.get('room_code') or '').strip().upper()[:6]
    player_id = data.get('player_id', '')
    action = data.get('action')  # 'up','down','left','right','bomb'
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
            last_move = player.get('_last_move_at', 0)
            if time.time() - last_move < 0.1:
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
    """Process bombs, explosions, player deaths, powerup spawning. Mutates game in place."""
    blocks_set = set((b[0], b[1]) for b in game.get('blocks', []))
    now = datetime.now()
    now_ts = time.time()
    bombs = game.get('bombs', [])
    explosions = game.get('explosions', [])
    powerups = game.setdefault('powerups', [])

    # Spawn random powerups every 20 seconds
    last_spawn = game.get('last_powerup_spawn', 0)
    if now_ts - last_spawn >= 20:
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

    # Remove expired explosions (0.4s display)
    explosions[:] = [e for e in explosions if (now - datetime.fromisoformat(e['at'])).total_seconds() < 0.4]

    # Check bombs for explosion (2.5s fuse) with chain reaction
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
        # Update stats
        try:
            conn = sqlite3.connect('stats.db')
            cur = conn.cursor()
            if winner.get('user_id'):
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
    """Reset game so players can start a new round"""
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
    """Get current game state (polling during game)"""
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
        g['players'] = [{k: v for k, v in p.items() if not k.startswith('_')} for p in g['players']]
        g['bombs'] = list(g.get('bombs', []))
        g['explosions'] = list(g.get('explosions', []))
        g['powerups'] = list(g.get('powerups', []))
        g['messages'] = list(room.get('messages', []))[-50:]
    return jsonify({'game': g})

@app.route('/benchmarks')
def benchmarks():
    """Performance benchmarks page - kyle only"""
    if session.get('username') != 'kyle':
        flash('Access denied. This page is only available to administrators.', 'error')
        return redirect(url_for('index'))
    
    # Load all benchmark files from benchmarks folder
    benchmarks_dir = os.path.join(os.path.dirname(__file__), 'benchmarks')
    benchmark_list = []
    
    if os.path.exists(benchmarks_dir):
        for filename in sorted(os.listdir(benchmarks_dir), reverse=True):
            if filename.endswith('.json'):
                filepath = os.path.join(benchmarks_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        data['filename'] = filename
                        benchmark_list.append(data)
                except Exception as e:
                    print(f"Error loading benchmark {filename}: {e}")
    
    return render_template('benchmarks.html', benchmarks=benchmark_list)

@app.route('/run_benchmark', methods=['POST'])
def run_benchmark():
    """Run a new benchmark - kyle only"""
    if session.get('username') != 'kyle':
        return jsonify({'success': False, 'error': 'Access denied'})
    
    import time
    from statistics import mean, stdev
    
    # Routes to benchmark
    routes = [
        ('/', 'Homepage'),
        ('/stats/2025/', 'Stats 2025'),
        ('/stats/2026/', 'Stats 2026'),
        ('/dashboard/', 'Dashboard'),
        ('/combined_dashboard/', 'Combined Dashboard'),
        ('/player_list/', 'Player List'),
        ('/player_trends/', 'Player Trends'),
        ('/games/', 'Games List'),
        ('/vollis_games/', 'Vollis Games'),
        ('/one_v_one_games/', 'One v One Games'),
        ('/other_games/', 'Other Games'),
        ('/vollis_stats/', 'Vollis Stats'),
        ('/one_v_one_stats/', 'One v One Stats'),
        ('/other_stats/', 'Other Stats'),
        ('/volleyball_stats/', 'Volleyball Stats'),
        ('/advanced_stats/', 'Advanced Stats'),
        ('/glicko_rankings/', 'Glicko Rankings'),
        ('/trueskill_rankings/', 'TrueSkill Rankings'),
        ('/kobs/', 'KOBs'),
        ('/tournaments/', 'Tournaments'),
        ('/top_teams/', 'Top Teams'),
        ('/game_hub', 'Game Hub'),
    ]
    
    results = []
    runs = 3
    
    with app.test_client() as client:
        # Login first to access protected pages
        client.post('/login', data={'username': 'kyle', 'password': 'stats2025'})
        
        for route, name in routes:
            times = []
            errors = []
            
            for _ in range(runs):
                try:
                    start = time.perf_counter()
                    response = client.get(route)
                    elapsed = time.perf_counter() - start
                    
                    if response.status_code == 200:
                        times.append(elapsed)
                    else:
                        errors.append(f"HTTP {response.status_code}")
                except Exception as e:
                    errors.append(str(e))
            
            results.append({
                'route': route,
                'name': name,
                'times': times,
                'avg': mean(times) if times else None,
                'min': min(times) if times else None,
                'max': max(times) if times else None,
                'stdev': stdev(times) if len(times) > 1 else 0,
                'errors': errors,
                'runs': runs,
                'successful_runs': len(times),
            })
    
    # Save results
    benchmarks_dir = os.path.join(os.path.dirname(__file__), 'benchmarks')
    os.makedirs(benchmarks_dir, exist_ok=True)
    
    timestamp = datetime.now().isoformat()
    filename = f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(benchmarks_dir, filename)
    
    data = {
        'timestamp': timestamp,
        'results': results,
    }
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    
    return jsonify({'success': True, 'filename': filename})

@app.route('/delete_benchmark/<filename>', methods=['POST'])
def delete_benchmark(filename):
    """Delete a benchmark file - kyle only"""
    if session.get('username') != 'kyle':
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    # Sanitize filename to prevent directory traversal
    if '..' in filename or '/' in filename:
        flash('Invalid filename.', 'error')
        return redirect(url_for('benchmarks'))
    
    benchmarks_dir = os.path.join(os.path.dirname(__file__), 'benchmarks')
    filepath = os.path.join(benchmarks_dir, filename)
    
    if os.path.exists(filepath):
        os.remove(filepath)
        flash('Benchmark deleted.', 'success')
    else:
        flash('Benchmark not found.', 'error')
    
    return redirect(url_for('benchmarks'))

@app.route('/testing_lab')
def testing_lab():
    """Testing lab for email and AI features"""
    if 'username' not in session:
        flash('Please login to access the testing lab', 'error')
        return redirect(url_for('login'))
    
    # Try to list available models for debugging
    available_models = None
    try:
        import google.generativeai as genai
        import os
        api_key = os.environ.get('GEMINI_API_KEY')
        if api_key:
            genai.configure(api_key=api_key)
            models = genai.list_models()
            available_models = [model.name for model in models if 'generateContent' in model.supported_generation_methods]
    except Exception as e:
        available_models = f"Error listing models: {str(e)}"
    
    return render_template('testing_lab.html', available_models=available_models)

@app.route('/generate_ai_summary', methods=['POST'])
def generate_ai_summary():
    """Generate AI summary for a specific date"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    import google.generativeai as genai
    import os
    
    # Check if Gemini API key is configured
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return jsonify({
            'success': False,
            'error': 'Gemini API key not configured. Please set GEMINI_API_KEY environment variable.'
        }), 400
    
    # Get the date from the request
    target_date = request.form.get('date', None)
    if not target_date:
        yesterday = datetime.now().date() - timedelta(days=1)
        target_date = yesterday.strftime('%Y-%m-%d')
    
    try:
        # Get stats for the date
        stats, games = specific_date_stats(target_date)
        
        if not games:
            return jsonify({
                'success': False,
                'error': f'No games found for {target_date}'
            }), 404
        
        # Build context for AI
        context = f"Date: {target_date}\n"
        context += f"Total Games: {len(games)}\n\n"
        context += "Player Stats:\n"
        for stat in stats[:10]:
            player_name = stat[0]
            wins = stat[1]
            losses = stat[2]
            win_pct = stat[3] * 100
            differential = stat[4]
            context += f"- {player_name}: {wins}-{losses} ({win_pct:.1f}%), Point Diff: {differential:+d}\n"
        
        context += f"\nGames Played:\n"
        for game in games[:5]:
            winners = f"{game[2]} & {game[3]}"
            losers = f"{game[5]} & {game[6]}"
            score = f"{game[4]}-{game[7]}"
            context += f"- {winners} def. {losers} ({score})\n"
        
        # Configure Gemini with stable model
        genai.configure(api_key=api_key)
        
        # Use the stable fast model from your available models list
        model = genai.GenerativeModel('models/gemini-flash-latest')
        
        # Generate summary
        prompt = f"""Write a fun, engaging 2-3 paragraph summary of these volleyball games. 
        Highlight the top performers, most exciting matches, and any notable achievements. 
        Make it conversational and entertaining, like a sports announcer recapping the day.

{context}

Write the summary:"""
        
        response = model.generate_content(prompt)
        summary = response.text
        
        return jsonify({
            'success': True,
            'summary': summary,
            'date': target_date,
            'games_count': len(games)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to generate summary: {str(e)}'
        }), 500

def format_name_for_email(name):
    if not name:
        return ""
    name = str(name).strip()
    if not name:
        return ""
    if ' ' in name:
        first, rest = name.split(' ', 1)
        return f"{first}<br>{rest}"
    if len(name) > 10:
        mid = len(name) // 2
        return f"{name[:mid]}<br>{name[mid:]}"
    return f"{name}<br>&nbsp;"


def create_doubles_email_html(summary, stats, games, date_obj):
    summary_html = summary.replace(chr(10), '<br>') if summary else ''
    formatted_date = date_obj.strftime('%m/%d/%Y')

    html_body = f"""
            <html>
            <head>
                <style>
                    body {{ 
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                        background-color: #0b0f14;
                        color: #e4e8eb;
                        padding: 20px;
                        line-height: 1.6;
                        margin: 0;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                    }}
                    h1 {{
                        color: #66d9ef;
                        text-align: center;
                        margin-bottom: 24px;
                        font-size: 22px;
                        font-weight: 600;
                    }}
                    .card {{
                        background: #131a24;
                        border-radius: 12px;
                        padding: 20px;
                        margin-bottom: 16px;
                        border: 1px solid rgba(255, 255, 255, 0.08);
                    }}
                    .card h2 {{
                        margin-top: 0;
                        padding-bottom: 12px;
                        font-size: 14px;
                        font-weight: 600;
                        margin-bottom: 16px;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                        color: #66d9ef;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                    }}
                    .summary-text {{
                        background: rgba(11, 15, 20, 0.5);
                        border-radius: 8px;
                        padding: 16px;
                        border: 1px solid rgba(255, 255, 255, 0.06);
                        color: #e4e8eb;
                        line-height: 1.7;
                        font-size: 14px;
                    }}
                    .stats-table {{
                        width: 100%;
                        border-collapse: collapse;
                        color: #e4e8eb;
                        font-size: 13px;
                    }}
                    .stats-table thead {{
                        background: rgba(255, 255, 255, 0.03);
                    }}
                    .stats-table th {{
                        padding: 10px 8px;
                        text-align: center;
                        font-size: 11px;
                        font-weight: 600;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        color: #8b949e;
                    }}
                    .stats-table td {{
                        padding: 10px 8px;
                        text-align: center;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                    }}
                    .stats-table tbody tr:last-child td {{
                        border-bottom: none;
                    }}
                    .stats-table tbody tr:nth-child(odd) {{
                        background: rgba(255, 255, 255, 0.02);
                    }}
                    .stats-rank {{
                        width: 30px;
                        font-weight: 600;
                        color: #66d9ef;
                    }}
                    .stats-player {{
                        text-align: left !important;
                        font-weight: 500;
                    }}
                    .diff-positive {{
                        color: #4ade80;
                        font-weight: 600;
                    }}
                    .diff-negative {{
                        color: #f87171;
                        font-weight: 600;
                    }}
                    .games-table {{
                        width: 100%;
                        border-collapse: collapse;
                        color: #e4e8eb;
                        font-size: 13px;
                    }}
                    .games-table thead {{
                        background: rgba(255, 255, 255, 0.03);
                    }}
                    .games-table th {{
                        padding: 10px 6px;
                        text-align: center;
                        font-size: 11px;
                        font-weight: 600;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        color: #8b949e;
                    }}
                    .games-table td {{
                        padding: 10px 6px;
                        text-align: center;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                        vertical-align: middle;
                    }}
                    .games-table tbody tr:last-child td {{
                        border-bottom: none;
                    }}
                    .games-table tbody tr:nth-child(odd) {{
                        background: rgba(255, 255, 255, 0.02);
                    }}
                    .time-cell {{
                        font-size: 12px;
                        color: #8b949e;
                    }}
                    .team-cell {{
                        text-align: center;
                    }}
                    .winner-team {{
                        color: #4ade80;
                    }}
                    .loser-team {{
                        color: #f87171;
                    }}
                    .player-name {{
                        font-size: 13px;
                        font-weight: 500;
                        display: block;
                        line-height: 1.4;
                    }}
                    .score-winner {{
                        color: #4ade80;
                        font-weight: 700;
                        font-size: 15px;
                    }}
                    .score-loser {{
                        color: #f87171;
                        font-weight: 700;
                        font-size: 15px;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 24px;
                        padding-top: 20px;
                        border-top: 1px solid rgba(255, 255, 255, 0.08);
                    }}
                    .link-button {{
                        display: inline-block;
                        background-color: #66d9ef;
                        color: #0b0f14;
                        padding: 12px 24px;
                        border-radius: 8px;
                        text-decoration: none;
                        font-weight: 600;
                        font-size: 14px;
                    }}
                    .opt-in-section {{
                        margin-top: 16px;
                        padding-top: 16px;
                        border-top: 1px solid rgba(255, 255, 255, 0.05);
                    }}
                    .opt-in-text {{
                        color: #8b949e;
                        font-size: 13px;
                        margin-bottom: 10px;
                    }}
                    .opt-in-button {{
                        display: inline-block;
                        background-color: rgba(102, 217, 239, 0.15);
                        color: #66d9ef;
                        padding: 10px 20px;
                        border-radius: 6px;
                        text-decoration: none;
                        font-weight: 500;
                        font-size: 13px;
                        border: 1px solid rgba(102, 217, 239, 0.3);
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Volleyball Recap - {formatted_date}</h1>
                    
                    <div class="card">
                        <h2>AI Summary</h2>
                        <div class="summary-text">
                            {summary_html}
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>Player Stats</h2>
                        <table class="stats-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Player</th>
                                    <th>W</th>
                                    <th>L</th>
                                    <th>Win %</th>
                                    <th>+/-</th>
                                </tr>
                            </thead>
                            <tbody>
            """

    for index, stat in enumerate(stats, start=1):
        player_name = stat[0]
        wins = stat[1]
        losses = stat[2]
        win_pct = stat[3] * 100
        differential = stat[4]
        diff_sign = '+' if differential >= 0 else ''

        if differential > 0:
            diff_class = "diff-positive"
        elif differential < 0:
            diff_class = "diff-negative"
        else:
            diff_class = ""

        html_body += f"""
                                <tr>
                                    <td class="stats-rank">{index}</td>
                                    <td class="stats-player">{format_name_for_email(player_name)}</td>
                                    <td>{wins}</td>
                                    <td>{losses}</td>
                                    <td>{win_pct:.0f}%</td>
                                    <td class="{diff_class}">{diff_sign}{differential}</td>
                                </tr>
                """

    html_body += """
                            </tbody>
                        </table>
                    </div>
                    
                    <div class="card">
                        <h2>Games (""" + str(len(games)) + """)</h2>
                        <table class="games-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Winners</th>
                                    <th></th>
                                    <th>Losers</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
            """

    for game in games:
        time_display = ""
        if len(game) > 1 and game[1]:
            date_time_str = str(game[1]).strip()
            parts = date_time_str.split()
            if len(parts) > 1:
                time_display = " ".join(parts[1:]).strip()
            elif parts:
                time_display = parts[0]
        if not time_display:
            time_display = "-"

        winner1 = format_name_for_email(game[2]) if game[2] else ""
        winner2 = format_name_for_email(game[3]) if game[3] else ""
        loser1 = format_name_for_email(game[5]) if game[5] else ""
        loser2 = format_name_for_email(game[6]) if game[6] else ""

        winner_score = game[4] if len(game) > 4 and game[4] is not None else ""
        loser_score = game[7] if len(game) > 7 and game[7] is not None else ""

        html_body += f"""
                                <tr>
                                    <td class="time-cell">{time_display}</td>
                                    <td class="team-cell winner-team"><span class="player-name">{winner1}</span><span class="player-name">{winner2}</span></td>
                                    <td class="score-winner">{winner_score}</td>
                                    <td class="team-cell loser-team"><span class="player-name">{loser1}</span><span class="player-name">{loser2}</span></td>
                                    <td class="score-loser">{loser_score}</td>
                                </tr>
                """

    html_body += """
                            </tbody>
                        </table>
                    </div>
            """

    stats_year = date_obj.year

    html_body += f"""
                    <div class="footer">
                        <a href="https://idynkydnk.pythonanywhere.com/stats/{stats_year}/" class="link-button">View {stats_year} Stats</a>
                        <div class="opt-in-section">
                            <p class="opt-in-text">Want all future AI summaries?</p>
                            <a href="https://idynkydnk.pythonanywhere.com/opt_in_ai_emails?email={{{{EMAIL_PLACEHOLDER}}}}" class="opt-in-button">Yes, include me</a>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """

    return html_body


def create_one_v_one_email_html(summary, stats, games):
    summary_html = summary.replace(chr(10), '<br>') if summary else ''

    html_body = f"""
            <html>
            <head>
                <style>
                    body {{ 
                        font-family: 'Open Sans', Arial, Helvetica, sans-serif;
                        background-color: #1d2025;
                        color: #ffffff;
                        padding: 20px;
                        line-height: 1.6;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                    }}
                    h1 {{
                        color: #aeee98;
                        text-align: center;
                        margin-bottom: 30px;
                    }}
                    .card {{
                        background: linear-gradient(140deg, rgba(34, 52, 70, 0.95), rgba(18, 28, 40, 0.95));
                        border-radius: 20px;
                        padding: 24px;
                        margin-bottom: 22px;
                        border: 1px solid rgba(174, 238, 152, 0.32);
                        box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
                    }}
                    .card h2 {{
                        margin-top: 0;
                        padding-bottom: 10px;
                        text-align: center;
                        font-size: 18px;
                        font-weight: bold;
                        margin-bottom: 18px;
                        text-transform: uppercase;
                        letter-spacing: 0.6px;
                        color: #aeee98;
                        border-bottom: 2px solid rgba(174, 238, 152, 0.45);
                    }}
                    .summary-text {{
                        background: rgba(12, 18, 25, 0.6);
                        border-radius: 18px;
                        padding: 16px;
                        border: 1px solid rgba(174, 238, 152, 0.25);
                        color: #ffffff;
                        line-height: 1.7;
                    }}
                    .table-wrapper {{
                        background: rgba(12, 18, 25, 0.6);
                        border-radius: 18px;
                        padding: 16px;
                    }}
                    .stat-item {{
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        padding: 12px;
                        border-radius: 8px;
                        margin-bottom: 8px;
                        color: #ffffff;
                    }}
                    .stat-item:last-child {{
                        margin-bottom: 0;
                    }}
                    .stat-item.win {{
                        background-color: rgba(76, 175, 80, 0.1);
                        border-left: 4px solid #4CAF50;
                    }}
                    .stat-item.loss {{
                        background-color: rgba(244, 67, 54, 0.1);
                        border-left: 4px solid #f44336;
                    }}
                    .stat-item.neutral {{
                        background-color: rgba(158, 158, 158, 0.1);
                        border-left: 4px solid #9E9E9E;
                    }}
                    .player-name-stat {{
                        font-size: 14px;
                        font-weight: 600;
                        color: #ffffff;
                        display: inline-block;
                        text-align: center;
                        white-space: nowrap;
                    }}
                    .stat-info {{
                        display: flex;
                        align-items: center;
                        gap: 12px;
                        font-size: 14px;
                    }}
                    .record-info {{
                        min-width: 60px;
                        text-align: center;
                    }}
                    .differential {{
                        min-width: 40px;
                        text-align: center;
                    }}
                    .game-item {{
                        padding: 12px;
                        border-radius: 8px;
                        border-left: 4px solid #aeee98;
                        background-color: rgba(174, 238, 152, 0.05);
                        margin-bottom: 8px;
                        color: #ffffff;
                    }}
                    .game-item:last-child {{
                        margin-bottom: 0;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 30px;
                    }}
                    .link-button {{
                        display: inline-block;
                        background-color: rgba(174, 238, 152, 0.9);
                        color: #102436;
                        padding: 12px 24px;
                        border-radius: 12px;
                        text-decoration: none;
                        font-weight: bold;
                        margin: 5px;
                        box-shadow: 0 6px 15px rgba(174, 238, 152, 0.25);
                    }}
                    .link-button:hover {{
                        background-color: #c0f7a0;
                    }}
                    .today-games-table {{
                        width: 100%;
                        border-collapse: collapse;
                        color: #ffffff;
                        font-size: 14px;
                        background: rgba(17, 22, 28, 0.6);
                        border-radius: 18px;
                        overflow: hidden;
                    }}
                    .today-games-table thead {{
                        background: rgba(36, 56, 76, 0.85);
                    }}
                    .today-games-table th {{
                        padding: 12px 10px;
                        text-align: center;
                        font-size: 12px;
                        font-weight: 700;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                        color: #dbe2ea;
                    }}
                    .today-games-table td {{
                        padding: 14px 10px;
                        text-align: center;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                        vertical-align: middle;
                    }}
                    .today-games-table tbody tr:last-child td {{
                        border-bottom: none;
                    }}
                    .time-cell {{
                        font-weight: 600;
                        color: #aeee98;
                        font-size: 14px;
                    }}
                    .team-cell {{
                        text-align: center;
                    }}
                    .player-line {{
                        font-size: 13px;
                        font-weight: 600;
                        color: #ffffff;
                        margin: 2px 0;
                        white-space: nowrap;
                        display: inline-block;
                        text-align: center;
                    }}
                    .score-cell {{
                        width: 42px;
                    }}
                    .score-pill {{
                        display: inline-block;
                        min-width: 34px;
                        padding: 6px 10px;
                        border-radius: 10px;
                        font-size: 14px;
                        font-weight: 700;
                        letter-spacing: 0.5px;
                    }}
                    .score-pill.winner {{
                        background: rgba(76, 175, 80, 0.18);
                        color: #aeee98;
                        box-shadow: inset 0 0 0 1px rgba(174, 238, 152, 0.45);
                    }}
                    .score-pill.loser {{
                        background: rgba(244, 67, 54, 0.18);
                        color: #ff8686;
                        box-shadow: inset 0 0 0 1px rgba(255, 134, 134, 0.4);
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🎯 Today's 1v1 Recap</h1>
                    
                    <div class="card">
                        <h2>AI Summary</h2>
                        <div class="summary-text">
                            {summary_html}
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>Player Stats</h2>
            """

    for stat in stats:
        player_name = stat[0]
        wins = stat[1]
        losses = stat[2]
        win_pct = stat[3] * 100
        differential = stat[4]
        diff_sign = '+' if differential >= 0 else ''

        if win_pct > 50:
            color_class = "win"
        elif win_pct == 50:
            color_class = "neutral"
        else:
            color_class = "loss"

        html_body += f"""
                        <div class="stat-item {color_class}">
                            <span class="player-name-stat">{format_name_for_email(player_name)}</span>
                            <span class="stat-info">
                                <span class="record-info">{wins}-{losses} ({win_pct:.1f}%)</span>
                                <span class="differential">{diff_sign}{differential}</span>
                            </span>
                        </div>
                """

    html_body += """
                    </div>
                    
                    <div class="card">
                        <h2>Today's 1v1 Games (""" + str(len(games)) + """)</h2>
                        <div class="table-wrapper">
                        <table class="today-games-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Winner</th>
                                    <th>Score</th>
                                    <th>Loser</th>
                                    <th>Score</th>
                                </tr>
                            </thead>
                            <tbody>
            """

    for game in games:
        time_display = ""
        if len(game) > 1 and game[1]:
            date_time_str = str(game[1]).strip()
            parts = date_time_str.split()
            if len(parts) > 1:
                time_display = " ".join(parts[1:]).strip()
            elif parts:
                time_display = parts[0]
        if not time_display:
            time_display = "&nbsp;"

        winner_name = game[4] if len(game) > 4 and game[4] else ""
        loser_name = game[6] if len(game) > 6 and game[6] else ""
        winner_score = game[5] if len(game) > 5 and game[5] is not None else ""
        loser_score = game[7] if len(game) > 7 and game[7] is not None else ""

        html_body += f"""
                                <tr>
                                    <td class=\"time-cell\">{time_display}</td>
                                    <td class=\"team-cell\"><div class=\"player-line\">{format_name_for_email(winner_name)}</div></td>
                                    <td class=\"score-cell\"><span class=\"score-pill winner\">{winner_score}</span></td>
                                    <td class=\"team-cell\"><div class=\"player-line\">{format_name_for_email(loser_name)}</div></td>
                                    <td class=\"score-cell\"><span class=\"score-pill loser\">{loser_score}</span></td>
                                </tr>
                """

    html_body += """
                            </tbody>
                        </table>
                        </div>
                    </div>
                    <div class="footer">
                        <a href="https://idynkydnk.pythonanywhere.com/one_v_one_stats/" class="link-button">View 1v1 Stats</a>
                        <a href="https://idynkydnk.pythonanywhere.com/dashboard/" class="link-button">Go to Dashboard</a>
                    </div>
                    <div class="footer" style="margin-top: 20px; padding-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.1);">
                        <p style="color: #aeee98; font-size: 14px; margin-bottom: 10px;">Want all future AI summaries?</p>
                        <a href="https://idynkydnk.pythonanywhere.com/opt_in_ai_emails?email={{{{EMAIL_PLACEHOLDER}}}}" class="link-button" style="background-color: rgba(174, 238, 152, 0.7); font-size: 13px; padding: 10px 20px;">Yes, include me</a>
                    </div>
                </div>
            </body>
            </html>
            """

    return html_body


def build_doubles_email_payload(selected_game_ids, prompt_style='announcer', custom_prompt=''):
    import google.generativeai as genai
    from stat_functions import calculate_stats_from_games, get_current_streaks_last_365_days, convert_ampm
    from player_functions import get_player_by_name

    # Define different prompt styles
    PROMPT_STYLES = {
        'announcer': """You are an energetic sports announcer writing an exciting recap email.
Use dramatic language, exciting calls, and hype up big plays and close games.
Write like you're doing live ESPN commentary - high energy, dramatic pauses, and memorable catchphrases.
Make readers feel the excitement of being there. Use short punchy sentences mixed with longer dramatic buildups.
Keep it to 2-3 compact paragraphs.""",

        'analyst': """You are a data-driven sports analyst writing a statistical breakdown email.
Focus on the numbers: win percentages, point differentials, streaks, and trends.
Draw insights from the statistics and explain what they mean for each player's performance.
Be precise and factual, but still engaging. Reference specific stats to back up your observations.
Keep it to 2-3 compact paragraphs.""",

        'storyteller': """You are a sports storyteller writing a narrative recap email.
Weave the games into an engaging story with character development and dramatic tension.
Create narrative arcs - underdogs rising, champions defending, rivalries intensifying.
Use vivid imagery and build suspense. Make readers feel emotionally invested in the outcomes.
Keep it to 2-3 compact paragraphs.""",

        'comedian': """You are a comedy writer doing a sports recap email.
Be playful, witty, and don't be afraid to gently roast players (in good fun).
Find the humor in the games - funny moments, ironic outcomes, playful observations.
Keep it lighthearted and fun. Everyone should laugh, including those being teased.
Keep it to 2-3 compact paragraphs.""",

        'roast': """You are a brutal roast comedian writing a savage recap email.
Show absolutely NO mercy. Destroy everyone's performance with brutal honesty and savage insults.
Mock the winners for barely winning, demolish the losers for their failures.
Be creative with your insults - reference specific plays, scores, and failures.
This is all in good fun but don't hold back. Make it hurt (but funny).
Keep it to 2-3 compact paragraphs.""",

    }

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('Gemini API key not configured.')

    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        raise ValueError('Email not configured.')

    if not selected_game_ids:
        raise ValueError('No games selected.')

    # Fetch selected games by ID
    cur = set_cur()
    placeholders = ','.join('?' * len(selected_game_ids))
    cur.execute(f"SELECT * FROM games WHERE id IN ({placeholders}) ORDER BY game_date DESC", 
                [int(gid) for gid in selected_game_ids])
    raw_games = cur.fetchall()
    
    if not raw_games:
        raise ValueError('None of the selected games were found.')
    
    games = convert_ampm(raw_games)
    stats = calculate_stats_from_games(games)

    all_streaks = get_current_streaks_last_365_days()
    streaks_dict = {streak[0]: {'length': streak[1], 'type': streak[2], 'max': streak[3]} for streak in all_streaks}

    # Get date range from selected games
    game_dates = sorted(set(game[1].split(' ')[0] for game in games))
    if len(game_dates) == 1:
        date_str = game_dates[0]
    else:
        date_str = f"{game_dates[0]} to {game_dates[-1]}"
    
    context = f"Date: {date_str}\n"
    context += f"Total Games: {len(games)}\n\n"
    
    # Helper to parse height string like "5'10"" or "6'2"" to inches
    def parse_height_to_inches(height_str):
        if not height_str:
            return None
        try:
            # Handle formats like 5'10" or 5'10
            height_str = height_str.replace('"', '').replace("'", ' ').strip()
            parts = height_str.split()
            if len(parts) >= 2:
                feet = int(parts[0])
                inches = int(parts[1])
                return feet * 12 + inches
            elif len(parts) == 1:
                return int(parts[0]) * 12  # Just feet
        except:
            pass
        return None
    
    # Helper to calculate actual age (accounting for whether birthday has passed)
    def calculate_age(birth_date_str):
        try:
            birth_date = datetime.strptime(birth_date_str[:10], '%Y-%m-%d')
            today = datetime.now()
            age = today.year - birth_date.year
            # Subtract 1 if birthday hasn't occurred yet this year
            if (today.month, today.day) < (birth_date.month, birth_date.day):
                age -= 1
            return age
        except:
            return None
    
    # First pass: collect all player heights and ages to find outliers
    player_heights = {}
    player_ages = {}
    for stat in stats[:10]:
        player_name = stat[0]
        player_info = get_player_by_name(player_name)
        if player_info:
            if player_info[4]:
                height_inches = parse_height_to_inches(player_info[4])
                if height_inches:
                    player_heights[player_name] = (height_inches, player_info[4])
            if player_info[3]:
                age = calculate_age(player_info[3])
                if age:
                    player_ages[player_name] = age
    
    # Only mention height if there's a significant outlier (4+ inches from average)
    height_outliers = set()
    if len(player_heights) >= 2:
        heights = [h[0] for h in player_heights.values()]
        avg_height = sum(heights) / len(heights)
        for player_name, (height_inches, _) in player_heights.items():
            if abs(height_inches - avg_height) >= 4:
                height_outliers.add(player_name)
    
    # Only mention age if there's a significant outlier (10+ years from average)
    age_outliers = set()
    if len(player_ages) >= 2:
        ages = list(player_ages.values())
        avg_age = sum(ages) / len(ages)
        for player_name, age in player_ages.items():
            if abs(age - avg_age) >= 10:
                age_outliers.add(player_name)
    
    context += "Player Stats (with details & streaks):\n"
    for stat in stats[:10]:
        player_name = stat[0]
        wins = stat[1]
        losses = stat[2]
        win_pct = stat[3] * 100
        differential = stat[4]

        player_info = get_player_by_name(player_name)
        age_str = ""
        height_str = ""
        if player_info:
            # Only include age if this player is a notable outlier (10+ years from avg)
            if player_name in age_outliers and player_name in player_ages:
                age_str = f", Age: {player_ages[player_name]}"
            # Only include height if this player is a notable outlier (4+ inches from avg)
            if player_name in height_outliers and player_info[4]:
                height_str = f", Height: {player_info[4]}"

        streak_str = ""
        if player_name in streaks_dict:
            streak_info = streaks_dict[player_name]
            # Only mention streaks of 3+ games - shorter isn't interesting
            if streak_info['length'] >= 3:
                streak_str = f", Current Streak: {streak_info['length']} {streak_info['type']}s"

        # Only show point differential if it's significant (+/- 5 or more)
        diff_str = f", Point Diff: {differential:+d}" if abs(differential) >= 5 else ""
        context += f"- {player_name}: {wins}-{losses} ({win_pct:.1f}%){diff_str}{age_str}{height_str}{streak_str}\n"

    # Get earliest game date for historical queries
    earliest_game_date = min(raw_game[1] for raw_game in raw_games)
    
    context += "\nHistorical Context:\n"
    for game in games[:5]:
        team1 = (game[2], game[3])
        team2 = (game[5], game[6])

        cur.execute("""
                SELECT COUNT(*) FROM games 
                WHERE ((winner1 = ? AND winner2 = ?) OR (winner1 = ? AND winner2 = ?))
                  AND ((loser1 = ? AND loser2 = ?) OR (loser1 = ? AND loser2 = ?))
                  AND game_date < ?
            """, (team1[0], team1[1], team1[1], team1[0], 
                  team2[0], team2[1], team2[1], team2[0], earliest_game_date))
        team1_wins = cur.fetchone()[0]

        cur.execute("""
                SELECT COUNT(*) FROM games 
                WHERE ((winner1 = ? AND winner2 = ?) OR (winner1 = ? AND winner2 = ?))
                  AND ((loser1 = ? AND loser2 = ?) OR (loser1 = ? AND loser2 = ?))
                  AND game_date < ?
            """, (team2[0], team2[1], team2[1], team2[0],
                  team1[0], team1[1], team1[1], team1[0], earliest_game_date))
        team2_wins = cur.fetchone()[0]

        # Only mention historical record if teams have played 3+ times
        total_games = team1_wins + team2_wins
        if total_games >= 3:
            context += f"- {team1[0]} & {team1[1]} vs {team2[0]} & {team2[1]}: Historical record {team1_wins}-{team2_wins}\n"

    context += "\nGames Played (in chronological order):\n"
    for game in reversed(games[:10]):
        winners = f"{game[2]} & {game[3]}"
        losers = f"{game[5]} & {game[6]}"
        score = f"{game[4]}-{game[7]}"
        comment_str = ""
        if len(game) > 9 and game[9]:
            comment_str = f" - Comment: {game[9]}"
        context += f"- {winners} def. {losers} ({score}){comment_str}\n"

    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-flash-latest')

    # Get the prompt style instructions
    if prompt_style == 'custom' and custom_prompt.strip():
        style_instructions = custom_prompt.strip() + "\nKeep it to 2-3 compact paragraphs."
    else:
        style_instructions = PROMPT_STYLES.get(prompt_style, PROMPT_STYLES['announcer'])
    
    prompt = f"""{style_instructions}

Write in clean, professional sentences—no bullet points, asterisks, emojis, or decorative quotation marks.
Only quote a comment if it is already in the data enclosed in quotation marks.
Weave any comments smoothly into the narrative.

Here is the game data:

{context}

Write the recap:"""
    response = model.generate_content(prompt)
    summary = getattr(response, 'text', '') or ''

    players_set = set()
    for game in games:
        for player_name in [game[2], game[3], game[5], game[6]]:
            if player_name and player_name.strip():
                players_set.add(player_name)

    players = []
    players_without_email = []
    for player_name in players_set:
        player_info = get_player_by_name(player_name)
        if player_info and player_info[2]:
            players.append({'name': player_name, 'email': player_info[2]})
        else:
            players_without_email.append(player_name)

    all_emails = [player['email'] for player in players]
    
    # Add emails from players who opted in to receive all AI emails
    cur = set_cur()
    cur.execute("SELECT email FROM players WHERE email IS NOT NULL AND notes LIKE ?", ('%AI_EMAILS_OPT_IN%',))
    opted_in_players = cur.fetchall()
    for opt_in_player in opted_in_players:
        opt_in_email = opt_in_player[0]
        if opt_in_email and opt_in_email not in all_emails:
            all_emails.append(opt_in_email)

    # Parse earliest game date for email subject
    date_obj = datetime.strptime(earliest_game_date[:10], '%Y-%m-%d')
    formatted_date = date_obj.strftime('%m/%d/%y')

    html_body = create_doubles_email_html(summary, stats, games, date_obj)
    subject = f"Vball Summary - {formatted_date}"

    summary_preview = summary[:150] + "..." if len(summary) > 150 else summary

    return {
        'date': date_str,
        'games': games,
        'stats': stats,
        'summary': summary,
        'summary_preview': summary_preview,
        'context': context,
        'players': players,
        'players_without_email': players_without_email,
        'all_emails': all_emails,
        'html_body': html_body,
        'subject': subject,
        'date_obj': date_obj,
        'formatted_date': formatted_date
    }


def build_one_v_one_email_payload(selected_game_ids):
    import google.generativeai as genai
    import random
    from one_v_one_functions import todays_one_v_one_stats, todays_one_v_one_games, calculate_one_v_one_stats_from_games
    from player_functions import get_player_by_name

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('Gemini API key not configured.')

    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        raise ValueError('Email not configured.')

    today = date.today().strftime('%Y-%m-%d')
    all_games = todays_one_v_one_games()

    if not all_games:
        raise ValueError(f'No 1v1 games found for today ({today})')

    selected_ids_set = set(str(gid) for gid in selected_game_ids if gid)
    if selected_ids_set:
        games = [game for game in all_games if str(game[0]) in selected_ids_set]
        if not games:
            raise ValueError('None of the selected games were found.')
        stats = calculate_one_v_one_stats_from_games(games)
    else:
        games = all_games
        stats = todays_one_v_one_stats()

    context = f"Date: {today}\n"
    context += f"Total 1v1 Games: {len(games)}\n\n"
    context += "Player Stats (with details):\n"

    for stat in stats[:10]:
        player_name = stat[0]
        wins = stat[1]
        losses = stat[2]
        win_pct = stat[3] * 100
        differential = stat[4]

        player_info = get_player_by_name(player_name)
        age_str = ""
        height_str = ""
        if player_info:
            if player_info[3]:
                try:
                    birth_date = datetime.strptime(player_info[3][:10], '%Y-%m-%d')
                    age = datetime.now().year - birth_date.year
                    age_str = f", Age: {age}"
                except Exception:
                    pass
            if player_info[4]:
                height_str = f", Height: {player_info[4]}"

        context += f"- {player_name}: {wins}-{losses} ({win_pct:.1f}%), Point Diff: {differential:+d}{age_str}{height_str}\n"

    context += "\n1v1 Games Played Today (in chronological order):\n"
    for game in reversed(games[:10]):
        winner = game[4]
        loser = game[6]
        score = f"{game[5]}-{game[7]}"
        game_name = game[3] if len(game) > 3 else "1v1"
        time_display = ""
        if len(game) > 1 and game[1]:
            date_time_str = str(game[1]).strip()
            parts = date_time_str.split()
            if len(parts) > 1:
                time_display = " ".join(parts[1:]).strip()
            elif parts:
                time_display = parts[0]
        time_suffix = f" ({time_display})" if time_display else ""
        context += f"- {winner} def. {loser} ({score}) - {game_name}{time_suffix}\n"

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-flash-latest')

    num_games = len(games)
    if num_games <= 2:
        length_guide = "1-2 sentences"
    elif num_games <= 5:
        length_guide = "1 short paragraph (3-4 sentences)"
    elif num_games <= 10:
        length_guide = "2 paragraphs"
    else:
        length_guide = "3 paragraphs"

    prompts = [
        f"""Write a fun, engaging summary of these 1v1 games in {length_guide}. 
            Highlight the top performers, most exciting matches, and any notable achievements. 
            Use clear sentences without bullet points, asterisks, emojis, or decorative quotation marks. 
            Only quote a comment if it already appears in quotation marks in the data.
            Make it conversational and entertaining.

{context}

Write the summary:""",
        f"""You're a witty sports journalist writing a 1v1 games recap in {length_guide}. 
            Create a story about today's action, weaving in interesting context when relevant. 
            Stay away from bullet points, asterisks, emojis, or unnecessary quotation marks. 
            Only quote comments if they are already quoted. 
            Focus on rivalries, upsets, and standout performances.

{context}

Write the recap:""",
        f"""Write a {length_guide} 1v1 games recap as if you're texting a friend who missed the action. 
            Be casual and highlight the wild moments.
            Avoid bullet lists, asterisks, emojis, or decorative quotation marks—only quote comments that come quoted in the data.

{context}

Tell the story:"""
    ]

    prompt = random.choice(prompts)
    response = model.generate_content(prompt)
    summary = getattr(response, 'text', '') or ''

    players_set = set()
    for game in games:
        if game[4]:
            players_set.add(game[4])
        if game[6]:
            players_set.add(game[6])

    players_with_emails = []
    players_without_email = []
    for player_name in players_set:
        player_info = get_player_by_name(player_name)
        if player_info and player_info[2]:
            players_with_emails.append({'name': player_name, 'email': player_info[2]})
        else:
            players_without_email.append(player_name)

    all_emails = [player['email'] for player in players_with_emails]
    
    # Add emails from players who opted in to receive all AI emails
    from database_functions import set_cur
    cur = set_cur()
    cur.execute("SELECT email FROM players WHERE email IS NOT NULL AND notes LIKE ?", ('%AI_EMAILS_OPT_IN%',))
    opted_in_players = cur.fetchall()
    for opt_in_player in opted_in_players:
        opt_in_email = opt_in_player[0]
        if opt_in_email and opt_in_email not in all_emails:
            all_emails.append(opt_in_email)

    date_obj = datetime.strptime(today, '%Y-%m-%d')
    formatted_date = date_obj.strftime('%m/%d/%y')

    html_body = create_one_v_one_email_html(summary, stats, games)
    subject = f"Vball Summary - {formatted_date}"

    summary_preview = summary[:150] + "..." if len(summary) > 150 else summary

    return {
        'today': today,
        'games': games,
        'stats': stats,
        'summary': summary,
        'summary_preview': summary_preview,
        'context': context,
        'players': players_with_emails,
        'players_without_email': players_without_email,
        'all_emails': all_emails,
        'html_body': html_body,
        'subject': subject,
        'date_obj': date_obj,
        'formatted_date': formatted_date,
        'length_guide': length_guide
    }


@app.route('/generate_and_email_today', methods=['POST'])
def generate_and_email_today():
    """Send AI summary email - uses provided HTML from preview instead of regenerating"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    try:
        if request.is_json:
            data = request.get_json() or {}
            additional_emails = data.get('additional_emails', [])
            selected_emails = data.get('selected_emails', [])
            provided_html = data.get('email_html', None)
            provided_subject = data.get('subject', None)
        else:
            raw_additional = request.form.get('additional_emails', '')
            additional_emails = raw_additional.split(',') if raw_additional else []
            selected_emails = []
            provided_html = None
            provided_subject = None

        # Use provided HTML from preview (don't regenerate!)
        if not provided_html or not provided_subject:
            return jsonify({'success': False, 'error': 'Missing email content. Please go back and preview again.'}), 400

        # Build list of all recipient emails
        all_emails = list(selected_emails) if selected_emails else []
        
        # Append any additional email addresses provided by the user
        if additional_emails:
            for email in additional_emails:
                if isinstance(email, str):
                    email = email.strip()
                    if email and re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email) and email not in all_emails:
                        all_emails.append(email)

        if not all_emails:
            return jsonify({'success': False, 'error': 'No recipients selected.'}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to process request: {str(e)}'}), 500

    try:
        # Set sender with display name
        sender_email = app.config['MAIL_DEFAULT_SENDER']
        if '@' in sender_email and not '<' in sender_email:
            sender = f"KT Vball Summary <{sender_email}>"
        else:
            sender = sender_email
        
        # Send individual emails to each recipient with personalized opt-in link
        for recipient_email in all_emails:
            # Replace email placeholder with actual recipient email for personalized opt-in link
            html_body_personalized = provided_html.replace('{{EMAIL_PLACEHOLDER}}', recipient_email)
            
            msg = Message(subject=provided_subject, recipients=[recipient_email], sender=sender, bcc=['idynkydnk@gmail.com', 'kt@omg.lol'])
            msg.html = html_body_personalized
            mail.send(msg)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to send email: {str(e)}'}), 500

    return jsonify({
        'success': True,
        'emails_sent': len(all_emails)
    })

@app.route('/generate_and_email_today_1v1', methods=['POST'])
def generate_and_email_today_1v1():
    """Send 1v1 AI summary email - uses provided HTML from preview instead of regenerating"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    try:
        if request.is_json:
            data = request.get_json() or {}
            additional_emails = data.get('additional_emails', [])
            selected_emails = data.get('selected_emails', [])
            provided_html = data.get('email_html', None)
            provided_subject = data.get('subject', None)
        else:
            raw_additional = request.form.get('additional_emails', '')
            additional_emails = raw_additional.split(',') if raw_additional else []
            selected_emails = []
            provided_html = None
            provided_subject = None

        # Use provided HTML from preview (don't regenerate!)
        if not provided_html or not provided_subject:
            return jsonify({'success': False, 'error': 'Missing email content. Please go back and preview again.'}), 400

        # Build list of all recipient emails
        all_emails = list(selected_emails) if selected_emails else []
        
        # Append any additional email addresses provided by the user
        if additional_emails:
            for email in additional_emails:
                if isinstance(email, str):
                    email = email.strip()
                    if email and re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email) and email not in all_emails:
                        all_emails.append(email)

        if not all_emails:
            return jsonify({'success': False, 'error': 'No recipients selected.'}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to process request: {str(e)}'}), 500

    try:
        # Set sender with display name
        sender_email = app.config['MAIL_DEFAULT_SENDER']
        if '@' in sender_email and not '<' in sender_email:
            sender = f"KT Vball Summary <{sender_email}>"
        else:
            sender = sender_email
        
        # Send individual emails to each recipient with personalized opt-in link
        for recipient_email in all_emails:
            # Replace email placeholder with actual recipient email for personalized opt-in link
            html_body_personalized = provided_html.replace('{{EMAIL_PLACEHOLDER}}', recipient_email)
            
            msg = Message(subject=provided_subject, recipients=[recipient_email], sender=sender, bcc=['idynkydnk@gmail.com', 'kt@omg.lol'])
            msg.html = html_body_personalized
            mail.send(msg)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to send email: {str(e)}'}), 500

    return jsonify({
        'success': True,
        'emails_sent': len(all_emails)
    })


@app.route('/preview_ai_summary', methods=['POST'])
def preview_ai_summary():
    if 'username' not in session:
        return redirect(url_for('login'))

    selected_game_ids = request.form.getlist('game_ids')
    if not selected_game_ids:
        raw_ids = request.form.get('game_ids', '')
        if raw_ids:
            selected_game_ids = [gid for gid in raw_ids.split(',') if gid]

    if not selected_game_ids:
        flash('Please select at least one game to preview the AI summary.', 'error')
        return redirect(url_for('ai_summary_redesign'))

    try:
        payload = build_doubles_email_payload(selected_game_ids)
    except ValueError as ve:
        flash(str(ve), 'error')
        return redirect(url_for('ai_summary_redesign'))
    except Exception as e:
        flash(f'Failed to prepare summary preview: {str(e)}', 'error')
        return redirect(url_for('ai_summary_redesign'))

    selected_game_ids_json = json.dumps([str(gid) for gid in selected_game_ids])

    can_send = len(payload['players']) > 0 and len(payload['all_emails']) > 0

    return render_template(
        'preview_ai_summary_redesign.html',
        game_type='doubles',
        header_title="Doubles AI Summary Preview",
        subject=payload['subject'],
        email_html=payload['html_body'],
        players=payload['players'],
        players_without_email=payload['players_without_email'],
        selected_game_ids_json=selected_game_ids_json,
        selected_game_ids=selected_game_ids,
        send_url=url_for('generate_and_email_today'),
        back_url=url_for('ai_summary_redesign'),
        can_send=can_send,
        formatted_date=payload['formatted_date']
    )


@app.route('/preview_ai_summary_1v1', methods=['POST'])
def preview_ai_summary_1v1():
    if 'username' not in session:
        return redirect(url_for('login'))

    selected_game_ids = request.form.getlist('game_ids')
    if not selected_game_ids:
        raw_ids = request.form.get('game_ids', '')
        if raw_ids:
            selected_game_ids = [gid for gid in raw_ids.split(',') if gid]

    if not selected_game_ids:
        flash('Please select at least one game to preview the AI summary.', 'error')
        return redirect(url_for('add_one_v_one_game'))

    try:
        payload = build_one_v_one_email_payload(selected_game_ids)
    except ValueError as ve:
        flash(str(ve), 'error')
        return redirect(url_for('add_one_v_one_game'))
    except Exception as e:
        flash(f'Failed to prepare summary preview: {str(e)}', 'error')
        return redirect(url_for('add_one_v_one_game'))

    selected_game_ids_json = json.dumps([str(gid) for gid in selected_game_ids])
    can_send = len(payload['players']) > 0 and len(payload['all_emails']) > 0

    return render_template(
        'preview_ai_summary.html',
        game_type='one_v_one',
        header_title="1v1 AI Summary Preview",
        subject=payload['subject'],
        email_html=payload['html_body'],
        players=payload['players'],
        players_without_email=payload['players_without_email'],
        selected_game_ids_json=selected_game_ids_json,
        selected_game_ids=selected_game_ids,
        send_url=url_for('generate_and_email_today_1v1'),
        back_url=url_for('add_one_v_one_game'),
        can_send=can_send,
        formatted_date=payload['formatted_date']
    )


@app.route('/api/add_player', methods=['POST'])
@login_required
def api_add_player():
    """Add a new player via AJAX and ensure they appear in future dropdowns."""
    data = request.get_json() or {}
    full_name = (data.get('full_name') or '').strip()
    email = (data.get('email') or '').strip() or None
    date_of_birth = (data.get('date_of_birth') or '').strip() or None
    height = (data.get('height') or '').strip() or None
    notes = (data.get('notes') or '').strip() or None

    if not full_name:
        return jsonify({'success': False, 'error': 'Full name is required.'}), 400

    if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'success': False, 'error': 'Invalid email address.'}), 400

    from player_functions import get_player_by_name, add_new_player

    existing = get_player_by_name(full_name)
    if existing:
        return jsonify({'success': False, 'error': 'Player already exists.'}), 400

    player_id = add_new_player(full_name, email=email, date_of_birth=date_of_birth, height=height, notes=notes)

    user = session.get('username', 'unknown')
    log_user_action(user, 'Added new player', f'{full_name} ({email or "no email"})')

    return jsonify({'success': True, 'player_id': player_id})


@app.route('/api/rename_player', methods=['POST'])
@login_required
def api_rename_player():
    """Rename a player across all game types via AJAX."""
    data = request.get_json() or {}
    old_name = (data.get('old_name') or '').strip()
    new_name = (data.get('new_name') or '').strip()

    if not old_name or not new_name:
        return jsonify({'success': False, 'error': 'Both old name and new name are required.'}), 400

    if old_name == new_name:
        return jsonify({'success': False, 'error': 'New name must be different from the old name.'}), 400

    try:
        updates_made = update_player_name(old_name, new_name)
        user = session.get('username', 'unknown')
        log_user_action(user, 'Renamed player', f'"{old_name}" to "{new_name}" ({updates_made} records)')
        
        # Clear caches so stats reflect the new name
        clear_stats_cache()
        
        return jsonify({'success': True, 'updates_made': updates_made, 'message': f'Successfully renamed "{old_name}" to "{new_name}" in {updates_made} records.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/add_player_email', methods=['POST'])
@login_required
def add_player_email():
    """Add or update a player's email address from the AI summary preview."""
    data = request.get_json() or {}
    player_name = (data.get('player_name') or '').strip()
    email = (data.get('email') or '').strip()

    if not player_name or not email:
        return jsonify({'success': False, 'error': 'Player name and email are required.'}), 400

    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'success': False, 'error': 'Invalid email address.'}), 400

    from player_functions import get_player_by_name, add_new_player, update_player_info

    player_record = get_player_by_name(player_name)
    if player_record:
        player_id = player_record[0]
        # Preserve existing metadata when updating
        existing_full_name = player_record[1]
        date_of_birth = player_record[3]
        height = player_record[4]
        notes = player_record[5]
        update_player_info(player_id, existing_full_name, email=email,
                           date_of_birth=date_of_birth, height=height, notes=notes)
    else:
        add_new_player(player_name, email=email)

    user = session.get('username', 'unknown')
    log_user_action(user, 'Updated player email', f'{player_name} -> {email}')

    return jsonify({'success': True, 'email': email})


@app.route('/api/update_player_info', methods=['POST'])
@login_required
def api_update_player_info():
    """Update player info (email, birthday, height) from AI summary preview."""
    data = request.get_json() or {}
    player_name = (data.get('player_name') or '').strip()
    email = (data.get('email') or '').strip() or None
    birthday = (data.get('birthday') or '').strip() or None
    height = (data.get('height') or '').strip() or None

    if not player_name:
        return jsonify({'success': False, 'error': 'Player name is required.'}), 400

    if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'success': False, 'error': 'Invalid email address.'}), 400

    from player_functions import get_player_by_name, add_new_player, update_player_info

    player_record = get_player_by_name(player_name)
    if player_record:
        player_id = player_record[0]
        existing_full_name = player_record[1]
        # Use new values if provided, otherwise keep existing
        new_email = email if email else player_record[2]
        new_birthday = birthday if birthday else player_record[3]
        new_height = height if height else player_record[4]
        notes = player_record[5]
        update_player_info(player_id, existing_full_name, email=new_email,
                           date_of_birth=new_birthday, height=new_height, notes=notes)
    else:
        add_new_player(player_name, email=email)
        # If we just created the player, update with birthday/height if provided
        if birthday or height:
            player_record = get_player_by_name(player_name)
            if player_record:
                update_player_info(player_record[0], player_record[1], 
                                   email=email, date_of_birth=birthday, height=height, notes=None)

    user = session.get('username', 'unknown')
    updates = []
    if email: updates.append(f'email={email}')
    if birthday: updates.append(f'birthday={birthday}')
    if height: updates.append(f'height={height}')
    log_user_action(user, 'Updated player info', f'{player_name}: {", ".join(updates)}')

    return jsonify({'success': True})


@app.route('/opt_in_ai_emails')
def opt_in_ai_emails():
    """Handle opt-in link from AI summary emails"""
    email = request.args.get('email', '').strip()
    
    # Handle case where user clicked link in preview (placeholder not replaced)
    if not email or email == '{{EMAIL_PLACEHOLDER}}' or 'EMAIL_PLACEHOLDER' in email:
        return render_template('opt_in_error.html', error='This link only works from the actual email. When you receive the AI summary email, the link will be personalized for you.')
    
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return render_template('opt_in_error.html', error='Invalid email address.')
    
    # Store opt-in preference - add note to player with this email
    from player_functions import get_player_by_name, update_player_info
    from database_functions import set_cur
    
    cur = set_cur()
    
    # Check if there's a player with this email
    cur.execute("SELECT id, full_name, email, notes FROM players WHERE email = ?", (email,))
    player = cur.fetchone()
    
    if player:
        # Update player's notes to include opt-in flag
        player_id = player[0]
        full_name = player[1]
        existing_email = player[2]
        existing_notes = player[3] or ""
        
        # Add opt-in flag if not already present
        if "AI_EMAILS_OPT_IN" not in existing_notes:
            new_notes = existing_notes + ("\n" if existing_notes else "") + "AI_EMAILS_OPT_IN"
            update_player_info(player_id, full_name, email=existing_email, notes=new_notes)
            success = True
        else:
            success = True  # Already opted in
    else:
        # No player found with this email - still show success
        success = True
    
    return render_template('opt_in_success.html', email=email, success=success)


@app.route('/cleanup_tokens')
def cleanup_tokens():
    """Clean up expired authentication tokens (can be called periodically)"""
    cleanup_expired_tokens()
    return 'Expired tokens cleaned up successfully', 200

def get_players_who_played_on_date(target_date):
    """Get all players who played on a specific date with their email addresses"""
    from player_functions import get_player_by_name
    
    # Get database connection
    cur = set_cur()
    
    # Get all games from that date across all game types
    players_set = set()
    
    # Doubles games
    cur.execute("SELECT winner1, winner2, loser1, loser2 FROM games WHERE date(game_date) = ?", (target_date,))
    doubles_games = cur.fetchall()
    for game in doubles_games:
        for player in game:
            if player and player.strip():
                players_set.add(player)
    
    # Vollis games
    cur.execute("SELECT winner, loser FROM vollis_games WHERE date(game_date) = ?", (target_date,))
    vollis_games = cur.fetchall()
    for game in vollis_games:
        for player in game:
            if player and player.strip():
                players_set.add(player)
    
    # One v One games
    cur.execute("SELECT winner, loser FROM one_v_one_games WHERE date(game_date) = ?", (target_date,))
    one_v_one_games = cur.fetchall()
    for game in one_v_one_games:
        for player in game:
            if player and player.strip():
                players_set.add(player)
    
    # Other games - get all player columns
    cur.execute("""SELECT winner1, winner2, winner3, winner4, winner5, winner6, 
                   loser1, loser2, loser3, loser4, loser5, loser6 
                   FROM other_games WHERE date(game_date) = ?""", (target_date,))
    other_games = cur.fetchall()
    for game in other_games:
        for player in game:
            if player and player.strip():
                players_set.add(player)
    
    # Get player emails
    players_with_emails = []
    for player_name in players_set:
        player_info = get_player_by_name(player_name)
        if player_info:
            # player_info format: (id, full_name, email, date_of_birth, height, notes, created_at, updated_at)
            email = player_info[2] if len(player_info) > 2 else None
            if email and email.strip():
                players_with_emails.append({
                    'name': player_name,
                    'email': email
                })
    
    return players_with_emails

@app.route('/test_email', methods=['POST'])
def test_email():
    """Send a test email to verify email configuration"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    # Check if email is configured
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        return jsonify({
            'success': False, 
            'error': 'Email not configured. Please set MAIL_USERNAME and MAIL_PASSWORD environment variables.'
        }), 400
    
    try:
        # Create test email
        msg = Message(
            subject="Test Email from Stats Site",
            recipients=["acwodzinski@gmail.com"]
        )
        
        msg.body = "I love you"
        
        # Send the email
        mail.send(msg)
        
        flash('Test email sent successfully to acwodzinski@gmail.com!', 'success')
        return jsonify({
            'success': True,
            'message': 'Test email sent to acwodzinski@gmail.com'
        })
        
    except Exception as e:
        error_msg = f"Failed to send test email: {str(e)}"
        flash(error_msg, 'error')
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500

@app.route('/send_daily_emails', methods=['POST'])
def send_daily_emails():
    """Send emails to all players who played on a specific date"""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    # Get the date to send emails for (default to yesterday)
    target_date = request.form.get('date', None)
    if not target_date:
        yesterday = datetime.now().date() - timedelta(days=1)
        target_date = yesterday.strftime('%Y-%m-%d')
    
    # Check if email is configured
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        flash('Email not configured. Please set MAIL_USERNAME and MAIL_PASSWORD environment variables.', 'error')
        return jsonify({
            'success': False, 
            'error': 'Email not configured. Please contact administrator.'
        }), 400
    
    # Get players who played on that date
    players = get_players_who_played_on_date(target_date)
    
    if not players:
        flash(f'No players with email addresses found for {target_date}', 'warning')
        return jsonify({
            'success': False, 
            'error': f'No players with email addresses found for {target_date}'
        }), 404
    
    # Get stats for that date
    stats, games = specific_date_stats(target_date)
    
    # Send emails to each player
    emails_sent = 0
    errors = []
    
    for player in players:
        try:
            # Find player's stats for that day
            player_stats = None
            for stat in stats:
                if stat[0] == player['name']:
                    player_stats = stat
                    break
            
            # Create email message
            msg = Message(
                subject=f"Your Stats for {target_date}",
                recipients=[player['email']]
            )
            
            # Build email body
            email_body = f"Hi {player['name']},\n\n"
            email_body += f"Here are your stats for {target_date}:\n\n"
            
            if player_stats:
                wins = player_stats[1]
                losses = player_stats[2]
                win_pct = player_stats[3] * 100
                differential = player_stats[4]
                
                email_body += f"Record: {wins}-{losses} ({win_pct:.1f}%)\n"
                email_body += f"Point Differential: {differential:+d}\n\n"
            else:
                email_body += "You played on this date!\n\n"
            
            email_body += f"Total games played on {target_date}: {len(games)}\n\n"
            email_body += "Thanks for playing!\n\n"
            email_body += "— Your Stats Team"
            
            msg.body = email_body
            
            # Send the email
            mail.send(msg)
            emails_sent += 1
            
        except Exception as e:
            errors.append(f"Failed to send to {player['name']} ({player['email']}): {str(e)}")
    
    # Flash success/error messages
    if emails_sent > 0:
        flash(f'Successfully sent {emails_sent} email(s) for {target_date}!', 'success')
    
    if errors:
        for error in errors:
            flash(error, 'error')
    
    return jsonify({
        'success': True,
        'emails_sent': emails_sent,
        'errors': errors
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
