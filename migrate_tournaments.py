import sqlite3
from sqlite3 import Error
from datetime import datetime
import re

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

def parse_date(date_str):
    """Convert MM/DD/YY format to YYYY-MM-DD format"""
    try:
        # Parse MM/DD/YY format
        month, day, year = date_str.split('/')
        # Convert 2-digit year to 4-digit (assuming 20xx)
        year_int = int(year)
        if year_int < 100:
            year_int = 2000 + year_int
        return f"{year_int}-{month.zfill(2)}-{day.zfill(2)}"
    except:
        return None

def migrate_tournaments():
    """Extract tournament data from HTML and insert into database"""
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        database = r'stats.db'
        conn = create_connection(database)
    
    if conn is None:
        print("Error! cannot create the database connection.")
        return
    
    cur = conn.cursor()
    
    # Check if tournaments already exist
    cur.execute("SELECT COUNT(*) FROM tournaments")
    count = cur.fetchone()[0]
    if count > 0:
        print(f"Tournaments table already has {count} entries. Skipping migration.")
        conn.close()
        return
    
    # Tournament data extracted from tournaments.html
    tournaments = [
        ("11/15/25", "3rd", "Dan Ferris", "Orlando", "Dino tournament"),
        ("11/11/25", "5th", "Sergey Shvets", "Hermosa Beach", "Spike N Go Solo"),
        ("10/28/25", "9th", "Joe Garvey", "Hermosa Beach", "Spike N Go Solo"),
        ("10/25/25", "5th", "Justin Chow", "Santa Monica", "CBVA Open"),
        ("10/22/25", "5th", "Mert Kurt", "Hermosa Beach", "Spike N Go Solo"),
        ("10/11/25", "5th", "Phil Burrow", "Hermosa Beach", "Spike N Go"),
        ("10/08/25", "2nd", "Rick Rodrick", "Hermosa Beach", "Spike N Go Solo"),
        ("09/16/25", "3rd", "Matias Moreno", "Hermosa Beach", "Spike N Go Solo"),
        ("09/07/25", "41st", "Cash Essert", "Hermosa Beach", "Hermosa Beach Open 2025"),
        ("08/30/25", "5th", "Justin Chow", "Hermosa Beach", "Mich Ultra Premier Tour: $4,000 Gene Selznick Men's Open"),
        ("08/24/25", "1st", "John Ferraro", "Manhattan Beach", "Men's AA at Manhattan Pier"),
        ("08/17/25", "89th", "Kevin Cleary", "Hermosa Beach", "Heritage 2025"),
        ("08/06/25", "1st", "Dom Arcona", "Hermosa Beach", "Spike N Go Solo"),
        ("07/27/25", "15th", "Tom Kohler", "Manhattan Beach", "Men's AA at Manhattan Pier"),
        ("07/23/25", "2nd", "Solo", "Hermosa Beach", "Spike N Go"),
        ("07/17/25", "3rd", "Solo", "Hermosa Beach", "Spike N Go Short Kings"),
        ("07/16/25", "2nd", "Solo", "Hermosa Beach", "Spike N Go"),
        ("07/13/25", "2nd", "Justin Chow", "Hermosa Beach", "Spike N Go"),
        ("07/08/25", "2nd", "Solo", "Hermosa Beach", "Spike N Go"),
        ("07/05/25", "17th", "Kevin Cleary", "Long Beach", "Men's AA at Belmont Shore"),
        ("07/02/25", "1st", "Brendan Schmidt", "Hermosa Beach", "Spike N Go Solo"),
        ("06/24/25", "3rd", "Solo", "Hermosa Beach", "Spike N Go"),
        ("04/26/25", "3rd", "Lisa Hoang", "New Jersey", "GAC Finale"),
        ("10/19/24", "2nd", "Justin Chow", "Hermosa Beach", "Volley4Sound 2024"),
        ("09/22/24", "1st", "Tyler Boone", "Hermosa Beach", "Pirate 4s 2024"),
        ("09/07/24", "41st", "Luis Sandoval", "Hermosa Beach", "Hermosa Beach Open 2024"),
        ("08/31/24", "5th", "Justin Chow", "Hermosa Beach", "Mich Ultra Premier Tour: $5,000 Gene Selznick Men's Open"),
        ("08/18/24", "89th", "Kevin Cleary", "Hermosa Beach", "Heritage 2024"),
        ("08/04/24", "22nd", "Tyler Stock", "Hermosa Beach", "Mich Ultra Premier Tour: $2,000 Men's Open"),
        ("06/22/24", "2nd", "Brian Gadaleta", "New Jersey", "Big Wave Splash"),
        ("10/21/23", "9th", "Justin Chow", "Hermosa Beach", "Volley4Sound 2023"),
        ("08/20/23", "89th", "Kevin Cleary", "Hermosa Beach", "Hermosa Beach Open 2023"),
        ("08/06/23", "9th", "Justin Chow", "Hermosa Beach", "AVP Manhattan Beach Wildcard Series: $2,500 Hermosa Beach Open Event 3 of Series 2 Men's Open"),
        ("06/10/23", "1st", "Justin Chow", "Manhattan Beach", "Men's AA at Manhattan Pier"),
        ("05/27/23", "25th", "Justin Chow", "Hermosa Beach", "AVP Hermosa Beach Wildcard Series: $2,500 Hermosa Beach Open Event 2 of Series 1 Men's Open"),
        ("05/14/23", "2nd", "Justin Chow", "Santa Monica", "Men's AA at Ocean Park, Santa Monica"),
        ("04/30/23", "3rd", "Justin Chow", "Manhattan Beach", "Men's AA at Manhattan Pier"),
        ("03/25/23", "9th", "Beach Baller & team", "Hermosa Beach", "Socal Cup 4 Man"),
        ("10/15/22", "9th", "Brian Fung", "Santa Barbara", "Men's Open at East Beach, Santa Barbara"),
        ("09/11/22", "2nd", "Brian Fung", "Santa Monica", "Men's AA at Ocean Park, Santa Monica"),
        ("09/03/22", "9th", "Justin Chow", "Hermosa Beach", "Gene Selznick-Premier Tour: $2,000 Hermosa Beach Men's Open"),
        ("08/28/22", "5th", "Cameron Steen", "Manhattan Beach", "Men's AA at Manhattan Pier"),
        ("07/28/22", "3rd", "Daniel Ferris", "Hermosa Beach", "QuickSand 2022"),
        ("06/04/22", "5th", "Brian O'Neill", "Santa Monica", "Men's AA at Ocean Park, Santa Monica"),
        ("05/15/22", "3rd", "Justin Chow", "Santa Monica", "Men's Open at Ocean Park, Santa Monica"),
        ("05/07/22", "13th", "Justin Chow", "Long Beach", "Men's Open at Belmont Shore"),
        ("04/30/22", "17th", "Justin Chow", "Manhattan Beach", "AVP Hermosa Beach Wildcard Series: Manhattan Beach Open Event #2 of 3 Men's Open"),
        ("10/17/21", "5th", "Luis Sandoval", "Santa Monica", "Men's AA at Will Rogers, Santa Monica"),
        ("07/11/21", "5th", "Chris Chown", "Long Beach", "Men's AA at Belmont Shore"),
        ("10/05/19", "9th", "Justin Chow", "Hermosa Beach", "AVP America Open Nationals"),
        ("10/05/19", "1st", "Lisa Hoang", "Hermosa Beach", "AVP America Open Nationals"),
        ("08/10/19", "9th", "Brian Gadaleta", "Hermosa Beach", "Miller Lite California Beach Volleyball Championships"),
        ("07/28/18", "5th", "Rob deAurora", "Manhattan Beach", "Men's Open at Marine Ave, Manhattan Beach"),
        ("05/26/18", "9th", "Chris Dedo", "Hermosa Beach", "$3,000 Open (2-Day) Men's Open at Hermosa Pier"),
        ("03/18/18", "1st", "Christopher Jones", "Long Beach", "Men's AA at Belmont Shore"),
        ("11/19/17", "5th", "Chris Dedo", "Huntington Beach", "Men's Open at Newland, Huntington Beach"),
        ("08/26/17", "N/A", "Scott Olson", "Hermosa Beach", "Campsurf Men's A at Hermosa Pier"),
    ]
    
    inserted_count = 0
    for date_str, place, team, location, tournament_name in tournaments:
        tournament_date = parse_date(date_str)
        if tournament_date:
            try:
                cur.execute("""INSERT INTO tournaments(tournament_date, place, team, location, tournament_name)
                               VALUES(?,?,?,?,?)""",
                           (tournament_date, place, team, location, tournament_name))
                inserted_count += 1
            except Error as e:
                print(f"Error inserting tournament {date_str}: {e}")
    
    conn.commit()
    conn.close()
    print(f"Successfully migrated {inserted_count} tournaments to database.")

if __name__ == '__main__':
    migrate_tournaments()

