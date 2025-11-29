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
            if player == game['winner1']:  # winner
                wins += 1
            elif player == game['loser1']:  # loser
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
        game_games = [game for game in games if game.get('game_name') == game_name]
        if game_games:
            game_players = all_other_players(game_games)
            game_player_stats = []
            for player in game_players:
                wins, losses = 0, 0
                for game in game_games:
                    if player == game.get('winner1'):  # winner
                        wins += 1
                    elif player == game.get('loser1'):  # loser
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
                    losers, loser_scores, comment, updated_at):
    """Insert an other-game record with per-player scores."""
    winners_normalized, winner_scores_normalized = _normalize_players(winners, winner_scores)
    losers_normalized, loser_scores_normalized = _normalize_players(losers, loser_scores)

    # Maintain legacy aggregate columns for backward compatibility
    aggregate_winner_score = next((score for score in winner_scores_normalized if score is not None), None)
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
    cur = set_cur()
    cur.execute("SELECT * FROM other_games WHERE game_date > date('now','-15 hours') ORDER BY game_date DESC")
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
            x = 1 + 1
            if player in ( game["winner1"], game["winner2"], game["winner3"], game["winner4"], game["winner5"], game["winner6"],
                          game["winner7"], game["winner8"], game["winner9"], game["winner10"], game["winner11"], game["winner12"],
                          game["winner13"], game["winner14"], game["winner15"] ):
                wins += 1
            elif player in ( game["loser1"], game["loser2"], game["loser3"], game["loser4"], game["loser5"], game["loser6"],
                            game["loser7"], game["loser8"], game["loser9"], game["loser10"], game["loser11"], game["loser12"],
                            game["loser13"], game["loser14"], game["loser15"] ):
                losses += 1
        win_percentage = wins / (wins + losses)
        if wins + losses >= minimum_games:
            stats.append([player, wins, losses, win_percentage])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats

def all_other_players(games):
    players = []
    for game in games:
        # Check all 15 winner slots
        for i in range(1, 16):
            winner_key = f'winner{i}'
            if winner_key in game and game[winner_key] and game[winner_key] not in players:
                players.append(game[winner_key])
        # Check all 15 loser slots
        for i in range(1, 16):
            loser_key = f'loser{i}'
            if loser_key in game and game[loser_key] and game[loser_key] not in players:
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
    for game in other_games_raw:
        game_date = game[1]  # game_date is at index 1 in raw data
        players = [game[4], game[5], game[6], game[7], game[8], game[9], game[10], game[11], game[12], game[13], game[14], game[15]]  # winner1-6, loser1-6
        
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
            if player in (game['winner1'], game['winner2'], game['winner3'], game['winner4'], game['winner5'], game['winner6']):
                print(player)
                wins += 1
                differential += (0-0) # TEMPORARY
            elif player in (game['loser1'], game['loser2'], game['loser3'], game['loser4'], game['loser5'], game['loser6']):
                losses += 1
                differential -= (0-0) # TEMPORARY
        win_percentage = 0 ##wins / (wins + losses)
        stats.append([player, wins, losses, win_percentage, differential])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats


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
            if player in (game['winner1'], game['winner2'], game['winner3'], game['winner4'], game['winner5'], game['winner6']):
                wins += 1
            elif player in (game['loser1'], game['loser2'], game['loser3'], game['loser4'], game['loser5'], game['loser6']):
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


