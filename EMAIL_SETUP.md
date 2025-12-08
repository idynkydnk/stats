# Email Configuration Guide

This guide explains how to set up email functionality to send daily stats to players.

## Overview

The stats site can now send emails to players who played on a specific date (defaults to yesterday). Players must have email addresses stored in the database to receive emails.

## Quick Setup

### 1. Install the Required Package

```bash
pip install Flask-Mail==0.9.1
```

Or install from requirements.txt:
```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables

You need to set the following environment variables before running the app:

**For Gmail (Recommended):**
```bash
export MAIL_SERVER=smtp.gmail.com
export MAIL_PORT=587
export MAIL_USE_TLS=True
export MAIL_USERNAME=your_email@gmail.com
export MAIL_PASSWORD=your_app_password_here
export MAIL_DEFAULT_SENDER=your_email@gmail.com
```

**For Outlook/Hotmail:**
```bash
export MAIL_SERVER=smtp.office365.com
export MAIL_PORT=587
export MAIL_USE_TLS=True
export MAIL_USERNAME=your_email@outlook.com
export MAIL_PASSWORD=your_password
export MAIL_DEFAULT_SENDER=your_email@outlook.com
```

### 3. Gmail App Password Setup

If using Gmail, you MUST use an "App Password" instead of your regular password:

1. Go to your Google Account: https://myaccount.google.com/
2. Click on "Security" in the left sidebar
3. Under "How you sign in to Google," enable "2-Step Verification" if not already enabled
4. Go back to Security, scroll to "App passwords"
5. Select "Mail" as the app and your device type
6. Click "Generate"
7. Copy the 16-character password (remove spaces)
8. Use this as your `MAIL_PASSWORD`

### 4. Add Email Addresses to Players

Make sure your players have email addresses in the database:

1. Go to "Player List" in your stats site
2. Click "Edit" for each player
3. Add their email address
4. Save

## How to Use

### From the Dashboard

1. Log in to your stats site
2. Go to the Dashboard
3. Click the "Send Yesterday's Stats to Players" button
4. Confirm the action
5. Emails will be sent to all players who played yesterday and have email addresses on file

### What Gets Sent

Each player receives an email with:
- Their record for the day (wins-losses, win percentage)
- Their point differential
- Total games played that day
- Personalized greeting

## Troubleshooting

### "Email not configured" error
- Make sure all environment variables are set before starting the Flask app
- Verify the variables are exported in your shell
- If using a virtual environment, set variables after activating it

### "Authentication failed" error
- For Gmail: Make sure you're using an App Password, not your regular password
- Verify your username and password are correct
- Check that 2-Step Verification is enabled for Gmail

### "No players with email addresses found"
- Make sure players have email addresses in the database
- Check that the date has games recorded
- Verify players who played on that date have emails set

### Emails not being received
- Check spam/junk folders
- Verify the email addresses are correct in the database
- Check Flask logs for error messages

## Testing

To test email functionality without spamming all players:

1. Add your own email to a test player account
2. Add a game for that player on yesterday's date
3. Click the send emails button
4. You should receive the test email

## Permanent Configuration

To make environment variables permanent, add them to your shell profile:

**For bash (~/.bashrc or ~/.bash_profile):**
```bash
export MAIL_SERVER=smtp.gmail.com
export MAIL_PORT=587
export MAIL_USE_TLS=True
export MAIL_USERNAME=your_email@gmail.com
export MAIL_PASSWORD=your_app_password
export MAIL_DEFAULT_SENDER=your_email@gmail.com
```

**For zsh (~/.zshrc):**
```bash
export MAIL_SERVER=smtp.gmail.com
export MAIL_PORT=587
export MAIL_USE_TLS=True
export MAIL_USERNAME=your_email@gmail.com
export MAIL_PASSWORD=your_app_password
export MAIL_DEFAULT_SENDER=your_email@gmail.com
```

Then reload your shell:
```bash
source ~/.bashrc  # or source ~/.zshrc
```

## Automation (Optional)

To automatically send emails daily without clicking the button:

### Using Cron (Linux/Mac)

1. Create a simple script `send_daily_stats.sh`:
```bash
#!/bin/bash
cd /path/to/stats
source venv/bin/activate
python -c "
from stats import app, send_daily_emails
with app.test_request_context():
    send_daily_emails()
"
```

2. Make it executable:
```bash
chmod +x send_daily_stats.sh
```

3. Add to crontab (run at 8 AM daily):
```bash
crontab -e
```
Add this line:
```
0 8 * * * /path/to/send_daily_stats.sh
```

## PythonAnywhere Setup

If you're deploying to PythonAnywhere, the `.env` file won't work there. Instead, you need to set environment variables through PythonAnywhere's web interface.

**See `PYTHONANYWHERE_EMAIL_SETUP.md` for detailed instructions.**

Quick steps:
1. Go to PythonAnywhere → Web tab → Your web app
2. Scroll to "Environment variables" section
3. Add: `MAIL_SERVER = smtp.gmail.com`
4. Add: `MAIL_PORT = 587`
5. Add: `MAIL_USE_TLS = True`
6. Add: `MAIL_USERNAME = your_email@gmail.com`
7. Add: `MAIL_PASSWORD = your_app_password`
8. Add: `MAIL_DEFAULT_SENDER = your_email@gmail.com`
9. Save and Reload your web app

## Security Notes

- Never commit your email password to git
- Use App Passwords instead of real passwords when possible
- Keep your .env file in .gitignore
- On PythonAnywhere, use environment variables (not .env file)
- Consider using environment-specific configuration management

## Support

If you encounter issues:
1. Check the Flask application logs
2. Verify all environment variables are set correctly
3. Test with a single email address first
4. Check your email provider's SMTP documentation

