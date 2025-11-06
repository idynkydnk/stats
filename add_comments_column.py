#!/usr/bin/env python3
"""
Migration script to add comments column to games table
"""
import sqlite3
import os

def create_connection(db_file):
    """Create a database connection"""
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except sqlite3.Error as e:
        print(e)
    return conn

def add_comments_column():
    """Add comments column to games table"""
    # Try PythonAnywhere path first, then local
    database = '/home/Idynkydnk/stats/stats.db'
    if not os.path.exists(database):
        database = 'stats.db'
    
    conn = create_connection(database)
    if conn is None:
        print("Error! Cannot create database connection.")
        return
    
    try:
        cur = conn.cursor()
        
        # Check if column already exists
        cur.execute("PRAGMA table_info(games)")
        columns = [column[1] for column in cur.fetchall()]
        
        if 'comments' in columns:
            print("✅ Comments column already exists in games table")
        else:
            # Add comments column
            cur.execute("ALTER TABLE games ADD COLUMN comments TEXT DEFAULT ''")
            conn.commit()
            print("✅ Successfully added comments column to games table")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"❌ Error adding comments column: {e}")
        if conn:
            conn.close()

if __name__ == '__main__':
    add_comments_column()

