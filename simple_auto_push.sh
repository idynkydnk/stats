#!/bin/bash

# Simple auto-push script
# Run this script to automatically commit and push all current changes

set -e

REPO_PATH="/Users/mila/Library/CloudStorage/Dropbox/coding/stats"
cd "$REPO_PATH"

# Get current timestamp
timestamp=$(date '+%Y-%m-%d %H:%M:%S')

# Add all changes (including deletions)
git add -A

# Check if there are changes to commit
if git diff --staged --quiet; then
    echo "No changes to commit"
    exit 0
fi

# Commit with timestamp
git commit -m "Auto-update: $timestamp"

# Push to GitHub with failure handling
if git push origin main; then
    echo "✅ Changes pushed to GitHub successfully!"
else
    echo "❌ Failed to push changes. Please resolve the issue and run the script again."
    exit 1
fi
