from datetime import datetime, timedelta, timezone
import io
import json
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
from patrick.weather import WeatherTools, weather_from_env


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 14, 18, 25, tzinfo=timezone.utc)
        self.calls = []
        self.results = [{'name': 'Bengaluru', 'admin1': 'Karnataka', 'country': 'India',
                         'country_code': 'IN', 'latitude': 12.97, 'longitude': 77.59}]
        self.tool = WeatherTools(opener=self.open, now=lambda: self.now)

    def open(self, request, timeout):
        self.calls.append(request.full_url)
        query = parse_qs(urlparse(request.full_url).query)
        if '/search?' in request.full_url:
            data = {'results': self.results}
        else:
            date = (self.now + timedelta(seconds=19800)).date()
            count = int(query['forecast_days'][0])
            data = {'timezone': 'Asia/Kolkata', 'utc_offset_seconds': 19800,
                'daily': {'time': [(date + timedelta(days=i)).isoformat() for i in range(count)],
                    'weather_code': [2] * count, 'temperature_2m_max': [29] * count,
                    'temperature_2m_min': [20] * count, 'precipitation_probability_max': [0] * count,
                    'wind_speed_10m_max': [12] * count},
                'current': {'time': date.isoformat() + 'T23:45', 'temperature_2m': 24,
                    'weather_code': 2, 'apparent_temperature': 25, 'relative_humidity_2m': 60,
                    'wind_speed_10m': 5, 'precipitation': 0}}
        return io.BytesIO(json.dumps(data).encode())

    def lookup(self, **args):
        return self.tool.execute('weather_lookup', args, threading.Event())

    def test_no_location_asks_without_network(self):
        self.assertEqual(self.lookup(location='')['status'], 'needs_location')
        self.assertEqual(self.calls, [])

    def test_current_weather_has_location_time_and_zero_rain(self):
        result = self.lookup(location='Bengaluru, Karnataka')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['location'], 'Bengaluru, Karnataka, India')
        self.assertEqual(result['current']['temperature'], 24)
        self.assertEqual(result['current']['conditions'], 'partly cloudy')
        self.assertEqual(result['forecast'][0]['rain_probability_percent'], 0)
        self.assertEqual(result['timezone'], 'Asia/Kolkata')

    def test_tomorrow_uses_location_date_and_week_has_seven_days(self):
        self.now = datetime(2026, 10, 14, 23, tzinfo=timezone.utc)  # Already Oct 15 in India.
        tomorrow = self.lookup(location='Bengaluru', period='tomorrow')
        self.assertEqual(tomorrow['forecast'][0]['date'], '2026-10-16')
        self.assertNotIn('current', tomorrow)
        week = self.lookup(location='Bengaluru', period='week')
        self.assertEqual(len(week['forecast']), 7)

    def test_ambiguous_location_does_not_fetch_weather(self):
        self.results += [{**self.results[0], 'admin1': 'Another State', 'latitude': 10}]
        result = self.lookup(location='Bengaluru')
        self.assertEqual(result['status'], 'ambiguous')
        self.assertEqual(len(result['candidates']), 2)
        self.assertEqual(len(self.calls), 1)

    def test_unknown_location_is_not_guessed(self):
        self.results = []
        self.assertEqual(self.lookup(location='Unknown')['status'], 'not_found')
        self.assertEqual(len(self.calls), 1)

    def test_units_and_country_are_forwarded(self):
        result = self.lookup(location='Bengaluru', units='imperial', country_code='in')
        self.assertEqual(result['units']['temperature'], '°F')
        self.assertIn('countryCode=IN', self.calls[0])
        self.assertIn('temperature_unit=fahrenheit', self.calls[1])
        self.assertIn('wind_speed_unit=mph', self.calls[1])

    def test_cache_and_midnight_refresh(self):
        first = self.lookup(location='Bengaluru')
        second = self.lookup(location='Bengaluru')
        self.assertFalse(first['cached'])
        self.assertTrue(second['cached'])
        self.assertEqual(len(self.calls), 2)
        self.now += timedelta(minutes=10)  # New local day, even within the monotonic TTL.
        refreshed = self.lookup(location='Bengaluru')
        self.assertFalse(refreshed['cached'])
        self.assertEqual(len(self.calls), 3)

    def test_invalid_arguments_make_no_request(self):
        for args in ({'location': 5}, {'location': 'Berlin', 'period': 'yesterday'},
                     {'location': 'Berlin', 'country_code': 'IND'}, {'location': 'Berlin', 'secret': 'x'}):
            self.assertIn('error', self.tool.execute('weather_lookup', args, threading.Event()))
        self.assertEqual(self.calls, [])

    def test_cancellation_before_or_during_request(self):
        cancelled = threading.Event()
        cancelled.set()
        self.assertIn('cancelled', self.tool.execute('weather_lookup', {'location': 'Berlin'}, cancelled)['error'])
        self.assertEqual(self.calls, [])
        cancelled.clear()
        def register(stream):
            if stream is not None:
                cancelled.set()
        self.assertIn('cancelled', self.tool.execute('weather_lookup', {'location': 'Berlin'}, cancelled, register)['error'])
        self.assertEqual(len(self.calls), 1)

    def test_timeout_does_not_reveal_key_or_cache_failure(self):
        self.tool.api_key = 'private-test-key'
        with patch.object(self.tool, 'opener', side_effect=TimeoutError('private-test-key')):
            result = self.lookup(location='Bengaluru')
        self.assertIn('error', result)
        self.assertNotIn('private-test-key', json.dumps(result))
        self.assertEqual(self.tool.cache, {})

    def test_customer_endpoints_and_key(self):
        self.tool.api_key = 'test-commercial-key'
        self.lookup(location='Bengaluru')
        self.assertEqual(urlparse(self.calls[0]).hostname, 'customer-geocoding-api.open-meteo.com')
        self.assertEqual(urlparse(self.calls[1]).hostname, 'customer-api.open-meteo.com')
        self.assertIn('apikey=test-commercial-key', self.calls[1])

    def test_weather_independent_of_web_search_and_can_be_disabled(self):
        with patch.dict('os.environ', {'WEATHER_ENABLED': 'true', 'WEATHER_DEFAULT_CITY': '',
                                      'OPEN_METEO_API_KEY': '', 'WEB_SEARCH_ENABLED': 'false'}):
            self.assertIsInstance(weather_from_env(), WeatherTools)
        with patch.dict('os.environ', {'WEATHER_ENABLED': 'false'}):
            sentinel = object()
            self.assertIs(weather_from_env(sentinel), sentinel)

    def test_delegates_existing_tools_unchanged(self):
        class Other:
            schemas = []
            def execute(self, *args): return {'existing': True}
        self.assertEqual(WeatherTools(Other()).execute('web_search', '{}', threading.Event()), {'existing': True})

    def test_stale_or_missing_current_weather_is_rejected(self):
        data = json.loads(self.open(type('Request', (), {'full_url': 'https://api.open-meteo.com/v1/forecast?forecast_days=1'})(), 8).getvalue())
        data['current']['temperature_2m'] = None
        with self.assertRaises(ValueError):
            self.tool._result(data, {'label': 'Bengaluru'}, 'current', 'metric')
        data['daily']['time'] = ['2020-01-01']
        with self.assertRaises(ValueError):
            self.tool._result(data, {'label': 'Bengaluru'}, 'today', 'metric')
