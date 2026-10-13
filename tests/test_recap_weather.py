from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import requests

from recap_weather import append_recap_weather, recap_weather_context
from email_content import generate_email_hero_image, _try_generate_email_hero_image


PLACE = {'name': 'Hermosa Beach', 'admin1': 'California', 'country_code': 'US',
         'latitude': 33.86, 'longitude': -118.4, 'timezone': 'America/Los_Angeles'}


def weather(day='2020-06-01', hour=15):
    return {'hourly': {'time': [f'{day}T{hour:02d}:00'], 'weather_code': [3],
                       'cloud_cover': [100], 'precipitation': [0], 'temperature_2m': [64],
                       'wind_speed_10m': [12], 'is_day': [int(6 <= hour < 20)]}}


def game(date='2020-06-01 15:30:00', location='Hermosa Beach', zone='America/Los_Angeles'):
    return {'game_date': date, 'location': location, 'entered_timezone': zone}


class RecapWeatherTests(unittest.TestCase):
    @patch('recap_weather._get_json')
    def test_historical_weather_uses_hermosa_and_game_hour(self, get):
        get.side_effect = [{'results': [PLACE]}, weather()]
        result = recap_weather_context([game()])
        self.assertEqual(get.call_args_list[0].args[1]['name'], 'Hermosa Beach, California')
        self.assertIn('archive-api', get.call_args.args[0])
        params = get.call_args.args[1]
        self.assertEqual(params['start_date'], '2020-06-01')
        self.assertEqual(params['latitude'], PLACE['latitude'])
        self.assertIn('overcast', result)
        self.assertIn('cloud cover 100%', result)
        self.assertIn('15:30', result)
        self.assertIn('daylight', result)

    @patch('recap_weather._get_json')
    def test_recent_weather_uses_forecast_endpoint(self, get):
        today = datetime.now(timezone.utc).date().isoformat()
        get.side_effect = [{'results': [PLACE]}, weather(today)]
        self.assertIn('overcast', recap_weather_context([game(today + ' 15:00:00')]))
        self.assertIn('api.open-meteo.com/v1/forecast', get.call_args.args[0])

    @patch('recap_weather._get_json')
    def test_converts_entry_timezone_to_location_time_and_date(self, get):
        get.side_effect = [{'results': [PLACE]}, weather(hour=22)]
        result = recap_weather_context([game('2020-06-02 05:30:00', zone='UTC')])
        self.assertEqual(get.call_args.args[1]['start_date'], '2020-06-01')
        self.assertIn('22:30', result)
        self.assertIn('nighttime', result)

    @patch('recap_weather._get_json')
    def test_date_only_does_not_invent_game_time(self, get):
        get.side_effect = [{'results': [PLACE]}, weather()]
        result = recap_weather_context([game('2020-06-01')])
        self.assertIn('game time not recorded', result)
        self.assertNotIn('daylight', result)
        self.assertIn('overcast', result)

    @patch('recap_weather._get_json')
    def test_multiple_locations_use_one_real_session(self, get):
        get.side_effect = [{'results': [PLACE]}, weather(hour=16)]
        result = recap_weather_context([game(), game('2020-06-01 16:00:00'),
                                       game('2020-06-02 13:00:00', 'Boston')])
        self.assertIn('overcast', result)
        self.assertEqual(get.call_args_list[0].args[1]['name'], 'Hermosa Beach, California')
        self.assertEqual(get.call_args.args[1]['start_date'], '2020-06-01')

    @patch('recap_weather._get_json')
    def test_missing_location_skips_lookup(self, get):
        self.assertEqual(recap_weather_context([game(location='')]), '')
        get.assert_not_called()

    @patch('recap_weather._get_json')
    def test_failure_and_ambiguous_city_never_invent_weather(self, get):
        for answer in (requests.Timeout(), {'results': []},
                       {'results': [PLACE, PLACE]}):
            with self.subTest(answer=answer):
                get.side_effect = [answer]
                self.assertIn('Weather unavailable', recap_weather_context([game()]))

    @patch('recap_weather.recap_weather_context', return_value='New weather')
    def test_remake_replaces_saved_weather(self, lookup):
        result = append_recap_weather('Scene\n[RECAP WEATHER]\nOld weather\n[/RECAP WEATHER]', [game()])
        self.assertNotIn('Old weather', result)
        self.assertEqual(result.count('[RECAP WEATHER]'), 1)
        self.assertIn('New weather', result)

    @patch('recap_weather.recap_weather_context')
    def test_text_only_does_not_lookup_weather(self, lookup):
        _try_generate_email_hero_image('key', 'doubles', [], [], image_mode='none', weather_games=[game()])
        lookup.assert_not_called()

    def test_default_and_custom_images_receive_weather_and_safe_reference_names(self):
        for custom in (None, 'Draw Alex Smith at sunset.'):
            with (
                self.subTest(custom=custom),
                patch('email_content.filter_illustratable_players', return_value=['Alex Smith']),
                patch('player_functions.player_display_name', return_value='Ace'),
                patch('email_content._image_labels_for_players', return_value={'Alex Smith': 'Ace'}),
                patch('email_content._reference_parts_from_uploaded_photos', return_value=(
                    [{'text': 'Alex Smith: Ace', 'image_name': 'Alex Smith'}], ['Alex Smith'])),
                patch('recap_weather.recap_weather_context', return_value='Overcast, 100% clouds.') as lookup,
                patch('recap_visuals.extract_visual_checklist', return_value=[]),
                patch('email_content._generate_image_bytes', return_value=(b'img', 'image/png')) as generate,
                patch('email_content._normalize_image_bytes_to_aspect', return_value=(b'img', 'image/png')),
                patch('email_content._save_email_image', return_value=('url', 'path')),
            ):
                result = generate_email_hero_image('key', 'doubles', [], ['Alex Smith'],
                                                   custom_scene_prompt=custom, weather_games=[game()])
                lookup.assert_called_once_with([game()])
                self.assertIn('Overcast', generate.call_args.args[0])
                self.assertNotIn('Alex Smith', str(generate.call_args))
                self.assertNotIn('Alex Smith', result[2] + result[4])


if __name__ == '__main__':
    unittest.main()
