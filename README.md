# Stats

A Flask website for tracking games and stats with a friend group — doubles volleyball (the main event), vollis, and other games (gin rummy, coed, etc.). Includes TrueSkill ratings, streaks, AI-generated recap emails (Gemini), and a REST API used by an iPhone app.

Live at `idynkydnk.pythonanywhere.com`.

The native iPhone companion lives in [`ios/`](ios/README.md). It wraps the live
site in a SwiftUI app so the full website remains available, and adds native
navigation, sharing/downloads, and uploads.

## Tech stack

- **Backend:** Python 3 / Flask, Jinja2 templates
- **Database:** SQLite (`stats.db`)
- **Email:** Flask-Mail via Gmail SMTP
- **AI summaries / illustrations:** OpenAI (preferred, `OPENAI_API_KEY`) or Google Gemini fallback (`GEMINI_API_KEY`)
- **Hosting:** PythonAnywhere, auto-deployed from GitHub Actions on push to `main`

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in email/OpenAI or Gemini values as needed
python local.py        # serves on http://127.0.0.1:5000
```

The app works without `.env` — email and AI features just stay disabled.

## Project layout

| Path | Purpose |
|------|---------|
| `stats.py` | Flask app: routes, auth, notifications, iPhone API |
| `stat_functions.py` | Doubles stats, TrueSkill ratings, caching |
| `vollis_functions.py`, `other_functions.py`, `player_functions.py`, `kob_functions.py` | Domain logic per game type |
| `database_functions.py` | Core DB operations |
| `email_content.py` | HTML email bodies + AI summary payload builders |
| `templates/`, `static/` | Jinja2 templates and CSS/JS |
| `create_*_database.py` | One-off schema setup scripts |
| `migrations/` | One-off data migration scripts |
| `backups/` | Local DB backups (gitignored) |

## Deployment

Pushing to `main` triggers `.github/workflows/deploy-to-pythonanywhere.yml`, which calls the site's `/deploy` webhook. That pulls the latest code and reloads the web app. Environment variables (email password, API keys) live in the WSGI file on PythonAnywhere — see `wsgi_config.py` for instructions.

## More docs

- `API_DOUBLES.md` — iPhone app REST API
- `EMAIL_SETUP.md` / `PYTHONANYWHERE_EMAIL_SETUP.md` — email configuration
- `GEMINI_SETUP.md` — AI summary setup (OpenAI preferred; Gemini fallback)
- `GITHUB_ACTIONS_SETUP.md` — deploy pipeline

## AI recap and flyer retention

After a successful new publication, each account keeps a target of 100 recaps
and 50 flyers. The oldest eligible items are removed first. Pin favorites from
the website or iPhone app to protect them. Flyers dated today or later (Pacific
time), and legacy flyers with unrecognized dates, are also protected. Protected
items count toward the target and can exceed it; cleanup never removes the item
just created. Failed generation, browsing, and deployment do not trigger cleanup.

Set `AI_RECAP_LIMIT` and `AI_FLYER_LIMIT` to positive integers to adjust the
per-account targets. Unpinning takes effect on the next successful creation.
Deletion retires the page link, removes its carousel slides, and removes its main
images and previews only when no other published recap or flyer references them.
Historical prompt logs do not keep deleted-page images alive. Recaps currently
being emailed are protected; deleting a recap cancels its pending email. Existing
unused files from older deletions can still be reviewed under Admin → AI Images,
which also shows image storage usage.

New recaps offer text only or a still illustration. Requests from older clients
for animations use a still illustration; existing animated recaps remain viewable.
