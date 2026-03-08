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
    if len(game) >= 11 and game[10] is not None:
        sql = ''' INSERT INTO games(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, entered_timezone, updated_by)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?) '''
    elif len(game) >= 10 and game[9] is not None:
        sql = ''' INSERT INTO games(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, entered_timezone)
                  VALUES(?,?,?,?,?,?,?,?,?,?) '''
        game = game[:10]
    else:
        sql = ''' INSERT INTO games(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments)
                  VALUES(?,?,?,?,?,?,?,?,?) '''
        game = game[:9]
    cur = conn.cursor()
    cur.execute(sql, game)
    conn.commit()

def database_update_game(conn, game):
    # game: (game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, updated_by, game_id2) when len==12
    #   or: (game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, game_id2) when len==11
    if len(game) >= 12:
        sql = ''' UPDATE games
                  SET game_date = ?, winner1 = ?, winner2 = ?, winner_score = ?, loser1 = ?, loser2 = ?, loser_score = ?, updated_at = ?, comments = ?, updated_by = ?
                  WHERE id = ?'''
        cur = conn.cursor()
        cur.execute(sql, (game[1], game[2], game[3], game[4], game[5], game[6], game[7], game[8], game[9], game[10], game[11]))
    else:
        sql = ''' UPDATE games
                  SET game_date = ?, winner1 = ?, winner2 = ?, winner_score = ?, loser1 = ?, loser2 = ?, loser_score = ?, updated_at = ?, comments = ?
                  WHERE id = ?'''
        cur = conn.cursor()
        cur.execute(sql, (game[1], game[2], game[3], game[4], game[5], game[6], game[7], game[8], game[9], game[10]))
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
