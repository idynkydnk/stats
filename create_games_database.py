import sqlite3
from sqlite3 import Error
from os import path

def db_get_filepath():
	'''Returns the database filepath'''
	this_file_path = path.realpath(__file__) # get path to this python file
	dir_path = path.dirname(this_file_path)
	db_path = path.join(dir_path, 'stats.db')
	return db_path

def db_get_connection():
    """ Returns database connection to the SQLite database. If the database does not exist, it will be created.
    :return: database connection object
    """
    return sqlite3.connect(db_get_filepath())

def db_get_cursor():
	'''
    :return: database cursor and connection
    '''
	conn = db_get_connection()
	cur = conn.cursor()
	return cur, conn

def db_create_table(create_table_sql):
    """ create a table from the create_table_sql statement
    :param create_table_sql: a CREATE TABLE statement
    """
    cur = db_get_cursor()[0]
    cur.execute(create_table_sql)


def db_add_game(game):
    """
    Add a game (row) to the games table in the database
    :param game: description of game
    """
    sql = ''' INSERT INTO games(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at)
              VALUES(?,?,?,?,?,?,?,?) '''
    cur, conn = db_get_cursor()
    cur.execute(sql, game.convert2db_row()[1:])
    conn.commit()

def db_update_game(game):
    """
    Update a game (row) in the games table in the database
    :param game: doubles_game object instance
    """
    sql = ''' UPDATE games
                SET
                    id = ? ,
                    game_date = ?,
                    winner1 = ?,
                    winner2 = ?,
                    winner_score = ?,
                    loser1 = ?,
                    loser2 = ?,
                    loser_score = ?,
                    updated_at = ? 
                WHERE id = ?'''
    cur, conn = db_get_cursor()
    tmp = game.convert2db_row() + (game.game_id,)
    cur.execute(sql, tmp)
    if cur.rowcount == 0:
            raise Exception('Failed to update game with id = ' + str(game.game_id) + ' in the database.')
    conn.commit()

def db_delete_game(game_id):
    conn = db_get_connection()
    sql = 'DELETE FROM games WHERE id=?'
    cur = conn.cursor()
    cur.execute(sql, (game_id,))
    if cur.rowcount == 0:
        raise Exception('Failed to delete game with id = ' + str(game_id) + ' in the database.')
    conn.commit()

def main():
    sql_create_games_table = """CREATE TABLE IF NOT EXISTS games (
                                    id integer PRIMARY KEY,
                                    game_date DATETIME NOT NULL,
                                    winner1 text NOT NULL,
                                    winner2 text NOT NULL,
                                    winner_score integer NOT NULL,
                                    loser1 text NOT NULL,
                                    loser2 text NOT NULL,
                                    loser_score integer NOT NULL,
                                    updated_at DATETIME NOT NULL
                                );"""

    # create games table
    db_create_table(sql_create_games_table)


if __name__ == '__main__':
    main()