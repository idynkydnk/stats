import sqlite3
from sqlite3 import Error

def create_connection(db_file):
    """ create a database connection to the SQLite database
        specified by db_file
    :param db_file: database file
    :return: Connection object or None
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except Error as e:
        print(e)

    return conn

def create_table(conn, create_table_sql):
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

def create_game(conn, game):
    sql = ''' INSERT INTO games(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at)
              VALUES(?,?,?,?,?,?,?,?) '''
    cur = conn.cursor()
    cur.execute(sql, game)
    conn.commit()

def database_update_game(conn, game):
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

def database_delete_game(conn, game_id):
    sql = 'DELETE FROM games WHERE id=?'
    cur = conn.cursor()
    cur.execute(sql, (game_id,))
    conn.commit()

def main():
    database = r"stats.db"

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
    conn = create_connection(database)

    # create tables
    if conn is not None:
        # create games table
        create_table(conn, sql_create_games_table)
    else:
        print("Error! cannot create the database connection.")


main()
