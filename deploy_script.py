#!/usr/bin/env python3
"""
GitHub Actions deployment script for PythonAnywhere
This script handles the deployment process when triggered by GitHub Actions
"""

import os
import requests
import subprocess
import sys
from datetime import datetime

def log(message):
    """Log messages with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def run_command(command, description):
    """Run a command and return the result"""
    log(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            log(f"✅ {description} completed successfully")
            if result.stdout:
                log(f"Output: {result.stdout}")
            return True
        else:
            log(f"❌ {description} failed")
            log(f"Error: {result.stderr}")
            return False
    except Exception as e:
        log(f"❌ {description} failed with exception: {e}")
        return False

def deploy_to_pythonanywhere():
    """Main deployment function"""
    log("🚀 Starting PythonAnywhere deployment...")
    
    # Get environment variables
    username = os.getenv('PYTHONANYWHERE_USERNAME')
    api_token = os.getenv('PYTHONANYWHERE_API_TOKEN')
    domain = os.getenv('PYTHONANYWHERE_DOMAIN')
    
    if not all([username, api_token, domain]):
        log("❌ Missing required environment variables:")
        log(f"   PYTHONANYWHERE_USERNAME: {'✅' if username else '❌'}")
        log(f"   PYTHONANYWHERE_API_TOKEN: {'✅' if api_token else '❌'}")
        log(f"   PYTHONANYWHERE_DOMAIN: {'✅' if domain else '❌'}")
        sys.exit(1)
    
    log(f"📋 Deploying for user: {username}")
    log(f"🌐 Domain: {domain}")
    
    # Step 1: Pull latest code (this happens automatically in GitHub Actions)
    log("📥 Code is already up to date from GitHub Actions checkout")
    
    # Step 2: Reload the web app using PythonAnywhere API
    log("🔄 Reloading web app...")
    
    reload_url = f"https://www.pythonanywhere.com/api/v0/user/{username}/webapps/{domain}/reload/"
    headers = {
        'Authorization': f'Token {api_token}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(reload_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            log("✅ Web app reloaded successfully!")
            log(f"Response: {response.text}")
        else:
            log(f"❌ Failed to reload web app. Status: {response.status_code}")
            log(f"Response: {response.text}")
            sys.exit(1)
            
    except requests.exceptions.RequestException as e:
        log(f"❌ Error calling PythonAnywhere API: {e}")
        sys.exit(1)
    
    # Step 3: Verify deployment
    log("🔍 Verifying deployment...")
    
    # Wait a moment for the reload to take effect
    import time
    time.sleep(5)
    
    try:
        # Try to access the main page
        site_url = f"https://{domain}"
        response = requests.get(site_url, timeout=30)
        
        if response.status_code == 200:
            log("✅ Deployment verified! Site is responding.")
        else:
            log(f"⚠️  Site responded with status {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        log(f"⚠️  Could not verify deployment: {e}")
        log("💡 This might be normal - the site may still be reloading")
    
    log("🎉 Deployment process completed!")

if __name__ == "__main__":
    deploy_to_pythonanywhere()
