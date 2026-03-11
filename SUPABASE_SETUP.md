# Supabase dual-write (doubles games)

When you add, edit, or delete a doubles game on the web app, the same change is written to your Supabase project so other apps (e.g. iPhone) stay in sync.

## 1. Environment variables

Set these where the app runs (e.g. PythonAnywhere env, or `.env` locally):

- **SUPABASE_URL** – Project URL (e.g. `https://xxxx.supabase.co`)
- **SUPABASE_SERVICE_ROLE_KEY** or **SUPABASE_KEY** – Service role key from Project Settings → API (keeps sync server-side; don’t commit this)

Optional:

- **SUPABASE_DOUBLES_TABLE** – Table name (default: `games`)

## 2. Table in Supabase

The app writes to a table named **`games`** by default. It expects columns: `id` (uuid), `db_id` (uuid), `game_date`, `winner1`, `winner2`, `winner_score`, `loser1`, `loser2`, `loser_score`, `comments`, `updated_at`, `entered_timezone`, `updated_by`, and optionally `editor_db_id`. On **insert** the app generates a new UUID for `id` and a deterministic UUID from the SQLite game id for `db_id` (so it can find the row on **update** and **delete**).

## 3. If Supabase isn’t configured

If `SUPABASE_URL` or the key is missing, the app skips Supabase and still works; only SQLite is updated.
