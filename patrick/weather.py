"""Open-Meteo weather lookup; no LLM, location inference, or extra dependencies."""
from datetime import datetime, timedelta, timezone
import json
import math
import os
import re
import threading
import time
import urllib.request
from urllib.parse import urlencode

WEATHER_SCHEMA = {'type': 'function', 'function': {
    'name': 'weather_lookup',
    'description': 'Get current weather or today/tomorrow/7-day forecasts from Open-Meteo. Use a user-specified city, preferably with state/country. Empty location uses the configured default or asks for a city. Clarify ambiguous locations; never infer user location.',
    'parameters': {'type': 'object', 'properties': {
        'location': {'type': 'string'},
        'period': {'type': 'string', 'enum': ['current', 'today', 'tomorrow', 'week']},
        'units': {'type': 'string', 'enum': ['metric', 'imperial']},
        'country_code': {'type': 'string', 'description': 'Optional two-letter country filter'}},
        'required': ['location'], 'additionalProperties': False}}}

CONDITIONS = {0: 'clear', 1: 'mostly clear', 2: 'partly cloudy', 3: 'overcast',
    45: 'fog', 48: 'freezing fog', 51: 'light drizzle', 53: 'moderate drizzle',
    55: 'dense drizzle', 56: 'light freezing drizzle', 57: 'dense freezing drizzle',
    61: 'light rain', 63: 'moderate rain', 65: 'heavy rain', 66: 'light freezing rain',
    67: 'heavy freezing rain', 71: 'light snow', 73: 'moderate snow', 75: 'heavy snow',
    77: 'snow grains', 80: 'light rain showers', 81: 'moderate rain showers',
    82: 'violent rain showers', 85: 'light snow showers', 86: 'heavy snow showers',
    95: 'thunderstorm', 96: 'thunderstorm with light hail', 99: 'thunderstorm with heavy hail'}


class WeatherCancelled(Exception):
    pass


def number(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Invalid weather value')
    return value


class WeatherTools:
    def __init__(self, other=None, default_city='', units='metric', timeout=8, cache_seconds=600,
                 api_key='', opener=None, now=None):
        if units not in ('metric', 'imperial') or not 0 < timeout <= 30 or not math.isfinite(timeout):
            raise ValueError('Weather units must be metric/imperial; timeout must be 0–30 seconds.')
        if not math.isfinite(cache_seconds) or not 0 <= cache_seconds <= 3600:
            raise ValueError('Weather cache must be 0–3600 seconds.')
        self.other, self.default_city, self.units = other, default_city.strip(), units
        self.timeout, self.cache_seconds, self.api_key = timeout, cache_seconds, api_key
        self.opener = opener or urllib.request.urlopen
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.schemas = list(getattr(other, 'schemas', [])) + [WEATHER_SCHEMA]
        self.cache, self.places = {}, {}
        self.lock = threading.Lock()

    def _get(self, url, parameters, cancelled, register_stream):
        if cancelled.is_set():
            raise WeatherCancelled()
        if self.api_key:
            parameters = {**parameters, 'apikey': self.api_key}
        request = urllib.request.Request(url + '?' + urlencode(parameters),
            headers={'User-Agent': 'Revobots-Weather/1.0', 'Accept': 'application/json'})
        try:
            with self.opener(request, timeout=self.timeout) as response:
                register_stream(response)
                raw = response.read(262145)
                if cancelled.is_set():
                    raise WeatherCancelled()
                if len(raw) > 262144:
                    raise ValueError('Weather response too large')
                data = json.loads(raw)
                if not isinstance(data, dict) or data.get('error'):
                    raise ValueError('Weather provider error')
                return data
        finally:
            register_stream(None)

    def _location(self, location, country, cancelled, register_stream):
        key = (location.casefold(), country)
        with self.lock:
            entry = self.places.get(key)
            if entry and time.monotonic() - entry[0] < 86400:
                return entry[1]
        parameters = {'name': location, 'count': 10, 'language': 'en', 'format': 'json'}
        if country:
            parameters['countryCode'] = country
        host = 'customer-geocoding-api.open-meteo.com' if self.api_key else 'geocoding-api.open-meteo.com'
        data = self._get('https://' + host + '/v1/search', parameters, cancelled, register_stream)
        places = []
        labels = set()
        for item in data.get('results', []):
            if not isinstance(item, dict):
                raise ValueError('Invalid geocoding response')
            lat, lon = number(item.get('latitude')), number(item.get('longitude'))
            if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                continue
            if country and str(item.get('country_code') or '').upper() != country:
                continue
            label = ', '.join(dict.fromkeys(str(item[k]) for k in ('name', 'admin2', 'admin1', 'country') if item.get(k)))
            if label.casefold() in labels:
                continue
            labels.add(label.casefold())
            places.append({'name': str(item.get('name', '')), 'label': label,
                           'latitude': lat, 'longitude': lon})
        # Exact city names outrank API prefix matches, without picking between distinct exact matches.
        city = location.split(',', 1)[0].strip().casefold()
        exact = [p for p in places if p['name'].casefold() == city]
        places = exact or places
        with self.lock:
            self.places[key] = (time.monotonic(), places)
            while len(self.places) > 64:
                self.places.pop(next(iter(self.places)))
        return places

    def execute(self, name, arguments, cancelled, register_stream=lambda stream: None):
        if name != 'weather_lookup':
            return self.other.execute(name, arguments, cancelled, register_stream) if self.other else {'error': 'Unknown tool'}
        if cancelled.is_set():
            return {'error': 'Weather lookup cancelled'}
        try:
            if isinstance(arguments, str):
                if len(arguments) > 4096:
                    raise ValueError()
                arguments = json.loads(arguments)
            if not isinstance(arguments, dict) or set(arguments) - {'location', 'period', 'units', 'country_code'}:
                raise ValueError()
            location = arguments.get('location', '')
            period, units = arguments.get('period', 'current'), arguments.get('units', self.units)
            country = arguments.get('country_code', '')
            if not isinstance(location, str) or len(location) > 200 or not isinstance(country, str):
                raise ValueError()
            country = country.strip().upper()
            if country and not re.fullmatch('[A-Z]{2}', country):
                raise ValueError()
            if period not in ('current', 'today', 'tomorrow', 'week') or units not in ('metric', 'imperial'):
                raise ValueError()
            location = location.strip() or self.default_city
        except (ValueError, TypeError):
            return {'error': 'Invalid weather arguments: location, period, units or country_code.'}
        if not location:
            return {'status': 'needs_location', 'message': 'Ask which city. Do not infer location or use another tool to guess.'}
        try:
            places = self._location(location, country, cancelled, register_stream)
            if not places:
                return {'status': 'not_found', 'message': 'No matching city. Ask for the city and state/country.'}
            if len(places) != 1:
                return {'status': 'ambiguous', 'message': 'Ask which location the user means.',
                        'candidates': [p['label'] for p in places[:5]]}
            place = places[0]
            key = (place['latitude'], place['longitude'], period, units)
            with self.lock:
                entry = self.cache.get(key)
                if entry and time.monotonic() - entry[0] < self.cache_seconds:
                    cached = entry[1]
                    today = (self.now() + timedelta(seconds=cached['utc_offset_seconds'])).date().isoformat()
                    if today == cached['local_date']:
                        return {**cached, 'cached': True}
            days = 7 if period == 'week' else 2 if period == 'tomorrow' else 1
            parameters = {'latitude': place['latitude'], 'longitude': place['longitude'], 'timezone': 'auto',
                'forecast_days': days, 'temperature_unit': 'fahrenheit' if units == 'imperial' else 'celsius',
                'wind_speed_unit': 'mph' if units == 'imperial' else 'kmh',
                'precipitation_unit': 'inch' if units == 'imperial' else 'mm',
                'daily': 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max'}
            if period == 'current':
                parameters['current'] = 'temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation'
            host = 'customer-api.open-meteo.com' if self.api_key else 'api.open-meteo.com'
            data = self._get('https://' + host + '/v1/forecast', parameters, cancelled, register_stream)
            result = self._result(data, place, period, units)
            with self.lock:
                self.cache[key] = (time.monotonic(), result)
                while len(self.cache) > 64:
                    self.cache.pop(next(iter(self.cache)))
            return result
        except WeatherCancelled:
            return {'error': 'Weather lookup cancelled'}
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            return {'error': 'Weather is unavailable or timed out. Say you could not get fresh weather; do not guess.'}

    def _result(self, data, place, period, units):
        daily = data['daily']
        times = daily['time']
        if not isinstance(times, list) or len(times) < (7 if period == 'week' else 2 if period == 'tomorrow' else 1):
            raise ValueError('Incomplete forecast')
        local_date = (self.now() + timedelta(seconds=number(data['utc_offset_seconds']))).date().isoformat()
        if times[0] != local_date:
            raise ValueError('Stale forecast')
        result = {'status': 'ok', 'provider': 'Open-Meteo', 'source_url': 'https://open-meteo.com/',
            'location': place['label'], 'timezone': data['timezone'], 'utc_offset_seconds': data['utc_offset_seconds'],
            'local_date': local_date, 'retrieved_at': self.now().isoformat(), 'cached': False,
            'units': {'temperature': '°F' if units == 'imperial' else '°C',
                      'wind': 'mph' if units == 'imperial' else 'km/h',
                      'precipitation': 'in' if units == 'imperial' else 'mm'},
            'forecast': [], 'note': 'Weather model estimates, not a local sensor. Null values are unavailable.'}
        selected = range(7) if period == 'week' else [1] if period == 'tomorrow' else [0]
        for i in selected:
            code = number(daily['weather_code'][i])
            result['forecast'].append({'date': times[i], 'conditions': CONDITIONS.get(code, 'unknown'),
                'temperature_high': number(daily['temperature_2m_max'][i]),
                'temperature_low': number(daily['temperature_2m_min'][i]),
                'rain_probability_percent': number(daily['precipitation_probability_max'][i]),
                'wind_max': number(daily['wind_speed_10m_max'][i])})
        if period == 'current':
            current = data['current']
            code, temp = number(current.get('weather_code')), number(current.get('temperature_2m'))
            if code is None or temp is None:
                raise ValueError('Missing current weather')
            result['current'] = {'time': current['time'], 'conditions': CONDITIONS.get(code, 'unknown'),
                'temperature': temp, 'feels_like': number(current.get('apparent_temperature')),
                'humidity_percent': number(current.get('relative_humidity_2m')),
                'wind': number(current.get('wind_speed_10m')), 'precipitation': number(current.get('precipitation'))}
        return result


def weather_from_env(other=None):
    enabled = os.getenv('WEATHER_ENABLED', 'true').strip().lower()
    if enabled not in ('true', 'false'):
        raise ValueError('WEATHER_ENABLED must be true or false')
    if enabled == 'false':
        return other
    return WeatherTools(other, default_city=os.getenv('WEATHER_DEFAULT_CITY', ''),
        units=os.getenv('WEATHER_UNITS', 'metric').strip().lower(),
        timeout=float(os.getenv('WEATHER_TIMEOUT_SECONDS', '8')),
        cache_seconds=float(os.getenv('WEATHER_CACHE_SECONDS', '600')), api_key=os.getenv('OPEN_METEO_API_KEY', '').strip())


def main():
    import argparse
    from .environment import load_env
    parser = argparse.ArgumentParser(description='Test Open-Meteo directly, without microphone or OpenAI calls.')
    parser.add_argument('location', nargs='?', default='')
    parser.add_argument('--period', choices=['current', 'today', 'tomorrow', 'week'], default='current')
    parser.add_argument('--units', choices=['metric', 'imperial'], default=None)
    parser.add_argument('--env-file', default='.env')
    args = parser.parse_args()
    load_env(args.env_file)
    tool = weather_from_env()
    if tool is None:
        parser.error('Weather is disabled. Set WEATHER_ENABLED=true.')
    arguments = {'location': args.location, 'period': args.period}
    if args.units:
        arguments['units'] = args.units
    result = tool.execute('weather_lookup', arguments, threading.Event())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('status') != 'ok':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
