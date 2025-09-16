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
		# Filter out players with question marks for doubles stats page
		if '?' in player:
			continue
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
		if total_games >= minimum_games and win_percent > 0.5:
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
	cur.execute("SELECT * FROM games WHERE game_date > date('now','-16 hours')")
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
			game_date = game_datetime.strftime("%m/%d/%Y %I:%M %p")
		if len(game[8]) > 19:
			updated_datetime = datetime.strptime(game[8], "%Y-%m-%d %H:%M:%S.%f")
			updated_date = updated_datetime.strftime("%m/%d/%Y %I:%M %p")
		else:
			updated_datetime = datetime.strptime(game[8], "%Y-%m-%d %H:%M:%S")
			updated_date = updated_datetime.strftime("%m/%d/%Y")
		converted_games.append([game[0], game_date, game[2], game[3], game[4], game[5], game[6], game[7], updated_date])
	return converted_games

def search_games_by_player(year, player_name):
	cur = set_cur()
	if year == 'All years':
		cur.execute("SELECT * FROM games WHERE winner1 LIKE ? OR winner2 LIKE ? OR loser1 LIKE ? OR loser2 LIKE ? ORDER BY game_date DESC", 
			(f'%{player_name}%', f'%{player_name}%', f'%{player_name}%', f'%{player_name}%'))
	else:
		cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date)=? AND (winner1 LIKE ? OR winner2 LIKE ? OR loser1 LIKE ? OR loser2 LIKE ?) ORDER BY game_date DESC", 
			(year, f'%{player_name}%', f'%{player_name}%', f'%{player_name}%', f'%{player_name}%'))
	row = cur.fetchall()
	row = convert_ampm(row)
	return row
	
def rare_stats_per_year(year, minimum_games):
	if year == 'All years':
		games = all_games()
	else:
		games = year_games(year)
	players = all_players(games)
	stats = []
	no_wins = []
	for player in players:
		# Filter out players with question marks for doubles stats page
		if '?' in player:
			continue
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
		cur.execute("SELECT * FROM games ORDER BY game_date DESC")
	else:
		cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date)=? ORDER BY game_date DESC", (year,))
	row = cur.fetchall()
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

def get_player_trends_data(player_name):
	"""Get comprehensive trends data for a player for doubles games only"""
	from datetime import datetime, timedelta
	import calendar
	
	# Get only doubles games for the player
	all_games = []
	
	# Doubles games only
	doubles_games = get_player_doubles_games(player_name)
	all_games.extend([(game, 'Doubles') for game in doubles_games])
	
	# Sort by date
	all_games.sort(key=lambda x: x[0][1], reverse=True)
	
	# Calculate overall stats
	total_games = len(all_games)
	total_wins = 0
	total_losses = 0
	
	for game, game_type in all_games:
		if is_player_winner(game, player_name, game_type):
			total_wins += 1
		else:
			total_losses += 1
	
	win_percentage = total_wins / total_games if total_games > 0 else 0
	
	# Calculate current streak
	current_streak = calculate_current_streak(all_games, player_name)
	
	# Calculate monthly stats
	monthly_stats = calculate_monthly_stats(all_games, player_name)
	
	# Get recent games (last 20)
	recent_games = format_recent_games(all_games[:20], player_name)
	
	# Calculate streaks
	streaks = calculate_streaks(all_games, player_name)
	
	return {
		'total_games': total_games,
		'total_wins': total_wins,
		'total_losses': total_losses,
		'win_percentage': win_percentage,
		'current_streak': current_streak,
		'monthly_stats': monthly_stats,
		'recent_games': recent_games,
		'streaks': streaks
	}

def get_player_doubles_games(player_name):
	"""Get all doubles games for a player"""
	cur = set_cur()
	cur.execute("SELECT * FROM games WHERE winner1 = ? OR winner2 = ? OR loser1 = ? OR loser2 = ? ORDER BY game_date DESC", 
				(player_name, player_name, player_name, player_name))
	return cur.fetchall()

def get_player_one_v_one_games(player_name):
	"""Get all 1v1 games for a player"""
	cur = set_cur()
	cur.execute("SELECT * FROM one_v_one_games WHERE winner = ? OR loser = ? ORDER BY game_date DESC", 
				(player_name, player_name))
	return cur.fetchall()

def get_player_other_games(player_name):
	"""Get all other games for a player"""
	cur = set_cur()
	cur.execute("SELECT * FROM other_games WHERE winner1 = ? OR winner2 = ? OR winner3 = ? OR winner4 = ? OR winner5 = ? OR winner6 = ? OR loser1 = ? OR loser2 = ? OR loser3 = ? OR loser4 = ? OR loser5 = ? OR loser6 = ? ORDER BY game_date DESC", 
				(player_name, player_name, player_name, player_name, player_name, player_name, player_name, player_name, player_name, player_name, player_name, player_name))
	return cur.fetchall()

def get_player_vollis_games(player_name):
	"""Get all vollis games for a player"""
	cur = set_cur()
	cur.execute("SELECT * FROM vollis_games WHERE winner = ? OR loser = ? ORDER BY game_date DESC", 
				(player_name, player_name))
	return cur.fetchall()

def is_player_winner(game, player_name, game_type):
	"""Check if player won the doubles game"""
	return player_name == game[2] or player_name == game[3]

def calculate_current_streak(games, player_name):
	"""Calculate current win/loss streak"""
	if not games:
		return "No games"
	
	current_type = None
	streak_length = 0
	
	for game, game_type in games:
		is_winner = is_player_winner(game, player_name, game_type)
		result_type = 'Win' if is_winner else 'Loss'
		
		if current_type is None:
			current_type = result_type
			streak_length = 1
		elif current_type == result_type:
			streak_length += 1
		else:
			break
	
	return f"{streak_length} {current_type}{'s' if streak_length != 1 else ''}"

def calculate_monthly_stats(games, player_name):
	"""Calculate monthly statistics"""
	from collections import defaultdict
	from datetime import datetime
	import calendar
	
	monthly_data = defaultdict(lambda: {'games': 0, 'wins': 0, 'losses': 0})
	
	for game, game_type in games:
		# Handle datetime strings with or without microseconds
		game_date_str = game[1]
		if len(game_date_str) > 19:  # Has microseconds
			game_date = datetime.strptime(game_date_str, "%Y-%m-%d %H:%M:%S.%f")
		else:  # Standard format
			game_date = datetime.strptime(game_date_str, "%Y-%m-%d %H:%M:%S")
		month_key = f"{game_date.year}-{game_date.month:02d}"
		month_name = f"{calendar.month_name[game_date.month]} {game_date.year}"
		
		monthly_data[month_key]['month'] = month_name
		monthly_data[month_key]['games'] += 1
		
		if is_player_winner(game, player_name, game_type):
			monthly_data[month_key]['wins'] += 1
		else:
			monthly_data[month_key]['losses'] += 1
	
	# Convert to list and calculate win percentages
	monthly_stats = []
	for month_key in sorted(monthly_data.keys(), reverse=True):
		data = monthly_data[month_key]
		data['win_percentage'] = data['wins'] / data['games'] if data['games'] > 0 else 0
		monthly_stats.append(data)
	
	return monthly_stats

def format_recent_games(games, player_name):
	"""Format recent games for display"""
	from datetime import datetime
	
	recent_games = []
	for game, game_type in games:
		# Handle datetime strings with or without microseconds
		game_date_str = game[1]
		if len(game_date_str) > 19:  # Has microseconds
			game_date = datetime.strptime(game_date_str, "%Y-%m-%d %H:%M:%S.%f")
		else:  # Standard format
			game_date = datetime.strptime(game_date_str, "%Y-%m-%d %H:%M:%S")
		formatted_date = game_date.strftime("%m/%d/%Y")
		
		is_winner = is_player_winner(game, player_name, game_type)
		result = 'Win' if is_winner else 'Loss'
		
		# Get score and opponents for doubles games
		if is_winner:
			score = f"{game[4]} - {game[7]}"
			opponents = f"{game[5]}, {game[6]}"
		else:
			score = f"{game[7]} - {game[4]}"
			opponents = f"{game[2]}, {game[3]}"
		
		recent_games.append({
			'date': formatted_date,
			'game_type': game_type,
			'result': result,
			'score': score,
			'opponents': opponents
		})
	
	return recent_games

def calculate_streaks(games, player_name):
	"""Calculate all win/loss streaks"""
	from datetime import datetime, timedelta
	
	streaks = []
	current_streak = None
	streak_length = 0
	streak_start = None
	
	for game, game_type in games:
		is_winner = is_player_winner(game, player_name, game_type)
		result_type = 'Win' if is_winner else 'Loss'
		# Handle datetime strings with or without microseconds
		game_date_str = game[1]
		if len(game_date_str) > 19:  # Has microseconds
			game_date = datetime.strptime(game_date_str, "%Y-%m-%d %H:%M:%S.%f")
		else:  # Standard format
			game_date = datetime.strptime(game_date_str, "%Y-%m-%d %H:%M:%S")
		
		if current_streak is None:
			current_streak = result_type
			streak_length = 1
			streak_start = game_date
		elif current_streak == result_type:
			streak_length += 1
		else:
			# End of current streak, record it
			streaks.append({
				'type': current_streak,
				'length': streak_length,
				'start_date': streak_start.strftime("%m/%d/%Y"),
				'end_date': (streak_start - timedelta(days=1)).strftime("%m/%d/%Y") if streak_length > 1 else streak_start.strftime("%m/%d/%Y")
			})
			
			# Start new streak
			current_streak = result_type
			streak_length = 1
			streak_start = game_date
	
	# Add the last streak
	if current_streak is not None:
		streaks.append({
			'type': current_streak,
			'length': streak_length,
			'start_date': streak_start.strftime("%m/%d/%Y"),
			'end_date': (streak_start - timedelta(days=1)).strftime("%m/%d/%Y") if streak_length > 1 else streak_start.strftime("%m/%d/%Y")
		})
	
	# Sort by length (longest first) and limit to top 10
	streaks.sort(key=lambda x: x['length'], reverse=True)
	return streaks[:10]

def get_all_players_for_trends():
	"""Get all unique players from doubles games sorted by number of games played"""
	cur = set_cur()
	
	# Get all players with their game counts
	cur.execute("""
		SELECT player, COUNT(*) as game_count FROM (
			SELECT winner1 as player FROM games
			UNION ALL
			SELECT winner2 as player FROM games
			UNION ALL
			SELECT loser1 as player FROM games
			UNION ALL
			SELECT loser2 as player FROM games
		) WHERE player IS NOT NULL
		GROUP BY player
		ORDER BY game_count DESC, player ASC
	""")
	
	players_with_counts = cur.fetchall()
	return [player[0] for player in players_with_counts if player[0]]

def date_range_games(start_date, end_date):
	"""Get all doubles games within a date range"""
	cur = set_cur()
	cur.execute("SELECT * FROM games WHERE game_date >= ? AND game_date <= ? ORDER BY game_date DESC", 
				(start_date, end_date))
	games = cur.fetchall()
	return convert_ampm(games)

def get_date_range_stats(start_date, end_date):
	"""Calculate stats for players within a date range"""
	games = date_range_games(start_date, end_date)
	players = all_players(games)
	stats = []
	
	for player in players:
		# Filter out players with question marks for stats
		if '?' in player:
			continue
			
		wins, losses = 0, 0
		for game in games:
			if player == game[2] or player == game[3]:
				wins += 1
			elif player == game[5] or player == game[6]:
				losses += 1
		
		if wins + losses > 0:  # Only include players who played games
			win_percentage = wins / (wins + losses)
			differential = wins - losses
			stats.append([player, wins, losses, win_percentage, differential])
	
	# Sort by win percentage, then by differential
	stats.sort(key=lambda x: x[4], reverse=True)
	stats.sort(key=lambda x: x[3], reverse=True)
	return stats




