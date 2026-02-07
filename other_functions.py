from create_other_database import *
from datetime import datetime, date
import sqlite3

def get_other_dashboard_data(year):
    """Get dashboard data for other games"""
    games = other_year_games(year)
    players = all_other_players(games)
    
    # Calculate stats for each player
    player_stats = []
    for player in players:
        wins, losses = 0, 0
        for game in games:
            # Get all valid winner names from the game
            winner_names = []
            for i in range(1, 16):
                val = game.get(f'winner{i}')
                if _is_valid_player_name(val):
                    winner_names.append(val)
            
            # Get all valid loser names from the game
            loser_names = []
            for i in range(1, 16):
                val = game.get(f'loser{i}')
                if _is_valid_player_name(val):
                    loser_names.append(val)
            
            if player in winner_names:
                wins += 1
            elif player in loser_names:
                losses += 1
        
        if wins + losses > 0:
            win_percentage = wins / (wins + losses)
            player_stats.append([player, wins, losses, win_percentage, wins - losses])
    
    # Sort by win percentage
    player_stats.sort(key=lambda x: x[3], reverse=True)
    
    # Get top players by win percentage and games played
    top_win_percentage = player_stats[:20]
    top_games_played = sorted(player_stats, key=lambda x: x[1] + x[2], reverse=True)[:20]
    
    # Get recent games
    recent_games = games[-10:] if games else []
    
    # Get game types
    game_types = other_game_types(games)
    
    # Get game-specific data
    game_specific_data = {}
    for game_name in ['Sequence', 'Coed', 'No jump', 'Mixed doubles', 'Euchre']:
        game_games = [g for g in games if g.get('game_name') == game_name]
        if game_games:
            game_players = all_other_players(game_games)
            game_player_stats = []
            for player in game_players:
                wins, losses = 0, 0
                for g in game_games:
                    # Get all valid winner names from the game
                    winner_names = []
                    for i in range(1, 16):
                        val = g.get(f'winner{i}')
                        if _is_valid_player_name(val):
                            winner_names.append(val)
                    
                    # Get all valid loser names from the game
                    loser_names = []
                    for i in range(1, 16):
                        val = g.get(f'loser{i}')
                        if _is_valid_player_name(val):
                            loser_names.append(val)
                    
                    if player in winner_names:
                        wins += 1
                    elif player in loser_names:
                        losses += 1
                
                if wins + losses > 0:
                    win_percentage = wins / (wins + losses)
                    game_player_stats.append([player, wins, losses, win_percentage, wins - losses])
            
            game_player_stats.sort(key=lambda x: x[3], reverse=True)
            game_specific_data[game_name] = {
                'top_players': game_player_stats[:10],
                'total_games': len(game_games),
                'total_players': len(game_players)
            }
    
    return {
        'top_win_percentage': top_win_percentage,
        'top_games_played': top_games_played,
        'recent_games': recent_games,
        'total_players': len(players),
        'total_games': len(games),
        'game_types': game_types,
        'game_specific': game_specific_data
    }

MAX_OTHER_PLAYERS = 15


def _normalize_players(players, scores):
    """Ensure exactly MAX_OTHER_PLAYERS entries and convert blank scores to None."""
    normalized_players = (players + [""] * MAX_OTHER_PLAYERS)[:MAX_OTHER_PLAYERS]
    normalized_scores = []
    for score in (scores + [None] * MAX_OTHER_PLAYERS)[:MAX_OTHER_PLAYERS]:
        if score in ("", None):
            normalized_scores.append(None)
        else:
            try:
                normalized_scores.append(int(score))
            except (TypeError, ValueError):
                normalized_scores.append(None)
    return normalized_players, normalized_scores


def add_other_stats(game_date, game_type, game_name, winners, winner_scores,
                    losers, loser_scores, comment, updated_at,
                    team_winner_score=None, team_loser_score=None):
    """Insert an other-game record with per-player scores or team scores.
    
    If team_winner_score/team_loser_score are provided, they are used as the
    aggregate scores (for team games). Otherwise, the first individual score
    is used as the aggregate (for individual games).
    """
    winners_normalized, winner_scores_normalized = _normalize_players(winners, winner_scores)
    losers_normalized, loser_scores_normalized = _normalize_players(losers, loser_scores)

    # Use explicit team scores if provided, otherwise fall back to first individual score
    if team_winner_score not in (None, ''):
        try:
            aggregate_winner_score = int(team_winner_score)
        except (TypeError, ValueError):
            aggregate_winner_score = None
    else:
        aggregate_winner_score = next((score for score in winner_scores_normalized if score is not None), None)
    
    if team_loser_score not in (None, ''):
        try:
            aggregate_loser_score = int(team_loser_score)
        except (TypeError, ValueError):
            aggregate_loser_score = None
    else:
        aggregate_loser_score = next((score for score in loser_scores_normalized if score is not None), None)

    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)

    with conn:
        values = (
            [game_date, game_type, game_name]
            + winners_normalized
            + winner_scores_normalized
            + [aggregate_winner_score]
            + losers_normalized
            + loser_scores_normalized
            + [aggregate_loser_score, comment, updated_at]
        )
        create_other_game(conn, tuple(values))

def _parse_datetime_string(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None

def _build_other_game_display(game, include_time=False):
    record = dict(game)

    game_dt = _parse_datetime_string(record.get('game_date'))
    updated_dt = _parse_datetime_string(record.get('updated_at'))

    if game_dt:
        date_only = game_dt.strftime("%m/%d/%y")
        time_only = game_dt.strftime("%I:%M %p") if len(record.get('game_date', '')) > 10 else ''
        combined_date = f"{date_only} {time_only}".strip()
    else:
        combined_date = record.get('game_date', '')
        date_only = combined_date[:8]
        time_only = combined_date[9:] if len(combined_date) > 9 else ''

    data = {
        'game_id': record.get('id'),
        'game_date': combined_date,
        'game_date_only': date_only,
        'game_time': time_only if include_time else '',
        'game_type': record.get('game_type'),
        'game_name': record.get('game_name'),
        'comment': record.get('comment') or '',
        'updated_at': updated_dt.strftime("%m/%d/%y %I:%M %p") if updated_dt else (record.get('updated_at') or '')
    }

    winners_list = []
    for i in range(1, MAX_OTHER_PLAYERS + 1):
        name_key = f'winner{i}'
        score_key = f'{name_key}_score'
        name = record.get(name_key, '')
        score = record.get(score_key)
        data[name_key] = name
        data[score_key] = score
        if name:
            winners_list.append({'name': name, 'score': score})
    data['winners'] = winners_list
    data['winner_score'] = record.get('winner_score')

    losers_list = []
    for i in range(1, MAX_OTHER_PLAYERS + 1):
        name_key = f'loser{i}'
        score_key = f'{name_key}_score'
        name = record.get(name_key, '')
        score = record.get(score_key)
        data[name_key] = name
        data[score_key] = score
        if name:
            losers_list.append({'name': name, 'score': score})
    data['losers'] = losers_list
    data['loser_score'] = record.get('loser_score')

    return data

def todays_other_games():
    from datetime import datetime
    cur = set_cur()
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("SELECT * FROM other_games WHERE date(game_date) = ? ORDER BY game_date DESC", (today,))
    games = cur.fetchall()
    readable_games = readable_games_data(games)
    return readable_games

def recent_other_games(limit=10):
    """Get the most recent other games across all dates"""
    cur = set_cur()
    cur.execute("SELECT * FROM other_games ORDER BY game_date DESC LIMIT ?", (limit,))
    games = cur.fetchall()
    readable_games = readable_games_data(games)
    return readable_games

def readable_games_data(games):
    return [_build_other_game_display(game, include_time=False) for game in games]

def other_stats_per_year(year, minimum_games):
    games = other_year_games(year)
    players = all_other_players(games)
    stats = []
    for player in players:
        wins, losses = 0, 0
        for game in games:
            # Get all valid winner names from the game
            winner_names = []
            for i in range(1, 16):
                val = game.get(f'winner{i}')
                if _is_valid_player_name(val):
                    winner_names.append(val)
            
            # Get all valid loser names from the game
            loser_names = []
            for i in range(1, 16):
                val = game.get(f'loser{i}')
                if _is_valid_player_name(val):
                    loser_names.append(val)
            
            if player in winner_names:
                wins += 1
            elif player in loser_names:
                losses += 1
        if wins + losses == 0:
            continue
        win_percentage = wins / (wins + losses)
        if wins + losses >= minimum_games:
            stats.append([player, wins, losses, win_percentage])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats

def rare_other_stats_per_year(year, minimum_games):
    """Get stats for players below the minimum games threshold"""
    games = other_year_games(year)
    players = all_other_players(games)
    stats = []
    for player in players:
        wins, losses = 0, 0
        for game in games:
            # Get all valid winner names from the game
            winner_names = []
            for i in range(1, 16):
                val = game.get(f'winner{i}')
                if _is_valid_player_name(val):
                    winner_names.append(val)
            
            # Get all valid loser names from the game
            loser_names = []
            for i in range(1, 16):
                val = game.get(f'loser{i}')
                if _is_valid_player_name(val):
                    loser_names.append(val)
            
            if player in winner_names:
                wins += 1
            elif player in loser_names:
                losses += 1
        if wins + losses == 0:
            continue
        win_percentage = wins / (wins + losses)
        if wins + losses < minimum_games:
            stats.append([player, wins, losses, win_percentage])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats

def _is_valid_player_name(value):
    """Check if a value is a valid player name (not a score, timestamp, or round sequence)."""
    if not value or not isinstance(value, str):
        return False
    value = value.strip()
    if not value:
        return False
    # Filter out numeric values (scores)
    if value.replace('-', '').replace('.', '').isdigit():
        return False
    # Filter out timestamps (contain colons or look like dates)
    if ':' in value or value.startswith('20'):
        return False
    # Filter out round-by-round win sequences (mostly single letters/initials separated by spaces)
    # These look like "K L A K L A" or "A K L A K"
    words = value.split()
    if len(words) >= 3:
        # If most words are very short (1-2 chars), it's likely a round sequence
        short_words = sum(1 for w in words if len(w) <= 2)
        if short_words >= len(words) * 0.7:  # 70% or more are short
            return False
    return True

def all_other_players(games):
    players = []
    for game in games:
        # Check all 15 winner slots
        for i in range(1, 16):
            winner_key = f'winner{i}'
            if winner_key in game and _is_valid_player_name(game[winner_key]) and game[winner_key] not in players:
                players.append(game[winner_key])
        # Check all 15 loser slots
        for i in range(1, 16):
            loser_key = f'loser{i}'
            if loser_key in game and _is_valid_player_name(game[loser_key]) and game[loser_key] not in players:
                players.append(game[loser_key])
    if "" in players: players.remove("")
    return players

def all_combined_players():
    """Get all players from both doubles games and other games, ordered by most recent game"""
    from stat_functions import year_games
    from datetime import datetime
    
    # Get all games from both doubles and other games
    doubles_games = year_games('All years')
    other_games_raw = other_year_games_raw('All years')  # Use raw data for other games
    
    # Create a dictionary to track each player's most recent game date
    player_last_game = {}
    
    # Process doubles games (these are already processed)
    for game in doubles_games:
        game_date = game[1]  # game_date is at index 1
        players = [game[2], game[3], game[5], game[6]]  # winner1, winner2, loser1, loser2
        
        for player in players:
            if player and isinstance(player, str) and player.strip():  # Skip empty players and non-strings
                if player not in player_last_game or game_date > player_last_game[player]:
                    player_last_game[player] = game_date
    
    # Process other games (raw data - tuples from database)
    # Schema: id(0), game_date(1), game_type(2), game_name(3), 
    #         winner1-15(4-18), winner1_score-15_score(19-33), winner_score(34),
    #         loser1-15(35-49), loser1_score-15_score(50-64), loser_score(65)
    for game in other_games_raw:
        game_date = game[1]  # game_date is at index 1 in raw data
        # Winners are at indices 4-18, losers are at indices 35-49
        winners = [game[i] for i in range(4, 19)]  # winner1 through winner15
        losers = [game[i] for i in range(35, 50)]  # loser1 through loser15
        players = winners + losers
        
        for player in players:
            if player and isinstance(player, str) and player.strip():  # Skip empty players and non-strings
                if player not in player_last_game or game_date > player_last_game[player]:
                    player_last_game[player] = game_date
    
    # Sort players by their most recent game date (most recent first)
    sorted_players = sorted(player_last_game.items(), key=lambda x: x[1], reverse=True)
    
    # Return just the player names in order
    return [player[0] for player in sorted_players]

def other_game_types(games):
    game_types = []
    for game in games:
        if game['game_type'] not in game_types:
            game_types.append(game['game_type'])
    return game_types

def other_game_names(games):
    game_names = []
    for game in games:
        if game['game_name'] not in game_names:
            game_names.append(game['game_name'])
    return game_names

def other_game_type_for_name(games, game_name):
    """Get the game type for a given game name"""
    for game in games:
        if game['game_name'] == game_name:
            return game['game_type']
    return None

def other_year_games(year):
    cur = set_cur()
    if year == 'All years':
        cur.execute("SELECT * FROM other_games ORDER BY game_date DESC")
    else:
        cur.execute("SELECT * FROM other_games WHERE strftime('%Y',game_date)=? ORDER BY game_date DESC", (year,))
    row = cur.fetchall()
    games = readable_games_data(row)
    return games

def other_year_games_raw(year):
    cur = set_cur()
    if year == 'All years':
        cur.execute("SELECT * FROM other_games ORDER BY game_date DESC")
    else:
        cur.execute("SELECT * FROM other_games WHERE strftime('%Y',game_date)=? ORDER BY game_date DESC", (year,))
    row = cur.fetchall()
    return row

def convert_other_ampm(games):
    return [_build_other_game_display(game, include_time=True) for game in games]

def set_cur():
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    return cur  


def get_score_type_for_game(game_name):
    """Determine if a game uses individual or team scoring based on previous entries.
    
    Returns 'team' if winner_score is set but winner1_score is not (or all individual scores match).
    Returns 'individual' if winner1_score is set with different values per player.
    Returns 'individual' as default if no previous games exist.
    """
    cur = set_cur()
    cur.execute("""
        SELECT winner_score, winner1_score, winner2_score, loser_score, loser1_score, loser2_score
        FROM other_games 
        WHERE game_name = ? 
        ORDER BY game_date DESC 
        LIMIT 1
    """, (game_name,))
    row = cur.fetchone()
    
    if not row:
        return 'individual'  # Default for new games
    
    winner_score = row['winner_score']
    winner1_score = row['winner1_score']
    winner2_score = row['winner2_score']
    
    # If there's a team winner_score but no individual scores, it's a team game
    if winner_score is not None and winner1_score is None:
        return 'team'
    
    # If there are individual scores, it's an individual game
    if winner1_score is not None:
        return 'individual'
    
    # Default to individual
    return 'individual'


def enter_data_into_database(games_data):
    for x in games_data:
        new_other_game(x[4], x[2], 0, x[3], 0, x[4])

def find_other_game(game_id):
    cur = set_cur()
    cur.execute("SELECT * FROM other_games WHERE id=?", (game_id,))
    row = cur.fetchall()
    return row

def edit_other_game(game_id, game_date, game_type, game_name, winner, winner_score, loser, loser_score, updated_at, game_id2):
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn: 
        game = (game_id, game_date, game_type, game_name, winner, winner_score, loser, loser_score, updated_at, game_id2);
        database_update_other_game(conn, game)

def remove_other_game(game_id):
    from create_other_database import database_delete_other_game
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn: 
        database_delete_other_game(conn, game_id)

def all_other_years():
    cur = set_cur()
    cur.execute("SELECT DISTINCT strftime('%Y', game_date) FROM other_games ORDER BY game_date DESC")
    years = [row[0] for row in cur.fetchall()]
    years.append('All years')
    return years

def all_years_other_player(name):
    years = []
    games = all_other_games_by_player(name)
    for game in games:
        if game[1][0:4] not in years:
            years.append(game[1][0:4])
    if len(years) > 1:
        years.append('All years')
    return years

def all_other_games_by_player(name):
    cur = set_cur()
    cur.execute("SELECT * FROM other_games WHERE (winner=? OR loser=?)", (name, name))
    row = cur.fetchall()
    return row

def all_other_games():
    cur = set_cur()
    cur.execute("SELECT * FROM other_games")
    row = cur.fetchall()
    games = readable_games_data(row)
    return games

def games_from_other_player_by_year(year, name):
    cur = set_cur()
    if year == 'All years':
        cur.execute("SELECT * FROM other_games WHERE winner=? OR loser=?", (name, name))
    else:
        cur.execute("SELECT * FROM other_games WHERE strftime('%Y',game_date)=? AND (winner=? OR loser=?)", (year, name, name))
    row = cur.fetchall()
    games = readable_games_data(row)
    return games

def all_other_opponents(player, games):
    players = []
    for game in games:
        if game[4] not in players:
            players.append(game[4])
        if game[6] not in players:
            players.append(game[6])
    players.remove(player)
    return players


def other_opponent_stats_by_year(name, games):
    opponents = all_other_opponents(name, games)
    stats = []
    for opponent in opponents:
        wins, losses = 0, 0
        for game in games:
            if game[4] == opponent:
                losses += 1
            if game[6] == opponent:
                wins += 1
        win_percent = wins / (wins + losses)
        total_games = wins + losses
        stats.append({'opponent':opponent, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
    stats.sort(key=lambda x: x['win_percentage'], reverse=True)
    return stats

def total_other_stats(name, games):
    stats = []
    wins, losses = 0, 0
    for game in games:
        if game[4] == name:
            wins += 1
        if game[6] == name:
            losses += 1
    win_percent = wins / (wins + losses)
    total_games = wins + losses
    stats.append([name, wins, losses, win_percent, total_games])
    return stats

def todays_other_stats():
    games = todays_other_games()
    players = all_other_players(games)
    stats = []
    for player in players:
        wins, losses, differential = 0, 0, 0
        for game in games:
            # Get all valid winner names from the game
            winner_names = []
            for i in range(1, 16):
                val = game.get(f'winner{i}')
                if _is_valid_player_name(val):
                    winner_names.append(val)
            
            # Get all valid loser names from the game
            loser_names = []
            for i in range(1, 16):
                val = game.get(f'loser{i}')
                if _is_valid_player_name(val):
                    loser_names.append(val)
            
            if player in winner_names:
                wins += 1
                differential += (0-0) # TEMPORARY
            elif player in loser_names:
                losses += 1
                differential -= (0-0) # TEMPORARY
        win_percentage = 0 ##wins / (wins + losses)
        stats.append([player, wins, losses, win_percentage, differential])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats


def todays_other_stats_by_game():
    """Get today's other stats grouped by game name."""
    games = todays_other_games()
    
    # Group games by game_name
    games_by_name = {}
    for game in games:
        game_name = game.get('game_name', 'Unknown')
        if game_name not in games_by_name:
            games_by_name[game_name] = []
        games_by_name[game_name].append(game)
    
    # Build stats for each game name
    result = []
    for game_name, game_list in games_by_name.items():
        players = all_other_players(game_list)
        stats = []
        for player in players:
            wins, losses = 0, 0
            for game in game_list:
                winner_names = []
                for i in range(1, 16):
                    val = game.get(f'winner{i}')
                    if _is_valid_player_name(val):
                        winner_names.append(val)
                
                loser_names = []
                for i in range(1, 16):
                    val = game.get(f'loser{i}')
                    if _is_valid_player_name(val):
                        loser_names.append(val)
                
                if player in winner_names:
                    wins += 1
                elif player in loser_names:
                    losses += 1
            
            win_pct = wins / (wins + losses) if (wins + losses) > 0 else 0
            stats.append([player, wins, losses, win_pct])
        
        stats.sort(key=lambda x: (-x[3], -x[1]))  # Sort by win%, then wins
        result.append({
            'game_name': game_name,
            'game_count': len(game_list),
            'stats': stats
        })
    
    # Sort by game count descending
    result.sort(key=lambda x: -x['game_count'])
    return result


def other_winning_scores():
    scores = [11,12,13]
    return scores

def other_losing_scores():
    scores = [9,8,7]
    return scores


def game_name_years(game_name):
    cur = set_cur()
    cur.execute("SELECT DISTINCT strftime('%Y', game_date) FROM other_games WHERE game_name = ? ORDER BY game_date DESC", (game_name,))
    years = []
    for row in cur.fetchall():
        years.append(row[0])
    years.append('All years')
    return years

def total_game_name_stats(games):
    players = all_other_players(games)
    stats = []
    for player in players:
        wins, losses = 0, 0
        for game in games:
            # Get all valid winner names from the game
            winner_names = []
            for i in range(1, 16):
                val = game.get(f'winner{i}')
                if _is_valid_player_name(val):
                    winner_names.append(val)
            
            # Get all valid loser names from the game
            loser_names = []
            for i in range(1, 16):
                val = game.get(f'loser{i}')
                if _is_valid_player_name(val):
                    loser_names.append(val)
            
            if player in winner_names:
                wins += 1
            elif player in loser_names:
                losses += 1
        total_games = wins + losses
        if total_games == 0:
            continue
        win_percentage = wins / total_games
        stats.append([player, wins, losses, win_percentage, total_games])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats

def game_name_games(year, game_name):
    games = other_year_games(year)
    game_name_games = []
    for game in games:
        if game["game_name"] == game_name:
            game_name_games.append(game)
    return game_name_games

def player_game_name_games(year, game_name, player_name):
    """Get all games for a specific player in a specific game type for a given year."""
    games = game_name_games(year, game_name)
    player_games = []
    for game in games:
        # Check if player is in winners
        for i in range(1, 16):
            val = game.get(f'winner{i}')
            if _is_valid_player_name(val) and val == player_name:
                player_games.append(game)
                break
        else:
            # Check if player is in losers
            for i in range(1, 16):
                val = game.get(f'loser{i}')
                if _is_valid_player_name(val) and val == player_name:
                    player_games.append(game)
                    break
    return player_games

def player_game_name_stats(games, player_name):
    """Calculate stats for a specific player from a list of games."""
    wins, losses = 0, 0
    for game in games:
        # Get all valid winner names from the game
        winner_names = []
        for i in range(1, 16):
            val = game.get(f'winner{i}')
            if _is_valid_player_name(val):
                winner_names.append(val)
        
        # Get all valid loser names from the game
        loser_names = []
        for i in range(1, 16):
            val = game.get(f'loser{i}')
            if _is_valid_player_name(val):
                loser_names.append(val)
        
        if player_name in winner_names:
            wins += 1
        elif player_name in loser_names:
            losses += 1
    
    total_games = wins + losses
    win_percentage = wins / total_games if total_games > 0 else 0
    return {
        'wins': wins,
        'losses': losses,
        'win_percentage': win_percentage,
        'total_games': total_games
    }

def game_name_stats(game_name):
    games = other_year_games(year)
    game_name_games = []
    readable_games = readable_games_data(games)
    for game in readable_games:
        if game["game_name"] == game_name:
            game_name_games.append(game)
    if game_name_games == []:
        for game in games:
            if game["game_name"] == game_name:
                game_name_games.append(game)
    return game_name_games


