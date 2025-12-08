# Setting Up Email on PythonAnywhere

This guide explains how to configure Gmail app password for the AI summary feature on PythonAnywhere.

## 🔐 Why Environment Variables?

The `.env` file is only for **local development** and is gitignored (not committed to GitHub). On PythonAnywhere, you need to set environment variables through their web interface instead.

## 📋 Step-by-Step Instructions

### Step 1: Get Your Gmail App Password

If you haven't already:
1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** if not already enabled
3. Go to **App passwords** (under "How you sign in to Google")
4. Select **Mail** as the app and your device
5. Click **Generate**
6. Copy the 16-character password (remove spaces)

### Step 2: Set Environment Variables in the WSGI File

The WSGI file on PythonAnywhere is **separate** from the one in your git repository. It's safe to put your password there because it's only stored on PythonAnywhere's servers, not in git.

1. **Log in to PythonAnywhere**
   - Go to [www.pythonanywhere.com](https://www.pythonanywhere.com)
   - Log in with your account

2. **Navigate to Web App Settings**
   - Click on the **Web** tab in the top menu
   - Click on your web app (usually `idynkydnk.pythonanywhere.com`)

3. **Find the WSGI Configuration File**
   - Scroll down to the **"Code:"** section
   - Look for **"WSGI configuration file:"**
   - You'll see: `/var/www/idynkydnk_pythonanywhere_com_wsgi.py`
   - **Click on that file path** - it's a link that will open the file editor

4. **Edit the WSGI File**
   
   In the editor, find the line that says:
   ```python
   from stats import app as application
   ```
   
   **Add these lines RIGHT BEFORE that line:**
   ```python
   # Email configuration
   os.environ['MAIL_SERVER'] = 'smtp.gmail.com'
   os.environ['MAIL_PORT'] = '587'
   os.environ['MAIL_USE_TLS'] = 'True'
   os.environ['MAIL_USERNAME'] = 'kt.vball.summary@gmail.com'
   os.environ['MAIL_PASSWORD'] = 'your_16_character_app_password_here'
   os.environ['MAIL_DEFAULT_SENDER'] = 'kt.vball.summary@gmail.com'
   ```
   
   **Important:** Replace `'your_16_character_app_password_here'` with your actual Gmail app password (keep the quotes).

5. **Save and Reload**
   - Click the **Save** button at the top of the editor
   - Go back to the **Web** tab
   - Click the green **Reload** button (near the top, under "Reload:")
   - Wait for the reload to complete (usually takes 10-30 seconds)

### Step 3: Verify It Works

1. Go to your stats site on PythonAnywhere
2. Log in
3. Try generating and sending an AI summary email
4. Check that emails are sent successfully

## 🔄 Updating Your Password

If you need to update your Gmail app password:

1. Generate a new app password from Google (see Step 1)
2. Go to PythonAnywhere → Web tab → Your web app
3. Find the `MAIL_PASSWORD` line in the Environment variables section
4. Update the value with your new password
5. Click **Save** and **Reload**

## 🛠️ Troubleshooting

### Emails Not Sending

**Check 1: Environment Variables**
- Make sure all 6 variables are set correctly
- Verify there are no extra spaces or typos
- Check that `MAIL_PASSWORD` has your actual app password (not the placeholder)

**Check 2: App Password**
- Make sure you're using a Gmail **App Password**, not your regular password
- Verify 2-Step Verification is enabled on your Google account
- Try generating a new app password

**Check 3: Reload**
- Make sure you clicked **Reload** after saving
- Check the error logs in PythonAnywhere → Web tab → Error log

### "Email not configured" Error

This means one or more environment variables are missing:
- Go back to the Environment variables section
- Verify all 6 variables are present
- Make sure variable names match exactly (case-sensitive)
- Save and reload again

### Authentication Failed

- Double-check your Gmail app password is correct
- Make sure you're using an App Password, not your regular Gmail password
- Verify 2-Step Verification is enabled

## 📝 Notes

- **Local vs Production**: 
  - **Local**: Uses `.env` file (gitignored, not in GitHub)
  - **PythonAnywhere**: Uses environment variables set in web interface
  
- **Security**: 
  - Your password is stored securely on PythonAnywhere's servers
  - It's never committed to GitHub
  - Only you can see/edit it through your PythonAnywhere account

- **Multiple Environments**:
  - You can have different passwords for local development and production
  - Just make sure each environment has the correct values set

## 🔗 Related Files

- `.env` - Local development configuration (gitignored)
- `.env.example` - Template for local setup (safe to commit)
- `wsgi_config.py` - PythonAnywhere WSGI configuration
- `stats.py` - Main Flask app (reads from environment variables)

