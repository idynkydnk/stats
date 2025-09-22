#!/bin/bash

# Auto-push script for GitHub
# This script watches for file changes and automatically commits and pushes them

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_PATH="/Users/mila/Library/CloudStorage/Dropbox/coding/stats"
COMMIT_MESSAGE_PREFIX="Auto-update:"
IGNORE_PATTERNS="*.pyc,__pycache__/*,.git/*,*.db,*.db.backup,new_venv/*,venv/*"

echo -e "${BLUE}🚀 Starting auto-push watcher for GitHub...${NC}"
echo -e "${YELLOW}📁 Watching: $REPO_PATH${NC}"
echo -e "${YELLOW}🚫 Ignoring: $IGNORE_PATTERNS${NC}"
echo -e "${GREEN}✅ Press Ctrl+C to stop${NC}"
echo ""

# Function to commit and push changes
commit_and_push() {
    local changed_files="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    echo -e "${BLUE}📝 Changes detected at $timestamp${NC}"
    echo -e "${YELLOW}📄 Changed files: $changed_files${NC}"
    
    # Add all changes
    cd "$REPO_PATH"
    git add .
    
    # Check if there are any changes to commit
    if git diff --staged --quiet; then
        echo -e "${YELLOW}⚠️  No changes to commit${NC}"
        return
    fi
    
    # Create commit message
    local commit_msg="$COMMIT_MESSAGE_PREFIX $timestamp - $changed_files"
    
    # Commit changes
    echo -e "${BLUE}💾 Committing changes...${NC}"
    if git commit -m "$commit_msg"; then
        echo -e "${GREEN}✅ Changes committed successfully${NC}"
        
        # Push to GitHub
        echo -e "${BLUE}🚀 Pushing to GitHub...${NC}"
        if git push origin main; then
            echo -e "${GREEN}✅ Successfully pushed to GitHub!${NC}"
        else
            echo -e "${RED}❌ Failed to push to GitHub${NC}"
        fi
    else
        echo -e "${RED}❌ Failed to commit changes${NC}"
    fi
    
    echo ""
}

# Start watching for changes
fswatch -o -e ".*\.pyc$" -e "__pycache__" -e "\.git" -e ".*\.db$" -e ".*\.db\.backup$" -e "new_venv" -e "venv" "$REPO_PATH" | while read; do
    # Get list of changed files
    changed_files=$(git diff --name-only HEAD 2>/dev/null | head -5 | tr '\n' ' ')
    if [ -z "$changed_files" ]; then
        changed_files="various files"
    fi
    
    commit_and_push "$changed_files"
done
