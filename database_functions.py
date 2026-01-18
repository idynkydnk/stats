import requests
import sqlite3
from datetime import date, datetime
from bs4 import BeautifulSoup
from create_games_database import *


def scrape_database():

	URL = "https://speed-sheets.herokuapp.com/games"
	page = requests.get(URL)

	soup = BeautifulSoup(page.content, "html.parser")
	results = soup.find(id="main")

	games = results.find_all("tr")

	all_games = []

	for game in games:
		date1 = game.find("td", class_="date")
		date1 = str(date1)
		date1 = date1[17:27]
		full_game = []
		if len(date1) > 2:
				year1 = int(date1[6:10])
				month1 = int(date1[0:2])
				day1 = int(date1[3:5])
				game_date = datetime(year1, month1, day1)
				full_game.append(game_date)
		game_tds = game.find_all("td")
		x = 0
		for game_td in game_tds:
			x = x + 1
			players = game_td.find_all("a")
			for player in players:
				player = str(player)
				start = '<a href="/players/'
				end = '">'
				full_game.append(player[player.find(start)+len(start):player.find(end)])
			if x == 4:
				if len(str(game_td)) > 13:
					winner_score = str(game_td)[4:6]
					loser_score = str(game_td)[7:9]
				elif len(str(game_td)) > 11:
					winner_score = str(game_td)[4:6]
					loser_score = '0'
					loser_score += str(game_td)[7]
				elif len(str(game_td)) > 10:
					if int(str(game_td)[4:6]) > 19:
						winner_score = int(str(game_td)[4:6]) + 2
						loser_score = str(game_td)[4:6]
					else:
						winner_score = '21'
						loser_score = str(game_td)[4:6]
				else:
					winner_score = '00'
					loser_score = '00'
				
				winner_score = int(winner_score)
				loser_score = int(loser_score)
				full_game.append(winner_score)
				full_game.append(loser_score)
				full_game.append(datetime.now())

		if len(full_game) > 1:
			all_games.append(full_game)

	all_games.sort(key=lambda x: x[0])
	return all_games

def enter_data_into_database(games_data):
	for x in games_data:
		comments = x[8] if len(x) > 8 else ''
		new_game(x[0], x[1], x[2], x[5], x[3], x[4], x[6], x[7], comments)

def new_game(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments=''):
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	with conn: 
		game = (game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments);
		create_game(conn, game)


def main():
	enter_data_into_database(scrape_database())


def search_player_names(search_term):
    """Search for player names across all game types"""
    try:
        database = '/home/Idynkydnk/stats/stats.db'
        conn = sqlite3.connect(database)
    except:
        database = r'stats.db'
        conn = sqlite3.connect(database)
    cursor = conn.cursor()
    
    results = {
        'doubles': [],
        'vollis': [],
        'one_v_one': [],
        'other': []
    }
    
    # Search doubles games
    cursor.execute("""
        SELECT DISTINCT winner1 FROM games WHERE winner1 LIKE ? 
        UNION 
        SELECT DISTINCT winner2 FROM games WHERE winner2 LIKE ?
        UNION 
        SELECT DISTINCT loser1 FROM games WHERE loser1 LIKE ?
        UNION 
        SELECT DISTINCT loser2 FROM games WHERE loser2 LIKE ?
    """, (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'))
    results['doubles'] = [row[0] for row in cursor.fetchall()]
    
    # Search vollis games
    cursor.execute("""
        SELECT DISTINCT winner FROM vollis_games WHERE winner LIKE ?
        UNION 
        SELECT DISTINCT loser FROM vollis_games WHERE loser LIKE ?
    """, (f'%{search_term}%', f'%{search_term}%'))
    results['vollis'] = [row[0] for row in cursor.fetchall()]
    
    # Search 1v1 games
    cursor.execute("""
        SELECT DISTINCT winner FROM one_v_one_games WHERE winner LIKE ?
        UNION 
        SELECT DISTINCT loser FROM one_v_one_games WHERE loser LIKE ?
    """, (f'%{search_term}%', f'%{search_term}%'))
    results['one_v_one'] = [row[0] for row in cursor.fetchall()]
    
    # Search other games
    cursor.execute("""
        SELECT DISTINCT winner1 FROM other_games WHERE winner1 LIKE ?
        UNION 
        SELECT DISTINCT winner2 FROM other_games WHERE winner2 LIKE ?
        UNION 
        SELECT DISTINCT winner3 FROM other_games WHERE winner3 LIKE ?
        UNION 
        SELECT DISTINCT winner4 FROM other_games WHERE winner4 LIKE ?
        UNION 
        SELECT DISTINCT winner5 FROM other_games WHERE winner5 LIKE ?
        UNION 
        SELECT DISTINCT winner6 FROM other_games WHERE winner6 LIKE ?
        UNION 
        SELECT DISTINCT loser1 FROM other_games WHERE loser1 LIKE ?
        UNION 
        SELECT DISTINCT loser2 FROM other_games WHERE loser2 LIKE ?
        UNION 
        SELECT DISTINCT loser3 FROM other_games WHERE loser3 LIKE ?
        UNION 
        SELECT DISTINCT loser4 FROM other_games WHERE loser4 LIKE ?
        UNION 
        SELECT DISTINCT loser5 FROM other_games WHERE loser5 LIKE ?
        UNION 
        SELECT DISTINCT loser6 FROM other_games WHERE loser6 LIKE ?
    """, (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%', f'%{search_term}%', 
          f'%{search_term}%', f'%{search_term}%', f'%{search_term}%', f'%{search_term}%', 
          f'%{search_term}%', f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'))
    results['other'] = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return results

def update_player_name(old_name, new_name):
    """Update player name across all game types"""
    try:
        database = '/home/Idynkydnk/stats/stats.db'
        conn = sqlite3.connect(database)
    except:
        database = r'stats.db'
        conn = sqlite3.connect(database)
    cursor = conn.cursor()
    
    updates_made = 0
    
    # Update doubles games
    cursor.execute("UPDATE games SET winner1 = ? WHERE winner1 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE games SET winner2 = ? WHERE winner2 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE games SET loser1 = ? WHERE loser1 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE games SET loser2 = ? WHERE loser2 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    
    # Update vollis games
    cursor.execute("UPDATE vollis_games SET winner = ? WHERE winner = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE vollis_games SET loser = ? WHERE loser = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    
    # Update 1v1 games
    cursor.execute("UPDATE one_v_one_games SET winner = ? WHERE winner = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE one_v_one_games SET loser = ? WHERE loser = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    
    # Update other games
    cursor.execute("UPDATE other_games SET winner1 = ? WHERE winner1 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE other_games SET winner2 = ? WHERE winner2 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE other_games SET winner3 = ? WHERE winner3 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE other_games SET winner4 = ? WHERE winner4 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE other_games SET winner5 = ? WHERE winner5 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE other_games SET winner6 = ? WHERE winner6 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE other_games SET loser1 = ? WHERE loser1 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE other_games SET loser2 = ? WHERE loser2 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE other_games SET loser3 = ? WHERE loser3 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE other_games SET loser4 = ? WHERE loser4 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE other_games SET loser5 = ? WHERE loser5 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    cursor.execute("UPDATE other_games SET loser6 = ? WHERE loser6 = ?", (new_name, old_name))
    updates_made += cursor.rowcount
    
    conn.commit()
    conn.close()
    
    return updates_made

def get_all_unique_players():
    """Get all unique player names across all game types"""
    try:
        database = '/home/Idynkydnk/stats/stats.db'
        conn = sqlite3.connect(database)
    except:
        database = r'stats.db'
        conn = sqlite3.connect(database)
    cursor = conn.cursor()
    
    all_players = set()
    
    # Get players from doubles games
    cursor.execute("SELECT DISTINCT winner1 FROM games UNION SELECT DISTINCT winner2 FROM games UNION SELECT DISTINCT loser1 FROM games UNION SELECT DISTINCT loser2 FROM games")
    doubles_players = [row[0] for row in cursor.fetchall()]
    all_players.update(doubles_players)
    
    # Get players from vollis games
    cursor.execute("SELECT DISTINCT winner FROM vollis_games UNION SELECT DISTINCT loser FROM vollis_games")
    vollis_players = [row[0] for row in cursor.fetchall()]
    all_players.update(vollis_players)
    
    # Get players from 1v1 games
    cursor.execute("SELECT DISTINCT winner FROM one_v_one_games UNION SELECT DISTINCT loser FROM one_v_one_games")
    one_v_one_players = [row[0] for row in cursor.fetchall()]
    all_players.update(one_v_one_players)
    
    # Get players from other games
    cursor.execute("""
        SELECT DISTINCT winner1 FROM other_games 
        UNION SELECT DISTINCT winner2 FROM other_games 
        UNION SELECT DISTINCT winner3 FROM other_games 
        UNION SELECT DISTINCT winner4 FROM other_games 
        UNION SELECT DISTINCT winner5 FROM other_games 
        UNION SELECT DISTINCT winner6 FROM other_games 
        UNION SELECT DISTINCT loser1 FROM other_games 
        UNION SELECT DISTINCT loser2 FROM other_games 
        UNION SELECT DISTINCT loser3 FROM other_games 
        UNION SELECT DISTINCT loser4 FROM other_games 
        UNION SELECT DISTINCT loser5 FROM other_games 
        UNION SELECT DISTINCT loser6 FROM other_games
    """)
    other_players = [row[0] for row in cursor.fetchall()]
    all_players.update(other_players)
    
    conn.close()
    
    # Remove None values and sort
    all_players = [p for p in all_players if p is not None]
    return sorted(all_players)

def init_trueskill_table():
    """Create the trueskill_rankings table if it doesn't exist"""
    try:
        database = '/home/Idynkydnk/stats/stats.db'
        conn = sqlite3.connect(database)
    except:
        database = r'stats.db'
        conn = sqlite3.connect(database)
    
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trueskill_rankings (
            id INTEGER PRIMARY KEY,
            year TEXT NOT NULL,
            player TEXT NOT NULL,
            mu REAL NOT NULL,
            sigma REAL NOT NULL,
            rating REAL NOT NULL,
            games_played INTEGER NOT NULL,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            updated_at DATETIME NOT NULL,
            UNIQUE(year, player)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trueskill_year ON trueskill_rankings(year)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trueskill_rating ON trueskill_rankings(rating DESC)")
    conn.commit()
    conn.close()

def get_trueskill_from_db(year):
    """Get TrueSkill rankings from database for a specific year"""
    try:
        database = '/home/Idynkydnk/stats/stats.db'
        conn = sqlite3.connect(database)
    except:
        database = r'stats.db'
        conn = sqlite3.connect(database)
    
    cursor = conn.cursor()
    year_str = str(year) if year else 'All years'
    
    cursor.execute("""
        SELECT player, mu, sigma, rating, games_played, wins, losses, updated_at
        FROM trueskill_rankings
        WHERE year = ?
        ORDER BY rating DESC
    """, (year_str,))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return None
    
    rankings = []
    for row in rows:
        rankings.append({
            'player': row[0],
            'mu': row[1],
            'sigma': row[2],
            'rating': row[3],
            'games_played': row[4],
            'wins': row[5],
            'losses': row[6]
        })
    
    return rankings

def save_trueskill_to_db(year, rankings):
    """Save TrueSkill rankings to database"""
    try:
        database = '/home/Idynkydnk/stats/stats.db'
        conn = sqlite3.connect(database)
    except:
        database = r'stats.db'
        conn = sqlite3.connect(database)
    
    cursor = conn.cursor()
    year_str = str(year) if year else 'All years'
    now = datetime.now()
    
    # Delete existing rankings for this year
    cursor.execute("DELETE FROM trueskill_rankings WHERE year = ?", (year_str,))
    
    # Insert new rankings
    for ranking in rankings:
        cursor.execute("""
            INSERT INTO trueskill_rankings (year, player, mu, sigma, rating, games_played, wins, losses, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            year_str,
            ranking['player'],
            ranking['mu'],
            ranking['sigma'],
            ranking['rating'],
            ranking['games_played'],
            ranking.get('wins', 0),
            ranking.get('losses', 0),
            now
        ))
    
    conn.commit()
    conn.close()

def get_trueskill_last_updated(year):
    """Get when TrueSkill rankings were last updated for a year"""
    try:
        database = '/home/Idynkydnk/stats/stats.db'
        conn = sqlite3.connect(database)
    except:
        database = r'stats.db'
        conn = sqlite3.connect(database)
    
    cursor = conn.cursor()
    year_str = str(year) if year else 'All years'
    
    cursor.execute("""
        SELECT MAX(updated_at) FROM trueskill_rankings WHERE year = ?
    """, (year_str,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        return datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S.%f')
    return None

def get_last_game_date():
    """Get the date of the most recent game"""
    try:
        database = '/home/Idynkydnk/stats/stats.db'
        conn = sqlite3.connect(database)
    except:
        database = r'stats.db'
        conn = sqlite3.connect(database)
    
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(game_date) FROM games")
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        date_str = result[0]
        try:
            if len(date_str) > 19:
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S.%f')
            else:
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        except:
            return None
    return None

# Initialize the trueskill table on import
init_trueskill_table()

if __name__ == '__main__':
    main()



