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

def create_tournament(conn, tournament):
    sql = ''' INSERT INTO tournaments(tournament_date, place, team, location, tournament_name)
              VALUES(?,?,?,?,?) '''
    cur = conn.cursor()
    cur.execute(sql, tournament)
    conn.commit()
    return cur.lastrowid

def main():
    database = r"stats.db"

    sql_create_tournaments_table = """CREATE TABLE IF NOT EXISTS tournaments (
                                    id integer PRIMARY KEY,
                                    tournament_date DATE NOT NULL,
                                    place text NOT NULL,
                                    team text NOT NULL,
                                    location text NOT NULL,
                                    tournament_name text NOT NULL
                                );"""

    # create a database connection
    conn = create_connection(database)

    # create tables
    if conn is not None:
        # create tournaments table
        create_table(conn, sql_create_tournaments_table)
        print("Tournaments table created successfully.")
    else:
        print("Error! cannot create the database connection.")


if __name__ == '__main__':
    main()

