# iOS JSON API

Base URL: `https://idynkydnk.pythonanywhere.com`

The website HTML is unchanged. These routes wrap the same Python functions so the iPhone app and the site share `stats.db`.

## Auth

- `POST /api/auth/login` JSON `{username, password}` → `{token, username}`
- `GET /api/me` Bearer → `{username, is_admin, logged_in}`
- `POST /api/auth/logout` Bearer

Send `Authorization: Bearer <token>` on write endpoints. Session cookies still work for the website.

## Public reads

- `GET /api/years`
- `GET /api/doubles/stats?year=`
- `GET /api/doubles/games?year=&since=` (also `{deleted_ids}`)
- `GET /api/doubles/games/<id>`
- `GET /api/doubles/players/<name>?year=`
- `GET /api/network?year=`
- `GET /api/vollis/stats?year=`
- `GET /api/vollis/games?year=&since=`
- `GET /api/vollis/games/<id>`
- `GET /api/vollis/players/<name>?year=`
- `GET /api/other/stats?year=`
- `GET /api/other/game-types`
- `GET /api/other/games?year=&game_name=&since=`
- `GET /api/other/games/<id>`
- `GET /api/other/players/<name>?year=`
- `GET /api/volleyball/stats?year=`
- `GET /api/players`
- `GET /api/search_all_players?q=`

## Writes (Bearer)

- Doubles: existing `POST/PUT/DELETE /api/doubles/games`
- Vollis: `POST /api/vollis/games`, `PUT/DELETE /api/vollis/games/<id>`
- Other: `POST /api/other/games`, `PUT/DELETE /api/other/games/<id>`
- `GET/POST /api/tournaments`
- Players: existing `/api/add_player`, `/api/rename_player`, `/api/update_player_info`, `/api/player_photo/<name>/`, `POST /api/player_ai_image/<name>/` (create/remake saved AI character; returns `job_id` or `ai_image_url`), `POST /api/player_ai_image_traits/<name>/` JSON `{phrases: [String]}` (signature look)
- `GET /api/players` includes `photoUrl`, `aiImageUrl`, `aiImageTraits`
- AI: `POST /api/ai/summary`, `GET /api/ai/recaps`, `GET /api/ai/jobs/<id>`, `GET /api/flyers`, `POST /api/flyers`, `DELETE /api/flyers/<share_id>`
- Existing `/api/parse_voice_doubles`, `/api/generate_and_send_ai_summary/`

## Admin (Bearer + is_admin)

- `GET /api/admin/overview`
- `GET /api/admin/activity?page=&q=&username=`
- `POST /api/admin/undo/<id>`
- `POST /api/admin/users`
- `POST /api/admin/users/reset_password`
- `POST /api/admin/users/toggle_active`
- `POST /api/admin/backup`
- `POST /api/admin/clear_cache`
- `POST /api/admin/test_email`
