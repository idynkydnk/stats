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

def create_other_game(conn, game):
    sql = ''' INSERT INTO other_games(game_date, game_type, game_name, winner1, winner2, winner3, winner4, 
                                        winner5, winner6, winner_score, loser1, loser2, loser3, loser4, loser5, loser6, 
                                        loser_score, comment, updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) '''
    cur = conn.cursor()
    cur.execute(sql, game)
    conn.commit()

def database_update_other_game(conn, game):
    sql = ''' UPDATE other_games
              SET id = ? ,
                    game_date = ?,
                    game_type = ?,
                    game_name = ?,
                    winner1 = ?,
                    winner2 = ?,
                    winner3 = ?,
                    winner4 = ?,
                    winner5 = ?,
                    winner6 = ?,
                    winner_score = ?,
                    loser1 = ?,
                    loser2 = ?,
                    loser3 = ?,
                    loser4 = ?,
                    loser5 = ?,
                    loser6 = ?,
                    loser_score = ?,
                    comment = ?,
                    updated_at = ? 
              WHERE id = ?'''
    cur = conn.cursor()
    cur.execute(sql, game)
    conn.commit()

def database_delete_other_game(conn, game_id):
    sql = 'DELETE FROM other_games WHERE id=?'
    cur = conn.cursor()
    cur.execute(sql, (game_id,))
    conn.commit()

def main():
    database = r"stats.db"

    sql_create_other_games_table = """CREATE TABLE IF NOT EXISTS other_games (
                                    id integer PRIMARY KEY,
                                    game_date DATETIME NOT NULL,
                                    game_type text NOT NULL,
                                    game_name text NOT NULL,
                                    winner1 text NOT NULL,
                                    winner2 text,
                                    winner3 text,
                                    winner4 text,
                                    winner5 text,
                                    winner6 text,
                                    winner_score integer,
                                    loser1 text NOT NULL,
                                    loser2 text,
                                    loser3 text,
                                    loser4 text,
                                    loser5 text,
                                    loser6 text,
                                    loser_score integer,
                                    comment text,
                                    updated_at DATETIME NOT NULL
                                );"""

    # create a database connection
    conn = create_connection(database)

    # create tables
    if conn is not None:
        # create games table
        create_table(conn, sql_create_other_games_table)
    else:
        print("Error! cannot create the database connection.")


main()
