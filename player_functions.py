from create_players_database import *
from datetime import datetime

def set_cur():
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    return cur

def get_all_players():
    """Get all players from the database with their first game date and game count"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    
    # Get all players
    cur.execute("SELECT * FROM players")
    players = cur.fetchall()
    
    # For each player, find their first game and total game count
    players_with_stats = []
    for player in players:
        player_name = player[1]  # full_name is at index 1
        
        # Count doubles games
        cur.execute("""
            SELECT COUNT(*), MIN(game_date) FROM games 
            WHERE winner1 = ? OR winner2 = ? OR loser1 = ? OR loser2 = ?
        """, (player_name, player_name, player_name, player_name))
        doubles_result = cur.fetchone()
        doubles_count = doubles_result[0] if doubles_result else 0
        doubles_date = doubles_result[1] if doubles_result else None
        
        # Count vollis games
        cur.execute("""
            SELECT COUNT(*), MIN(game_date) FROM vollis_games 
            WHERE winner = ? OR loser = ?
        """, (player_name, player_name))
        vollis_result = cur.fetchone()
        vollis_count = vollis_result[0] if vollis_result else 0
        vollis_date = vollis_result[1] if vollis_result else None
        
        # Count 1v1 games
        cur.execute("""
            SELECT COUNT(*), MIN(game_date) FROM one_v_one_games 
            WHERE winner = ? OR loser = ?
        """, (player_name, player_name))
        one_v_one_result = cur.fetchone()
        one_v_one_count = one_v_one_result[0] if one_v_one_result else 0
        one_v_one_date = one_v_one_result[1] if one_v_one_result else None
        
        # Calculate total games and earliest date
        total_games = doubles_count + vollis_count + one_v_one_count
        dates = [d for d in [doubles_date, vollis_date, one_v_one_date] if d is not None]
        first_game_date = min(dates) if dates else None
        
        # Convert player tuple to list and append first game date and total games
        player_list = list(player)
        player_list.append(first_game_date)  # index 8
        player_list.append(total_games)      # index 9
        players_with_stats.append(tuple(player_list))
    
    # Sort by total games (descending)
    players_with_stats.sort(key=lambda x: x[9], reverse=True)
    
    conn.close()
    return players_with_stats

def get_player_by_id(player_id):
    """Get a specific player by ID"""
    cur = set_cur()
    cur.execute("SELECT * FROM players WHERE id=?", (player_id,))
    player = cur.fetchone()
    return player

def get_player_by_name(full_name):
    """Get a specific player by full name"""
    cur = set_cur()
    cur.execute("SELECT * FROM players WHERE full_name=?", (full_name,))
    player = cur.fetchone()
    return player

def add_new_player(full_name, email=None, date_of_birth=None, height=None, notes=None):
    """Add a new player to the database"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    now = datetime.now()
    with conn:
        player = (full_name, email, date_of_birth, height, notes, now, now)
        player_id = create_player(conn, player)
        return player_id

def update_player_info(player_id, full_name, email=None, date_of_birth=None, height=None, notes=None):
    """Update a player's information and update their name across all game tables"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    cur = conn.cursor()
    
    # Get the old name first
    cur.execute("SELECT full_name FROM players WHERE id=?", (player_id,))
    result = cur.fetchone()
    old_name = result[0] if result else None
    
    now = datetime.now()
    
    # If name has changed, update it across all game tables
    if old_name and old_name != full_name:
        # Update doubles games
        cur.execute("UPDATE games SET winner1 = ? WHERE winner1 = ?", (full_name, old_name))
        cur.execute("UPDATE games SET winner2 = ? WHERE winner2 = ?", (full_name, old_name))
        cur.execute("UPDATE games SET loser1 = ? WHERE loser1 = ?", (full_name, old_name))
        cur.execute("UPDATE games SET loser2 = ? WHERE loser2 = ?", (full_name, old_name))
        
        # Update vollis games
        try:
            cur.execute("UPDATE vollis_games SET winner = ? WHERE winner = ?", (full_name, old_name))
            cur.execute("UPDATE vollis_games SET loser = ? WHERE loser = ?", (full_name, old_name))
        except:
            pass  # Table might not exist
        
        # Update 1v1 games
        try:
            cur.execute("UPDATE one_v_one_games SET winner = ? WHERE winner = ?", (full_name, old_name))
            cur.execute("UPDATE one_v_one_games SET loser = ? WHERE loser = ?", (full_name, old_name))
        except:
            pass  # Table might not exist
        
        # Update other games
        try:
            cur.execute("UPDATE other_games SET winner = ? WHERE winner = ?", (full_name, old_name))
            cur.execute("UPDATE other_games SET loser = ? WHERE loser = ?", (full_name, old_name))
        except:
            pass  # Table might not exist
        
        conn.commit()
    
    # Update the player record
    with conn:
        player = (full_name, email, date_of_birth, height, notes, now, player_id)
        update_player(conn, player)

def remove_player(player_id):
    """Delete a player from the database"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn:
        delete_player(conn, player_id)

def search_players(search_term):
    """Search for players by name or email"""
    cur = set_cur()
    cur.execute("SELECT * FROM players WHERE full_name LIKE ? OR email LIKE ? ORDER BY full_name ASC", 
                (f'%{search_term}%', f'%{search_term}%'))
    players = cur.fetchall()
    return players

