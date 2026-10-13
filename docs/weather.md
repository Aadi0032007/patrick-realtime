# Open-Meteo weather tool

Weather works through `weather_lookup` alongside local RAG and web search, independently of WEB_SEARCH_ENABLED. No extra Python dependency or extra research-model call is needed. This trial uses the public Open-Meteo endpoints without a weather API key.

By default there is no location: Scout asks which city when one is not provided. It never uses IP location or the machine's timezone to infer where the user is. Use city plus state/country for precision; ambiguous matches prompt a clarification. Tool results are reference data.

Supported periods: current conditions, today, tomorrow, or a seven-day forecast. Results include units, location timezone, data time and retrieval time. Open-Meteo current conditions are weather-model estimates, not readings from the robot's sensors. Today's daily maximum rain probability is labeled separately from current conditions.

Successful weather results cache for ten minutes and refresh across the location's midnight. Geocoding caches for one day. Weather failures are not cached or replaced with invented values. Responses are bounded and requests have a timeout. Source attribution is retained in tool results, documentation and terminal output; sources are spoken only when asked.

Configuration in `.env`:

```dotenv
WEATHER_ENABLED=true
WEATHER_DEFAULT_CITY=
WEATHER_UNITS=metric
WEATHER_TIMEOUT_SECONDS=8
WEATHER_CACHE_SECONDS=600
OPEN_METEO_API_KEY=
```

Leave WEATHER_DEFAULT_CITY empty to ask for location. `imperial` uses Fahrenheit, mph and inches. An optional future default city can be set, including a state or country qualifier. A commercial Open-Meteo API key selects customer endpoints automatically.

Independent provider test (does not use audio or OpenAI):

```bash
conda activate chatbot
cd ~/aditya/patrick-realtime
python -m patrick.weather "Bengaluru, Karnataka"
python -m patrick.weather "Bengaluru, Karnataka" --period tomorrow
python -m patrick.weather "Bengaluru, Karnataka" --period week --units imperial
```

Then run `bash run.sh`, or restart the installed service:

```bash
sudo systemctl restart scout_chatbot.service
sudo journalctl -u scout_chatbot.service -f
```

Ask “What's the weather in Bengaluru, Karnataka?” or “Will it rain tomorrow in Bengaluru, Karnataka?” A question with no city should prompt for one. Startup prints `Weather: Open-Meteo`, and tool calls print status in the terminal.

Attribution: weather data by [Open-Meteo](https://open-meteo.com/); geocoding data based on [GeoNames](https://www.geonames.org/). See the [forecast API](https://open-meteo.com/en/docs) and [geocoding API](https://open-meteo.com/en/docs/geocoding-api). The public hosted API is for non-commercial testing; commercial deployment requires the appropriate [Open-Meteo subscription](https://open-meteo.com/en/pricing). Customer endpoints are supported but were not tested against a paid account.
