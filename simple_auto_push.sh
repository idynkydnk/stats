#!/bin/bash

# Simple auto-push script
# Run this script to automatically commit and push all current changes

REPO_PATH="/Users/mila/Library/CloudStorage/Dropbox/coding/stats"
cd "$REPO_PATH"

# Get current timestamp
timestamp=$(date '+%Y-%m-%d %H:%M:%S')

# Add all changes
git add .

# Check if there are changes to commit
if git diff --staged --quiet; then
    echo "No changes to commit"
    exit 0
fi

# Commit with timestamp
git commit -m "Auto-update: $timestamp"

# Push to GitHub
git push origin main

echo "✅ Changes pushed to GitHub successfully!"
