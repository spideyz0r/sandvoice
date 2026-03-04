import json
import logging
import os

import requests

from common.error_handling import handle_api_error

logger = logging.getLogger(__name__)


class OpenWeatherReader:
    def __init__(self, location, unit="metric", timeout=10):
        if not os.environ.get('OPENWEATHERMAP_API_KEY'):
            error_msg = "Missing OPENWEATHERMAP_API_KEY environment variable"
            logger.error(error_msg)
            raise ValueError(error_msg)
        self.api_key = os.environ['OPENWEATHERMAP_API_KEY']
        self.location = location
        self.unit = unit
        self.timeout = timeout
        self.base_url = "https://api.openweathermap.org/data/2.5/weather?"

    def get_current_weather(self):
        try:
            url = f"{self.base_url}q={self.location}&appid={self.api_key}&units={self.unit}"
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            # not formatting the output, since the model can understand that
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = handle_api_error(e, service_name="OpenWeatherMap")
            logger.error("Weather API error: %s", e)
            logger.debug(error_msg)
            return {"error": "Unable to fetch weather data"}
        except Exception as e:
            logger.error("Weather error: %s", e)
            return {"error": "Weather service unavailable"}


def _cache_key(location, unit):
    # JSON-encode the pair to avoid collisions when location contains ':'.
    encoded = json.dumps([location, unit], separators=(",", ":"))
    return f"weather:{encoded}"


def process(user_input, route, s):
    try:
        if not route.get('location'):
            if s.config.debug:
                print("No location found in route, using default location")
            route['location'] = s.config.location
        if not route.get('unit'):
            if s.config.debug:
                print("No unit found in route, using default unit")
            route['unit'] = s.config.unit

        location = route['location']
        unit = route['unit']
        refresh_only = route.get('refresh_only', False)
        cache = getattr(s, 'cache', None)
        cache_key = _cache_key(location, unit)

        # Try serving from cache when not a background refresh
        if not refresh_only and cache is not None:
            try:
                entry = cache.get(cache_key)
                if entry is not None and cache.can_serve(entry):
                    if cache.is_fresh(entry):
                        logger.debug("Weather cache hit (fresh): key=%r", cache_key)
                    else:
                        logger.debug("Weather cache hit (stale-but-valid): key=%r", cache_key)
                    try:
                        current_weather = json.loads(entry.value)
                        response = s.ai.generate_response(
                            user_input,
                            f"You can answer questions about weather. This is the information of the weather the user asked: {str(current_weather)}\n",
                        )
                        return response.content
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning("Corrupt weather cache entry for key=%r, fetching live data: %s", cache_key, e)
            except Exception as e:
                logger.warning("Weather cache read failed for key=%r, fetching live data: %s", cache_key, e)

        # Fetch live data
        weather = OpenWeatherReader(location, unit, s.config.api_timeout)
        current_weather = weather.get_current_weather()

        # Update cache if fetch was successful and cache is available
        if cache is not None and "error" not in current_weather:
            try:
                cache.set(
                    cache_key,
                    json.dumps(current_weather),
                    ttl_s=s.config.cache_weather_ttl_s,
                    max_stale_s=s.config.cache_weather_max_stale_s,
                )
                logger.debug("Weather cache updated: key=%r", cache_key)
            except Exception as e:
                logger.warning("Weather cache write failed for key=%r: %s", cache_key, e)

        if refresh_only:
            return None

        response = s.ai.generate_response(
            user_input,
            f"You can answer questions about weather. This is the information of the weather the user asked: {str(current_weather)}\n",
        )
        return response.content
    except ValueError as e:
        if s.config.debug:
            logger.error("Weather plugin configuration error: %s", e)
        if route.get('refresh_only', False):
            return None
        return "Unable to fetch weather information. Please check your configuration."
    except Exception as e:
        if s.config.debug:
            logger.error("Weather plugin error: %s", e)
        if route.get('refresh_only', False):
            return None
        return "Unable to fetch weather information. Please try again later."
