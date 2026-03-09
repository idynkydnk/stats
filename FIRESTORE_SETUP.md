# Firestore dual-write (doubles games)

When you add, edit, or delete a doubles game on the web app, the same change is written to Firestore so your iPhone app stays in sync.

## Setup

1. **Key file**  
   Put your Firebase service account JSON in the `stats` folder (you already did this). The code will find any file whose name contains `firebase` and `adminsdk` and ends in `.json`.

2. **Optional: env var**  
   To use a specific path (e.g. on PythonAnywhere), set:
   ```bash
   GOOGLE_APPLICATION_CREDENTIALS=/full/path/to/your-key.json
   ```

3. **Collection name**  
   Games are written to the **`doubles_games`** collection. To match a different collection used by your iPhone app, set:
   ```bash
   FIRESTORE_DOUBLES_COLLECTION=your_collection_name
   ```

4. **Document ID**  
   Each game is stored as a document with ID = the SQLite game `id` (e.g. `"9264"`). Your iPhone app can use this same ID to read/update.

5. **Fields**  
   Each document has: `id`, `game_date`, `winner1`, `winner2`, `winner_score`, `loser1`, `loser2`, `loser_score`, `updated_at`, `comments`, `entered_timezone`, `updated_by`. Dates are ISO strings.

If the key is missing or Firebase isn’t configured, the web app still works; Firestore writes are skipped.
