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
	'''Returns the database cursor'''
	conn = db_get_connection()
	cur = conn.cursor()
	return cur, conn

def db_create_table(conn, create_table_sql):
    """ create a table from the create_table_sql statement
    :param conn: Connection object
    :param create_table_sql: a CREATE TABLE statement
    :return:
    """
    try:
        c = conn.cursor()
        c.execute(create_table_sql)
    except Error as e:
        print(e)

def db_add_game(game):
    """
    Add a game (row) to the games table in the database
    :param conn: database cursor
    :param game: description of game
    """
    sql = ''' INSERT INTO games(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at)
              VALUES(?,?,?,?,?,?,?,?) '''
    cur, conn = db_get_cursor()
    cur.execute(sql, game.convert2db_row()[1:])
    conn.commit()

def db_update_game(conn, game):
    """
    Update a game (row) in the games table in the database
    :param conn: database cursor
    :param game: description of game
    """
    sql = ''' UPDATE games
                SET id = ? ,
                game_date = ?,
                winner1 = ?,
                winner2 = ?,
                winner_score = ?,
                loser1 = ?,
                loser2 = ?,
                loser_score = ?,
                updated_at = ? 
                WHERE id = ?'''
    cur = conn.cursor()
    cur.execute(sql, game)
    conn.commit()

def db_delete_game(game_id):
    conn = db_get_connection()
    sql = 'DELETE FROM games WHERE id=?'
    cur = conn.cursor()
    cur.execute(sql, (game_id,))
    conn.commit()

def main():
    database = db_get_filepath()

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

    # create a database connection
    conn = db_get_connection()

    # create tables
    if conn is not None:
        # create games table
        db_create_table(conn, sql_create_games_table)
    else:
        print("Error! cannot create the database connection.")


if __name__ == '__main__':
    main()