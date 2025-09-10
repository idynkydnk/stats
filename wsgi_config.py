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

# Optional: Set environment variables if needed
# os.environ['FLASK_ENV'] = 'production'

if __name__ == "__main__":
    application.run()
