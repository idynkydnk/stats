# Balloono

Multiplayer Balloono-inspired game built with Flask and long-polling. Clone and run locally or deploy to PythonAnywhere.

## Run locally

```shell
git clone https://github.com/PrometheusPrograms/balloono.git
cd balloono
python -m venv .venv
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in your browser.

## How to play

1. Register or log in
2. Create a room or join an existing one
3. Share the room code with a friend
4. Move around the lobby with arrow keys
5. Click "Start Balloono" when ready (1 or 2 players)
6. Arrow keys to move, Space to drop balloons
7. Power-ups: 💧 bigger splash, 🎈 more balloons, ⚡ faster moves

## Configuration

- `SECRET_KEY`: Flask session secret (set in production)
- `DATABASE_URL`: e.g. `sqlite:///balloono.db` (default)
- `PORT`: Port to run on (default 5000)
- `FLASK_DEBUG`: Set to `1` for debug mode

## Deploy to PythonAnywhere

1. Clone this repo to your account
2. Create a virtualenv and install requirements
3. Set WSGI to load `app.app`
4. Add static files mapping: `/static/` → `.../balloono/static/`
