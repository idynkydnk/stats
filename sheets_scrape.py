import requests
from datetime import date
from bs4 import BeautifulSoup
from stats_database_code import *


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
				game_date = date(year1, month1, day1)
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

		if len(full_game) > 1:
			all_games.append(full_game)

	all_games.sort(key=lambda x: x[0])
	return all_games

def enter_data_into_database(games_data):
	for x in games_data:
		new_game(x[0], x[1], x[2], x[5], x[3], x[4], x[6])
		update_winners(x[1], x[2])
		update_losers(x[3], x[4])

def update_winners(winner1, winner2):
	update_player_stats(winner1, "win")
	update_player_stats(winner2, "win")

def update_losers(loser1, loser2):
	update_player_stats(loser1, "loss")
	update_player_stats(loser2, "loss")

def update_all_players(games_data):
	for x in games_data:
		update_winners(x[1], x[2])
		update_losers(x[3], x[4])

def all_player_stats():
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	cur = conn.cursor()
	cur.execute("SELECT * FROM players")
	row = cur.fetchall()
	row.sort(key=lambda x: x[4], reverse=True)
	return row


def player_stats_over(minimum_games):
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	cur = conn.cursor()
	cur.execute("SELECT * FROM players")
	row = cur.fetchall()
	for player in row.copy():
		if (player[2] + player[3]) < minimum_games:
			row.remove(player)
	
	row.sort(key=lambda x: x[4], reverse=True)
	return row	

def all_games():
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	cur = conn.cursor()
	cur.execute("SELECT * FROM games")
	row = cur.fetchall()
	return row

def current_year_games():
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	cur = conn.cursor()
	cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date) = strftime('%Y','now')")
	row = cur.fetchall()
	return row

def stats_per_year(year):
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
		stats.append([player, wins, losses, win_percentage])
	stats.sort(key=lambda x: x[3], reverse=True)
	return stats

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
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	cur = conn.cursor()
	cur.execute("SELECT * FROM games WHERE strftime('%Y',game_date)=?", (past_year,))
	row = cur.fetchall()
	return row

def main():
	enter_data_into_database(scrape_database())


if __name__ == '__main__':
    main()



