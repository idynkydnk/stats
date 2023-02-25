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
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	with conn: 
		game = (game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, game_id2);
		database_update_game(conn, game)

def remove_game(game_id):
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	with conn: 
		database_delete_game(conn, game_id)

def set_cur():
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	cur = conn.cursor()
	return cur	

def stats_per_year(year, minimum_games):
	if year == 'All years':
		games = all_games()
	else:
		games = year_games(year)
	players = all_players(games)
	stats = []
	no_wins = []
	for player in players:
		wins, losses = 0, 0
		for game in games:
			if player == game[2] or player == game[3]:
				wins += 1
			elif player == game[5] or player == game[6]:
				losses += 1
		win_percentage = wins / (wins + losses)
		if wins + losses >= minimum_games:
			if wins == 0:
				no_wins.append([player, wins, losses, win_percentage])
			else:
				stats.append([player, wins, losses, win_percentage])
	stats.sort(key=lambda x: x[1], reverse=True)
	stats.sort(key=lambda x: x[3], reverse=True)
	no_wins.sort(key=lambda x: x[2])
	for stat in no_wins:
		stats.append(stat)
	return stats

def team_stats_per_year(year, minimum_games, games):
	stats = []
	all_teams = teams(games)
	no_wins = []
	for team in all_teams:
		wins, losses = 0, 0
		for game in games:
			if team['player1'] == game[2] and team['player2'] == game[3] or team['player1'] == game[3] and team['player2'] == game[2]:
				wins += 1
			elif team['player1'] == game[5] and team['player2'] == game[6] or team['player1'] == game[6] and team['player2'] == game[5]:
				losses += 1
		win_percent = wins / (wins + losses)
		total_games = wins + losses
		x = { 'team':team, 'wins':wins, 'losses':losses, 
				'win_percentage':win_percent, 'total_games':total_games }
		if total_games >= minimum_games:
			if wins == 0:
				no_wins.append(x)
			else:
				stats.append(x)
	stats.sort(key=lambda x: x['win_percentage'], reverse=True)
	for stat in no_wins:
		stats.append(stat)
	return stats

def teams(games):
	all_teams = []
	for game in games:
		winners = {}
		losers = {}
		if game[2] > game[3]:
			winners['player1'] = game[3]
			winners['player2'] = game[2]
		else:
			winners['player1'] = game[2]
			winners['player2'] = game[3]
		if winners not in all_teams:
			all_teams.append(winners)
		if game[5] > game[6]:
			losers['player1'] = game[6]
			losers['player2'] = game[5]
		else:
			losers['player1'] = game[5]
			losers['player2'] = game[6]
		if losers not in all_teams:
			all_teams.append(losers)
	all_teams.sort(key=lambda x: x['player1'])
	return all_teams

def todays_stats():
	games = todays_games()
	players = all_players(games)
	stats = []
	for player in players:
		wins, losses, differential = 0, 0, 0
		for game in games:
			if player == game[2] or player == game[3]:
				wins += 1
				differential += (game[4] - game[7])
			elif player == game[5] or player == game[6]:
				losses += 1
				differential -= (game[4] - game[7])
		win_percentage = wins / (wins + losses)
		stats.append([player, wins, losses, win_percentage, differential])
	stats.sort(key=lambda x: x[4], reverse=True)
	stats.sort(key=lambda x: x[3], reverse=True)
	return stats

def todays_games():
	cur = set_cur()
	cur.execute("SELECT * FROM games WHERE game_date > date('now','-15 hours')")
	games = cur.fetchall()
	games.sort(reverse=True)
	row = convert_ampm(games)
	return row

def convert_ampm(games):
	converted_games = []
	for game in games:
		if len(game[1]) > 19:
			game_datetime = datetime.strptime(game[1], "%Y-%m-%d %H:%M:%S.%f")
			game_date = game_datetime.strftime("%m/%d/%Y %I:%M %p")
		else:
			game_datetime = datetime.strptime(game[1], "%Y-%m-%d %H:%M:%S")
			game_date = game_datetime.strftime("%m/%d/%Y")
		if len(game[8]) > 19:
			updated_datetime = datetime.strptime(game[8], "%Y-%m-%d %H:%M:%S.%f")
			updated_date = updated_datetime.strftime("%m/%d/%Y %I:%M %p")
		else:
			updated_datetime = datetime.strptime(game[8], "%Y-%m-%d %H:%M:%S")
			updated_date = updated_datetime.strftime("%m/%d/%Y")
		converted_games.append([game[0], game_date, game[2], game[3], game[4], game[5], game[6], game[7], updated_date])
	return converted_games
	
def rare_stats_per_year(year, minimum_games):
	if year == 'All years':
		games = all_games()
	else:
		games = year_games(year)
	players = all_players(games)
	stats = []
	no_wins = []
	for player in players:
		wins, losses = 0, 0
		for game in games:
			if player == game[2] or player == game[3]:
				wins += 1
			elif player == game[5] or player == game[6]:
				losses += 1
		win_percentage = wins / (wins + losses)
		if wins + losses < minimum_games:
			if wins == 0:
				no_wins.append([player, wins, losses, win_percentage])
			else:
				stats.append([player, wins, losses, win_percentage])
	stats.sort(key=lambda x: x[1], reverse=True)
	stats.sort(key=lambda x: x[3], reverse=True)
	no_wins.sort(key=lambda x: x[2])
	for stat in no_wins:
		stats.append(stat)
	return stats

def winners_scores():
	scores = [21,22,23]
	return scores

def losers_scores():
	scores = [19,18,17]
	return scores

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

def year_games(year):
	cur = set_cur()
	if year == 'All years':
		cur.execute("SELECT * FROM games")
	else:
		cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date)=?", (year,))
	row = cur.fetchall()
	row.sort(reverse=True)
	row = convert_ampm(row)
	return row

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

def grab_all_years():
	games = all_games()
	years = []
	for game in games:
		if game[1][0:4] not in years:
			years.append(game[1][0:4])
	years.append('All years')
	return years

def all_years_player(name):
	years = []
	games = all_games_player(name)
	for game in games:
		if game[1][0:4] not in years:
			years.append(game[1][0:4])
	if len(years) > 1:
		years.append('All years')
	return years


def all_games_player(name):
	cur = set_cur()
	cur.execute("SELECT * FROM games WHERE (winner1=? OR winner2=? OR loser1=? OR loser2=?)", (name, name, name, name))
	row = cur.fetchall()
	return row

def find_game(id):
	cur = set_cur()
	cur.execute("SELECT * FROM games WHERE id=?", (id,))
	row = cur.fetchall()
	return row

def games_from_player_by_year(year, name):
	cur = set_cur()
	if year == 'All years':
		cur.execute("SELECT * FROM games WHERE (winner1=? OR winner2=? OR loser1=? OR loser2=?)", (name, name, name, name))
	else:
		cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date)=? AND (winner1=? OR winner2=? OR loser1=? OR loser2=?)", (year, name, name, name, name))
	row = cur.fetchall()
	return row

def partner_stats_by_year(name, games, minimum_games):
	stats = []
	no_wins = []
	if not games:
		return stats
	else:
		players = all_players(games)
		players.remove(name)
		for partner in players:
			wins, losses = 0, 0
			for game in games:
				if game[2] == name or game[3] == name:
					if game[2] == partner or game[3] == partner:
						wins += 1
				if game[5] == name or game[6] == name:
					if game[5] == partner or game[6] == partner:
						losses += 1
			if wins + losses > 0:
				win_percent = wins / (wins + losses)
				total_games = wins + losses
				if total_games >= minimum_games:
					if wins == 0:
						no_wins.append({'partner':partner, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
					else:
						stats.append({'partner':partner, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
		stats.sort(key=lambda x: x['wins'], reverse=True)
		stats.sort(key=lambda x: x['win_percentage'], reverse=True)
		no_wins.sort(key=lambda x: x['losses'])
		for stat in no_wins:
			stats.append(stat)
		return stats


def rare_partner_stats_by_year(name, games, minimum_games):
	stats = []
	if not games:
		return stats
	else:
		players = all_players(games)
		players.remove(name)
		stats = []
		no_wins = []
		for partner in players:
			wins, losses = 0, 0
			for game in games:
				if game[2] == name or game[3] == name:
					if game[2] == partner or game[3] == partner:
						wins += 1
				if game[5] == name or game[6] == name:
					if game[5] == partner or game[6] == partner:
						losses += 1
			if wins + losses > 0:
				win_percent = wins / (wins + losses)
				total_games = wins + losses
				if total_games < minimum_games:
					if wins == 0:
						no_wins.append({'partner':partner, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
					else:
						stats.append({'partner':partner, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
		stats.sort(key=lambda x: x['wins'], reverse=True)
		stats.sort(key=lambda x: x['win_percentage'], reverse=True)
		no_wins.sort(key=lambda x: x['losses'])
		for stat in no_wins:
			stats.append(stat)
		return stats


def opponent_stats_by_year(name, games, minimum_games):
	stats = []
	if not games:
		return stats
	else:
		players = all_players(games)
		players.remove(name)
		stats = []
		no_wins = []
		for opponent in players:
			wins, losses = 0, 0
			for game in games:
				if game[2] == name or game[3] == name:
					if game[5] == opponent or game[6] == opponent:
						wins += 1
				if game[5] == name or game[6] == name:
					if game[2] == opponent or game[3] == opponent:
						losses += 1
			if wins + losses > 0:
				win_percent = wins / (wins + losses)
				total_games = wins + losses
				if total_games >= minimum_games:
					if wins == 0:
						no_wins.append({'opponent':opponent, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
					else:
						stats.append({'opponent':opponent, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
		stats.sort(key=lambda x: x['wins'], reverse=True)
		stats.sort(key=lambda x: x['win_percentage'], reverse=True)
		no_wins.sort(key=lambda x: x['losses'])
		for stat in no_wins:
			stats.append(stat)
		return stats

def rare_opponent_stats_by_year(name, games, minimum_games):
	stats = []
	if not games:
		return stats
	else:
		players = all_players(games)
		players.remove(name)
		stats = []
		no_wins = []
		for opponent in players:
			wins, losses = 0, 0
			for game in games:
				if game[2] == name or game[3] == name:
					if game[5] == opponent or game[6] == opponent:
						wins += 1
				if game[5] == name or game[6] == name:
					if game[2] == opponent or game[3] == opponent:
						losses += 1
			if wins + losses > 0:
				win_percent = wins / (wins + losses)
				total_games = wins + losses
				if total_games < minimum_games:
					if wins == 0:
						no_wins.append({'opponent':opponent, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
					else:
						stats.append({'opponent':opponent, 'wins':wins, 'losses':losses, 'win_percentage':win_percent, 'total_games':total_games})
		stats.sort(key=lambda x: x['wins'], reverse=True)
		stats.sort(key=lambda x: x['win_percentage'], reverse=True)
		no_wins.sort(key=lambda x: x['losses'])
		for stat in no_wins:
			stats.append(stat)
		return stats

def total_stats(games, player):
	stats = []
	wins, losses = 0, 0
	for game in games:
		if player == game[2] or player == game[3]:
			wins += 1
		elif player == game[5] or player == game[6]:
			losses += 1
	win_percentage = wins / (wins + losses)
	stats.append([player, wins, losses, win_percentage])
	return stats




