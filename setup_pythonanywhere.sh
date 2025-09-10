#!/bin/bash

# PythonAnywhere Setup Script
# This script helps set up your Flask app on PythonAnywhere

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 PythonAnywhere Setup Guide${NC}"
echo -e "${YELLOW}================================${NC}"

echo -e "\n${BLUE}📋 Step-by-step setup instructions:${NC}"

echo -e "\n${YELLOW}1. Create PythonAnywhere Account${NC}"
echo -e "   • Go to https://www.pythonanywhere.com"
echo -e "   • Sign up for a free account"
echo -e "   • Note your username"

echo -e "\n${YELLOW}2. Open Bash Console${NC}"
echo -e "   • Go to your PythonAnywhere dashboard"
echo -e "   • Click on 'Consoles' tab"
echo -e "   • Start a new Bash console"

echo -e "\n${YELLOW}3. Clone Your Repository${NC}"
echo -e "   • In the Bash console, run:"
echo -e "   ${GREEN}git clone https://github.com/idynkydnk/stats.git${NC}"
echo -e "   • Navigate to the project:"
echo -e "   ${GREEN}cd stats${NC}"

echo -e "\n${YELLOW}4. Install Dependencies${NC}"
echo -e "   • Install requirements:"
echo -e "   ${GREEN}pip3.10 install --user -r requirements.txt${NC}"

echo -e "\n${YELLOW}5. Create Web App${NC}"
echo -e "   • Go to 'Web' tab in PythonAnywhere dashboard"
echo -e "   • Click 'Add a new web app'"
echo -e "   • Choose 'Flask'"
echo -e "   • Select Python 3.10"
echo -e "   • Set source code path to: ${GREEN}/home/idynkydnk/stats${NC}"
echo -e "   • Set WSGI file to: ${GREEN}/var/www/idynkydnk_pythonanywhere_com_wsgi.py${NC}"

echo -e "\n${YELLOW}6. Configure WSGI File${NC}"
echo -e "   • Click on the WSGI file link"
echo -e "   • Replace the content with the content from ${GREEN}wsgi_config.py${NC}"
echo -e "   • Update the path to match your username"

echo -e "\n${YELLOW}7. Set Up Database${NC}"
echo -e "   • Upload your database file (stats.db) to the project directory"
echo -e "   • Or create a new database using your database creation scripts"

echo -e "\n${YELLOW}8. Configure Static Files${NC}"
echo -e "   • In the Web tab, set static files mapping:"
echo -e "   • URL: ${GREEN}/static/${NC}"
echo -e "   • Directory: ${GREEN}/home/idynkydnk/stats/static${NC}"

echo -e "\n${YELLOW}9. Reload Web App${NC}"
echo -e "   • Click the 'Reload' button in the Web tab"
echo -e "   • Your app should now be live!"

echo -e "\n${BLUE}🔄 For Automatic Updates:${NC}"
echo -e "   • Use the ${GREEN}auto_pull.sh${NC} script"
echo -e "   • Set up a scheduled task to run it periodically"
echo -e "   • Or manually run it after each push to GitHub"

echo -e "\n${GREEN}✅ Setup complete! Your Flask app should now be running on PythonAnywhere.${NC}"
echo -e "${GREEN}✅ All paths have been updated for username: idynkydnk${NC}"
