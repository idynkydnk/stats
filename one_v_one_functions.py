from create_one_v_one_database import *
from datetime import datetime, date

def one_v_one_stats_per_year(year, minimum_games):
    games = one_v_one_year_games(year)
    players = all_one_v_one_players(games)
    stats = []
    for player in players:
        wins, losses = 0, 0
        for game in games:
            if player == game[4]:
                wins += 1
            elif player == game[6]:
                losses += 1
        win_percentage = wins / (wins + losses)
        if wins + losses >= minimum_games:
            stats.append([player, wins, losses, win_percentage])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats

def all_one_v_one_players(games):
    players = []
    for game in games:
        if game[4] not in players:
            players.append(game[4])
        if game[6] not in players:
            players.append(game[6])
    return players

def one_v_one_game_types(games):
    game_types = []
    for game in games:
        if game[2] not in game_types:
            game_types.append(game[2])
    return game_types

def one_v_one_game_names(games):
    game_names = []
    for game in games:
        if game[3] not in game_names:
            game_names.append(game[3])
    return game_names

def one_v_one_game_type_for_name(games, game_name):
    """Get the game type for a given game name"""
    for game in games:
        if game[3] == game_name:
            return game[2]
    return None

def one_v_one_year_games(year):
    cur = set_cur()
    if year == 'All years':
        cur.execute("SELECT * FROM one_v_one_games")
    else:
        cur.execute("SELECT * FROM one_v_one_games WHERE strftime('%Y',game_date)=?", (year,))
    row = cur.fetchall()
    row.sort(reverse=True)
    row = convert_one_v_one_ampm(row)
    return row

def one_v_one_game_type_games(game_type):
    cur = set_cur()
    cur.execute("SELECT * FROM one_v_one_games WHERE game_type = ? ORDER BY game_date DESC", (game_type,))
    row = cur.fetchall()
    row = convert_one_v_one_ampm(row)
    return row

def one_v_one_year_and_game_type_games(year, game_type):
    cur = set_cur()
    if year == 'All years':
        cur.execute("SELECT * FROM one_v_one_games WHERE game_type = ? ORDER BY game_date DESC", (game_type,))
    else:
        cur.execute("SELECT * FROM one_v_one_games WHERE strftime('%Y',game_date) = ? AND game_type = ? ORDER BY game_date DESC", (year, game_type))
    row = cur.fetchall()
    row = convert_one_v_one_ampm(row)
    return row

def set_cur():
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    return cur  

def add_one_v_one_stats(game):
    new_one_v_one_game(game[0], game[1], game[2], game[3], game[5], game[4], game[6], game[7])

def enter_data_into_database(games_data):
    for x in games_data:
        new_one_v_one_game(x[4], x[2], 0, x[3], 0, x[4])

def new_one_v_one_game(game_date, game_type, game_name, winner, winner_score, loser, loser_score, updated_at):
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn: 
        game = (game_date, game_type, game_name, winner, winner_score, loser, loser_score, updated_at);
        create_one_v_one_game(conn, game)

def find_one_v_one_game(game_id):
    cur = set_cur()
    cur.execute("SELECT * FROM one_v_one_games WHERE id=?", (game_id,))
    row = cur.fetchall()
    return row

def edit_one_v_one_game(game_id, game_date, game_type, game_name, winner, winner_score, loser, loser_score, updated_at, game_id2):
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn: 
        game = (game_id, game_date, game_type, game_name, winner, winner_score, loser, loser_score, updated_at, game_id2);
        database_update_one_v_one_game(conn, game)

def remove_one_v_one_game(game_id):
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn: 
        database_delete_one_v_one_game(conn, game_id)

def all_one_v_one_years():
    games = all_one_v_one_games()
    years = []
    for game in games:
        if game[1][0:4] not in years:
            years.append(game[1][0:4])
    years.append('All years')
    return years

def all_years_one_v_one_player(name):
    years = []
    games = all_one_v_one_games_by_player(name)
    for game in games:
        if game[1][0:4] not in years:
            years.append(game[1][0:4])
    if len(years) > 1:
        years.append('All years')
    return years

def all_one_v_one_games_by_player(name):
    cur = set_cur()
    cur.execute("SELECT * FROM one_v_one_games WHERE (winner=? OR loser=?)", (name, name))
    row = cur.fetchall()
    return row

def all_one_v_one_games():
    cur = set_cur()
    cur.execute("SELECT * FROM one_v_one_games")
    row = cur.fetchall()
    return row

def games_from_one_v_one_player_by_year(year, name):
    cur = set_cur()
    if year == 'All years':
        cur.execute("SELECT * FROM one_v_one_games WHERE winner=? OR loser=?", (name, name))
    else:
        cur.execute("SELECT * FROM one_v_one_games WHERE strftime('%Y',game_date)=? AND (winner=? OR loser=?)", (year, name, name))
    row = cur.fetchall()
    return row

def all_one_v_one_opponents(player, games):
    players = []
    for game in games:
        if game[4] not in players:
            players.append(game[4])
        if game[6] not in players:
            players.append(game[6])
    players.remove(player)
    return players


def one_v_one_opponent_stats_by_year(name, games):
    opponents = all_one_v_one_opponents(name, games)
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

def total_one_v_one_stats(name, games):
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


def todays_one_v_one_stats():
    games = todays_one_v_one_games()
    players = all_one_v_one_players(games)
    stats = []
    for player in players:
        wins, losses, differential = 0, 0, 0
        for game in games:
            if player == game[4]:
                wins += 1
                differential += (game[5] - game[7])
            elif player == game[6]:
                losses += 1
                differential -= (game[5] - game[7])
        win_percentage = wins / (wins + losses)
        stats.append([player, wins, losses, win_percentage, differential])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats

def all_one_v_one_players(games):
    players = []
    for game in games:
        if game[4] not in players:
            players.append(game[4])
        if game[6] not in players:
            players.append(game[6])
    return players

def todays_one_v_one_games():
    cur = set_cur()
    cur.execute("SELECT * FROM one_v_one_games WHERE game_date > date('now','-15 hours')")
    games = cur.fetchall()
    games.sort(reverse=True)
    row = convert_one_v_one_ampm(games)
    return row

def one_v_one_winning_scores():
    scores = [11,12,13]
    return scores

def convert_one_v_one_ampm(games):
    from datetime import datetime
    converted_games = []
    for game in games:
        if len(game[1]) > 19:
            game_datetime = datetime.strptime(game[1], "%Y-%m-%d %H:%M:%S.%f")
            game_date = game_datetime.strftime("%m/%d/%y %I:%M %p")
        else:
            game_datetime = datetime.strptime(game[1], "%Y-%m-%d %H:%M:%S")
            game_date = game_datetime.strftime("%m/%d/%y")
        if len(game[8]) > 19:
            updated_datetime = datetime.strptime(game[8], "%Y-%m-%d %H:%M:%S.%f")
            updated_date = updated_datetime.strftime("%m/%d/%y %I:%M %p")
        else:
            updated_datetime = datetime.strptime(game[8], "%Y-%m-%d %H:%M:%S")
            updated_date = updated_datetime.strftime("%m/%d/%y")
        converted_games.append([game[0], game_date, game[2], game[3], game[4], game[5], game[6], game[7], updated_date])
    return converted_games

def one_v_one_losing_scores():
    scores = [9,8,7]
    return scores


def single_game_years(game_name):
    cur = set_cur()
    cur.execute("SELECT DISTINCT strftime('%Y', game_date) FROM one_v_one_games WHERE game_name = ? ORDER BY game_date DESC", (game_name,))
    years = []
    for row in cur.fetchall():
        years.append(row[0])
    years.append('All years')
    return years

def total_single_game_stats(games):
    players = all_one_v_one_players(games)
    stats = []
    for player in players:
        wins, losses = 0, 0
        for game in games:
            if player == game[4]:
                wins += 1
            elif player == game[6]:
                losses += 1
        win_percentage = wins / (wins + losses)
        stats.append([player, wins, losses, win_percentage])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats

def single_game_games(year, game_name):
    games = one_v_one_year_games(year)
    single_game_games = []
    for game in games:
        if game[3] == game_name:
            single_game_games.append(game)
    if single_game_games == []:
        for game in games:
            if game[2] == game_name:
                single_game_games.append(game)
    return single_game_games
