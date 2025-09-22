from datetime import date, datetime
from create_vollis_database import *
import json


def stats_from_json():
	json_file = open('vollis_stats.json')
	stats = json.load(json_file)
	json_file.close()
	return stats

def enter_data_into_database(games_data):
	for x in games_data:
		new_vollis_game(x[4], x[2], 0, x[3], 0, x[4])

def new_vollis_game(game_date, winner, winner_score, loser, loser_score, updated_at):
	database = '/home/Idynkydnk/stats/stats.db'
	conn = create_connection(database)
	if conn is None:
		database = r'stats.db'
		conn = create_connection(database)
	with conn: 
		game = (game_date, winner, winner_score, loser, loser_score, updated_at);
		create_vollis_game(conn, game)


def main():
	enter_data_into_database(stats_from_json())


if __name__ == '__main__':
	main()



