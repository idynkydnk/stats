#!/bin/bash
# Start the AI auto-send queue worker (for PythonAnywhere Always-on task).
#
# In the PythonAnywhere Always-on tasks tab, use a command like:
#
#   export GEMINI_API_KEY='your_key'
#   export MAIL_SERVER='smtp.gmail.com'
#   export MAIL_PORT='587'
#   export MAIL_USE_TLS='True'
#   export MAIL_USERNAME='kt.vball.summary@gmail.com'
#   export MAIL_PASSWORD='your_gmail_app_password'
#   export MAIL_DEFAULT_SENDER='kt.vball.summary@gmail.com'
#   export AI_EMAIL_COPY_TO='idynkydnk@gmail.com'
#   export AI_EMAIL_REPLY_TO='idynkydnk@gmail.com'
#   export SITE_BASE_URL='https://idynkydnk.pythonanywhere.com'
#   export SECRET_KEY='your_secret_key'
#   bash /home/idynkydnk/stats/start_ai_auto_send_daemon.sh
#
# Copy the export lines from your WSGI file (/var/www/idynkydnk_pythonanywhere_com_wsgi.py).

cd /home/idynkydnk/stats || exit 1
exec python3 ai_auto_send_daemon.py
