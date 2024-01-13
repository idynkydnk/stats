#!/bin/bash

# Path to file to backup
FILE="/home/MarkL/stats/stats.db"

# Backup directory
BACKUPDIR="/home/MarkL/stats/backup"

# Metadata file to store last modified date  
METAFILE="$BACKUPDIR/metadata.txt"

# If metadata file doesn't exist, create it
if [ ! -f "$METAFILE" ]; then
  touch "$METAFILE"
fi

# Get last modified date of file
FILE_MODTIME=$(stat -c %Y "$FILE")

# Get last backup date from metadata file
LAST_BACKUP=$(cat "$METAFILE")

# Compare last modified and last backup dates
if [ "$FILE_MODTIME" -gt "$LAST_BACKUP" ]; then

  # File modified since last backup, so make new backup
  BACKUPFILE="$BACKUPDIR/$(date +%Y%m%d%H%M%S)-$(basename $FILE)"
  cp "$FILE" "$BACKUPFILE"
 
  # Update metadata file timestamp
  echo "$FILE_MODTIME" > "$METAFILE"
 
  echo "Created backup of $FILE to $BACKUPFILE"

else

  echo "No backup needed, $FILE not modified since last backup"

fi