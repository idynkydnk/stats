#!/usr/bin/env python3
"""
PythonAnywhere Deployment Script
This script helps deploy your Flask app to PythonAnywhere automatically.
"""

import os
import subprocess
import sys
from pathlib import Path

def run_command(command, description):
    """Run a command and return the result."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} completed successfully")
            if result.stdout:
                print(f"Output: {result.stdout}")
            return True
        else:
            print(f"❌ {description} failed")
            print(f"Error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ {description} failed with exception: {e}")
        return False

def main():
    """Main deployment function."""
    print("🚀 Starting PythonAnywhere deployment process...")
    
    # Check if we're in the right directory
    if not os.path.exists("stats.py"):
        print("❌ Error: stats.py not found. Please run this script from the project root.")
        sys.exit(1)
    
    # Check if requirements.txt exists
    if not os.path.exists("requirements.txt"):
        print("❌ Error: requirements.txt not found. Please create it first.")
        sys.exit(1)
    
    print("📋 Deployment checklist:")
    print("1. ✅ Project files found")
    print("2. ✅ requirements.txt found")
    print("3. 🔄 Ready for deployment")
    
    print("\n📝 Manual steps for PythonAnywhere:")
    print("1. Go to your PythonAnywhere dashboard")
    print("2. Open a Bash console")
    print("3. Clone your repository:")
    print("   git clone https://github.com/idynkydnk/stats.git")
    print("4. Navigate to the project:")
    print("   cd stats")
    print("5. Install requirements:")
    print("   pip3.10 install --user -r requirements.txt")
    print("6. Set up your web app:")
    print("   - Go to Web tab in PythonAnywhere")
    print("   - Create new web app (Flask)")
    print("   - Set source code to: /home/yourusername/stats")
    print("   - Set WSGI file to: /var/www/yourusername_pythonanywhere_com_wsgi.py")
    print("7. Configure WSGI file (see wsgi_config.py)")
    print("8. Reload your web app")
    
    print("\n🔄 For automatic updates, you can:")
    print("1. Set up a scheduled task to pull from GitHub")
    print("2. Use the auto_pull.sh script provided")
    print("3. Set up GitHub webhooks (requires paid account)")

if __name__ == "__main__":
    main()
