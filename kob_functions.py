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
    
    # Count how many times each pair played together AND track their wins/losses
    pair_counts = Counter()
    pair_records = {}  # Track wins and losses for each pair
    
    for game in games:
        winning_pair = tuple(sorted([game['winner1'], game['winner2']]))
        losing_pair = tuple(sorted([game['loser1'], game['loser2']]))
        
        pair_counts[winning_pair] += 1
        pair_counts[losing_pair] += 1
        
        # Track wins/losses
        if winning_pair not in pair_records:
            pair_records[winning_pair] = {'wins': 0, 'losses': 0}
        if losing_pair not in pair_records:
            pair_records[losing_pair] = {'wins': 0, 'losses': 0}
        
        pair_records[winning_pair]['wins'] += 1
        pair_records[losing_pair]['losses'] += 1
    
    # Get all possible pairs (should be 6 for 4 players)
    players_list = sorted(list(all_players))
    all_possible_pairs = set(combinations(players_list, 2))
    
    # All 6 pairs must appear
    if set(pair_counts.keys()) != all_possible_pairs:
        return False
    
    # Get counts and stats
    counts = sorted(pair_counts.values())
    min_count = min(counts)
    max_count = max(counts)
    num_games = len(games)
    count_freq = Counter(counts)
    
    # Formula: Valid counts are 3t where t = total games
    # Also valid: t+1 or t+2 ONLY if there are actual tiebreakers (pairs with odd counts)
    # Tiebreakers only exist when the base is even (so adding 1 makes it odd)
    
    remainder = num_games % 3
    
    # Pattern 1: t % 3 == 0 (3, 6, 9, 12...)
    # All pairs must play the same number of times
    if remainder == 0:
        if min_count == max_count:
            expected_games = min_count * 3
            return num_games == expected_games
        return False
    
    # Pattern 2: t % 3 == 1 (7, 13, 19...)
    # Must have exactly ONE tiebreaker: 2 pairs with odd counts, 4 pairs with even counts
    # AND those pairs with odd counts must have SPLIT their games (not 3-0 or 0-3)
    if remainder == 1:
        # Check if there's actually a tiebreaker
        # A tiebreaker means some pairs have ODD counts (they played an extra game to break a tie)
        odd_count_pairs = sum(1 for count in counts if count % 2 == 1)
        
        # Must have exactly 2 pairs with odd counts (one tiebreaker game involves 2 pairs)
        if odd_count_pairs != 2:
            return False
        
        # Check if the structure is correct
        if max_count - min_count == 1 and count_freq[max_count] == 2:
            # min_count must be even for this to be a valid tiebreaker
            if min_count % 2 == 0:
                # Verify that pairs with odd counts actually SPLIT (have both wins and losses)
                for pair, count in pair_counts.items():
                    if count % 2 == 1:  # Pair with odd count
                        wins = pair_records[pair]['wins']
                        losses = pair_records[pair]['losses']
                        # They must have both won AND lost (not all wins or all losses)
                        if wins == 0 or losses == 0:
                            return False
                
                expected_games = (4 * min_count + 2 * max_count) // 2
                return num_games == expected_games
        return False
    
    # Pattern 3: t % 3 == 2 (8, 14, 20...)
    # Must have exactly TWO tiebreakers: 4 pairs with odd counts, 2 pairs with even counts
    # AND those pairs with odd counts must have SPLIT their games
    if remainder == 2:
        # Check if there are actually two tiebreakers
        odd_count_pairs = sum(1 for count in counts if count % 2 == 1)
        
        # Must have exactly 4 pairs with odd counts (two tiebreaker games involve 4 pairs)
        if odd_count_pairs != 4:
            return False
        
        # Check if the structure is correct
        if max_count - min_count == 1 and count_freq[max_count] == 4:
            # min_count must be even for this to be a valid tiebreaker
            if min_count % 2 == 0:
                # Verify that pairs with odd counts actually SPLIT (have both wins and losses)
                for pair, count in pair_counts.items():
                    if count % 2 == 1:  # Pair with odd count
                        wins = pair_records[pair]['wins']
                        losses = pair_records[pair]['losses']
                        # They must have both won AND lost (not all wins or all losses)
                        if wins == 0 or losses == 0:
                            return False
                
                expected_games = (2 * min_count + 4 * max_count) // 2
                return num_games == expected_games
        return False
    
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

