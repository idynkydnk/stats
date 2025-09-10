#!/bin/bash

# Auto-pull script for PythonAnywhere
# This script pulls the latest changes from GitHub and reloads the web app

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration - UPDATED FOR idynkydnk
REPO_PATH="/home/idynkydnk/stats"  # Updated with actual path
PYTHONANYWHERE_USERNAME="idynkydnk"  # Updated with actual username

echo -e "${BLUE}🚀 Starting auto-pull from GitHub...${NC}"
echo -e "${YELLOW}📁 Repository path: $REPO_PATH${NC}"

# Navigate to the repository
cd "$REPO_PATH" || {
    echo -e "${RED}❌ Error: Could not navigate to $REPO_PATH${NC}"
    exit 1
}

# Pull latest changes from GitHub
echo -e "${BLUE}📥 Pulling latest changes from GitHub...${NC}"
if git pull origin main; then
    echo -e "${GREEN}✅ Successfully pulled latest changes${NC}"
else
    echo -e "${RED}❌ Failed to pull changes from GitHub${NC}"
    exit 1
fi

# Install/update requirements if needed
echo -e "${BLUE}📦 Checking requirements...${NC}"
if [ -f "requirements.txt" ]; then
    echo -e "${BLUE}📦 Installing/updating requirements...${NC}"
    pip3.10 install --user -r requirements.txt
    echo -e "${GREEN}✅ Requirements updated${NC}"
fi

# Reload the web app (this requires the PythonAnywhere API or manual reload)
echo -e "${BLUE}🔄 Reloading web app...${NC}"
echo -e "${YELLOW}⚠️  Note: You may need to manually reload your web app in the PythonAnywhere dashboard${NC}"

# Optional: Try to reload using PythonAnywhere API (requires API token)
# Uncomment and configure if you have a PythonAnywhere API token
# curl -X POST -H "Authorization: Token your_api_token_here" \
#      https://www.pythonanywhere.com/api/v0/user/idynkydnk/webapps/idynkydnk.pythonanywhere.com/reload/

echo -e "${GREEN}✅ Auto-pull completed successfully!${NC}"
echo -e "${YELLOW}💡 Don't forget to reload your web app in the PythonAnywhere dashboard${NC}"
