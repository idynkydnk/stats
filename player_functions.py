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
    """Get all players from the database with their first game date"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    
    # Get all players with their first game date
    # We'll check all game tables and find the earliest date for each player
    cur.execute("SELECT * FROM players ORDER BY full_name ASC")
    players = cur.fetchall()
    
    # For each player, find their first game
    players_with_first_game = []
    for player in players:
        player_name = player[1]  # full_name is at index 1
        
        # Check doubles games
        cur.execute("""
            SELECT MIN(game_date) FROM games 
            WHERE winner1 = ? OR winner2 = ? OR loser1 = ? OR loser2 = ?
        """, (player_name, player_name, player_name, player_name))
        doubles_date = cur.fetchone()[0]
        
        # Check vollis games
        cur.execute("""
            SELECT MIN(game_date) FROM vollis_games 
            WHERE winner = ? OR loser = ?
        """, (player_name, player_name))
        vollis_date = cur.fetchone()[0]
        
        # Check 1v1 games
        cur.execute("""
            SELECT MIN(game_date) FROM one_v_one_games 
            WHERE winner = ? OR loser = ?
        """, (player_name, player_name))
        one_v_one_date = cur.fetchone()[0]
        
        # Find the earliest date across all game types
        dates = [d for d in [doubles_date, vollis_date, one_v_one_date] if d is not None]
        first_game_date = min(dates) if dates else None
        
        # Convert player tuple to list and append first game date
        player_list = list(player)
        player_list.append(first_game_date)
        players_with_first_game.append(tuple(player_list))
    
    conn.close()
    return players_with_first_game

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

def add_new_player(full_name, email=None, age=None, height=None, phone=None, notes=None):
    """Add a new player to the database"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    now = datetime.now()
    with conn:
        player = (full_name, email, age, height, phone, notes, now, now)
        player_id = create_player(conn, player)
        return player_id

def update_player_info(player_id, full_name, email=None, age=None, height=None, phone=None, notes=None):
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
        player = (full_name, email, age, height, phone, notes, now, player_id)
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
    """Search for players by name"""
    cur = set_cur()
    cur.execute("SELECT * FROM players WHERE full_name LIKE ? ORDER BY full_name ASC", 
                (f'%{search_term}%',))
    players = cur.fetchall()
    return players

