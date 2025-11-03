#!/bin/bash
# Run Flask app with email configuration

cd /Users/mila/Library/CloudStorage/Dropbox/coding/stats
source venv/bin/activate

export MAIL_USERNAME=idynkydnk@gmail.com
export MAIL_PASSWORD="mvjb jpls tlnp opzy"
export MAIL_DEFAULT_SENDER=idynkydnk@gmail.com

python stats.py

