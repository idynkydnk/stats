import sqlite3
from datetime import datetime

COLUMNS = [f"winner{i}_score" for i in range(1, 16)] + [f"loser{i}_score" for i in range(1, 16)]

def column_exists(cursor, column_name):
    cursor.execute("PRAGMA table_info(other_games)")
    return any(row[1] == column_name for row in cursor.fetchall())

def main():
    db_path = "stats.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    added_columns = []
    for column in COLUMNS:
        if not column_exists(cursor, column):
            cursor.execute(f"ALTER TABLE other_games ADD COLUMN {column} INTEGER")
            added_columns.append(column)

    if added_columns:
        conn.commit()
        print(f"✅ Added columns: {', '.join(added_columns)}")
    else:
        print("ℹ️ All per-player score columns already exist.")

    conn.close()

if __name__ == "__main__":
    main()

