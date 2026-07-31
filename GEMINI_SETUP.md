# AI Setup Guide (OpenAI + Gemini)

Summaries and illustrations use **OpenAI when `OPENAI_API_KEY` is set** (preferred for higher-quality images via `gpt-image-2`). If that key is unset, the app falls back to **Google Gemini** (`GEMINI_API_KEY`).

## Option A — OpenAI (recommended for image quality)

### 1. Get an API key

1. Go to https://platform.openai.com/api-keys
2. Create a secret key
3. Ensure the org can use GPT Image models (organization verification may be required)

### 2. Set environment variables

**macOS/Linux:**
```bash
export OPENAI_API_KEY="sk-..."
# Optional overrides:
# export OPENAI_TEXT_MODEL="gpt-4.1"
# export OPENAI_IMAGE_MODEL="gpt-image-2"
# export OPENAI_IMAGE_QUALITY="high"
```

**PythonAnywhere (WSGI):**
```python
import os
os.environ['OPENAI_API_KEY'] = 'sk-...'
```

Or put the same values in your local `.env` (see `.env.example`).

### 3. Cost note

OpenAI is paid (per token / per image). Image generation with reference photos (solo caricatures + group scenes) uses the Images **edits** endpoint and can cost more than text alone.

---

## Option B — Gemini (free-tier fallback)

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

**OpenAI:** paid — see platform pricing for chat + GPT Image.

**Gemini:** free tier
- No credit card needed
- 1,500 requests per day
- That's 1,500 daily summaries for free

## Troubleshooting

**"AI API key not configured" error:**
- Set `OPENAI_API_KEY` and/or `GEMINI_API_KEY`
- Restart your Flask app after setting the variable

**"API key invalid" error:**
- Check that you copied the entire key
- Make sure there are no extra spaces

**OpenAI image / moderation errors:**
- Complete organization verification for GPT Image models
- Soften prompt language if moderation blocks a request

**Gemini "Quota exceeded" error:**
- You've hit the free daily limit
- Wait until tomorrow, create another API key, or switch to `OPENAI_API_KEY`

## Security Note

Keep your API key private! Don't commit it to GitHub.
