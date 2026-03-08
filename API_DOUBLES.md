# Doubles Games API (iPhone app sync)

Base URL: your server root (e.g. `https://yoursite.com`).

## Authentication

### Login (get token)

```http
POST /api/auth/login
Content-Type: application/json

{"username": "iosapp", "password": "your_password"}
```

Response (200):

```json
{"token": "long-secret-token", "username": "iosapp"}
```

Use the token in subsequent requests:

```http
Authorization: Bearer <token>
```

(You can also use the web session cookie if the client is browser-based.)

---

## List games (sync)

```http
GET /api/doubles/games
Authorization: Bearer <token>
```

Optional query params:

- **year** – e.g. `2025` or omit for all years.
- **since** – ISO8601 datetime (e.g. `2025-03-01T00:00:00`). Returns only games with `updated_at >= since` for incremental sync.

Response (200):

```json
{
  "games": [
    {
      "id": 1,
      "game_date": "2025-03-07 14:30:00",
      "winner1": "Alice",
      "winner2": "Bob",
      "winner_score": 21,
      "loser1": "Carol",
      "loser2": "Dan",
      "loser_score": 15,
      "updated_at": "2025-03-07 14:35:00",
      "comments": "",
      "entered_timezone": "America/Los_Angeles",
      "updated_by": "iosapp"
    }
  ]
}
```

`updated_by` is the username of whoever added or last edited the game.

---

## Get one game

```http
GET /api/doubles/games/<id>
Authorization: Bearer <token>
```

Response (200): single game object as above. (404 if not found.)

---

## Create game

```http
POST /api/doubles/games
Content-Type: application/json
Authorization: Bearer <token>

{
  "game_date": "2025-03-07 14:30:00",
  "winner1": "Alice",
  "winner2": "Bob",
  "loser1": "Carol",
  "loser2": "Dan",
  "winner_score": 21,
  "loser_score": 15,
  "comments": "",
  "entered_timezone": "America/Los_Angeles"
}
```

- **game_date** – required; use `YYYY-MM-DD HH:MM:SS` or ISO8601.
- **winner1, winner2, loser1, loser2** – required; all four must be unique.
- **winner_score, loser_score** – required integers; winner_score must be &gt; loser_score.
- **comments**, **entered_timezone** – optional.

Response (201): full game object including `id` and `updated_by` (set to the authenticated user).

---

## Update game

```http
PUT /api/doubles/games/<id>
Content-Type: application/json
Authorization: Bearer <token>

{
  "game_date": "2025-03-07 14:30:00",
  "winner1": "Alice",
  "winner2": "Bob",
  "loser1": "Carol",
  "loser2": "Dan",
  "winner_score": 21,
  "loser_score": 15,
  "comments": "optional"
}
```

Same field rules as create. Omitted fields keep existing values. `updated_at` and `updated_by` are set by the server.

Response (200): full updated game object.

---

## Delete game

```http
DELETE /api/doubles/games/<id>
Authorization: Bearer <token>
```

Response (200): `{"message": "Deleted", "id": <id>}`. (404 if not found.)

---

## Sync flow (iPhone app)

1. **Login** once; store `token` (e.g. in Keychain).
2. **Full sync**: `GET /api/doubles/games` (no query) to get all games; replace or merge into local DB.
3. **Incremental sync**: store last sync time; then `GET /api/doubles/games?since=<last_sync_iso>` to get only games updated since then; apply creates/updates locally. Deletes are not inferred (you can track deleted IDs from a previous response or use a separate strategy).
4. **Push changes**: use `POST` to create and `PUT` / `DELETE` for edits; then run incremental sync to get server state including `updated_by` and `updated_at`.

All mutation endpoints set `updated_by` to the authenticated username so you can show “who updated” in the app.
