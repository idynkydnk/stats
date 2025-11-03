# Google Gemini AI Setup Guide

## Quick Setup (5 minutes)

### 1. Get Your Free Gemini API Key

1. Go to https://makersuite.google.com/app/apikey
2. Click **"Get API Key"**
3. Click **"Create API key in new project"**
4. Copy your API key (it looks like: `AIzaSy...`)

**That's it!** The API key is completely free with generous limits:
- 60 requests per minute
- 1,500 requests per day
- No credit card required

### 2. Set Environment Variable

**For macOS/Linux (add to ~/.zshrc or ~/.bashrc):**
```bash
export GEMINI_API_KEY="your_api_key_here"
```

Then reload:
```bash
source ~/.zshrc
```

**For temporary testing:**
```bash
export GEMINI_API_KEY="your_api_key_here"
GEMINI_API_KEY="your_api_key_here" python stats.py
```

**For PythonAnywhere:**
Add to your WSGI file:
```python
import os
os.environ['GEMINI_API_KEY'] = 'your_api_key_here'
```

### 3. Install Package

```bash
pip install google-generativeai
```

Or:
```bash
pip install -r requirements.txt
```

### 4. Test It!

1. Run your Flask app: `stats`
2. Log in
3. Go to "Work in Progress"
4. Click "Open Testing Lab"
5. Select a date and click "Generate AI Summary"

## What You Get

The AI will generate fun, engaging summaries like:

> "🏐 What a day at the courts! Kyle dominated the competition, going an 
> impressive 8-2 with a stellar +42 point differential. The closest match 
> of the day saw Aaron & Dan edge out Ryan & Mark 21-19 in a nail-biter. 
> Ben showed up with authority, maintaining a perfect 5-0 record..."

## Cost

**Completely FREE!**
- No credit card needed
- 1,500 requests per day
- That's 1,500 daily summaries for free

## Troubleshooting

**"Gemini API key not configured" error:**
- Make sure you exported the environment variable
- Restart your Flask app after setting the variable

**"API key invalid" error:**
- Check that you copied the entire key
- Make sure there are no extra spaces

**"Quota exceeded" error:**
- You've hit the 1,500/day limit (unlikely)
- Wait until tomorrow or create another API key

## Security Note

Keep your API key private! Don't commit it to GitHub.

