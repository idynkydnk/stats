# Supabase dual-write (doubles games)

When you add, edit, or delete a doubles game on the web app, the same change is written to your Supabase project so other apps (e.g. iPhone) stay in sync.

## 1. Environment variables

Set these where the app runs (e.g. PythonAnywhere env, or `.env` locally):

- **SUPABASE_URL** – Project URL (e.g. `https://xxxx.supabase.co`)
- **SUPABASE_SERVICE_ROLE_KEY** or **SUPABASE_KEY** – Service role key from Project Settings → API (keeps sync server-side; don’t commit this)

Optional:

- **SUPABASE_DOUBLES_TABLE** – Table name (default: `doubles_games`)

## 2. Table in Supabase

Create a table that matches the doubles game shape. Example SQL:

```sql
create table doubles_games (
  id bigint primary key,
  game_date timestamptz,
  winner1 text not null,
  winner2 text not null,
  winner_score int not null,
  loser1 text not null,
  loser2 text not null,
  loser_score int not null,
  updated_at timestamptz,
  comments text default '',
  entered_timezone text,
  updated_by text
);
```

The app will **insert** on add, **update** on edit, and **delete** on delete, using the same `id` as SQLite.

## 3. If Supabase isn’t configured

If `SUPABASE_URL` or the key is missing, the app skips Supabase and still works; only SQLite is updated.
