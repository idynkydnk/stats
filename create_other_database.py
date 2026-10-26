import sqlite3
from private_accounts import connect_data, data_path
from sqlite3 import Error
from other_game_categories import canonical_other_category
from other_game_outcomes import (ensure_other_game_outcome_column, parse_is_tie,
                                 validate_tie_scores, validate_tie_game_type)

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
    + ["loser_score", "comment", "updated_at", "entered_timezone", "entered_by", "location"]
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
    # Skip paths whose directory doesn't exist (e.g. server path when running locally)
    import os
    db_file = data_path(db_file)
    parent = os.path.dirname(db_file)
    if parent and not os.path.isdir(parent):
        return None
    conn = None
    try:
        conn = connect_data(db_file)
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


def _validate_record_tie(columns, values, is_tie):
    record = dict(zip(columns, values))
    validate_tie_game_type(is_tie, record.get('game_type'))
    individual = any(record.get(column) not in (None, '')
                     for column in WINNER_SCORE_FIELDS + LOSER_SCORE_FIELDS)
    validate_tie_scores(is_tie, 'individual' if individual else 'team',
                        [record.get(column) for column in WINNER_SCORE_FIELDS],
                        [record.get(column) for column in LOSER_SCORE_FIELDS],
                        record.get('winner_score'), record.get('loser_score'))


def create_other_game(conn, game, is_tie=False):
    game = list(game)
    is_tie = parse_is_tie(is_tie)
    _validate_record_tie(BASE_INSERT_COLUMNS, game, is_tie)
    game[BASE_INSERT_COLUMNS.index("game_type")] = canonical_other_category(game[BASE_INSERT_COLUMNS.index("game_type")])
    columns = {row[1] for row in conn.execute('PRAGMA table_info(other_games)').fetchall()}
    if 'location' not in columns:
        conn.execute('ALTER TABLE other_games ADD COLUMN location TEXT')
    ensure_other_game_outcome_column(conn)
    insert_columns = BASE_INSERT_COLUMNS + ['is_tie']
    game.append(int(is_tie))
    placeholders = ",".join(["?"] * len(insert_columns))
    sql = f"""INSERT INTO other_games({', '.join(insert_columns)})
              VALUES({placeholders})"""
    cur = conn.cursor()
    from mobile_game_sync import commit_insert
    def insert():
        cur.execute(sql, game)
        return cur.lastrowid
    return commit_insert(conn, 'other', insert)


def database_update_other_game(conn, game, is_tie=None, location=None):
    game = list(game)
    ensure_other_game_outcome_column(conn)
    if is_tie is None:
        saved = conn.execute('SELECT is_tie FROM other_games WHERE id = ?', (game[-1],)).fetchone()
        is_tie = saved[0] if saved else False
    is_tie = parse_is_tie(is_tie)
    _validate_record_tie(BASE_UPDATE_COLUMNS, game, is_tie)
    game[BASE_UPDATE_COLUMNS.index("game_type")] = canonical_other_category(game[BASE_UPDATE_COLUMNS.index("game_type")])
    set_clause = ", ".join([f"{col} = ?" for col in BASE_UPDATE_COLUMNS + ['is_tie']])
    game.insert(-1, int(is_tie))
    sql = f"""UPDATE other_games
              SET {set_clause}
              WHERE id = ?"""
    cur = conn.cursor()
    cur.execute(sql, game)
    if location is not None:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(other_games)')}
        if 'location' not in columns:
            conn.execute('ALTER TABLE other_games ADD COLUMN location TEXT')
        conn.execute('UPDATE other_games SET location = ? WHERE id = ?',
                     (location.strip(), game[-1]))
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
                                    entered_timezone text,
                                    entered_by text,
                                    location text,
                                    is_tie integer NOT NULL DEFAULT 0
                                );"""

    # create a database connection
    conn = create_connection(database)

    # create tables
    if conn is not None:
        create_table(conn, sql_create_other_games_table)
    else:
        print("Error! cannot create the database connection.")


main()
