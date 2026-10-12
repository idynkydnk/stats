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


HOURLY = 'weather_code,cloud_cover,precipitation,temperature_2m,wind_speed_10m,is_day'
WEATHER_CODES = {
    0: 'clear sky', 1: 'mainly clear', 2: 'partly cloudy', 3: 'overcast',
    45: 'fog', 48: 'freezing fog', 51: 'light drizzle', 53: 'drizzle',
    55: 'heavy drizzle', 56: 'freezing drizzle', 57: 'heavy freezing drizzle',
    61: 'light rain', 63: 'rain', 65: 'heavy rain', 66: 'freezing rain',
    67: 'heavy freezing rain', 71: 'light snow', 73: 'snow', 75: 'heavy snow',
    77: 'snow grains', 80: 'light rain showers', 81: 'rain showers',
    82: 'heavy rain showers', 85: 'snow showers', 86: 'heavy snow showers',
    95: 'thunderstorm', 96: 'thunderstorm with hail', 99: 'severe hailstorm',
}


def _get_json(url, params):
    response = requests.get(url, params=params, timeout=(3, 8))
    response.raise_for_status()
    return response.json()


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
    if location.casefold() in {'hermosa', 'hermosa beach', 'hermosa beach, ca',
                               'hermosa beach, california'}:
        search = 'Hermosa Beach, California'
    try:
        results = _get_json('https://geocoding-api.open-meteo.com/v1/search',
                            {'name': search, 'count': 5, 'language': 'en'}).get('results') or []
        # Do not silently pick a different or ambiguous city.
        city = search.split(',')[0].strip().casefold()
        matches = [row for row in results if str(row.get('name') or '').casefold() == city]
        if search == 'Hermosa Beach, California':
            matches = [row for row in matches if row.get('admin1') == 'California'
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
            timing = f'{day.isoformat()} at {when:%H:%M} ({zone})'
        else:
            # Date-only records cannot support a claim about a particular hour.
            indices = [i for i, value in enumerate(hours) if value[:10] == day.isoformat()]
            timing = f'{day.isoformat()} (game time not recorded; daily conditions only)'
        descriptions = []
        for i in indices:
            values = {key: (hourly.get(key) or [])[i] for key in HOURLY.split(',')}
            condition = WEATHER_CODES.get(values['weather_code'])
            if condition is None:
                continue
            bits = [condition]
            for key, label, unit in (
                ('cloud_cover', 'cloud cover', '%'), ('precipitation', 'precipitation', ' mm'),
                ('temperature_2m', 'temperature', '°F'), ('wind_speed_10m', 'wind', ' mph'),
            ):
                if values[key] is not None:
                    bits.append(f'{label} {values[key]}{unit}')
            if when and values['is_day'] in (0, 1):
                bits.append('daylight' if values['is_day'] else 'nighttime')
            # For date-only records, summarize the range of weather types;
            # there is no basis for selecting an exact hour or lighting.
            description = ', '.join(bits) if when else condition
            if description not in descriptions:
                descriptions.append(description)
        if not descriptions:
            raise ValueError('No weather available for the selected game time')
        return (
            f'Weather source: Open-Meteo, {place["name"]}, {place.get("admin1", "")}.\n'
            f'Picture setting: {timing}. Conditions: {"; ".join(descriptions)}.\n'
            'Match the sky, cloud cover, rain/fog, wind cues, clothing and lighting '
            'to these conditions. These conditions take precedence over generic '
            'sunny beach or sunset scenery and conflicting picture instructions. '
            'Do not print weather labels or invent weather-related game events. '
            'For multiple sessions, this setting represents the session with the most '
            'selected games (latest on ties).'
        )
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        logging.getLogger(__name__).warning('Recap weather unavailable for %s: %s', location, exc)
        return (f'Weather unavailable for {location} on {day.isoformat()}. '
                'Do not invent specific weather or claim it was verified. Use a neutral '
                'background without a prominent sunny sky, rain, fog, or sunset.')


def append_recap_weather(prompt, games):
    # Refresh our saved block on a remake rather than accumulating stale weather.
    prompt = re.sub(r'\n*\[RECAP WEATHER\].*?\[/RECAP WEATHER\]', '',
                    prompt, flags=re.DOTALL).strip()
    context = recap_weather_context(games)
    if context:
        prompt += f'\n\n[RECAP WEATHER]\n{context}\n[/RECAP WEATHER]'
    return prompt
