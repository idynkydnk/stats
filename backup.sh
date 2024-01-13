#!/bin/bash

# Path to database file to backup
DB_FILE="/home/MarkL/stats/stats.db"

# Backup directory
BACKUPDIR="/home/MarkL/backup"

# Metadata file to store last modified date
METAFILE="$BACKUPDIR/metadata.txt"

# If metadata file doesn't exist, create it
if [ ! -f "$METAFILE" ]; then
  echo "No last modified date file found, creating $METAFILE"
  echo "0" >> "$METAFILE"
fi

# Get last modified date of db file
FILE_MODTIME=$(stat -c %Y "$DB_FILE")

# Get last backup date from metadata file
LAST_BACKUP=$(cat "$METAFILE")

# Compare last modified and last backup dates
if [ "$FILE_MODTIME" -gt "$LAST_BACKUP" ]; then

  # Vacuum the database to reduce size
  sqlite3 $DB_FILE 'VACUUM;'
  echo "Vacuumed the database $DB_FILE"
  # Get last modified date of db after vacuuming
  FILE_MODTIME=$(stat -c %Y "$DB_FILE")
  # Create a backup
  BACKUPFILE="$BACKUPDIR/$(date +%Y_%m_%d_%H%M)-$(basename $DB_FILE)"
  cp "$DB_FILE" "$BACKUPFILE"

  # Update metadata file timestamp
  echo "$FILE_MODTIME" > "$METAFILE"

  echo "Created backup of $FILE to $BACKUPFILE"

else

  echo "No backup needed, $DB_FILE not modified since last backup"

fi