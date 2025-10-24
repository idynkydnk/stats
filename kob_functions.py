import sqlite3
from datetime import datetime, timedelta
from collections import Counter
from itertools import combinations

def create_connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except sqlite3.Error as e:
        print(e)
    return conn

def validate_kob(games):
    """Validate if a group of games forms a valid KOB."""
    if not games or len(games) < 3:
        return False
    
    # Get all unique players across ALL games
    all_players = set()
    for game in games:
        all_players.add(game['winner1'])
        all_players.add(game['winner2'])
        all_players.add(game['loser1'])
        all_players.add(game['loser2'])
    
    # Must have exactly 4 players TOTAL
    if len(all_players) != 4:
        return False
    
    # Count how many times each pair played together
    pair_counts = Counter()
    for game in games:
        winning_pair = tuple(sorted([game['winner1'], game['winner2']]))
        losing_pair = tuple(sorted([game['loser1'], game['loser2']]))
        pair_counts[winning_pair] += 1
        pair_counts[losing_pair] += 1
    
    # Get all possible pairs (should be 6 for 4 players)
    players_list = sorted(list(all_players))
    all_possible_pairs = set(combinations(players_list, 2))
    
    # All 6 pairs must appear
    if set(pair_counts.keys()) != all_possible_pairs:
        return False
    
    # Get the counts
    counts = sorted(pair_counts.values())
    min_count = min(counts)
    max_count = max(counts)
    num_games = len(games)
    
    # Count how many pairs have each count
    count_freq = Counter(counts)
    
    # All pairs same count (valid 3n pattern)
    if min_count == max_count:
        expected_games = min_count * 3
        return num_games == expected_games
    
    # Counts differ by more than 1 - invalid
    if max_count - min_count != 1:
        return False
    
    # max_count must be ODD for a true split
    if max_count % 2 == 0:
        return False
    
    # Count how many pairs have the higher count
    num_high_pairs = count_freq[max_count]
    num_low_pairs = count_freq[min_count]
    
    # Calculate expected number of games
    expected_games = (num_low_pairs * min_count + num_high_pairs * max_count) // 2
    
    if num_games != expected_games:
        return False
    
    # Valid split patterns
    if num_high_pairs == 1:
        return (num_games - 1) % 3 == 0 and num_games >= 7
    elif num_high_pairs == 2:
        return (num_games - 2) % 3 == 0 and num_games >= 8
    
    return False

def update_kobs():
    """Update KOBs by checking all games and recreating sessions."""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    if conn is None:
        return
    
    cur = conn.cursor()
    
    # Clear existing sessions
    cur.execute("DELETE FROM sessions")
    conn.commit()
    
    # Get all doubles games ordered by date
    cur.execute("""
        SELECT id, game_date, winner1, winner2, loser1, loser2, winner_score, loser_score
        FROM games
        ORDER BY game_date
    """)
    
    all_games = cur.fetchall()
    
    # Convert to list of dicts
    games_list = []
    for game in all_games:
        game_id, game_date, w1, w2, l1, l2, ws, ls = game
        games_list.append({
            'id': game_id,
            'date': game_date,
            'winner1': w1,
            'winner2': w2,
            'loser1': l1,
            'loser2': l2,
            'winner_score': ws,
            'loser_score': ls
        })
    
    session_number = 0
    
    i = 0
    while i < len(games_list):
        # Start a potential KOB with current game
        potential_kob = [games_list[i]]
        
        # Look ahead for more games within 2 hours
        j = i + 1
        while j < len(games_list):
            next_game = games_list[j]
            
            # Check time gap from the LAST game in potential KOB
            try:
                last_time = datetime.fromisoformat(potential_kob[-1]['date'])
                next_time = datetime.fromisoformat(next_game['date'])
                time_gap = next_time - last_time
                
                if time_gap > timedelta(hours=2):
                    break
                else:
                    potential_kob.append(next_game)
            except:
                break
            
            j += 1
        
        # Validate the potential KOB
        if validate_kob(potential_kob):
            session_number += 1
            save_kob(cur, conn, session_number, potential_kob)
        
        # Move to the next unprocessed game
        i = j if j > i + 1 else i + 1
    
    conn.close()

def save_kob(cur, conn, session_number, games):
    """Save a KOB to the database."""
    start_time = min(game['date'] for game in games)
    end_time = max(game['date'] for game in games)
    total_games = len(games)
    
    cur.execute("""
        INSERT INTO sessions 
        (session_number, start_time, end_time, total_games, doubles_games, vollis_games, one_v_one_games, other_games, created_at)
        VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?)
    """, (session_number, start_time, end_time, total_games, total_games, datetime.now()))
    
    conn.commit()

