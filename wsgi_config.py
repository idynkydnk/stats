"""
WSGI Configuration for PythonAnywhere
Copy this content to your PythonAnywhere WSGI file.
Updated for username: idynkydnk
"""

import sys
import os

# Add your project directory to the Python path
path = '/home/idynkydnk/stats'
if path not in sys.path:
    sys.path.append(path)

# Import your Flask app
from stats import app as application

# Email environment variables
# IMPORTANT: The WSGI file on PythonAnywhere is SEPARATE from this file in git.
# The actual WSGI file is at: /var/www/idynkydnk_pythonanywhere_com_wsgi.py
# It's safe to put your password there because it's NOT in git.
#
# To set up email on PythonAnywhere:
#   1. Go to PythonAnywhere dashboard → Web tab
#   2. Click on your web app (idynkydnk.pythonanywhere.com)
#   3. Find "WSGI configuration file" section (shows: /var/www/idynkydnk_pythonanywhere_com_wsgi.py)
#   4. Click the link to edit the WSGI file
#   5. Add these lines BEFORE "from stats import app as application":
#
#      os.environ['MAIL_SERVER'] = 'smtp.gmail.com'
#      os.environ['MAIL_PORT'] = '587'
#      os.environ['MAIL_USE_TLS'] = 'True'
#      os.environ['MAIL_USERNAME'] = 'kt.vball.summary@gmail.com'
#      os.environ['MAIL_PASSWORD'] = 'your_gmail_app_password_here'
#      os.environ['MAIL_DEFAULT_SENDER'] = 'kt.vball.summary@gmail.com'
#      os.environ['AI_EMAIL_COPY_TO'] = 'idynkydnk@gmail.com'
#      os.environ['AI_EMAIL_REPLY_TO'] = 'idynkydnk@gmail.com'
#      os.environ['SITE_BASE_URL'] = 'https://idynkydnk.pythonanywhere.com'
#
#      # AI: OpenAI preferred for higher-quality images; Gemini is the free fallback
#      os.environ['OPENAI_API_KEY'] = 'sk-...'
#      # os.environ['GEMINI_API_KEY'] = 'your_gemini_api_key_here'
#
#      os.environ['SUPABASE_URL'] = 'https://your-project.supabase.co'
#      os.environ['SUPABASE_SERVICE_ROLE_KEY'] = 'your_service_role_key_here'
#
#      # Flask session signing key - generate with:
#      #   python3 -c "import secrets; print(secrets.token_hex(32))"
#      os.environ['SECRET_KEY'] = 'your_random_secret_key_here'
#
#      # Deploy webhook token - must match the DEPLOY_TOKEN secret in the
#      # GitHub repo (Settings -> Secrets and variables -> Actions).
#      # Without it, POST /deploy returns 503 and auto-deploy is disabled.
#      os.environ['DEPLOY_TOKEN'] = 'your_random_deploy_token_here'
#
#   6. Replace 'your_gmail_app_password_here' with your actual Gmail app password
#   7. Click "Save" at the top of the editor
#   8. Go back to the Web tab and click the green "Reload" button
#
# Your password will NOT be in git - it's only in the WSGI file on PythonAnywhere's servers.
#
# --- AI auto-send "tap and walk away" (Always-on task) ---
#
# The web app queues jobs in stats.db; a separate long-running worker processes them.
# Without this task, Generate & Send (walk away) will queue jobs but never process them.
#
# Always-on tasks do NOT inherit WSGI env vars automatically. The daemon now reads
# missing keys from this WSGI file, so the Always-on Command should be SHORT — do
# not paste OPENAI_API_KEY into the task Command (long keys get truncated/mangled
# and leave the task stuck on "Starting").
#
#   1. PythonAnywhere dashboard → Tasks tab → Always-on tasks
#   2. Command (exactly this one line):
#        bash "$HOME/stats/start_ai_auto_send_daemon.sh"
#   3. Description: AI auto-send worker
#   4. Save → Restart → State should become Running
#   5. Logs: ~/stats/ai_auto_send_daemon.log (or the task log icon)
#   6. Heartbeat file (worker alive): ~/stats/ai_auto_send_daemon.heartbeat


if __name__ == "__main__":
    application.run()
