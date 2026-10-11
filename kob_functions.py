import sqlite3
from private_accounts import connect_data, data_path
from datetime import datetime, timedelta
from collections import Counter
from itertools import combinations

def create_connection(db_file):
    import os
    db_file = data_path(db_file)
    parent = os.path.dirname(db_file)
    if parent and not os.path.isdir(parent):
        return None
    conn = None
    try:
        conn = connect_data(db_file)
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
    """Revalidate changed tournament groups and publish sessions atomically.

    Group boundaries still use the complete ordered history, so edits that split
    or join groups (including across midnight) have the same result as a rebuild.
    """
    import hashlib
    import json
    from pathlib import Path
    rules_revision = str(Path(__file__).stat().st_mtime_ns)
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database) or create_connection('stats.db')
    if conn is None:
        return
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('CREATE TABLE IF NOT EXISTS kob_group_cache (signature TEXT PRIMARY KEY, valid INTEGER NOT NULL)')
            previous = dict(conn.execute('SELECT signature, valid FROM kob_group_cache'))
            rows = conn.execute("""SELECT id, game_date, winner1, winner2, loser1, loser2,
                winner_score, loser_score FROM games ORDER BY game_date, id""").fetchall()
            keys = ('id', 'date', 'winner1', 'winner2', 'loser1', 'loser2', 'winner_score', 'loser_score')
            games = [dict(zip(keys, row)) for row in rows]
            groups = []
            for game in games:
                together = False
                if groups:
                    try:
                        together = (datetime.fromisoformat(game['date']) -
                                    datetime.fromisoformat(groups[-1][-1]['date'])) <= timedelta(hours=2)
                    except (ValueError, TypeError):
                        pass
                if together:
                    groups[-1].append(game)
                else:
                    groups.append([game])
            current = {}
            sessions = []
            for group in groups:
                signature = hashlib.sha256((rules_revision + json.dumps(group, sort_keys=True)).encode()).hexdigest()
                valid = previous[signature] if signature in previous else int(validate_kob(group))
                current[signature] = valid
                if valid:
                    sessions.append((len(sessions) + 1, min(g['date'] for g in group),
                                     max(g['date'] for g in group), len(group), len(group)))
            existing = conn.execute('SELECT session_number, start_time, end_time, total_games, doubles_games FROM sessions ORDER BY session_number').fetchall()
            if existing != sessions:
                conn.execute('DELETE FROM sessions')
                conn.executemany("""INSERT INTO sessions
                    (session_number, start_time, end_time, total_games, doubles_games,
                     vollis_games, one_v_one_games, other_games, created_at)
                    VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?)""",
                    [row + (datetime.now(),) for row in sessions])
            conn.executemany('DELETE FROM kob_group_cache WHERE signature=?',
                             [(key,) for key in previous.keys() - current.keys()])
            conn.executemany('INSERT OR REPLACE INTO kob_group_cache VALUES (?, ?)',
                             [(key, value) for key, value in current.items() if key not in previous])
    finally:
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
