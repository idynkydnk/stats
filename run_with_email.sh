#!/bin/bash
# Run Flask app with email configuration
# 
# IMPORTANT: Set these environment variables before running:
#   export MAIL_USERNAME=your_email@gmail.com
#   export MAIL_PASSWORD=your_app_password
#   export MAIL_DEFAULT_SENDER=your_email@gmail.com
#
# Or create a .env file in this directory and source it:
#   source .env

cd /Users/mila/Library/CloudStorage/Dropbox/coding/stats
source venv/bin/activate

# Check if environment variables are set
if [ -z "$MAIL_USERNAME" ] || [ -z "$MAIL_PASSWORD" ]; then
    echo "Error: MAIL_USERNAME and MAIL_PASSWORD must be set as environment variables"
    echo "Set them manually or create a .env file (see .env.example)"
    exit 1
fi

# Load .env file if it exists (but don't fail if it doesn't)
if [ -f .env ]; then
    source .env
fi

python stats.py

