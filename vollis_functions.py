from create_vollis_database import *

def vollis_stats_per_year(year, minimum_games):
    games = vollis_year_games(year)
    players = all_players(games)
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

def all_players(games):
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
