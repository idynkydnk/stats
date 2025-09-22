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
        game = (game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, game_id2)
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
        x = {
            'team': team,
            'wins': wins,
            'losses': losses,
            'win_percentage': win_percent,
            'total_games': total_games
        }
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
    from datetime import datetime
    cur = set_cur()
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("SELECT * FROM games WHERE date(game_date) = ?", (today,))
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
	row = convert_ampm(row)
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

def get_dashboard_data(selected_year=None):
	"""Get comprehensive data for the dashboard"""
	from datetime import datetime, timedelta
	
	# Use selected year or default to current year
	if selected_year is None:
		selected_year = str(datetime.now().year)
	else:
		selected_year = str(selected_year)  # Ensure it's a string
	
	# Get stats for selected year (no minimum games filter yet - we'll apply it later)
	current_stats = stats_per_year(selected_year, 0)  # 0 minimum games for dashboard
	
	# Get all-time stats
	all_time_stats = stats_per_year('All years', 0)  # 0 minimum games for dashboard
	
	# Get recent games (last 10) for selected year
	recent_games = year_games(selected_year)[:10]
	
	# Get monthly game counts for selected year
	monthly_data = get_monthly_game_counts(selected_year)
	
	# Calculate minimum games using same formula as doubles stats page
	games_for_year = year_games(selected_year)
	if games_for_year:
		if len(games_for_year) < 30:
			minimum_games = 1
		else:
			minimum_games = len(games_for_year) // 30
	else:
		minimum_games = 1
	
	# Get top performers for selected year
	# Top 10 by win percentage (must meet minimum games requirement)
	qualified_players = [s for s in current_stats if s[1] + s[2] >= minimum_games]
	top_win_percentage = sorted(qualified_players, key=lambda x: x[3], reverse=True)[:10]
	
	# Top 10 by games played (no minimum games requirement - show actual top 10)
	top_games_played = sorted(current_stats, key=lambda x: x[1] + x[2], reverse=True)[:10]
	
	# Get today's stats (always show today's activity regardless of selected year)
	today_stats = todays_stats()
	
	# Get current win/loss streaks for last 365 days (not year-specific)
	current_streaks = get_current_streaks_last_365_days()
	
	# Separate winning and losing streaks
	win_streaks = [streak for streak in current_streaks if streak[2] == 'win']
	loss_streaks = [streak for streak in current_streaks if streak[2] == 'loss']
	
	# Get best streaks for the selected year
	year_best_streaks = get_best_streaks_for_year(selected_year)
	best_win_streaks = [streak for streak in year_best_streaks if streak[2] == 'win']
	best_loss_streaks = [streak for streak in year_best_streaks if streak[2] == 'loss']
	
	return {
		'current_year': selected_year,
		'current_stats': current_stats,
		'all_time_stats': all_time_stats,
		'recent_games': recent_games,
		'monthly_data': monthly_data,
		'top_win_percentage': top_win_percentage,
		'top_games_played': top_games_played,
		'today_stats': today_stats,
		'win_streaks': win_streaks,
		'loss_streaks': loss_streaks,
		'best_win_streaks': best_win_streaks,
		'best_loss_streaks': best_loss_streaks,
		'minimum_games': minimum_games
	}

def get_monthly_game_counts(year):
	"""Get game counts by month for a given year"""
	cur = set_cur()
	if year == 'All years':
		cur.execute("""
			SELECT strftime('%m', game_date) as month, COUNT(*) as count
			FROM games 
			GROUP BY strftime('%m', game_date)
			ORDER BY month
		""")
	else:
		cur.execute("""
			SELECT strftime('%m', game_date) as month, COUNT(*) as count
			FROM games 
			WHERE strftime('%Y', game_date) = ?
			GROUP BY strftime('%m', game_date)
			ORDER BY month
		""", (str(year),))
	
	results = cur.fetchall()
	monthly_counts = {}
	for month, count in results:
		monthly_counts[int(month)] = count
	
	# Fill in missing months with 0
	for month in range(1, 13):
		if month not in monthly_counts:
			monthly_counts[month] = 0
	
	return monthly_counts

def get_win_loss_streaks():
	"""Get current win/loss streaks for all players"""
	cur = set_cur()
	cur.execute("SELECT * FROM games ORDER BY game_date DESC")
	all_games = cur.fetchall()
	
	streaks = {}
	for game in all_games:
		# Check winners
		for i in [2, 3]:  # winner1, winner2
			player = game[i]
			if player not in streaks:
				streaks[player] = {'current': 0, 'type': None, 'max': 0}
			
			if streaks[player]['type'] == 'win':
				streaks[player]['current'] += 1
			elif streaks[player]['type'] == 'loss':
				streaks[player]['current'] = 1
				streaks[player]['type'] = 'win'
			else:
				streaks[player]['current'] = 1
				streaks[player]['type'] = 'win'
			
			streaks[player]['max'] = max(streaks[player]['max'], streaks[player]['current'])
		
		# Check losers
		for i in [5, 6]:  # loser1, loser2
			player = game[i]
			if player not in streaks:
				streaks[player] = {'current': 0, 'type': None, 'max': 0}
			
			if streaks[player]['type'] == 'loss':
				streaks[player]['current'] += 1
			elif streaks[player]['type'] == 'win':
				streaks[player]['current'] = 1
				streaks[player]['type'] = 'loss'
			else:
				streaks[player]['current'] = 1
				streaks[player]['type'] = 'loss'
			
			streaks[player]['max'] = max(streaks[player]['max'], streaks[player]['current'])
	
	# Convert to list and sort by current streak
	streak_list = []
	for player, data in streaks.items():
		if '?' not in player and data['current'] > 0:
			streak_list.append([player, data['current'], data['type'], data['max']])
	
	streak_list.sort(key=lambda x: x[1], reverse=True)
	return streak_list[:10]  # Top 10 current streaks

def get_win_loss_streaks_for_year(year):
	"""Get current win/loss streaks for all players in a specific year"""
	cur = set_cur()
	if year == 'All years':
		cur.execute("SELECT * FROM games ORDER BY game_date DESC")
	else:
		cur.execute("SELECT * FROM games WHERE strftime('%Y', game_date) = ? ORDER BY game_date DESC", (str(year),))
	all_games = cur.fetchall()

def get_current_streaks_last_365_days():
	"""Get current win/loss streaks for all players in the last 365 days"""
	from datetime import datetime, timedelta
	cur = set_cur()
	
	# Calculate date 365 days ago
	one_year_ago = datetime.now() - timedelta(days=365)
	one_year_ago_str = one_year_ago.strftime('%Y-%m-%d %H:%M:%S')
	
	cur.execute("SELECT * FROM games WHERE game_date >= ? ORDER BY game_date DESC", (one_year_ago_str,))
	all_games = cur.fetchall()
	
	# Track the most recent result for each player
	player_recent_results = {}
	player_max_streaks = {}
	
	for game in all_games:
		# Process winners
		for i in [2, 3]:  # winner1, winner2
			player = game[i]
			if player not in player_recent_results:
				player_recent_results[player] = []
				player_max_streaks[player] = {'win': 0, 'loss': 0}
			player_recent_results[player].append('win')
		
		# Process losers
		for i in [5, 6]:  # loser1, loser2
			player = game[i]
			if player not in player_recent_results:
				player_recent_results[player] = []
				player_max_streaks[player] = {'win': 0, 'loss': 0}
			player_recent_results[player].append('loss')
	
	# Calculate current streaks from most recent results
	streak_list = []
	for player, results in player_recent_results.items():
		if '?' in player or not results:
			continue
			
		# Calculate current streak from most recent games
		current_streak = 0
		current_type = results[0]  # Most recent result
		
		for result in results:
			if result == current_type:
				current_streak += 1
			else:
				break  # Streak broken
		
		# Calculate max streak for this type
		max_streak = 0
		temp_streak = 0
		temp_type = None
		
		for result in results:
			if result == temp_type:
				temp_streak += 1
			else:
				temp_streak = 1
				temp_type = result
			max_streak = max(max_streak, temp_streak)
		
		if current_streak > 0:
			streak_list.append([player, current_streak, current_type, max_streak])
	
	# Sort by type (wins first), then by streak length (highest first)
	streak_list.sort(key=lambda x: (x[2] == 'win', x[1]), reverse=True)
	return streak_list  # Return all streaks, not just top 10

def calculate_glicko_rankings():
	"""Calculate Glicko-2 rankings for all players based on doubles games"""
	import math
	from collections import defaultdict
	
	cur = set_cur()
	cur.execute("SELECT * FROM games ORDER BY game_date ASC")
	games = cur.fetchall()
	
	# Initialize player ratings (rating, rating_deviation, volatility)
	# Glicko-2 default values
	INITIAL_RATING = 1500
	INITIAL_RD = 350
	INITIAL_VOLATILITY = 0.06
	TAU = 0.5  # System constraint
	
	player_ratings = defaultdict(lambda: {
		'rating': INITIAL_RATING,
		'rd': INITIAL_RD,
		'volatility': INITIAL_VOLATILITY
	})
	
	# Process games chronologically
	for game in games:
		# Get game date
		game_date_str = game[1]
		if len(game_date_str) > 19:
			game_date = datetime.strptime(game_date_str, "%Y-%m-%d %H:%M:%S.%f")
		else:
			game_date = datetime.strptime(game_date_str, "%Y-%m-%d %H:%M:%S")
		
		# Skip players with question marks
		winners = [game[2], game[3]]  # winner1, winner2
		losers = [game[5], game[6]]   # loser1, loser2
		
		# Filter out players with question marks
		winners = [w for w in winners if '?' not in w]
		losers = [l for l in losers if '?' not in l]
		
		if not winners or not losers:
			continue
		
		# Update ratings for each player
		for winner in winners:
			for loser in losers:
				update_glicko_rating(player_ratings[winner], player_ratings[loser], 1, TAU)
				update_glicko_rating(player_ratings[loser], player_ratings[winner], 0, TAU)
	
	# Convert to list and sort by rating
	rankings = []
	for player, rating_data in player_ratings.items():
		rankings.append({
			'player': player,
			'rating': round(rating_data['rating']),
			'rd': round(rating_data['rd']),
			'volatility': round(rating_data['volatility'], 4)
		})
	
	# Sort by rating (highest first)
	rankings.sort(key=lambda x: x['rating'], reverse=True)
	
	return rankings

def update_glicko_rating(player_rating, opponent_rating, score, tau):
	"""Update a player's Glicko-2 rating after a game"""
	import math
	
	# Convert ratings to Glicko scale
	mu = (player_rating['rating'] - 1500) / 173.7178
	phi = player_rating['rd'] / 173.7178
	sigma = player_rating['volatility']
	
	opp_mu = (opponent_rating['rating'] - 1500) / 173.7178
	opp_phi = opponent_rating['rd'] / 173.7178
	
	# Calculate Glicko-2 update
	v = 1 / (g(opp_phi) * E(mu, opp_mu, opp_phi) * (1 - E(mu, opp_mu, opp_phi)))
	delta = v * g(opp_phi) * (score - E(mu, opp_mu, opp_phi))
	
	# New volatility
	a = math.log(sigma**2)
	A = a
	B = None
	
	if delta**2 > phi**2 + v:
		B = math.log(delta**2 - phi**2 - v)
	else:
		k = 1
		while f(a - k * tau, delta, phi, v, a, tau) < 0:
			k += 1
		B = a - k * tau
	
	fA = f(A, delta, phi, v, a, tau)
	fB = f(B, delta, phi, v, a, tau)
	
	while abs(B - A) > 0.000001:
		C = A + (A - B) * fA / (fB - fA)
		fC = f(C, delta, phi, v, a, tau)
		
		if fC * fB < 0:
			A = B
			fA = fB
		else:
			fA = fA / 2
		
		B = C
		fB = fC
	
	new_sigma = math.exp(A / 2)
	
	# New rating deviation
	phi_star = math.sqrt(phi**2 + new_sigma**2)
	new_phi = 1 / math.sqrt(1 / phi_star**2 + 1 / v)
	
	# New rating
	new_mu = mu + new_phi**2 * g(opp_phi) * (score - E(mu, opp_mu, opp_phi))
	
	# Convert back to original scale
	player_rating['rating'] = 173.7178 * new_mu + 1500
	player_rating['rd'] = 173.7178 * new_phi
	player_rating['volatility'] = new_sigma

def g(phi):
	"""Glicko-2 g function"""
	import math
	return 1 / math.sqrt(1 + 3 * phi**2 / math.pi**2)

def E(mu, opp_mu, opp_phi):
	"""Glicko-2 E function"""
	import math
	return 1 / (1 + math.exp(-g(opp_phi) * (mu - opp_mu)))

def f(x, delta, phi, v, a, tau=0.5):
	"""Glicko-2 f function"""
	import math
	ex = math.exp(x)
	num1 = ex * (delta**2 - phi**2 - v - ex)
	denom1 = 2 * (phi**2 + v + ex)**2
	num2 = x - a
	denom2 = tau**2
	return num1 / denom1 - num2 / denom2

def get_best_streaks_for_year(year):
	"""Get the best win/loss streaks for a specific year"""
	cur = set_cur()
	if year == 'All years':
		cur.execute("SELECT * FROM games ORDER BY game_date ASC")  # Chronological order
	else:
		cur.execute("SELECT * FROM games WHERE strftime('%Y', game_date) = ? ORDER BY game_date ASC", (str(year),))
	all_games = cur.fetchall()
	
	# Track all results for each player in chronological order
	player_all_results = {}
	
	for game in all_games:
		# Process winners
		for i in [2, 3]:  # winner1, winner2
			player = game[i]
			if player not in player_all_results:
				player_all_results[player] = []
			player_all_results[player].append('win')
		
		# Process losers
		for i in [5, 6]:  # loser1, loser2
			player = game[i]
			if player not in player_all_results:
				player_all_results[player] = []
			player_all_results[player].append('loss')
	
	# Calculate best streaks for each player
	best_streaks = []
	for player, results in player_all_results.items():
		if '?' in player or not results:
			continue
		
		# Find the longest winning streak
		max_win_streak = 0
		current_win_streak = 0
		
		# Find the longest losing streak
		max_loss_streak = 0
		current_loss_streak = 0
		
		for result in results:
			if result == 'win':
				current_win_streak += 1
				current_loss_streak = 0
				max_win_streak = max(max_win_streak, current_win_streak)
			else:  # loss
				current_loss_streak += 1
				current_win_streak = 0
				max_loss_streak = max(max_loss_streak, current_loss_streak)
		
		# Add best streaks to the list
		if max_win_streak > 0:
			best_streaks.append([player, max_win_streak, 'win'])
		if max_loss_streak > 0:
			best_streaks.append([player, max_loss_streak, 'loss'])
	
	# Sort by streak length (highest first)
	best_streaks.sort(key=lambda x: x[1], reverse=True)
	return best_streaks

def get_streak_games(player_name, streak_type, streak_length, year=None):
	"""Get the games that made up a specific streak for a player"""
	cur = set_cur()
	
	# Use a more robust query that handles apostrophe issues
	# Split the player name to handle apostrophes
	name_parts = player_name.split("'")
	if len(name_parts) == 2:
		# Handle names with apostrophes like "Brian O'Neill"
		first_part = name_parts[0]  # "Brian O"
		second_part = name_parts[1]  # "Neill"
		like_pattern = f"{first_part}%{second_part}"
	else:
		# Handle names without apostrophes
		like_pattern = player_name
	
	if year and year != 'All years':
		cur.execute("""
			SELECT * FROM games 
			WHERE strftime('%Y', game_date) = ? 
			AND (winner1 LIKE ? OR winner2 LIKE ? OR loser1 LIKE ? OR loser2 LIKE ?)
			ORDER BY game_date ASC
		""", (str(year), like_pattern, like_pattern, like_pattern, like_pattern))
	else:
		cur.execute("""
			SELECT * FROM games 
			WHERE (winner1 LIKE ? OR winner2 LIKE ? OR loser1 LIKE ? OR loser2 LIKE ?)
			ORDER BY game_date ASC
		""", (like_pattern, like_pattern, like_pattern, like_pattern))
	
	all_games = cur.fetchall()
	
	# Find all games for this player
	player_games = []
	for game in all_games:
		# Check if player was in this game
		game_players = [game[2], game[3], game[5], game[6]]  # winner1, winner2, loser1, loser2
		player_found = False
		matched_name = None
		
		for game_player in game_players:
			# Use fuzzy matching to handle apostrophe issues
			if (player_name == game_player or 
				player_name.replace("'", "'") == game_player or 
				player_name == game_player.replace("'", "'") or
				player_name.replace("'", "'") == game_player.replace("'", "'")):
				player_found = True
				matched_name = game_player
				break
		
		if player_found:
			# Determine if player won or lost
			if matched_name in [game[2], game[3]]:  # winners
				result = 'win'
			else:  # losers
				result = 'loss'
			
			player_games.append((game, result))
	
	# Find the most recent streak of the specified length and type
	# We need to work backwards from the most recent games
	player_games.reverse()  # Start from most recent
	
	streak_games = []
	current_streak = 0
	current_type = None
	
	for game, result in player_games:
		if result == current_type:
			current_streak += 1
			streak_games.append(game)
			
			# Check if we found the streak we're looking for
			if current_streak == streak_length and current_type == streak_type:
				streak_games.reverse()  # Put back in chronological order
				return convert_ampm(streak_games)
		else:
			# Streak broken, start new one
			current_streak = 1
			current_type = result
			streak_games = [game]
			
			# Check if this single game is the streak we're looking for
			if current_streak == streak_length and current_type == streak_type:
				streak_games.reverse()  # Put back in chronological order
				return convert_ampm(streak_games)
	
	# If we get here, we didn't find the exact streak
	# Return the longest streak of the requested type
	if current_type == streak_type and current_streak >= streak_length:
		streak_games.reverse()  # Put back in chronological order
		return convert_ampm(streak_games[-streak_length:])  # Return the last streak_length games
	
	return []  # No streak found
