"""Format game date/time for display, optionally with timezone abbreviation."""
from datetime import datetime

def format_game_time(datetime_str, timezone_name=None):
    """Format a stored game_date string for display.
    If timezone_name is set (e.g. 'America/Los_Angeles'), append abbreviation like (PST).
    Stored time is treated as local time in that zone for the abbreviation.
    """
    if not datetime_str:
        return ''
    s = datetime_str.strip()
    dt_naive = None
    try:
        dt_naive = datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        try:
            dt_naive = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                dt_naive = datetime.strptime(s[:10], "%Y-%m-%d")
            except ValueError:
                return datetime_str
    has_time = len(s) > 10 and ' ' in s
    if timezone_name and has_time:
        try:
            from zoneinfo import ZoneInfo
            dt_aware = dt_naive.replace(tzinfo=ZoneInfo(timezone_name))
            return dt_aware.strftime("%m/%d/%Y %I:%M %p") + " (" + dt_aware.strftime("%Z") + ")"
        except Exception:
            pass
    if timezone_name and not has_time:
        try:
            from zoneinfo import ZoneInfo
            abbr = datetime.now(ZoneInfo(timezone_name)).strftime("%Z")
            return dt_naive.strftime("%m/%d/%y") + " (" + abbr + ")"
        except Exception:
            pass
    if has_time:
        return dt_naive.strftime("%m/%d/%Y %I:%M %p")
    return dt_naive.strftime("%m/%d/%y")
