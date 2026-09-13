import os
import sqlite3
from sqlite3 import Error
from player_identity import canonical_player_name

def create_connection(db_file):
    """ create a database connection to the SQLite database
        specified by db_file
    :param db_file: database file
    :return: Connection object or None
    """
    # Skip absolute paths whose directory doesn't exist (e.g. the PythonAnywhere
    # path when running locally) instead of spamming "unable to open database file".
    parent = os.path.dirname(db_file)
    if parent and not os.path.isdir(parent):
        return None
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
    from game_entry_ownership import ensure_game_entry_owner
    ensure_game_entry_owner(conn, 'games')
    columns = {row[1] for row in conn.execute('PRAGMA table_info(games)').fetchall()}
    if 'location' not in columns:
        conn.execute('ALTER TABLE games ADD COLUMN location TEXT')
        columns.add('location')
    cur = conn.cursor()
    field_values = [
        ('game_date', game[0]),
        ('winner1', canonical_player_name(game[1])),
        ('winner2', canonical_player_name(game[2])),
        ('winner_score', game[3]), ('loser1', game[4]), ('loser2', game[5]),
        ('loser_score', game[6]), ('updated_at', game[7]),
        ('comments', game[8] if len(game) > 8 else ''),
        ('entered_timezone', game[9] if len(game) > 9 else None),
        ('updated_by', game[10] if len(game) > 10 else None),
        ('entered_by', game[10] if len(game) > 10 else None),
        ('location', game[11] if len(game) > 11 else ''),
    ]
    field_values = [
        (name, canonical_player_name(value) if name in {'loser1', 'loser2'} else value)
        for name, value in field_values
    ]
    insert_fields = [(name, value) for name, value in field_values if name in columns]
    names = ', '.join(name for name, _ in insert_fields)
    placeholders = ','.join('?' for _ in insert_fields)
    cur.execute(
        f'INSERT INTO games({names}) VALUES({placeholders})',
        tuple(value for _, value in insert_fields),
    )
    new_id = cur.lastrowid
    conn.commit()
    _update_player_last_played(conn, game[0], game[1], game[2], game[4], game[5])
    return new_id

def database_update_game(conn, game):
    from game_entry_ownership import ensure_game_entry_owner
    ensure_game_entry_owner(conn, 'games')
    # game: (game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, updated_by, game_id2) when len==12
    #   or: (game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, game_id2) when len==11
    game = list(game)
    for index in (2, 3, 5, 6):
        game[index] = canonical_player_name(game[index])
    game = tuple(game)
    cur = conn.cursor()
    if len(game) >= 12:
        sql = ''' UPDATE games
                  SET game_date = ?, winner1 = ?, winner2 = ?, winner_score = ?, loser1 = ?, loser2 = ?, loser_score = ?, updated_at = ?, comments = ?, updated_by = ?
                  WHERE id = ?'''
        try:
            cur.execute(sql, (game[1], game[2], game[3], game[4], game[5], game[6], game[7], game[8], game[9], game[10], game[11]))
        except sqlite3.OperationalError as e:
            if 'updated_by' in str(e) or 'no such column' in str(e).lower():
                sql_fallback = ''' UPDATE games
                                  SET game_date = ?, winner1 = ?, winner2 = ?, winner_score = ?, loser1 = ?, loser2 = ?, loser_score = ?, updated_at = ?, comments = ?
                                  WHERE id = ?'''
                cur.execute(sql_fallback, (game[1], game[2], game[3], game[4], game[5], game[6], game[7], game[8], game[9], game[11]))
            else:
                raise
    else:
        sql = ''' UPDATE games
                  SET game_date = ?, winner1 = ?, winner2 = ?, winner_score = ?, loser1 = ?, loser2 = ?, loser_score = ?, updated_at = ?, comments = ?
                  WHERE id = ?'''
        cur.execute(sql, (game[1], game[2], game[3], game[4], game[5], game[6], game[7], game[8], game[9], game[10]))
    conn.commit()
    _update_player_last_played(conn, game[1], game[2], game[3], game[5], game[6])

def _update_player_last_played(conn, game_date, winner1, winner2, loser1, loser2):
    """Update doubles_player_last_played for the four players (add/edit). Table may not exist yet."""
    try:
        cur = conn.cursor()
        for name in (winner1, winner2, loser1, loser2):
            if name and isinstance(name, str) and name.strip():
                cur.execute(
                    "INSERT INTO doubles_player_last_played (player_name, last_game_date) VALUES (?, ?) "
                    "ON CONFLICT(player_name) DO UPDATE SET last_game_date = excluded.last_game_date",
                    (name.strip(), game_date)
                )
    except sqlite3.OperationalError:
        pass  # table may not exist before migration

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
                                    updated_at DATETIME NOT NULL,
                                    location text
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
