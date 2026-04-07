import json
import logging
import os

import requests

logger = logging.getLogger(__name__)


class OpenWeatherReader:
    def __init__(self, location, unit="metric", timeout=10):
        if not os.environ.get('OPENWEATHERMAP_API_KEY'):
            raise ValueError("Missing OPENWEATHERMAP_API_KEY environment variable")
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
            status = getattr(getattr(e, 'response', None), 'status_code', None)
            if status is not None:
                logger.error("Weather API error: %s status=%d", type(e).__name__, status)
            else:
                logger.error("Weather API error: %s", type(e).__name__)
            return {"error": "Unable to fetch weather data"}
        except Exception as e:
            logger.error(
                "Weather error: %s: %s", type(e).__name__, e,
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )
            return {"error": "Weather service unavailable"}


def _cache_key(location, unit):
    # JSON-encode the pair to avoid collisions when location contains ':'.
    encoded = json.dumps([location, unit], separators=(",", ":"))
    return f"weather:{encoded}"


def _is_legacy_cache_entry(value):
    """Return True if the cached value looks like a raw OpenWeatherMap JSON payload.

    Older versions of the plugin stored raw weather JSON in the cache instead of
    the final response text.  Detect these entries so callers can fall through to
    a live fetch and overwrite them with the correct payload format.
    """
    try:
        parsed = json.loads(value)
        return isinstance(parsed, dict) and ("cod" in parsed or "weather" in parsed)
    except (json.JSONDecodeError, TypeError):
        return False


def process(user_input, route, s):
    try:
        if not route.get('location'):
            logger.debug("No location found in route, using default location")
            route['location'] = s.config.location
        if not route.get('unit'):
            logger.debug("No unit found in route, using default unit")
            route['unit'] = s.config.unit

        location = route['location']
        unit = route['unit']
        refresh_only = route.get('refresh_only', False)
        cache = getattr(s, 'cache', None)
        cache_key = _cache_key(location, unit)
        try:
            raw_ttl = route.get('ttl_s')
            ttl_s = s.config.cache_weather_ttl_s if (raw_ttl is None or isinstance(raw_ttl, bool)) else max(1, int(raw_ttl))
        except (TypeError, ValueError):
            ttl_s = s.config.cache_weather_ttl_s
        try:
            raw_max_stale = route.get('max_stale_s')
            max_stale_s = s.config.cache_weather_max_stale_s if (raw_max_stale is None or isinstance(raw_max_stale, bool)) else max(1, int(raw_max_stale))
        except (TypeError, ValueError):
            max_stale_s = s.config.cache_weather_max_stale_s
        if max_stale_s < ttl_s:
            max_stale_s = ttl_s

        # Try serving from cache when not a background refresh
        if not refresh_only and cache is not None:
            try:
                entry = cache.get(cache_key)
                if entry is not None and cache.can_serve(entry):
                    if _is_legacy_cache_entry(entry.value):
                        logger.debug("Weather cache legacy JSON entry, invalidating: key=%r", cache_key)
                        # Fall through to live fetch; response text will overwrite it
                    elif cache.is_fresh(entry):
                        logger.debug("Weather cache hit (fresh): key=%r", cache_key)
                        return entry.value
                    else:
                        logger.debug("Weather cache hit (stale-but-valid): key=%r", cache_key)
                        return entry.value
            except Exception as e:
                logger.warning("Weather cache read failed for key=%r, fetching live data: %s", cache_key, e)

        # Fetch live data
        weather = OpenWeatherReader(location, unit, s.config.api_timeout)
        current_weather = weather.get_current_weather()

        response_text = None
        if "error" not in current_weather:
            response = s.ai.generate_response(
                user_input,
                f"You can answer questions about weather. This is the information of the weather the user asked: {str(current_weather)}. You are a voice bot, don't mention it, but keep the answer in an appropriate amount of words for such case. Also use correct punctuation, because your answer will be translated TTS. Don't overwhelm the user with a lot of information, they want to know how is the weather.\n",
            )
            response_text = response.content

            # Cache the full response text so future hits skip the LLM call entirely
            if cache is not None:
                try:
                    cache.set(
                        cache_key,
                        response_text,
                        ttl_s=ttl_s,
                        max_stale_s=max_stale_s,
                    )
                    logger.debug("Weather cache updated: key=%r", cache_key)
                except Exception as e:
                    logger.warning("Weather cache write failed for key=%r: %s", cache_key, e)

        if refresh_only:
            return None

        if response_text is not None:
            return response_text

        # Fetch returned an error dict — generate a response without caching
        response = s.ai.generate_response(
            user_input,
            f"You can answer questions about weather. This is the information of the weather the user asked: {str(current_weather)}\n",
        )
        return response.content
    except ValueError as e:
        logger.error("Weather plugin configuration error: %s", e)
        if route.get('refresh_only', False):
            return None
        return "Unable to fetch weather information. Please check your configuration."
    except Exception as e:
        logger.error("Weather plugin error: %s", e)
        if route.get('refresh_only', False):
            return None
        return "Unable to fetch weather information. Please try again later."
