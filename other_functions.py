from create_other_database import *
from datetime import datetime, date

def add_other_stats(game_date, game_type, game_name, winner1, winner2, winner3, winner4, winner5, winner6, 
                    winner_score, loser1, loser2, loser3, loser4, loser5, loser6, loser_score, comment, updated_at):
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn: 
        game = (game_date, game_type, game_name, winner1, winner2, winner3, winner4, winner5, winner6, 
                winner_score, loser1, loser2, loser3, loser4, loser5, loser6, loser_score, comment, updated_at);
        create_other_game(conn, game)

def todays_other_games():
    cur = set_cur()
    cur.execute("SELECT * FROM other_games WHERE game_date > date('now','-15 hours')")
    games = cur.fetchall()
    games.sort(reverse=True)
    readable_games = readable_games_data(games)
    return readable_games

def readable_games_data(games):
    readable_games = []
    for game in games:
        data = {'game_id':game[0], 'game_date':game[1], 'game_type':game[2], 'game_name':game[3], 'winner1':game[4], 'winner2':game[5], 
                'winner3':game[6], 'winner4':game[7], 'winner5':game[8], 'winner6':game[9], 'winner_score':game[10], 'loser1':game[11], 
                'loser2':game[12], 'loser3':game[13], 'loser4':game[14], 'loser5':game[15], 'loser6':game[16], 'loser_score':game[17], 
                'comment':game[18], 'updated_at':game[19]}
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
            if player in ( game["winner1"], game["winner2"], game["winner3"], game["winner4"], game["winner5"], game["winner6"] ):
                wins += 1
            elif player in ( game["loser1"], game["loser2"], game["loser3"], game["loser4"], game["loser5"], game["loser6"] ):
                losses += 1
        win_percentage = wins / (wins + losses)
        if wins + losses >= minimum_games:
            stats.append([player, wins, losses, win_percentage])
    stats.sort(key=lambda x: x[3], reverse=True)
    return stats

def all_other_players(games):
    players = []
    for game in games:
        if game['winner1'] not in players:
            players.append(game['winner1'])
        if game["winner2"] not in players:
            players.append(game["winner2"])
        if game["winner3"] not in players:
            players.append(game["winner3"])
        if game["winner4"] not in players:
            players.append(game["winner4"])
        if game["winner5"] not in players:
            players.append(game["winner5"])
        if game["winner6"] not in players:
            players.append(game["winner6"])
        if game['loser1'] not in players:
            players.append(game['loser1'])
        if game['loser2'] not in players:
            players.append(game['loser2'])
        if game['loser3'] not in players:
            players.append(game['loser3'])
        if game['loser4'] not in players:
            players.append(game['loser4'])
        if game['loser5'] not in players:
            players.append(game['loser5'])
        if game['loser6'] not in players:
            players.append(game['loser6'])
    if "" in players: players.remove("")
    return players

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
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn: 
        database_delete_other_game(conn, game_id)

def all_other_years():
    games = all_other_games()
    years = []
    for game in games:
        if game['game_date'][0:4] not in years:
            years.append(game['game_date'][0:4])
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
    games = all_other_games()
    years = []
    for game in games:
        if game["game_name"] == game_name:
            if game["game_date"][0:4] not in years:
                years.append(game["game_date"][0:4])
        if years == []:
            for game in games:
                if game["game_name"] == game_name:
                    if game["game_date"][0:4] not in years:
                        years.append(game["game_date"][0:4])
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


