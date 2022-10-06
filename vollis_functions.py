from create_vollis_database import *
from datetime import datetime, date

def vollis_stats_per_year(year, minimum_games):
    games = vollis_year_games(year)
    players = all_vollis_players(games)
    stats = []
    for player in players:
        wins, losses = 0, 0
        for game in games:
            if player == game[2]:
                wins += 1
            elif player == game[4]:
                losses += 1
        win_percentage = wins / (wins + losses)
        if wins + losses >= minimum_games:
            stats.append([player, wins, losses, win_percentage])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats

def all_vollis_players(games):
    players = []
    for game in games:
        if game[2] not in players:
            players.append(game[2])
        if game[4] not in players:
            players.append(game[4])
    return players


def vollis_year_games(year):
    cur = set_cur()
    if year == 'All years':
        cur.execute("SELECT * FROM vollis_games")
    else:
        cur.execute("SELECT * FROM vollis_games WHERE strftime('%Y',game_date)=?", (year,))
    row = cur.fetchall()
    row.sort(reverse=True)
    return row

def set_cur():
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    cur = conn.cursor()
    return cur  

def add_vollis_stats(game):
    new_vollis_game(game[0], game[1], game[3], game[2], game[4], game[5])

def enter_data_into_database(games_data):
    for x in games_data:
        new_vollis_game(x[4], x[2], 0, x[3], 0, x[4])

def new_vollis_game(game_date, winner, winner_score, loser, loser_score, updated_at):
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn: 
        game = (game_date, winner, winner_score, loser, loser_score, updated_at);
        create_vollis_game(conn, game)

def find_vollis_game(game_id):
    cur = set_cur()
    cur.execute("SELECT * FROM vollis_games WHERE id=?", (game_id,))
    row = cur.fetchall()
    return row

def edit_vollis_game(game_id, game_date, winner, winner_score, loser, loser_score, updated_at, game_id2):
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn: 
        game = (game_id, game_date, winner, winner_score, loser, loser_score, updated_at, game_id2);
        database_update_vollis_game(conn, game)

def remove_vollis_game(game_id):
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn: 
        database_delete_vollis_game(conn, game_id)

def all_vollis_years():
    games = all_vollis_games()
    years = []
    for game in games:
        if game[1][0:4] not in years:
            years.append(game[1][0:4])
    years.append('All years')
    return years

def all_years_vollis_player(name):
    years = []
    games = all_vollis_games_by_player(name)
    for game in games:
        if game[1][0:4] not in years:
            years.append(game[1][0:4])
    if len(years) > 1:
        years.append('All years')
    return years

def all_vollis_games_by_player(name):
    cur = set_cur()
    cur.execute("SELECT * FROM vollis_games WHERE (winner=? OR loser=?)", (name, name))
    row = cur.fetchall()
    return row

def all_vollis_games():
    cur = set_cur()
    cur.execute("SELECT * FROM vollis_games")
    row = cur.fetchall()
    return row

def games_from_vollis_player_by_year(year, name):
    cur = set_cur()
    if year == 'All years':
        cur.execute("SELECT * FROM vollis_games WHERE winner=? OR loser=?", (name, name))
    else:
        cur.execute("SELECT * FROM vollis_games WHERE strftime('%Y',game_date)=? AND (winner=? OR loser=?)", (year, name, name))
    row = cur.fetchall()
    return row

def all_vollis_opponents(player, games):
    players = []
    for game in games:
        if game[2] not in players:
            players.append(game[2])
        if game[4] not in players:
            players.append(game[4])
    players.remove(player)
    return players


def vollis_opponent_stats_by_year(name, games):
    opponents = all_vollis_opponents(name, games)
    stats = []
    for opponent in opponents:
        wins, losses = 0, 0
        for game in games:
            if game[2] == opponent:
                losses += 1
            if game[4] == opponent:
                wins += 1
        win_percent = wins / (wins + losses)
        total_games = wins + losses
        stats.append({'opponent':opponent, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
    stats.sort(key=lambda x: x['win_percentage'], reverse=True)
    return stats

def total_vollis_stats(name, games):
    stats = []
    wins, losses = 0, 0
    for game in games:
        if game[2] == name:
            wins += 1
        if game[4] == name:
            losses += 1
    win_percent = wins / (wins + losses)
    total_games = wins + losses
    stats.append([name, wins, losses, win_percent, total_games])
    return stats


def todays_vollis_stats():
    games = todays_vollis_games()
    players = all_vollis_players(games)
    stats = []
    for player in players:
        wins, losses, differential = 0, 0, 0
        for game in games:
            if player == game[2]:
                wins += 1
                differential += (game[3] - game[5])
            elif player == game[4]:
                losses += 1
                differential -= (game[3] - game[5])
        win_percentage = wins / (wins + losses)
        stats.append([player, wins, losses, win_percentage, differential])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats

def all_vollis_players(games):
    players = []
    for game in games:
        if game[2] not in players:
            players.append(game[2])
        if game[4] not in players:
            players.append(game[4])
    return players

def todays_vollis_games():
    cur = set_cur()
    cur.execute("SELECT * FROM vollis_games WHERE game_date > date('now','-15 hours')")
    games = cur.fetchall()
    games.sort(reverse=True)
    #row = convert_ampm(games)
    return games

def vollis_winning_scores():
    scores = [21,15,11]
    return scores

def vollis_losing_scores():
    scores = [19,9,13]
    return scores







