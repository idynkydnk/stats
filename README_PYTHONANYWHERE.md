# PythonAnywhere Deployment Guide

This guide will help you deploy your Flask stats application to PythonAnywhere and set up automatic updates.

## Quick Setup

1. **Run the setup guide:**
   ```bash
   ./setup_pythonanywhere.sh
   ```

2. **Follow the step-by-step instructions** that appear on screen.

## Files Created for Deployment

- `requirements.txt` - Python dependencies for PythonAnywhere
- `wsgi_config.py` - WSGI configuration template
- `auto_pull.sh` - Script to pull updates from GitHub
- `setup_pythonanywhere.sh` - Interactive setup guide
- `deploy_to_pythonanywhere.py` - Deployment helper script

## Manual Setup Steps

### 1. PythonAnywhere Account
- Sign up at https://www.pythonanywhere.com
- Note your username

### 2. Clone Repository
In PythonAnywhere Bash console:
```bash
git clone https://github.com/idynkydnk/stats.git
cd stats
```

### 3. Install Dependencies
```bash
pip3.10 install --user -r requirements.txt
```

### 4. Create Web App
- Go to Web tab in PythonAnywhere dashboard
- Create new Flask web app
- Set source code to: `/home/idynkydnk/stats`
- Set WSGI file to: `/var/www/idynkydnk_pythonanywhere_com_wsgi.py`

### 5. Configure WSGI
Copy content from `wsgi_config.py` to your WSGI file (already updated for your username):
```python
path = '/home/idynkydnk/stats'  # Updated for idynkydnk
```

### 6. Upload Database
Upload your `stats.db` file to the project directory, or create a new database.

### 7. Configure Static Files
In Web tab, add static files mapping:
- URL: `/static/`
- Directory: `/home/idynkydnk/stats/static`

### 8. Reload Web App
Click the "Reload" button in the Web tab.

## Automatic Updates

### Option 1: GitHub Actions (Recommended - Real-time)
**For instant deployment when you push to GitHub:**
1. See `GITHUB_ACTIONS_SETUP.md` for complete setup instructions
2. Requires PythonAnywhere paid account for API access
3. Automatically deploys every time you push to GitHub

### Option 2: Scheduled Task (Free)
1. Go to Tasks tab in PythonAnywhere
2. Create a new task that runs: `bash /home/idynkydnk/stats/auto_pull.sh`
3. Set it to run every hour or as needed

### Option 3: Manual Updates
After pushing to GitHub, run in PythonAnywhere Bash console:
```bash
cd /home/idynkydnk/stats
./auto_pull.sh
```

## Troubleshooting

### Common Issues:
1. **Import errors**: Make sure all dependencies are installed
2. **Database not found**: Upload your database file to the project directory
3. **Static files not loading**: Check static files mapping in Web tab
4. **App not reloading**: Manually reload in Web tab after updates

### Logs:
- Check error logs in the Web tab
- Use PythonAnywhere console for debugging

## Security Notes

- Update the SECRET_KEY in `stats.py` for production
- Consider using environment variables for sensitive data
- The current setup is suitable for development/testing

## Support

If you encounter issues:
1. Check PythonAnywhere documentation
2. Verify all file paths are correct
3. Ensure all dependencies are installed
4. Check error logs in the Web tab
