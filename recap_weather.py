"""Weather at the selected games, used only as illustration context.

Open-Meteo hourly data: https://open-meteo.com/en/docs and
https://open-meteo.com/en/docs/historical-weather-api
Stored game timestamps are local wall times in entered_timezone.
"""
from collections import defaultdict
from datetime import datetime, timezone
import logging
import re
from zoneinfo import ZoneInfo

import requests


HOURLY = 'weather_code,temperature_2m,wind_speed_10m,is_day'
WEATHER_CODES = {
    0: 'clear', 1: 'clear', 2: 'partly cloudy', 3: 'cloudy',
    45: 'foggy', 48: 'foggy', 51: 'rainy', 53: 'rainy',
    55: 'rainy', 56: 'rainy', 57: 'rainy',
    61: 'rainy', 63: 'rainy', 65: 'rainy', 66: 'rainy',
    67: 'rainy', 71: 'snowy', 73: 'snowy', 75: 'snowy',
    77: 'snowy', 80: 'rainy', 81: 'rainy',
    82: 'rainy', 85: 'snowy', 86: 'snowy',
    95: 'stormy', 96: 'stormy', 99: 'stormy',
}


def _get_json(url, params):
    response = requests.get(url, params=params, timeout=(3, 8))
    response.raise_for_status()
    return response.json()


def picture_location(location):
    """Expand known private venue names without guessing an address."""
    location = (location or '').strip()
    if location.casefold() == 'the oasis':
        return (
            "The Oasis, Tyler's house in Dunedin, Florida, with a beach volleyball "
            'court, a black volleyball net, a creek in the back, a pool, a mango '
            'tree, a banana tree, and court lights. For nighttime scenes, show '
            'the court lights illuminating the court; keep daytime scenes in daylight'
        )
    return location


def _selected_session(games):
    sessions = defaultdict(list)
    for game in games:
        location = str(game.get('location') or '').strip()
        raw = str(game.get('game_date') or '').strip()
        if not location or not raw:
            continue
        try:
            when = datetime.fromisoformat(raw)
        except ValueError:
            continue
        zone = game.get('entered_timezone') or ''
        sessions[(location, when.date(), zone)].append((when, len(raw) > 10))
    if not sessions:
        return None
    # One picture needs one coherent setting. Prefer the session with the most
    # selected games, breaking ties by latest date and then location.
    key = max(sessions, key=lambda key: (len(sessions[key]), key[1], key[0], key[2]))
    return key, sorted(sessions[key])


def recap_weather_context(games):
    session = _selected_session(games)
    if not session:
        return ''
    (location, day, entered_zone), times = session
    # Hermosa is a common local shorthand. Pin it to the requested California
    # city, rather than trusting a similarly named geocoding result elsewhere.
    search = location
    expected_state = None
    if location.casefold() == 'the oasis':
        # Search the known city, never the private venue's ambiguous name.
        search = 'Dunedin'
        expected_state = 'Florida'
    if location.casefold() in {'hermosa', 'hermosa beach', 'hermosa beach, ca',
                               'hermosa beach, california'}:
        search = 'Hermosa Beach, California'
        expected_state = 'California'
    try:
        results = _get_json('https://geocoding-api.open-meteo.com/v1/search',
                            {'name': search, 'count': 5, 'language': 'en'}).get('results') or []
        # Do not silently pick a different or ambiguous city.
        city = search.split(',')[0].strip().casefold()
        matches = [row for row in results if str(row.get('name') or '').casefold() == city]
        if expected_state:
            matches = [row for row in matches if row.get('admin1') == expected_state
                       and row.get('country_code') == 'US']
        if len(matches) != 1:
            raise ValueError('Location could not be resolved unambiguously')
        place = matches[0]
        zone = place['timezone']
        local_zone = ZoneInfo(zone)
        source_zone = ZoneInfo(entered_zone) if entered_zone else local_zone
        timed = [when.replace(tzinfo=source_zone).astimezone(local_zone)
                 if when.tzinfo is None else when.astimezone(local_zone)
                 for when, has_time in times if has_time]
        when = timed[len(timed) // 2] if timed else None
        if when:
            day = when.date()
        age = (datetime.now(timezone.utc).astimezone(local_zone).date() - day).days
        url = ('https://archive-api.open-meteo.com/v1/archive' if age > 5
               else 'https://api.open-meteo.com/v1/forecast')
        data = _get_json(url, {
            'latitude': place['latitude'], 'longitude': place['longitude'],
            'start_date': day.isoformat(), 'end_date': day.isoformat(),
            'timezone': zone, 'hourly': HOURLY,
            'temperature_unit': 'fahrenheit', 'wind_speed_unit': 'mph',
        })
        hourly = data.get('hourly') or {}
        hours = hourly.get('time') or []
        if when:
            target = when.strftime('%Y-%m-%dT%H:00')
            indices = [hours.index(target)] if target in hours else []
        else:
            # Date-only records cannot support a claim about a particular hour.
            indices = [i for i, value in enumerate(hours) if value[:10] == day.isoformat()]
        conditions, temperatures, winds = [], [], []
        for i in indices:
            values = {key: (hourly.get(key) or [])[i] for key in HOURLY.split(',')}
            condition = WEATHER_CODES.get(values['weather_code'])
            if condition is None:
                continue
            if when and condition == 'clear' and values['is_day'] == 1:
                condition = 'sunny'
            if condition not in conditions:
                conditions.append(condition)
            if values['temperature_2m'] is not None:
                temperatures.append(float(values['temperature_2m']))
            if values['wind_speed_10m'] is not None:
                winds.append(float(values['wind_speed_10m']))
            if when and values['is_day'] == 0:
                conditions.append('nighttime')
        if not conditions:
            raise ValueError('No weather available for the selected game time')
        if temperatures:
            low, high = min(temperatures), max(temperatures)
            conditions.append(f'{low:g}°F' if low == high else f'{low:g}–{high:g}°F')
        if winds and max(winds) >= 15:
            conditions.append(f'windy ({max(winds):g} mph)')
        label = 'Weather' if when else 'Daily weather (game time unknown)'
        return f'{label}: {", ".join(conditions)}.'
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        logging.getLogger(__name__).warning('Recap weather unavailable for %s: %s', location, exc)
        return 'Weather unavailable; use a neutral sky.'


def append_recap_weather(prompt, games):
    # Refresh our saved block on a remake rather than accumulating stale weather.
    prompt = re.sub(r'\n*\[RECAP WEATHER\].*?\[/RECAP WEATHER\]', '',
                    prompt, flags=re.DOTALL).strip()
    context = recap_weather_context(games)
    if context:
        prompt += f'\n\n[RECAP WEATHER]\n{context}\n[/RECAP WEATHER]'
    return prompt
