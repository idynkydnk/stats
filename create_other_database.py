import sqlite3
from sqlite3 import Error

WINNER_FIELDS = [f"winner{i}" for i in range(1, 16)]
LOSER_FIELDS = [f"loser{i}" for i in range(1, 16)]
WINNER_SCORE_FIELDS = [f"{field}_score" for field in WINNER_FIELDS]
LOSER_SCORE_FIELDS = [f"{field}_score" for field in LOSER_FIELDS]

BASE_INSERT_COLUMNS = (
    ["game_date", "game_type", "game_name"]
    + WINNER_FIELDS
    + WINNER_SCORE_FIELDS
    + ["winner_score"]
    + LOSER_FIELDS
    + LOSER_SCORE_FIELDS
    + ["loser_score", "comment", "updated_at", "entered_timezone"]
)

BASE_UPDATE_COLUMNS = (
    ["game_date", "game_type", "game_name"]
    + WINNER_FIELDS
    + WINNER_SCORE_FIELDS
    + ["winner_score"]
    + LOSER_FIELDS
    + LOSER_SCORE_FIELDS
    + ["loser_score", "comment", "updated_at"]
)


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
    placeholders = ",".join(["?"] * len(BASE_INSERT_COLUMNS))
    sql = f"""INSERT INTO other_games({', '.join(BASE_INSERT_COLUMNS)})
              VALUES({placeholders})"""
    cur = conn.cursor()
    cur.execute(sql, game)
    conn.commit()


def database_update_other_game(conn, game):
    set_clause = ", ".join([f"{col} = ?" for col in BASE_UPDATE_COLUMNS])
    sql = f"""UPDATE other_games
              SET {set_clause}
              WHERE id = ?"""
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

    sql_create_other_games_table = f"""CREATE TABLE IF NOT EXISTS other_games (
                                    id integer PRIMARY KEY,
                                    game_date DATETIME NOT NULL,
                                    game_type text NOT NULL,
                                    game_name text NOT NULL,
                                    {', '.join(f'{field} text' for field in WINNER_FIELDS)},
                                    {', '.join(f'{field} integer' for field in WINNER_SCORE_FIELDS)},
                                    winner_score integer,
                                    {', '.join(f'{field} text' for field in LOSER_FIELDS)},
                                    {', '.join(f'{field} integer' for field in LOSER_SCORE_FIELDS)},
                                    loser_score integer,
                                    comment text,
                                    updated_at DATETIME NOT NULL,
                                    entered_timezone text
                                );"""

    # create a database connection
    conn = create_connection(database)

    # create tables
    if conn is not None:
        create_table(conn, sql_create_other_games_table)
    else:
        print("Error! cannot create the database connection.")


main()
