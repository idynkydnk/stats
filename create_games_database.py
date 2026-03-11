import sqlite3
from sqlite3 import Error

try:
    from supabase_games import write_game as supabase_write_game, update_game as supabase_update_game, delete_game as supabase_delete_game
except ImportError:
    supabase_write_game = supabase_update_game = supabase_delete_game = None

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

def _game_tuple_to_dict(game, game_id=None):
    """Build a dict for Supabase from game tuple (after insert: 9–11 elements)."""
    # game: (game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, entered_timezone?, updated_by?)
    d = {
        'game_date': game[0],
        'winner1': game[1],
        'winner2': game[2],
        'winner_score': game[3],
        'loser1': game[4],
        'loser2': game[5],
        'loser_score': game[6],
        'updated_at': game[7],
        'comments': game[8] if len(game) > 8 else '',
        'entered_timezone': game[9] if len(game) > 9 else None,
        'updated_by': game[10] if len(game) > 10 else None,
    }
    if game_id is not None:
        d['id'] = game_id
    return d

def create_game(conn, game):
    cur = conn.cursor()
    if len(game) >= 11 and game[10] is not None:
        sql = ''' INSERT INTO games(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, entered_timezone, updated_by)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?) '''
        try:
            cur.execute(sql, game)
        except sqlite3.OperationalError as e:
            if 'updated_by' in str(e) or 'no such column' in str(e).lower():
                # Production DB may not have migration run yet: insert without updated_by
                sql_fallback = ''' INSERT INTO games(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, entered_timezone)
                                  VALUES(?,?,?,?,?,?,?,?,?,?) '''
                cur.execute(sql_fallback, game[:10])
            else:
                raise
    elif len(game) >= 10 and game[9] is not None:
        sql = ''' INSERT INTO games(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, entered_timezone)
                  VALUES(?,?,?,?,?,?,?,?,?,?) '''
        cur.execute(sql, game[:10])
    else:
        sql = ''' INSERT INTO games(game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments)
                  VALUES(?,?,?,?,?,?,?,?,?) '''
        cur.execute(sql, game[:9])
    new_id = cur.lastrowid
    conn.commit()
    _update_player_last_played(conn, game[0], game[1], game[2], game[4], game[5])
    supabase_ok = None
    if supabase_write_game and new_id is not None:
        supabase_ok = supabase_write_game(new_id, _game_tuple_to_dict(game, game_id=new_id))
    return (new_id, supabase_ok)

def database_update_game(conn, game):
    # game: (game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, updated_by, game_id2) when len==12
    #   or: (game_id, game_date, winner1, winner2, winner_score, loser1, loser2, loser_score, updated_at, comments, game_id2) when len==11
    cur = conn.cursor()
    game_id = game[11] if len(game) >= 12 else game[10]
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
    supabase_ok = None
    if supabase_update_game:
        fd = {'id': game_id, 'game_date': game[1], 'winner1': game[2], 'winner2': game[3], 'winner_score': game[4],
              'loser1': game[5], 'loser2': game[6], 'loser_score': game[7], 'updated_at': game[8], 'comments': game[9],
              'entered_timezone': None, 'updated_by': game[10] if len(game) >= 12 else None}
        supabase_ok = supabase_update_game(game_id, fd)
    return supabase_ok

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
    supabase_ok = None
    if supabase_delete_game:
        supabase_ok = supabase_delete_game(game_id)
    return supabase_ok

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
