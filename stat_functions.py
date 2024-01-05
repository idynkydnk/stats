from database_functions import *
from datetime import datetime, date

def stats_per_year(year, minimum_games):
# year - 'All Years' , 'Past Year' or the desired year

	games = games_for_year(year)
	players = all_players(games)
	stats = []
	no_wins = []
	for player in players:
		wins, losses = 0, 0
		for game in games:
			if player == game.winner1 or player == game.winner2:
				wins += 1
			elif player == game.loser1 or player == game.loser2:
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
			if team['player1'] == game.winner1 and team['player2'] == game.winner2 or team['player1'] == game.winner2 and team['player2'] == game.winner1:
				wins += 1
			elif team['player1'] == game.loser1 and team['player2'] == game.loser2 or team['player1'] == game.loser2 and team['player2'] == game.loser1:
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
		if game.winner1 > game.winner2:
			winners['player1'] = game.winner2
			winners['player2'] = game.winner1
		else:
			winners['player1'] = game.winner1
			winners['player2'] = game.winner2
		if winners not in all_teams:
			all_teams.append(winners)
		if game.loser1 > game.loser2:
			losers['player1'] = game.loser2
			losers['player2'] = game.loser1
		else:
			losers['player1'] = game.loser1
			losers['player2'] = game.loser2
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
			if player == game.winner1 or player == game.winner2:
				wins += 1
				differential += (game.winner_score - game.loser_score)
			elif player == game.loser1 or player == game.loser2:
				losses += 1
				differential -= (game.winner_score - game.loser_score)
		win_percentage = wins / (wins + losses)
		stats.append([player, wins, losses, win_percentage, differential])
	stats.sort(key=lambda x: x[4], reverse=True)
	stats.sort(key=lambda x: x[3], reverse=True)
	return stats

def todays_games():
	cur = db_get_cursor()[0]
	cur.execute("SELECT * FROM games WHERE game_date > date('now','-15 hours')")
	rows = cur.fetchall()
	rows.sort(reverse=True)
	# think i need the "if rows" at the end in case of empty rows
	games = [doubles_game.db_row2doubles_game(row) for row in rows if rows]
	return games
	
def rare_stats_per_year(year, minimum_games):
# year - 'All Years' , 'Past Year' or the desired year
	games = games_for_year(year)
	players = all_players(games)
	stats = []
	no_wins = []
	for player in players:
		wins, losses = 0, 0
		for game in games:
			if player == game.winner1 or player == game.winner2:
				wins += 1
			elif player == game.loser1 or player == game.loser2:
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

def all_players(games):
	# [ToDo] Can do this cleaner by pulling all names and turning them into a set so only unique values are retained
	p1 = [x.winner1 for x in games]
	p2 = [x.winner2 for x in games]
	p3 = [x.loser1 for x in games]
	p4 = [x.loser2 for x in games]
	players = set(p1 + p2 + p3 + p4)
	return players

def games_for_year(year = None):
# return a list of doubles_game objects for a given year or All Years
# 	year - str or int, if not provided then will return all games

	cur = db_get_cursor()[0]
	if not year or year == 'All Years':
		cur.execute("SELECT * FROM games")
	elif year == 'Past Year':
		cur.execute("SELECT * FROM games WHERE game_date > date('now','-1 years')")
	else:
		cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date)=?", (str(year),))

	rows = cur.fetchall()
	games = [doubles_game.db_row2doubles_game(row) for row in rows if rows]
	return games

def grab_all_years():
	# [ToDo] Super inefficient to bring all games into memory as objects just to get the years 
	games = games_for_year() # get all games
	years = []
	for game in games:
		game_year = str(game.game_datetime.year)
		if game_year not in years:
			years.append(game_year)
	if len(years) > 1:
		years.append('All Years')
		years.append('Past Year')
	return years

def all_years_player(name):
	years = []
	games = all_games_player(name)
	for game in games:
		game_year = str(game.game_datetime.year)
		if game_year not in years:
			years.append(game_year)
	if len(years) > 1:
		years.append('All Years')
		years.append('Past Year')
	return years


def all_games_player(name):
	cur = db_get_cursor()[0]
	cur.execute("SELECT * FROM games WHERE (winner1=? OR winner2=? OR loser1=? OR loser2=?)", (name, name, name, name))
	rows = cur.fetchall()
	games = [doubles_game.db_row2doubles_game(row) for row in rows if rows]
	return games

def find_game(game_id):
	cur = db_get_cursor()[0]
	cur.execute("SELECT * FROM games WHERE id=?", (game_id,))
	row = cur.fetchall()
	if len(row) == 0:
		raise Exception('No game with id = ' + str(game_id))
	elif len(row) == 1:
		return doubles_game.db_row2doubles_game(row[0])
	else:
		raise Exception('At most single row should have been returned. "id" column in database table should have unique values')
	

def games_from_player_by_year(year, name):
# year - can be a str, or int
	cur = db_get_cursor()[0]
	if year == 'All Years':
		cur.execute("SELECT * FROM games WHERE (winner1=? OR winner2=? OR loser1=? OR loser2=?)", (name, name, name, name))
	elif year == 'Past Year':
		cur.execute("SELECT * FROM games WHERE game_date > date('now','-1 years')  AND (winner1=? OR winner2=? OR loser1=? OR loser2=?)", (name, name, name, name))
	else:
		cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date)=? AND (winner1=? OR winner2=? OR loser1=? OR loser2=?)", (str(year), name, name, name, name))
	rows = cur.fetchall()
	games = [doubles_game.db_row2doubles_game(row) for row in rows if rows]
	return games

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
				if game.winner1 == name or game.winner2 == name:
					if game.winner1 == partner or game.winner2 == partner:
						wins += 1
				if game.loser1 == name or game.loser2 == name:
					if game.loser1 == partner or game.loser2 == partner:
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
				if game.winner1 == name or game.winner2 == name:
					if game.winner1 == partner or game.winner2 == partner:
						wins += 1
				if game.loser1 == name or game.loser2 == name:
					if game.loser1 == partner or game.loser2 == partner:
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
				if game.winner1 == name or game.winner2 == name:
					if game.loser1 == opponent or game.loser2 == opponent:
						wins += 1
				if game.loser1 == name or game.loser2 == name:
					if game.winner1 == opponent or game.winner2 == opponent:
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
				if game.winner1 == name or game.winner2 == name:
					if game.loser1 == opponent or game.loser2 == opponent:
						wins += 1
				if game.loser1 == name or game.loser2 == name:
					if game.winner1 == opponent or game.winner2 == opponent:
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
		if player == game.winner1 or player == game.winner2:
			wins += 1
		elif player == game.loser1 or player == game.loser2:
			losses += 1
	win_percentage = wins / (wins + losses)
	stats.append([player, wins, losses, win_percentage])
	return stats




