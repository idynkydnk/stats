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

def rare_vollis_stats_per_year(year, minimum_games):
    print('hey man')


def vollis_year_games(year):
    cur = set_cur()
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
    return years

def all_years_vollis_player(name):
    years = []
    games = all_games_player(name)
    for game in games:
        if game[1][0:4] not in years:
            years.append(game[1][0:4])
    return years

def all_vollis_games(name):
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
    cur.execute("SELECT * FROM vollis_games WHERE strftime('%Y',game_date)=? AND (winner=? OR loser=?)", (year, name, name))
    row = cur.fetchall()
    return row

def vollis_partner_stats_by_year(year, name, games):
    print('yo dog')

def vollis_opponent_stats_by_year(year, name, games):
    print('yoooooo')









