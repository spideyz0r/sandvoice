import datetime
import json
import logging
import os

import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # Python < 3.9 fallback

logger = logging.getLogger(__name__)

_TZ_CACHE = {}  # tz_name → ZoneInfo or None; avoids repeated resolution and duplicate warnings


def _resolve_tz(tz_name):
    """Return a ZoneInfo for tz_name, or None if unavailable or invalid."""
    if not tz_name or ZoneInfo is None:
        return None
    if tz_name in _TZ_CACHE:
        return _TZ_CACHE[tz_name]
    try:
        tz = ZoneInfo(tz_name)
        _TZ_CACHE[tz_name] = tz
        return tz
    except Exception as exc:
        logger.warning(
            "Weather: timezone %r could not be resolved (%s); falling back to UTC for cache key.",
            tz_name,
            exc,
        )
        _TZ_CACHE[tz_name] = None
        return None


class OpenWeatherReader:
    def __init__(self, location, unit="metric", timeout=10):
        if not os.environ.get('OPENWEATHERMAP_API_KEY'):
            raise ValueError("Missing OPENWEATHERMAP_API_KEY environment variable")
        self.api_key = os.environ['OPENWEATHERMAP_API_KEY']
        self.location = location
        self.unit = unit
        self.timeout = timeout
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"
        self.forecast_url = "https://api.openweathermap.org/data/2.5/forecast"

    def get_current_weather(self):
        try:
            response = requests.get(
                self.base_url,
                params={"q": self.location, "appid": self.api_key, "units": self.unit},
                timeout=self.timeout,
            )
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

    def get_forecast(self, days_ahead, _now=None):
        """Fetch the 5-day/3-hour forecast and return slots matching today + days_ahead.

        Uses the city.timezone offset from the API response to convert each slot's
        Unix timestamp to a local date, so the filtering is timezone-aware.

        Returns a list of forecast slot dicts.  Falls back to the full list if
        date-based filtering produces no matches.  Returns a dict with an "error"
        key on network/parse failure.

        _now is an optional datetime (with tzinfo) used to override "now" in tests.
        """
        try:
            response = requests.get(
                self.forecast_url,
                params={
                    "q": self.location,
                    "appid": self.api_key,
                    "units": self.unit,
                    "cnt": 40,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            # Derive target date using the city's UTC offset (seconds east of UTC).
            # Coerce to int to guard against null or unexpected string values from the API.
            raw_offset = data.get("city", {}).get("timezone", 0)
            try:
                tz_offset_s = int(raw_offset)
            except (TypeError, ValueError):
                logger.debug("Forecast: invalid city.timezone value %r; using UTC offset=0", raw_offset)
                tz_offset_s = 0
            tz = datetime.timezone(datetime.timedelta(seconds=tz_offset_s))
            now_local = _now.astimezone(tz) if _now is not None else datetime.datetime.now(tz)
            target_date = (now_local + datetime.timedelta(days=days_ahead)).date()

            slots = data.get("list", [])
            filtered = [
                slot for slot in slots
                if datetime.datetime.fromtimestamp(slot["dt"], tz=tz).date() == target_date
            ]

            if filtered:
                return filtered
            # Graceful fallback: filtering produced nothing (e.g. target date is at edge
            # of the 40-slot window), return everything so the LLM can still answer.
            logger.debug(
                "Forecast: no slots matched target date %s (tz_offset=%ds); returning full list",
                target_date,
                tz_offset_s,
            )
            return slots
        except requests.exceptions.RequestException as e:
            status = getattr(getattr(e, 'response', None), 'status_code', None)
            if status is not None:
                logger.error("Forecast API error: %s status=%d", type(e).__name__, status)
            else:
                logger.error("Forecast API error: %s", type(e).__name__)
            return {"error": "Unable to fetch forecast data"}
        except Exception as e:
            logger.error(
                "Forecast error: %s: %s", type(e).__name__, e,
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )
            return {"error": "Forecast service unavailable"}


def _cache_key(location, unit, days_ahead=0, timezone=None, _now=None):
    # JSON-encode to avoid collisions when location contains ':'.
    # Forecast keys include today's local date (in the user's configured timezone)
    # so a cached "tomorrow" entry is never served on a different calendar day
    # after local midnight.  Falls back to UTC if timezone is missing or invalid.
    # Note: uses s.config.timezone (the user's own timezone) as a best approximation.
    # For queries about a location in a different timezone, the date anchor may
    # drift by up to one day around the location's local midnight; the 1 h TTL
    # bounds any resulting stale-serve window.
    # _now is an optional datetime used to override "now" in tests.
    if days_ahead >= 1:
        tz = _resolve_tz(timezone)
        utc = datetime.timezone.utc
        if tz is not None:
            now = _now.astimezone(tz) if _now is not None else datetime.datetime.now(tz)
        else:
            now = _now.astimezone(utc) if _now is not None else datetime.datetime.now(utc)
        today = now.date().isoformat()
        encoded = json.dumps([location, unit, days_ahead, today], separators=(",", ":"))
    else:
        encoded = json.dumps([location, unit, days_ahead], separators=(",", ":"))
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
        raw_days_ahead = route.get('days_ahead', 0)
        if isinstance(raw_days_ahead, bool):
            logger.warning("Invalid days_ahead value %r in route; defaulting to 0", raw_days_ahead)
            days_ahead = 0
        else:
            try:
                days_ahead = int(raw_days_ahead)
            except (TypeError, ValueError):
                logger.warning("Invalid days_ahead value %r in route; defaulting to 0", raw_days_ahead)
                days_ahead = 0

        if days_ahead < 0:
            logger.warning("Negative days_ahead %d in route; defaulting to 0", days_ahead)
            days_ahead = 0

        refresh_only = route.get('refresh_only', False)

        if days_ahead > 5:
            if refresh_only:
                return None
            return "I can only forecast up to 5 days ahead."
        cache = getattr(s, 'cache', None)
        cache_key = _cache_key(location, unit, days_ahead, timezone=getattr(s.config, 'timezone', None))

        if days_ahead >= 1:
            ttl_s = route.get('ttl_s', s.config.cache_weather_forecast_ttl_s)
            max_stale_s = route.get('max_stale_s', s.config.cache_weather_forecast_max_stale_s)
        else:
            ttl_s = route.get('ttl_s', s.config.cache_weather_ttl_s)
            max_stale_s = route.get('max_stale_s', s.config.cache_weather_max_stale_s)

        # Skip live fetch during warmup if the cached entry is still fresh
        if refresh_only and cache is not None:
            try:
                entry = cache.get(cache_key)
                if entry is not None and cache.is_fresh(entry) and not _is_legacy_cache_entry(entry.value):
                    logger.debug("Weather cache warmup skip (fresh): key=%r", cache_key)
                    return None
            except Exception as e:
                logger.debug("Weather cache check failed during warmup, proceeding with fetch: %s", e)

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

        response_text = None
        if days_ahead >= 1:
            forecast_slots = weather.get_forecast(days_ahead)
            forecast_error = (isinstance(forecast_slots, dict) and "error" in forecast_slots) or not forecast_slots
            if forecast_error:
                # Fetch returned an error dict or empty result — skip LLM on warmup, no caching
                if refresh_only:
                    return None
                logger.warning("Forecast fetch failed or returned empty result: %s", forecast_slots)
                return "Unable to fetch forecast data. Please try again later."
            else:
                response = s.ai.generate_response(
                    user_input,
                    f"You can answer questions about weather forecasts. The user asked about weather "
                    f"{days_ahead} day(s) from now. Here is the forecast data: {str(forecast_slots)}. "
                    f"Summarize the expected conditions for that day in a natural, voice-friendly way.",
                )
                response_text = response.content
        else:
            current_weather = weather.get_current_weather()
            if "error" not in current_weather:
                response = s.ai.generate_response(
                    user_input,
                    f"You can answer questions about weather. This is the information of the weather the user asked: {str(current_weather)}. You are a voice bot, don't mention it, but keep the answer in an appropriate amount of words for such case. Also use correct punctuation, because your answer will be translated TTS. Don't overwhelm the user with a lot of information, they want to know how is the weather.\n",
                )
                response_text = response.content
            else:
                # Fetch returned an error dict — skip LLM on warmup, no caching
                if refresh_only:
                    return None
                logger.warning("Current weather fetch failed: %s", current_weather)
                return "Unable to fetch weather data. Please try again later."

        # Cache the full response text so future hits skip the LLM call entirely
        if response_text is not None and cache is not None:
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

        return "Unable to fetch weather information. Please try again later."
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
