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
			if player in game.winners:
				wins += 1
			elif player in game.losers:
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
			if (team['player1'] in game.winners) and (team['player2'] in game.winners):
				wins += 1
			elif (team['player1'] in game.losers) and (team['player2'] in game.losers):
				losses += 1
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
		if game.winners[0] > game.winners[1]:
			winners['player1'] = game.winners[1]
			winners['player2'] = game.winners[0]
		else:
			winners['player1'] = game.winners[0]
			winners['player2'] = game.winners[1]
		if winners not in all_teams:
			all_teams.append(winners)
		if game.losers[0] > game.losers[1]:
			losers['player1'] = game.losers[1]
			losers['player2'] = game.losers[0]
		else:
			losers['player1'] = game.losers[0]
			losers['player2'] = game.losers[1]
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
			if player in game.winners:
				wins += 1
				differential += (game.winner_score - game.loser_score)
			elif player in game.losers:
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
			if player in game.winners:
				wins += 1
			elif player in game.losers:
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
	all_players = set()
	for game in games:
		all_players = all_players.union(game.players)
	return all_players

def games_for_year(year = None):
# return a list of doubles_game objects for <year>
# 	year - str or int, if not provided then will return all games. Can also be 'All Years' or 'Past Year'

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

def year_dropdown_values(player_name = None):
	"""Returns the values to use for the years selection dropdown box"""
	years = db_years(player_name)
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
				if name in game.winners:
					if game.winners[0] == partner or game.winners[1] == partner:
						wins += 1
				if name in game.losers:
					if game.losers[0] == partner or game.losers[1] == partner:
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
	no_wins = []
	if not games:
		return stats
	else:
		players = all_players(games)
		players.remove(name)
		for partner in players:
			wins, losses = 0, 0
			for game in games:
				if name in game.winners:
					if game.winners[0] == partner or game.winners[1] == partner:
						wins += 1
				if name in game.losers:
					if game.losers[0] == partner or game.losers[1] == partner:
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
	no_wins = []
	if not games:
		return stats
	else:
		players = all_players(games)
		players.remove(name)
		for opponent in players:
			wins, losses = 0, 0
			for game in games:
				if name in game.winners:
					if opponent in game.losers:
						wins += 1
				if name in game.losers:
					if opponent in game.winners:
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
	no_wins = []
	if not games:
		return stats
	else:
		players = all_players(games)
		players.remove(name)
		for opponent in players:
			wins, losses = 0, 0
			for game in games:
				if name in game.winners:
					if opponent in game.losers:
						wins += 1
				if name in game.losers:
					if opponent in game.winners:
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
		if player in game.winners:
			wins += 1
		elif player in game.losers:
			losses += 1
	win_percentage = wins / (wins + losses)
	stats.append([player, wins, losses, win_percentage])
	return stats