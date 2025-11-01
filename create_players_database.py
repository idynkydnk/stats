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

def create_player(conn, player):
    sql = ''' INSERT INTO players(full_name, email, date_of_birth, height, notes, created_at, updated_at)
              VALUES(?,?,?,?,?,?,?) '''
    cur = conn.cursor()
    cur.execute(sql, player)
    conn.commit()
    return cur.lastrowid

def update_player(conn, player):
    sql = ''' UPDATE players
              SET full_name = ?,
                  email = ?,
                  date_of_birth = ?,
                  height = ?,
                  notes = ?,
                  updated_at = ?
              WHERE id = ?'''
    cur = conn.cursor()
    cur.execute(sql, player)
    conn.commit()

def delete_player(conn, player_id):
    sql = 'DELETE FROM players WHERE id=?'
    cur = conn.cursor()
    cur.execute(sql, (player_id,))
    conn.commit()

def main():
    database = r"stats.db"

    sql_create_players_table = """CREATE TABLE IF NOT EXISTS players (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    full_name TEXT NOT NULL,
                                    email TEXT,
                                    date_of_birth TEXT,
                                    height TEXT,
                                    notes TEXT,
                                    created_at DATETIME NOT NULL,
                                    updated_at DATETIME NOT NULL
                                );"""

    # create a database connection
    conn = create_connection(database)

    # create tables
    if conn is not None:
        # create players table
        create_table(conn, sql_create_players_table)
        print("Players table created successfully")
    else:
        print("Error! cannot create the database connection.")


if __name__ == '__main__':
    main()

