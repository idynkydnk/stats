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
#
#   6. Replace 'your_gmail_app_password_here' with your actual Gmail app password
#   7. Click "Save" at the top of the editor
#   8. Go back to the Web tab and click the green "Reload" button
#
# Your password will NOT be in git - it's only in the WSGI file on PythonAnywhere's servers.

if __name__ == "__main__":
    application.run()
