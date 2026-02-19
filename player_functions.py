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
    
    # Get all unique player names from all game tables
    all_player_names = set()
    
    # From doubles games
    cur.execute("SELECT DISTINCT winner1 FROM games WHERE winner1 IS NOT NULL AND winner1 != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    cur.execute("SELECT DISTINCT winner2 FROM games WHERE winner2 IS NOT NULL AND winner2 != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    cur.execute("SELECT DISTINCT loser1 FROM games WHERE loser1 IS NOT NULL AND loser1 != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    cur.execute("SELECT DISTINCT loser2 FROM games WHERE loser2 IS NOT NULL AND loser2 != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    
    # From vollis games
    cur.execute("SELECT DISTINCT winner FROM vollis_games WHERE winner IS NOT NULL AND winner != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    cur.execute("SELECT DISTINCT loser FROM vollis_games WHERE loser IS NOT NULL AND loser != ''")
    all_player_names.update([row[0] for row in cur.fetchall()])
    
    # From other games
    for position in ['winner1', 'winner2', 'winner3', 'winner4', 'winner5', 'winner6', 
                     'loser1', 'loser2', 'loser3', 'loser4', 'loser5', 'loser6']:
        cur.execute(f"SELECT DISTINCT {position} FROM other_games WHERE {position} IS NOT NULL AND {position} != ''")
        all_player_names.update([row[0] for row in cur.fetchall()])
    
    # For each player name, build their stats
    players_with_stats = []
    for player_name in all_player_names:
        # Check if player exists in players table
        cur.execute("SELECT * FROM players WHERE full_name = ?", (player_name,))
        player_record = cur.fetchone()
        
        # Count doubles games
        cur.execute("""
            SELECT COUNT(*), MIN(game_date) FROM games 
            WHERE winner1 = ? OR winner2 = ? OR loser1 = ? OR loser2 = ?
        """, (player_name, player_name, player_name, player_name))
        doubles_result = cur.fetchone()
        doubles_count = doubles_result[0] if doubles_result and doubles_result[0] else 0
        doubles_date = doubles_result[1] if doubles_result else None
        
        # Count vollis games
        cur.execute("""
            SELECT COUNT(*), MIN(game_date) FROM vollis_games 
            WHERE winner = ? OR loser = ?
        """, (player_name, player_name))
        vollis_result = cur.fetchone()
        vollis_count = vollis_result[0] if vollis_result and vollis_result[0] else 0
        vollis_date = vollis_result[1] if vollis_result else None
        
        # Count other games
        cur.execute("""
            SELECT COUNT(*), MIN(game_date) FROM other_games 
            WHERE winner1 = ? OR winner2 = ? OR winner3 = ? OR winner4 = ? OR winner5 = ? OR winner6 = ?
               OR loser1 = ? OR loser2 = ? OR loser3 = ? OR loser4 = ? OR loser5 = ? OR loser6 = ?
        """, (player_name, player_name, player_name, player_name, player_name, player_name,
              player_name, player_name, player_name, player_name, player_name, player_name))
        other_result = cur.fetchone()
        other_count = other_result[0] if other_result and other_result[0] else 0
        other_date = other_result[1] if other_result else None
        
        # Calculate total games and earliest date
        total_games = int(doubles_count + vollis_count + other_count)
        dates = [d for d in [doubles_date, vollis_date, other_date] if d is not None]
        first_game_date = min(dates) if dates else None
        
        # Build player record
        if player_record:
            # Player exists in database with their info
            # Only take the first 8 fields to ensure consistent structure
            player_list = list(player_record[:8])
        else:
            # Player doesn't exist in database, create minimal record
            # Format: id, full_name, email, date_of_birth, height, notes, created_at, updated_at
            from datetime import datetime
            now = datetime.now()
            player_list = [None, player_name, None, None, None, None, now, now]
        
        # Ensure we have exactly 8 fields before appending
        while len(player_list) < 8:
            player_list.append(None)
        player_list = player_list[:8]
        
        player_list.append(first_game_date)  # index 8
        player_list.append(int(total_games))  # index 9 - ensure it's an integer
        players_with_stats.append(tuple(player_list))
    
    # Sort by total games (descending) - safely handle any type issues
    def safe_game_count(player):
        try:
            return int(player[9]) if player[9] is not None else 0
        except (ValueError, TypeError):
            return 0
    
    players_with_stats.sort(key=safe_game_count, reverse=True)
    
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
        
        # Other games (winner1, winner2, etc.) updated via database_functions.update_player_name_in_all_tables
        
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

