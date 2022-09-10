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
    sql = ''' INSERT INTO games(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score)
              VALUES(?,?,?,?,?,?,?) '''
    cur = conn.cursor()
    cur.execute(sql, game)
    conn.commit()

def create_player(conn, player):

    sql = ''' INSERT OR IGNORE INTO players(name, wins, losses)
              VALUES(?,?,?) '''
    cur = conn.cursor()
    cur.execute(sql, player)
    conn.commit()
    return cur.lastrowid

def new_player(name, wins, losses):

    database = r"stats.db"
    conn = create_connection(database)
    with conn:
        player = (name, wins, losses)
        create_player(conn, player)

def new_game(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score):

    database = r"stats.db"

    conn = create_connection(database)
    with conn: 
        game = (game_date, winner1, winner2, winner_score, loser1, loser2, loser_score);
        create_game(conn, game)


def main():
    database = r"stats.db"

    sql_create_players_table = """ CREATE TABLE IF NOT EXISTS players (
                                        id integer PRIMARY KEY,
                                        name text NOT NULL,
                                        wins integer,
                                        losses integer,
                                        win_percentage real GENERATED ALWAYS AS ((CAST(wins as real) / (wins + losses))*100),
                                        UNIQUE(name)
                                    ); """

    sql_create_games_table = """CREATE TABLE IF NOT EXISTS games (
                                    id integer PRIMARY KEY,
                                    game_date DATETIME NOT NULL,
                                    winner1 text NOT NULL,
                                    winner2 text NOT NULL,
                                    winner_score integer NOT NULL,
                                    loser1 text NOT NULL,
                                    loser2 text NOT NULL,
                                    loser_score integer NOT NULL
                                );"""



    # create a database connection
    conn = create_connection(database)

    # create tables
    if conn is not None:
        # create players table
        create_table(conn, sql_create_players_table)

        # create games table
        create_table(conn, sql_create_games_table)
    else:
        print("Error! cannot create the database connection.")


def update_player_stats(player, win_or_loss):
    database = r"stats.db"
    conn = create_connection(database)
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE name=?", (player,))
    row = cur.fetchall()

    if row == []:
        new_player(player, 0, 0)
        cur.execute("SELECT * FROM players WHERE name=?", (player,))
        row = cur.fetchall()

    if win_or_loss == 'win':
        cur.execute("UPDATE players SET wins = wins + 1 WHERE id=?", (row[0][0],))
        conn.commit()
    else:
        cur.execute("UPDATE players SET losses = losses + 1 WHERE id=?", (row[0][0],))
        conn.commit()

    


main()
#update_player_stats('Chris Dedo', 'win')
#update_player_stats('Jim Joe', 'win')
#update_player_stats('Jim Joe', 'loss')

#new_player('Kyle Thomson', 73, 3)
#new_player('Chris Dedo', 34, 34)
#new_player('Brian Onenl', 3, 3)
#new_player('Chris Gretory', 7, 3)
#new_player('Justin Chow', 78, 34)
