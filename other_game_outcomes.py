"""Explicit outcomes for games whose result may be a tie."""


def ensure_other_game_outcome_column(conn):
    """Keep legacy rows decisive when upgrading a writable game database."""
    columns = {row[1] for row in conn.execute('PRAGMA table_info(other_games)')}
    if columns and 'is_tie' not in columns:
        conn.execute('ALTER TABLE other_games ADD COLUMN is_tie INTEGER NOT NULL DEFAULT 0')


def parse_is_tie(value):
    """Accept flags from HTML forms, JSON, and SQLite without treating '0' as true."""
    if value is None or value is False or value == 0:
        return False
    if value is True or value == 1:
        return True
    if isinstance(value, str):
        value = value.strip().lower()
        if value in ('', '0', 'false', 'off', 'no'):
            return False
        if value in ('1', 'true', 'on', 'yes'):
            return True
    raise ValueError('Choose a win/loss result or a tie.')


def is_tied_game(game):
    """Legacy records are decisive unless a tie was explicitly saved."""
    return parse_is_tie(dict(game).get('is_tie', False))


def validate_tie_game_type(is_tie, game_type):
    if parse_is_tie(is_tie) and 'volleyball' in str(game_type or '').casefold():
        raise ValueError('Volleyball games need a winner and a loser; they cannot end in a tie.')


def validate_tie_scores(is_tie, score_type, winner_scores, loser_scores,
                        team_winner_score=None, team_loser_score=None):
    """Keep the selected outcome consistent with supplied scores."""
    is_tie = parse_is_tie(is_tie)
    if score_type == 'none' or (not is_tie and score_type != 'team'):
        return
    scores = ([team_winner_score, team_loser_score] if score_type == 'team'
              else list(winner_scores or []) + list(loser_scores or []))
    supplied = [score for score in scores if score not in (None, '')]
    if not supplied:
        return
    if is_tie and score_type == 'team' and len(supplied) != 2:
        raise ValueError('Enter the same score for both sides of a tie, or choose No Scores.')
    try:
        values = [int(score) for score in supplied]
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Enter whole-number scores.') from None
    if any(isinstance(score, float) and score != value for score, value in zip(supplied, values)):
        raise ValueError('Enter whole-number scores.')
    if not is_tie and len(values) == 2 and values[0] == values[1]:
        raise ValueError('A win/loss result needs different team scores.')
    if is_tie and len(set(values)) > 1:
        raise ValueError('A tie needs equal scores. Enter matching scores or choose Win/loss.')
