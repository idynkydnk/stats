import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from other_functions import add_other_stats

DATA_FILE = Path("data/gin_rummy_games.txt")
GAME_TYPE = "Card games"
GAME_NAME = "Gin Rummy"


def normalize_date_token(token: str, year_hint: Optional[int]) -> Tuple[datetime, int]:
    token = token.strip()
    if not token:
        raise ValueError("Empty date token")
    parts = token.split('/')

    if len(parts) == 3:
        month, day, year = parts
    elif len(parts) == 2:
        left, right = parts
        if len(left) > 2 and left.isdigit() and len(right) == 2:
            month = left[:-2]
            day = left[-2:]
            year = right
        else:
            month = left
            day = right
            if year_hint is None:
                raise ValueError(f"Missing year context for token '{token}'")
            year = f"{year_hint % 100:02d}"
    else:
        raise ValueError(f"Unrecognized date token '{token}'")

    month = int(month)
    day = int(day)
    year_int = int(year) if len(year) == 2 else int(year[-2:])
    resolved = datetime(year=2000 + year_int, month=month, day=day)
    return resolved, resolved.year


def parse_player_line(line: str) -> Optional[Tuple[str, int]]:
    tokens = line.split()
    name_tokens = []
    numbers = []
    started_numbers = False

    for token in tokens:
        clean = token.rstrip(':')
        match = re.search(r'-?\d+', clean)
        if match:
            started_numbers = True
            numbers.append(int(match.group()))
        elif not started_numbers:
            name_tokens.append(clean)

    if not name_tokens or not numbers:
        return None

    name = ' '.join(name_tokens).strip()
    if not name:
        return None
    return name, numbers[-1]


def load_sections(raw_text: str) -> list[dict]:
    sections = []
    current = None

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower() in {"gin rummy", "card games"}:
            continue

        header_match = re.match(r'(?:(?P<date>[\d/]+)\s+)?winner\s+(?P<winner>.+)', line, re.IGNORECASE)
        if header_match:
            if current:
                sections.append(current)
            current = {
                "header": line,
                "date_token": header_match.group('date'),
                "winner": header_match.group('winner').strip(),
                "lines": [],
            }
        elif current:
            current['lines'].append(line)
        else:
            raise ValueError(f"Data line before header: {line}")

    if current:
        sections.append(current)
    return sections


def assign_dates(sections: list[dict]) -> None:
    last_date = None
    last_year = None

    for section in sections:
        token = section.get('date_token')
        if token:
            resolved, last_year = normalize_date_token(token, last_year)
            last_date = resolved
            section['resolved_date'] = resolved
        else:
            if last_date is None:
                raise ValueError("Undated game encountered before any dated games.")
            last_date = last_date - timedelta(days=1)
            section['resolved_date'] = last_date


def parse_players(section: dict) -> Optional[Tuple[list[str], list[int], list[str], list[int], str]]:
    player_entries = []
    comments = []

    for line in section['lines']:
        if any(ch.isdigit() for ch in line):
            entry = parse_player_line(line)
            if entry:
                player_entries.append(entry)
        else:
            if len(line.split()) > 2:
                comments.append(line)

    if not player_entries:
        return None

    winner_name = section['winner'].lower()
    winner_entry = next((p for p in player_entries if p[0].lower() == winner_name), None)
    if not winner_entry:
        raise ValueError(f"Winner '{section['winner']}' not found in section '{section['header']}'")

    winners = [winner_entry[0]]
    winner_scores = [winner_entry[1]]
    losers = [name for name, _ in player_entries if name.lower() != winner_name]
    loser_scores = [score for name, score in player_entries if name.lower() != winner_name]

    if not losers:
        raise ValueError(f"No losers found for section '{section['header']}'")

    return winners, winner_scores, losers, loser_scores, ' / '.join(comments)


def game_exists(conn: sqlite3.Connection, game_date: datetime, winner: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(1) FROM other_games WHERE date(game_date)=? AND winner1=? AND game_name=?",
        (game_date.date().isoformat(), winner, GAME_NAME),
    )
    return cur.fetchone()[0] > 0


def main():
    raw_text = DATA_FILE.read_text()
    sections = load_sections(raw_text)
    assign_dates(sections)

    conn = sqlite3.connect('stats.db')
    inserted = 0
    skipped = 0

    for section in reversed(sections):
        parsed = parse_players(section)
        if not parsed:
            skipped += 1
            continue
        winners, winner_scores, losers, loser_scores, comment = parsed
        game_date = section['resolved_date']
        game_datetime = datetime.combine(game_date.date(), datetime.min.time())

        if game_exists(conn, game_datetime, winners[0]):
            skipped += 1
            continue

        add_other_stats(
            game_datetime,
            GAME_TYPE,
            GAME_NAME,
            winners,
            winner_scores,
            losers,
            loser_scores,
            comment,
            datetime.now()
        )
        inserted += 1

    conn.close()
    print(f"Imported {inserted} games ({skipped} skipped).")


if __name__ == '__main__':
    main()
