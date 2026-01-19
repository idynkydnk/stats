from database_functions import *
from datetime import datetime, date
from functools import lru_cache
import time

# Simple in-memory cache with expiration
_cache = {}
_cache_timestamps = {}
CACHE_TTL = 1800  # 30 minutes - increased for better performance

def cached(ttl=CACHE_TTL):
    """Decorator for caching function results with TTL"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            key = (func.__name__, args, tuple(sorted(kwargs.items())))
            current_time = time.time()
            
            # Check if cached and not expired
            if key in _cache and key in _cache_timestamps:
                if current_time - _cache_timestamps[key] < ttl:
                    return _cache[key]
            
            # Calculate and cache result
            result = func(*args, **kwargs)
            _cache[key] = result
            _cache_timestamps[key] = current_time
            return result
        return wrapper
    return decorator

def clear_stats_cache():
    """Clear all cached stats - call after adding/editing games"""
    global _cache, _cache_timestamps
    _cache = {}
    _cache_timestamps = {}

@cached(ttl=1800)
def get_player_wins_losses(year):
    """Get wins and losses for all players in a year - O(n) instead of O(n²)"""
    if year == 'All years':
        games = all_games()
    else:
        games = year_games(year)
    
    player_wins_losses = {}
    for game in games:
        winners = [game[2], game[3]]
        losers = [game[5], game[6]]
        winners = [w for w in winners if '?' not in w]
        losers = [l for l in losers if '?' not in l]
        
        for player in winners:
            if player not in player_wins_losses:
                player_wins_losses[player] = {'wins': 0, 'losses': 0}
            player_wins_losses[player]['wins'] += 1
        
        for player in losers:
            if player not in player_wins_losses:
                player_wins_losses[player] = {'wins': 0, 'losses': 0}
            player_wins_losses[player]['losses'] += 1
    
    return player_wins_losses

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
    # Add comments if provided (index 8)
    if len(game) > 8:
        full_game.append(game[8])
    else:
        full_game.append('')
    all_games.append(full_game)
    enter_data_into_database(all_games)

def update_game(game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, game_id2):
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    with conn:
        game = (game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, game_id2)
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

@cached(ttl=1800)
def stats_per_year(year, minimum_games):
    if year == 'All years':
        games = all_games()
    else:
        games = year_games(year)
    
    # Calculate TrueSkill ratings
    trueskill_rankings = calculate_trueskill_rankings(year)
    rating_map = {r['player']: r['rating'] for r in trueskill_rankings}
    
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
        rating = rating_map.get(player, 0)  # Get TrueSkill rating, default to 0
        if wins + losses >= minimum_games:
            if wins == 0:
                no_wins.append([player, wins, losses, win_percentage, rating])
            else:
                stats.append([player, wins, losses, win_percentage, rating])
    # Sort by rating instead of win percentage
    stats.sort(key=lambda x: x[4], reverse=True)
    no_wins.sort(key=lambda x: x[4], reverse=True)
    for stat in no_wins:
        stats.append(stat)
    return stats

def team_stats_per_year(year, minimum_games, games):
    """Calculate team stats - uses cached helper for expensive computation"""
    return _team_stats_per_year_cached(year, minimum_games)

@cached(ttl=1800)
def _team_stats_per_year_cached(year, minimum_games):
    """Cached version of team stats calculation"""
    if year == 'All years':
        games = all_games()
    else:
        games = year_games(year)
    
    # Build a lookup dict for faster team matching
    team_records = {}
    
    for game in games:
        # Create normalized team keys (sorted player names)
        winner_key = tuple(sorted([game[2], game[3]]))
        loser_key = tuple(sorted([game[5], game[6]]))
        
        # Record win for winner team
        if winner_key not in team_records:
            team_records[winner_key] = {'wins': 0, 'losses': 0}
        team_records[winner_key]['wins'] += 1
        
        # Record loss for loser team
        if loser_key not in team_records:
            team_records[loser_key] = {'wins': 0, 'losses': 0}
        team_records[loser_key]['losses'] += 1
    
    # Convert to output format
    stats = []
    no_wins = []
    
    for team_key, record in team_records.items():
        wins = record['wins']
        losses = record['losses']
        total_games = wins + losses
        
        if total_games == 0:
            continue
            
        win_percent = wins / total_games
        
        x = {
            'team': {'player1': team_key[0], 'player2': team_key[1]},
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

def recent_games(limit=10):
    """Get the most recent games across all dates"""
    cur = set_cur()
    cur.execute("SELECT * FROM games ORDER BY game_date DESC LIMIT ?", (limit,))
    games = cur.fetchall()
    row = convert_ampm(games)
    return row

def calculate_stats_from_games(games):
    """Calculate player stats from a list of games"""
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

def specific_date_stats(target_date):
    """Get stats for a specific date"""
    cur = set_cur()
    cur.execute("SELECT * FROM games WHERE date(game_date) = ?", (target_date,))
    games = cur.fetchall()
    games.sort(reverse=True)
    converted_games = convert_ampm(games)
    
    stats = calculate_stats_from_games(games)
    return stats, converted_games

def get_previous_date(current_date, days_back=1):
    """Get the date that is days_back before current_date"""
    from datetime import datetime, timedelta
    if isinstance(current_date, str):
        current_date = datetime.strptime(current_date, '%Y-%m-%d')
    previous_date = current_date - timedelta(days=days_back)
    return previous_date.strftime('%Y-%m-%d')

def get_next_date(current_date, days_forward=1):
    """Get the date that is days_forward after current_date"""
    from datetime import datetime, timedelta
    if isinstance(current_date, str):
        current_date = datetime.strptime(current_date, '%Y-%m-%d')
    next_date = current_date + timedelta(days=days_forward)
    return next_date.strftime('%Y-%m-%d')

@cached(ttl=1800)
def get_all_game_dates():
    """Get all dates that have games - single query instead of checking each date"""
    cur = set_cur()
    cur.execute("SELECT DISTINCT date(game_date) FROM games ORDER BY game_date DESC")
    return set(row[0] for row in cur.fetchall())

def has_games_on_date(target_date):
    """Check if there are games on a specific date"""
    game_dates = get_all_game_dates()
    return target_date in game_dates

def get_previous_date_with_games(current_date, max_days_back=30):
    """Get the previous date that has games, skipping days with no games"""
    from datetime import datetime, timedelta
    if isinstance(current_date, str):
        current_date = datetime.strptime(current_date, '%Y-%m-%d')
    
    game_dates = get_all_game_dates()
    
    for days_back in range(1, max_days_back + 1):
        previous_date = current_date - timedelta(days=days_back)
        date_str = previous_date.strftime('%Y-%m-%d')
        if date_str in game_dates:
            return date_str
    return None

def get_next_date_with_games(current_date, max_days_forward=30):
    """Get the next date that has games, skipping days with no games"""
    from datetime import datetime, timedelta
    if isinstance(current_date, str):
        current_date = datetime.strptime(current_date, '%Y-%m-%d')
    
    game_dates = get_all_game_dates()
    
    for days_forward in range(1, max_days_forward + 1):
        next_date = current_date + timedelta(days=days_forward)
        date_str = next_date.strftime('%Y-%m-%d')
        if date_str in game_dates:
            return date_str
    return None

def get_most_recent_date_with_games(max_days_back=30):
    """Get the most recent date that has games, looking back from today"""
    from datetime import datetime, timedelta
    today = datetime.now()
    
    game_dates = get_all_game_dates()
    
    for days_back in range(0, max_days_back + 1):
        check_date = today - timedelta(days=days_back)
        date_str = check_date.strftime('%Y-%m-%d')
        if date_str in game_dates:
            return date_str
    return None

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

        comment_text = ""
        if len(game) > 9 and game[9]:
            comment_text = str(game[9])

        converted_games.append([
            game[0],
            game_date,
            game[2],
            game[3],
            game[4],
            game[5],
            game[6],
            game[7],
            updated_date,
            comment_text
        ])
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
	
@cached(ttl=1800)
def rare_stats_per_year(year, minimum_games):
    if year == 'All years':
        games = all_games()
    else:
        games = year_games(year)
    
    # Calculate TrueSkill ratings
    trueskill_rankings = calculate_trueskill_rankings(year)
    rating_map = {r['player']: r['rating'] for r in trueskill_rankings}
    
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
        rating = rating_map.get(player, 0)  # Get TrueSkill rating, default to 0
        if wins + losses < minimum_games:
            if wins == 0:
                no_wins.append([player, wins, losses, win_percentage, rating])
            else:
                stats.append([player, wins, losses, win_percentage, rating])
    # Sort by rating instead of win percentage
    stats.sort(key=lambda x: x[4], reverse=True)
    no_wins.sort(key=lambda x: x[4], reverse=True)
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

@cached(ttl=1800)
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

@cached(ttl=1800)
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

@cached(ttl=1800)
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
	
	# Get recent games (last 20) for selected year
	recent_games = year_games(selected_year)[:20]
	
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
	top_win_percentage = sorted(qualified_players, key=lambda x: x[3], reverse=True)[:20]
	
	# Top 10 by games played (no minimum games requirement - show actual top 10)
	top_games_played = sorted(current_stats, key=lambda x: x[1] + x[2], reverse=True)[:20]
	
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

def get_combined_dashboard_data(selected_year=None):
	"""Get comprehensive dashboard data with separate sections for 1v1, vollis, and other games"""
	from datetime import datetime
	from one_v_one_functions import get_one_v_one_dashboard_data, one_v_one_year_games, todays_one_v_one_stats
	from vollis_functions import get_vollis_dashboard_data, vollis_year_games, todays_vollis_stats
	from other_functions import get_other_dashboard_data, other_year_games, todays_other_stats
	
	# Use selected year or default to current year
	if selected_year is None:
		selected_year = str(datetime.now().year)
	else:
		selected_year = str(selected_year)
	
	# Get data from each game type
	one_v_one_data = get_one_v_one_dashboard_data(selected_year)
	vollis_data = get_vollis_dashboard_data(selected_year)
	other_data = get_other_dashboard_data(selected_year)
	
	# Get games for the year (already sorted most recent first)
	all_one_v_one_games = one_v_one_year_games(selected_year)
	all_vollis_games = vollis_year_games(selected_year)
	all_other_games = other_year_games(selected_year)
	
	# Get recent games for each type (first 10 = most recent, since they're sorted reverse=True)
	one_v_one_recent = all_one_v_one_games[:10] if all_one_v_one_games else []
	vollis_recent = all_vollis_games[:10] if all_vollis_games else []
	other_recent = all_other_games[:10] if all_other_games else []
	
	# Get today's stats for each type
	today_one_v_one = todays_one_v_one_stats()
	today_vollis = todays_vollis_stats()
	today_other = todays_other_stats()
	
	return {
		'current_year': selected_year,
		# 1v1 data
		'one_v_one_stats': one_v_one_data['top_win_percentage'][:10],
		'one_v_one_recent_games': one_v_one_recent,
		'one_v_one_today_stats': today_one_v_one[:10],
		'one_v_one_total_games': len(all_one_v_one_games),
		# Vollis data
		'vollis_stats': vollis_data['top_win_percentage'][:10],
		'vollis_recent_games': vollis_recent,
		'vollis_today_stats': today_vollis[:10],
		'vollis_total_games': len(all_vollis_games),
		# Other games data
		'other_stats': other_data['top_win_percentage'][:10],
		'other_recent_games': other_recent,
		'other_today_stats': today_other[:10],
		'other_total_games': len(all_other_games),
		# Summary
		'total_games': len(all_one_v_one_games) + len(all_vollis_games) + len(all_other_games)
	}

def get_combined_monthly_game_counts(year):
	"""Get combined monthly game counts from 1v1, vollis, and other games"""
	from one_v_one_functions import one_v_one_year_games
	from vollis_functions import vollis_year_games
	from other_functions import other_year_games
	from datetime import datetime
	
	# Get all games for the year
	one_v_one_games = one_v_one_year_games(year)
	vollis_games = vollis_year_games(year)
	other_games = other_year_games(year)
	
	# Combine all games
	all_games = []
	all_games.extend(one_v_one_games)
	all_games.extend(vollis_games)
	all_games.extend(other_games)
	
	# Count games by month
	monthly_counts = {}
	for game in all_games:
		# Extract date from game (date is typically at index 1)
		if isinstance(game, (list, tuple)) and len(game) > 1:
			game_date = game[1]
			if isinstance(game_date, str):
				try:
					# Try to parse the date
					if len(game_date) > 10:
						dt = datetime.strptime(game_date[:10], '%Y-%m-%d')
					else:
						dt = datetime.strptime(game_date, '%Y-%m-%d')
					month = dt.month
					monthly_counts[month] = monthly_counts.get(month, 0) + 1
				except:
					pass
	
	# Fill in missing months with 0
	for month in range(1, 13):
		if month not in monthly_counts:
			monthly_counts[month] = 0
	
	return monthly_counts

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

def get_combined_years():
	"""Get all years that have 1v1, vollis, or other games"""
	from one_v_one_functions import all_one_v_one_years
	from vollis_functions import all_vollis_years
	from other_functions import all_other_years
	
	one_v_one_years = all_one_v_one_years()
	vollis_years = all_vollis_years()
	other_years = all_other_years()
	
	# Combine and deduplicate years
	all_years = set()
	all_years.update(one_v_one_years)
	all_years.update(vollis_years)
	all_years.update(other_years)
	
	# Convert to list and sort
	years_list = [y for y in all_years if y != 'All years']
	years_list.sort(reverse=True)
	if 'All years' in all_years:
		years_list.append('All years')
	
	return years_list

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

@cached(ttl=1800)
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

@cached(ttl=1800)
def calculate_glicko_rankings(year=None):
	"""Calculate Glicko-2 rankings for all players based on doubles games"""
	import math
	from collections import defaultdict
	
	cur = set_cur()
	if year and year != 'All years':
		cur.execute("SELECT * FROM games WHERE strftime('%Y', game_date) = ? ORDER BY game_date ASC", (str(year),))
	else:
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
	
	# Calculate minimum games requirement (same as doubles stats page)
	if len(games) < 30:
		minimum_games = 1
	else:
		minimum_games = len(games) // 30
	
	# Count games per player
	player_game_counts = defaultdict(int)
	for game in games:
		# Count games for each player
		winners = [game[2], game[3]]  # winner1, winner2
		losers = [game[5], game[6]]   # loser1, loser2
		
		# Filter out players with question marks
		winners = [w for w in winners if '?' not in w]
		losers = [l for l in losers if '?' not in l]
		
		for player in winners + losers:
			player_game_counts[player] += 1
	
	# Convert to list and sort by rating, filtering by minimum games
	rankings = []
	for player, rating_data in player_ratings.items():
		# Only include players who meet the minimum games requirement
		if player_game_counts[player] >= minimum_games:
			rankings.append({
				'player': player,
				'rating': round(rating_data['rating']),
				'rd': round(rating_data['rd']),
				'volatility': round(rating_data['volatility'], 4),
				'games_played': player_game_counts[player]
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

@cached(ttl=1800)
def calculate_trueskill_rankings(year=None):
	"""Calculate TrueSkill rankings - uses database cache when available"""
	from database_functions import get_trueskill_from_db, save_trueskill_to_db, get_trueskill_last_updated, get_last_game_date
	
	# Check if we have cached rankings in the database
	db_rankings = get_trueskill_from_db(year)
	if db_rankings:
		# Check if rankings are still fresh (newer than last game)
		last_updated = get_trueskill_last_updated(year)
		last_game = get_last_game_date()
		
		if last_updated and last_game and last_updated > last_game:
			# Database rankings are fresh, use them
			return db_rankings
	
	# Calculate fresh rankings
	rankings = _calculate_trueskill_rankings_fresh(year)
	
	# Save to database for future use
	save_trueskill_to_db(year, rankings)
	
	return rankings

def _calculate_trueskill_rankings_fresh(year=None):
	"""Calculate TrueSkill rankings from scratch - expensive operation"""
	import math
	from collections import defaultdict
	
	cur = set_cur()
	if year and year != 'All years':
		cur.execute("SELECT * FROM games WHERE strftime('%Y', game_date) = ? ORDER BY game_date ASC", (str(year),))
	else:
		cur.execute("SELECT * FROM games ORDER BY game_date ASC")
	games = cur.fetchall()
	
	# TrueSkill default parameters
	INITIAL_MU = 25.0  # Mean skill
	INITIAL_SIGMA = 8.333  # Skill uncertainty
	BETA = 4.167  # Variance in performance
	TAU = 0.0833  # Dynamics factor (skill change)
	DRAW_PROBABILITY = 0.0  # No draws in doubles
	
	player_ratings = defaultdict(lambda: {
		'mu': INITIAL_MU,
		'sigma': INITIAL_SIGMA
	})
	
	# Process games chronologically
	for game in games:
		# Get game date
		game_date_str = game[1]
		if len(game_date_str) > 19:
			game_date = datetime.strptime(game_date_str, "%Y-%m-%d %H:%M:%S.%f")
		else:
			game_date = datetime.strptime(game_date_str, "%Y-%m-%d %H:%M:%S")
		
		# Get teams
		winners = [game[2], game[3]]  # winner1, winner2
		losers = [game[5], game[6]]   # loser1, loser2
		
		# Filter out players with question marks
		winners = [w for w in winners if '?' not in w]
		losers = [l for l in losers if '?' not in l]
		
		if not winners or not losers:
			continue
		
		# Calculate team ratings
		winner_team_mu = sum(player_ratings[w]['mu'] for w in winners)
		winner_team_sigma = math.sqrt(sum(player_ratings[w]['sigma']**2 for w in winners))
		
		loser_team_mu = sum(player_ratings[l]['mu'] for l in losers)
		loser_team_sigma = math.sqrt(sum(player_ratings[l]['sigma']**2 for l in losers))
		
		# Total uncertainty
		c = math.sqrt(winner_team_sigma**2 + loser_team_sigma**2 + 2 * BETA**2)
		
		# Team performance difference
		winner_team_performance = (winner_team_mu - loser_team_mu) / c
		loser_team_performance = (loser_team_mu - winner_team_mu) / c
		
		# Calculate v and w functions (simplified TrueSkill)
		winner_v = v_win(winner_team_performance)
		loser_v = v_lose(loser_team_performance)
		
		winner_w = w_win(winner_team_performance)
		loser_w = w_lose(loser_team_performance)
		
		# Update winner ratings
		for winner in winners:
			old_mu = player_ratings[winner]['mu']
			old_sigma = player_ratings[winner]['sigma']
			
			mu_multiplier = (old_sigma**2 + TAU**2) / c
			sigma_multiplier = (old_sigma**2 + TAU**2) / (c**2)
			
			player_ratings[winner]['mu'] = old_mu + mu_multiplier * winner_v
			player_ratings[winner]['sigma'] = math.sqrt((old_sigma**2 + TAU**2) * (1 - sigma_multiplier * winner_w))
		
		# Update loser ratings
		for loser in losers:
			old_mu = player_ratings[loser]['mu']
			old_sigma = player_ratings[loser]['sigma']
			
			mu_multiplier = (old_sigma**2 + TAU**2) / c
			sigma_multiplier = (old_sigma**2 + TAU**2) / (c**2)
			
			player_ratings[loser]['mu'] = old_mu + mu_multiplier * loser_v
			player_ratings[loser]['sigma'] = math.sqrt((old_sigma**2 + TAU**2) * (1 - sigma_multiplier * loser_w))
	
	# Calculate minimum games requirement
	if len(games) < 30:
		minimum_games = 1
	else:
		minimum_games = len(games) // 30
	
	# Count games per player and wins/losses
	player_game_counts = defaultdict(int)
	player_wins = defaultdict(int)
	player_losses = defaultdict(int)
	for game in games:
		winners = [game[2], game[3]]
		losers = [game[5], game[6]]
		
		winners = [w for w in winners if '?' not in w]
		losers = [l for l in losers if '?' not in l]
		
		for player in winners:
			player_game_counts[player] += 1
			player_wins[player] += 1
		for player in losers:
			player_game_counts[player] += 1
			player_losses[player] += 1
	
	# Convert to list and sort by conservative rating (mu - 3*sigma)
	all_rankings = []
	for player, rating_data in player_ratings.items():
		conservative_rating = rating_data['mu'] - 3 * rating_data['sigma']
		all_rankings.append({
			'player': player,
			'mu': round(rating_data['mu'], 2),
			'sigma': round(rating_data['sigma'], 2),
			'rating': round(conservative_rating, 2),
			'games_played': player_game_counts[player],
			'wins': player_wins[player],
			'losses': player_losses[player]
		})
	
	# Sort by conservative rating (highest first)
	all_rankings.sort(key=lambda x: x['rating'], reverse=True)
	
	return all_rankings

def v_win(t):
	"""TrueSkill v function for winners"""
	import math
	from math import sqrt, pi, exp, erf
	
	# Standard normal PDF and CDF
	def phi(x):
		return (1.0 / sqrt(2 * pi)) * exp(-0.5 * x**2)
	
	def Phi(x):
		return 0.5 * (1 + erf(x / sqrt(2)))
	
	return phi(t) / Phi(t)

def v_lose(t):
	"""TrueSkill v function for losers"""
	import math
	from math import sqrt, pi, exp, erf
	
	def phi(x):
		return (1.0 / sqrt(2 * pi)) * exp(-0.5 * x**2)
	
	def Phi(x):
		return 0.5 * (1 + erf(x / sqrt(2)))
	
	return -phi(t) / Phi(-t)

def w_win(t):
	"""TrueSkill w function for winners"""
	v = v_win(t)
	return v * (v + t)

def w_lose(t):
	"""TrueSkill w function for losers"""
	v = v_lose(t)
	return v * (v + t)

@cached(ttl=1800)
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
