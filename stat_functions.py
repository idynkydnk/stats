from database_functions import *
from datetime import datetime, date

def add_game_stats(game):
	all_games = []
	full_game = []
	game_date = game[0]
	full_game.append(game_date)
	full_game.append(game[1])
	full_game.append(game[2])
	full_game.append(game[3])
	full_game.append(game[4])
	full_game.append(game[5])
	full_game.append(game[6])
	full_game.append(game[7])
	all_games.append(full_game)
	enter_data_into_database(all_games)

def update_game(game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, game_id2):
	date1 = game_date
	year1 = int(date1[6:10])
	month1 = int(date1[0:2])
	day1 = int(date1[3:5])
	game_date = date(year1, month1, day1)
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	with conn: 
		game = (game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, game_id2);
		database_update_game(conn, game)

def set_cur():
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	cur = conn.cursor()
	return cur	

def all_games():
	cur = set_cur()
	cur.execute("SELECT * FROM games")
	row = cur.fetchall()
	return row

def current_year_games():
	cur = set_cur()
	cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date) = strftime('%Y','now')")
	row = cur.fetchall()
	return row

def stats_per_year(year, minimum_games):
	games = year_games(year)
	players = all_players(games)
	stats = []
	for player in players:
		wins, losses = 0, 0
		for game in games:
			if player == game[2] or player == game[3]:
				wins += 1
			elif player == game[5] or player == game[6]:
				losses += 1
		win_percentage = wins / (wins + losses)
		if wins + losses >= minimum_games:
			stats.append([player, wins, losses, win_percentage])
	stats.sort(key=lambda x: x[3], reverse=True)
	return stats
	
def rare_stats_per_year(year, minimum_games):
	games = year_games(year)
	players = all_players(games)
	stats = []
	for player in players:
		wins, losses = 0, 0
		for game in games:
			if player == game[2] or player == game[3]:
				wins += 1
			elif player == game[5] or player == game[6]:
				losses += 1
		win_percentage = wins / (wins + losses)
		if wins + losses < minimum_games:
			stats.append([player, wins, losses, win_percentage])
	stats.sort(key=lambda x: x[3], reverse=True)
	return stats

def all_scores():
	lst = []
	n = 23
	for i in range(n+1):
		lst.append(i)
	lst.sort(reverse=True)
	return(lst)

def all_players(games):
	players = []
	for game in games:
		if game[2] not in players:
			players.append(game[2])
		if game[3] not in players:
			players.append(game[3])
		if game[5] not in players:
			players.append(game[5])
		if game[6] not in players:
			players.append(game[6])
	return players

def year_games(past_year):
	cur = set_cur()
	cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date)=?", (past_year,))
	row = cur.fetchall()
	row.sort(reverse=True)
	return row

def grab_all_years():
	games = all_games()
	years = []
	for game in games:
		if game[1][0:4] not in years:
			years.append(game[1][0:4])
	return years

def find_game(id):
	cur = set_cur()
	cur.execute("SELECT * FROM games WHERE id=?", (id,))
	row = cur.fetchall()
	return row