from create_other_database import *
from datetime import datetime, date

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

def add_other_stats(game_date, game_type, game_name, winner1, winner2, winner3, winner4, winner5, winner6,
                    winner7, winner8, winner9, winner10, winner11, winner12, winner13, winner14, winner15,
                    winner_score, loser1, loser2, loser3, loser4, loser5, loser6, loser7, loser8, loser9,
                    loser10, loser11, loser12, loser13, loser14, loser15, loser_score, comment, updated_at):
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn: 
        game = (game_date, game_type, game_name, winner1, winner2, winner3, winner4, winner5, winner6,
                winner7, winner8, winner9, winner10, winner11, winner12, winner13, winner14, winner15,
                winner_score, loser1, loser2, loser3, loser4, loser5, loser6, loser7, loser8, loser9,
                loser10, loser11, loser12, loser13, loser14, loser15, loser_score, comment, updated_at);
        create_other_game(conn, game)

def todays_other_games():
    cur = set_cur()
    cur.execute("SELECT * FROM other_games WHERE game_date > date('now','-15 hours')")
    games = cur.fetchall()
    games.sort(reverse=True)
    readable_games = readable_games_data(games)
    return readable_games

def readable_games_data(games):
    from datetime import datetime
    readable_games = []
    for game in games:
        # Convert game_date format
        try:
            if len(game[1]) > 19:
                game_datetime = datetime.strptime(game[1], "%Y-%m-%d %H:%M:%S.%f")
                game_date = game_datetime.strftime("%m/%d/%y %I:%M %p")
            elif len(game[1]) > 10:
                game_datetime = datetime.strptime(game[1], "%Y-%m-%d %H:%M:%S")
                game_date = game_datetime.strftime("%m/%d/%y %I:%M %p")
            else:
                game_datetime = datetime.strptime(game[1], "%Y-%m-%d")
                game_date = game_datetime.strftime("%m/%d/%y")
        except:
            game_date = game[1]
        
        # Convert updated_at format (now at index 37)
        try:
            if len(game[37]) > 19:
                updated_datetime = datetime.strptime(game[37], "%Y-%m-%d %H:%M:%S.%f")
                updated_date = updated_datetime.strftime("%m/%d/%y %I:%M %p")
            elif len(game[37]) > 10:
                updated_datetime = datetime.strptime(game[37], "%Y-%m-%d %H:%M:%S")
                updated_date = updated_datetime.strftime("%m/%d/%y %I:%M %p")
            else:
                updated_datetime = datetime.strptime(game[37], "%Y-%m-%d")
                updated_date = updated_datetime.strftime("%m/%d/%y")
        except:
            updated_date = game[37] if len(game) > 37 else ''
        
        data = {
            'game_id': game[0], 
            'game_date': game_date, 
            'game_type': game[2], 
            'game_name': game[3],
            'winner1': game[4], 'winner2': game[5], 'winner3': game[6], 'winner4': game[7], 'winner5': game[8], 
            'winner6': game[9], 'winner7': game[10], 'winner8': game[11], 'winner9': game[12], 'winner10': game[13],
            'winner11': game[14], 'winner12': game[15], 'winner13': game[16], 'winner14': game[17], 'winner15': game[18],
            'winner_score': game[19],
            'loser1': game[20], 'loser2': game[21], 'loser3': game[22], 'loser4': game[23], 'loser5': game[24],
            'loser6': game[25], 'loser7': game[26], 'loser8': game[27], 'loser9': game[28], 'loser10': game[29],
            'loser11': game[30], 'loser12': game[31], 'loser13': game[32], 'loser14': game[33], 'loser15': game[34],
            'loser_score': game[35],
            'comment': game[36],
            'updated_at': updated_date
        }
        readable_games.append(data)
    return readable_games

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
        cur.execute("SELECT * FROM other_games")
    else:
        cur.execute("SELECT * FROM other_games WHERE strftime('%Y',game_date)=?", (year,))
    row = cur.fetchall()
    row.sort(reverse=True)
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
    from datetime import datetime
    converted_games = []
    for game in games:
        if len(game[1]) > 19:
            game_datetime = datetime.strptime(game[1], "%Y-%m-%d %H:%M:%S.%f")
            game_date = game_datetime.strftime("%m/%d/%y %I:%M %p")
        else:
            game_datetime = datetime.strptime(game[1], "%Y-%m-%d %H:%M:%S")
            game_date = game_datetime.strftime("%m/%d/%y %I:%M %p")
        if len(game[37]) > 19:
            updated_datetime = datetime.strptime(game[37], "%Y-%m-%d %H:%M:%S.%f")
            updated_date = updated_datetime.strftime("%m/%d/%y %I:%M %p")
        else:
            updated_datetime = datetime.strptime(game[37], "%Y-%m-%d %H:%M:%S")
            updated_date = updated_datetime.strftime("%m/%d/%y %I:%M %p")
        # Include all columns: id, date, type, name, winner1-15, winner_score, loser1-15, loser_score, comment, updated_at
        converted_games.append([
            game[0], game_date, game[2], game[3],  # id, date, type, name
            game[4], game[5], game[6], game[7], game[8], game[9], game[10], game[11], game[12], game[13], game[14], game[15], game[16], game[17], game[18],  # winner1-15
            game[19],  # winner_score
            game[20], game[21], game[22], game[23], game[24], game[25], game[26], game[27], game[28], game[29], game[30], game[31], game[32], game[33], game[34],  # loser1-15
            game[35],  # loser_score
            game[36],  # comment
            updated_date  # updated_at
        ])
    return converted_games

def set_cur():
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
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
        win_percentage = wins / (wins + losses)
        stats.append([player, wins, losses, win_percentage])
    stats.sort(key=lambda x: x[3], reverse=True)
    print(stats)
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


