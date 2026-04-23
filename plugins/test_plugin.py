import logging

import requests

logger = logging.getLogger(__name__)


def fetch_data(query, timeout=10):
    try:
        response = requests.get(
            "https://api.example.com/data",
            params={"q": query},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            logger.warning("Unexpected response shape from example API: got %s", type(data).__name__)
            return None
        value = data.get("value")
        if not isinstance(value, str):
            logger.warning(
                "Unexpected 'value' type from example API: got %s", type(value).__name__
            )
            return None
        return value
    except requests.exceptions.RequestException as e:
        logger.error("Example API request failed: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected error fetching example data: %s", e, exc_info=logger.isEnabledFor(logging.DEBUG))
        return None


def process(user_input, route, s):
    if route.get("refresh_only"):
        return None
    timeout = getattr(s.config, "api_timeout", 10)
    result = fetch_data(user_input, timeout=timeout)
    if result is None:
        return "Sorry, I couldn't fetch that information right now."
    return result
