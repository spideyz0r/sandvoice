import logging
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # Python < 3.9 fallback; local time will be used

from common.plugin_loader import build_extra_routes_text

logger = logging.getLogger(__name__)

_DEFAULT_TTL_S = 3600
_DEFAULT_MAX_STALE_S = 5400


def _resolve_tz(config):
    """Return a ZoneInfo for config.timezone, or None to fall back to local time."""
    tz_name = getattr(config, 'timezone', None)
    if not tz_name or ZoneInfo is None:
        return None
    try:
        return ZoneInfo(tz_name)
    except Exception as exc:
        logger.warning("greeting: timezone %r could not be resolved (%s); using local time.", tz_name, exc)
        return None


def _cache_key(config=None):
    tz = _resolve_tz(config)
    hour = datetime.now(tz).hour
    if 5 <= hour < 12:
        bucket = "morning"
    elif 12 <= hour < 18:
        bucket = "afternoon"
    elif 18 <= hour < 22:
        bucket = "evening"
    else:
        bucket = "night"
    return f"greeting:{bucket}"


def process(user_input, route, s):
    refresh_only = route.get('refresh_only', False)
    cache = getattr(s, 'cache', None)
    cache_key = _cache_key(s.config)
    ttl_s = route.get('ttl_s', _DEFAULT_TTL_S)
    max_stale_s = route.get('max_stale_s', _DEFAULT_MAX_STALE_S)

    # Try serving from cache when not a background refresh
    if not refresh_only and cache is not None:
        try:
            entry = cache.get(cache_key)
            if entry is not None and cache.can_serve(entry):
                logger.debug("Greeting cache hit: key=%r", cache_key)
                return entry.value
        except Exception as e:
            logger.warning("Greeting cache read failed for key=%r: %s", cache_key, e)

    # Live generation: fetch weather then generate greeting
    manifests = getattr(s, '_plugin_manifests', [])
    extra_routes = build_extra_routes_text(manifests, location=s.config.location)
    weather_route = s.ai.define_route("What's the weather?", extra_routes=extra_routes)
    weather_response = s.route_message("What's the weather?", weather_route)

    extra_system = f"""
    Greet the user! You are very friendly.
    Depending on the current date and time use good evening/afternoon/morning match the greeting with the time.
    Casually make a friendly and short comment on the weather. Weather info to consider the answer: {weather_response}
    Considering the current day and time, make a fun fact comment about today or this month.
    """
    response_text = s.ai.generate_response(user_input, extra_system).content

    if cache is not None:
        try:
            cache.set(cache_key, response_text, ttl_s=ttl_s, max_stale_s=max_stale_s)
            logger.debug("Greeting cache updated: key=%r", cache_key)
        except Exception as e:
            logger.warning("Greeting cache write failed for key=%r: %s", cache_key, e)

    if refresh_only:
        return None

    return response_text
