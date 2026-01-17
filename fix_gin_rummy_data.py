"""
Migration script to fix corrupted Gin Rummy data in the other_games table.
The original import put loser scores in the loser name columns.
This script re-parses the original data file and updates the records with correct loser names.
"""
import sqlite3
import re
from datetime import datetime, timedelta
from pathlib import Path

DATA_FILE = Path("data/gin_rummy_games.txt")
DATABASE = "stats.db"


def normalize_date_token(token, year_hint):
    """Parse date token from the data file."""
    token = token.strip()
    if not token:
        raise ValueError("Empty date token")
    parts = token.split('/')
    
    if len(parts) == 3:
        month, day, year = parts
    elif len(parts) == 2:
        left, right = parts
        if len(left) > 2 and left.isdigit() and len(right) == 2:
            month = left[:-2]
            day = left[-2:]
            year = right
        else:
            month = left
            day = right
            if year_hint is None:
                raise ValueError(f"Missing year context for token '{token}'")
            year = f"{year_hint % 100:02d}"
    else:
        raise ValueError(f"Unrecognized date token '{token}'")
    
    month = int(month)
    day = int(day)
    year_int = int(year) if len(year) == 2 else int(year[-2:])
    resolved = datetime(year=2000 + year_int, month=month, day=day)
    return resolved, resolved.year


def parse_player_line(line):
    """Parse a player line to extract name and final score."""
    tokens = line.split()
    name_tokens = []
    numbers = []
    started_numbers = False
    
    for token in tokens:
        clean = token.rstrip(':')
        match = re.search(r'-?\d+', clean)
        if match:
            started_numbers = True
            numbers.append(int(match.group()))
        elif not started_numbers:
            name_tokens.append(clean)
    
    if not name_tokens or not numbers:
        return None
    
    name = ' '.join(name_tokens).strip()
    if not name:
        return None
    return name, numbers[-1]  # Last number is the final score


def load_sections(raw_text):
    """Load game sections from the data file."""
    sections = []
    current = None
    
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower() in {"gin rummy", "card games"}:
            continue
        
        header_match = re.match(r'(?:(?P<date>[\d/]+)\s+)?winner\s+(?P<winner>.+)', line, re.IGNORECASE)
        if header_match:
            if current:
                sections.append(current)
            current = {
                "header": line,
                "date_token": header_match.group('date'),
                "winner": header_match.group('winner').strip(),
                "lines": [],
            }
        elif current:
            current['lines'].append(line)
        # Skip lines before first header
    
    if current:
        sections.append(current)
    return sections


def assign_dates(sections):
    """Assign dates to sections, inferring missing dates."""
    last_date = None
    last_year = None
    
    for section in sections:
        token = section.get('date_token')
        if token:
            resolved, last_year = normalize_date_token(token, last_year)
            last_date = resolved
            section['resolved_date'] = resolved
        else:
            if last_date is None:
                raise ValueError("Undated game encountered before any dated games.")
            last_date = last_date - timedelta(days=1)
            section['resolved_date'] = last_date


def parse_players(section):
    """Parse all players and their scores from a section."""
    player_entries = []
    
    for line in section['lines']:
        if any(ch.isdigit() for ch in line):
            entry = parse_player_line(line)
            if entry:
                player_entries.append(entry)
    
    return player_entries


def normalize_name(name):
    """Normalize player name for matching."""
    name = name.lower().strip()
    # Handle common abbreviations
    name_map = {
        'ash': 'ashleigh wodzinski',
        'leo': 'leo rojas',
        'leonel': 'leonel valdez',
    }
    return name_map.get(name, name)


def find_matching_record(cursor, game_date, winner_name):
    """Find a corrupted record matching the date and winner."""
    # Try exact date match first
    cursor.execute("""
        SELECT id, winner1, loser1, loser1_score 
        FROM other_games 
        WHERE game_name = 'Gin Rummy' 
        AND date(game_date) = date(?)
        AND lower(winner1) LIKE ?
    """, (game_date.isoformat(), f"%{winner_name.lower().split()[0]}%"))
    
    results = cursor.fetchall()
    return results


def main():
    # Read the original data file
    raw_text = DATA_FILE.read_text()
    sections = load_sections(raw_text)
    assign_dates(sections)
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    fixed = 0
    skipped = 0
    not_found = 0
    already_correct = 0
    
    for section in sections:
        players = parse_players(section)
        if not players:
            skipped += 1
            continue
        
        winner_name = section['winner']
        game_date = section['resolved_date']
        
        # Find the winner entry
        winner_entry = next((p for p in players if normalize_name(p[0]) == normalize_name(winner_name)), None)
        if not winner_entry:
            # Try partial match
            winner_entry = next((p for p in players if normalize_name(winner_name) in normalize_name(p[0]) or normalize_name(p[0]) in normalize_name(winner_name)), None)
        
        if not winner_entry:
            print(f"Warning: Winner '{winner_name}' not found in players for {game_date}")
            skipped += 1
            continue
        
        # Get losers (everyone except winner)
        losers = [(name, score) for name, score in players if normalize_name(name) != normalize_name(winner_entry[0])]
        
        if not losers:
            skipped += 1
            continue
        
        # Find matching record in database
        matches = find_matching_record(cursor, game_date, winner_name)
        
        if not matches:
            not_found += 1
            continue
        
        for match in matches:
            record_id, db_winner, db_loser1, db_loser1_score = match
            
            # Check if loser1 looks like a score (corrupted) or already has a name
            try:
                # If loser1 is numeric, it's corrupted
                float(db_loser1) if db_loser1 else None
                is_corrupted = db_loser1 and db_loser1.replace('-', '').replace('.', '').isdigit()
            except:
                is_corrupted = False
            
            if not is_corrupted and db_loser1 and not db_loser1.replace('-', '').replace('.', '').isdigit():
                already_correct += 1
                continue
            
            # Build update query with correct loser names and scores
            update_parts = []
            params = []
            
            for i, (loser_name, loser_score) in enumerate(losers[:15], 1):
                update_parts.append(f"loser{i} = ?")
                params.append(loser_name)
                update_parts.append(f"loser{i}_score = ?")
                params.append(loser_score)
            
            # Clear any extra loser slots
            for i in range(len(losers) + 1, 16):
                update_parts.append(f"loser{i} = ?")
                params.append("")
                update_parts.append(f"loser{i}_score = ?")
                params.append(None)
            
            # Set loser_score to the first loser's score (for backwards compatibility)
            if losers:
                update_parts.append("loser_score = ?")
                params.append(losers[0][1])
            
            params.append(record_id)
            
            sql = f"UPDATE other_games SET {', '.join(update_parts)} WHERE id = ?"
            cursor.execute(sql, params)
            fixed += 1
            
            if fixed <= 5:
                print(f"Fixed record {record_id}: {db_winner} vs {[l[0] for l in losers]}")
    
    conn.commit()
    conn.close()
    
    print(f"\n=== Migration Complete ===")
    print(f"Fixed: {fixed} records")
    print(f"Already correct: {already_correct} records")
    print(f"Not found in DB: {not_found} records")
    print(f"Skipped (parsing issues): {skipped} records")


if __name__ == '__main__':
    main()
