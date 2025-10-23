"""
Migration script to populate the players table with existing player names
from all game tables (doubles, vollis, 1v1, other)
"""
import sqlite3
from datetime import datetime

def create_connection(db_file):
    """Create a database connection"""
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except sqlite3.Error as e:
        print(e)
    return conn

def get_all_player_names():
    """Extract all unique player names from all game tables"""
    database = 'stats.db'
    conn = create_connection(database)
    cur = conn.cursor()
    
    player_names = set()
    
    # Get players from doubles games table
    print("Extracting players from doubles games...")
    cur.execute("SELECT winner1, winner2, loser1, loser2 FROM games")
    doubles_games = cur.fetchall()
    for game in doubles_games:
        for player in game:
            if player:  # Only filter out empty/null names
                player_names.add(player.strip())
    
    # Get players from vollis games table
    print("Extracting players from vollis games...")
    try:
        cur.execute("SELECT winner, loser FROM vollis_games")
        vollis_games = cur.fetchall()
        for game in vollis_games:
            for player in game:
                if player:
                    player_names.add(player.strip())
    except sqlite3.OperationalError:
        print("  Vollis games table not found or empty")
    
    # Get players from 1v1 games table
    print("Extracting players from 1v1 games...")
    try:
        cur.execute("SELECT winner, loser FROM one_v_one_games")
        one_v_one_games = cur.fetchall()
        for game in one_v_one_games:
            for player in game:
                if player:
                    player_names.add(player.strip())
    except sqlite3.OperationalError:
        print("  1v1 games table not found or empty")
    
    # Get players from other games table
    print("Extracting players from other games...")
    try:
        cur.execute("SELECT winner, loser FROM other_games")
        other_games = cur.fetchall()
        for game in other_games:
            for player in game:
                if player:
                    player_names.add(player.strip())
    except sqlite3.OperationalError:
        print("  Other games table not found or empty")
    
    conn.close()
    return sorted(list(player_names))

def check_existing_players():
    """Check which players already exist in the players table"""
    database = 'stats.db'
    conn = create_connection(database)
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT full_name FROM players")
        existing = cur.fetchall()
        existing_names = set(name[0] for name in existing)
    except sqlite3.OperationalError:
        existing_names = set()
    
    conn.close()
    return existing_names

def migrate_players():
    """Migrate all unique player names to the players table"""
    database = 'stats.db'
    
    # Get all unique player names from game tables
    print("\n=== Starting Player Migration ===\n")
    all_players = get_all_player_names()
    print(f"\nFound {len(all_players)} unique player names across all games")
    
    # Check existing players
    existing_players = check_existing_players()
    print(f"Already have {len(existing_players)} players in the database")
    
    # Filter out players that already exist
    new_players = [p for p in all_players if p not in existing_players]
    print(f"Will add {len(new_players)} new players")
    
    if not new_players:
        print("\nNo new players to add!")
        return
    
    # Add new players to the database
    conn = create_connection(database)
    cur = conn.cursor()
    
    now = datetime.now()
    added_count = 0
    
    print("\nAdding players to database...")
    for player_name in new_players:
        try:
            cur.execute("""
                INSERT INTO players (full_name, email, age, height, phone, notes, created_at, updated_at)
                VALUES (?, NULL, NULL, NULL, NULL, NULL, ?, ?)
            """, (player_name, now, now))
            added_count += 1
            if added_count % 10 == 0:
                print(f"  Added {added_count} players...")
        except sqlite3.IntegrityError:
            print(f"  Skipped duplicate: {player_name}")
    
    conn.commit()
    conn.close()
    
    print(f"\n=== Migration Complete ===")
    print(f"Successfully added {added_count} players to the database")
    print(f"Total players in database: {len(existing_players) + added_count}")
    
    # Show some sample players
    print("\nSample of migrated players:")
    for player in new_players[:10]:
        print(f"  - {player}")
    if len(new_players) > 10:
        print(f"  ... and {len(new_players) - 10} more")

if __name__ == '__main__':
    migrate_players()

