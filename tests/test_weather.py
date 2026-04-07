import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import requests as req_lib

from common.cache import VoiceCache
from plugins.weather import _cache_key

_CACHE_KEY = _cache_key("London", "metric")


def _make_sandvoice(cache=None, debug=False, location="London", unit="metric",
                    api_timeout=10, cache_weather_ttl_s=10800,
                    cache_weather_max_stale_s=21600):
    """Build a minimal SandVoice-like mock for weather plugin tests."""
    s = MagicMock()
    s.config.debug = debug
    s.config.location = location
    s.config.unit = unit
    s.config.api_timeout = api_timeout
    s.config.cache_weather_ttl_s = cache_weather_ttl_s
    s.config.cache_weather_max_stale_s = cache_weather_max_stale_s
    s.cache = cache

    # ai.generate_response returns an object with .content
    mock_response = Mock()
    mock_response.content = "It is 20°C in London."
    s.ai.generate_response.return_value = mock_response
    return s


_WEATHER_DATA = {"main": {"temp": 20}, "weather": [{"description": "clear sky"}]}


class TestWeatherPluginNoCache(unittest.TestCase):
    """Weather plugin behaviour when cache is None (disabled)."""

    def setUp(self):
        os.environ['OPENWEATHERMAP_API_KEY'] = 'test-key'

    def tearDown(self):
        os.environ.pop('OPENWEATHERMAP_API_KEY', None)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_fetches_and_returns_response(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        result = process("What's the weather?", {}, s)
        self.assertEqual(result, "It is 20°C in London.")

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_uses_route_location_and_unit(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        process("weather in Paris", {"location": "Paris", "unit": "imperial"}, s)
        MockReader.assert_called_once_with("Paris", "imperial", s.config.api_timeout)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_falls_back_to_config_location(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=None, location="Berlin")
        from plugins.weather import process
        process("weather", {}, s)
        MockReader.assert_called_once_with("Berlin", "metric", s.config.api_timeout)

    def test_missing_api_key_returns_error(self):
        os.environ.pop('OPENWEATHERMAP_API_KEY', None)
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        result = process("weather", {}, s)
        self.assertIn("Unable to fetch", result)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_refresh_only_returns_none(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        result = process("weather", {"refresh_only": True}, s)
        self.assertIsNone(result)


class TestWeatherPluginWithCache(unittest.TestCase):
    """Weather plugin behaviour with VoiceCache enabled."""

    def setUp(self):
        os.environ['OPENWEATHERMAP_API_KEY'] = 'test-key'
        self.tmp = tempfile.mkdtemp()
        self.cache = VoiceCache(os.path.join(self.tmp, "cache.db"))

    def tearDown(self):
        os.environ.pop('OPENWEATHERMAP_API_KEY', None)
        self.cache.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_fresh_cache_hit_skips_api(self, MockReader):
        self.cache.set(
            _CACHE_KEY, "It is 20°C in London.",
            ttl_s=10800, max_stale_s=21600,
        )
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        result = process("What's the weather?", {}, s)
        MockReader.assert_not_called()
        s.ai.generate_response.assert_not_called()
        self.assertEqual(result, "It is 20°C in London.")

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_cache_miss_fetches_and_populates_cache(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        process("What's the weather?", {}, s)
        MockReader.assert_called_once()
        entry = self.cache.get(_CACHE_KEY)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, "It is 20°C in London.")

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_refresh_only_bypasses_cache_read(self, MockReader):
        # Pre-populate cache with fresh data
        self.cache.set(
            _CACHE_KEY, "It is 20°C in London.",
            ttl_s=10800, max_stale_s=21600,
        )
        MockReader.return_value.get_current_weather.return_value = {
            "main": {"temp": 25}, "weather": [{"description": "sunny"}]
        }
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        result = process("weather", {"refresh_only": True}, s)
        # API should have been called (bypass cache read)
        MockReader.assert_called_once()
        # Return value should be None for refresh_only
        self.assertIsNone(result)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_refresh_only_updates_cache(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        process("weather", {"refresh_only": True}, s)
        entry = self.cache.get(_CACHE_KEY)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, "It is 20°C in London.")

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_ttl_override_from_route(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        with patch.object(self.cache, 'set', wraps=self.cache.set) as mock_set:
            process("weather", {"ttl_s": 3600, "max_stale_s": 7200}, s)
        mock_set.assert_called_once_with(_CACHE_KEY, "It is 20°C in London.", ttl_s=3600, max_stale_s=7200)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_ttl_falls_back_to_config(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache, cache_weather_ttl_s=1800, cache_weather_max_stale_s=3600)
        from plugins.weather import process
        with patch.object(self.cache, 'set', wraps=self.cache.set) as mock_set:
            process("weather", {}, s)
        mock_set.assert_called_once_with(_CACHE_KEY, "It is 20°C in London.", ttl_s=1800, max_stale_s=3600)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_api_error_does_not_cache(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = {"error": "bad"}
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        process("weather", {}, s)
        s.ai.generate_response.assert_called_once()
        self.assertIsNone(self.cache.get(_CACHE_KEY))

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_expired_cache_falls_through_to_api(self, MockReader):
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
        self.cache.set_with_timestamp(
            _CACHE_KEY, "It is 20°C in London.", ttl_s=1, max_stale_s=2,
            updated_at=old_ts,
        )
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        process("weather", {}, s)
        # Cache was expired (beyond max_stale), so API should be called
        MockReader.assert_called_once()

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_stale_but_valid_cache_hit(self, MockReader):
        # Insert entry that is expired (past TTL) but within max_stale
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        self.cache.set_with_timestamp(
            _CACHE_KEY, "It is 20°C in London.", ttl_s=1, max_stale_s=21600,
            updated_at=old_ts,
        )
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        result = process("weather", {}, s)
        # API and LLM should NOT be called — stale entry is still serviceable
        MockReader.assert_not_called()
        s.ai.generate_response.assert_not_called()
        self.assertEqual(result, "It is 20°C in London.")

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_cache_read_failure_falls_back_to_live(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache)
        # Simulate a DB read error (e.g. locked)
        with patch.object(self.cache, 'get', side_effect=Exception("DB locked")):
            from plugins.weather import process
            result = process("weather", {}, s)
        # Should still return a response via live fetch
        MockReader.assert_called_once()
        self.assertEqual(result, "It is 20°C in London.")

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_cache_write_failure_still_returns_response(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache)
        # Simulate a DB write error
        with patch.object(self.cache, 'set', side_effect=Exception("DB locked")):
            from plugins.weather import process
            result = process("weather", {}, s)
        # Response should still be returned despite cache write failure
        self.assertEqual(result, "It is 20°C in London.")

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_legacy_json_cache_entry_falls_back_to_live(self, MockReader):
        # Seed cache with old-format raw weather JSON (pre-migration payload)
        self.cache.set(
            _CACHE_KEY, json.dumps(_WEATHER_DATA),
            ttl_s=10800, max_stale_s=21600,
        )
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        result = process("weather", {}, s)
        # Should fall through to live fetch, not return raw JSON
        MockReader.assert_called_once()
        self.assertEqual(result, "It is 20°C in London.")
        # Cache should now contain the response text, not raw JSON
        entry = self.cache.get(_CACHE_KEY)
        self.assertEqual(entry.value, "It is 20°C in London.")


class TestWeatherPluginDebugPaths(unittest.TestCase):
    """Cover logger calls and exception branches (config.debug has no effect on these paths)."""

    def setUp(self):
        os.environ['OPENWEATHERMAP_API_KEY'] = 'test-key'

    def tearDown(self):
        os.environ.pop('OPENWEATHERMAP_API_KEY', None)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_debug_log_when_location_missing(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=None, debug=False, location="Tokyo")
        from plugins.weather import process
        with patch('plugins.weather.plugin.logger') as mock_logger:
            process("weather", {}, s)
        debug_calls = [str(call) for call in mock_logger.debug.call_args_list]
        self.assertTrue(any("location" in c for c in debug_calls))

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_debug_log_when_unit_missing(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=None, debug=False, unit="imperial")
        from plugins.weather import process
        with patch('plugins.weather.plugin.logger') as mock_logger:
            process("weather", {"location": "Tokyo"}, s)
        debug_calls = [str(call) for call in mock_logger.debug.call_args_list]
        self.assertTrue(any("unit" in c for c in debug_calls))

    def test_value_error_returns_error_message(self):
        os.environ.pop('OPENWEATHERMAP_API_KEY', None)
        s = _make_sandvoice(cache=None, debug=False)
        from plugins.weather import process
        result = process("weather", {}, s)
        self.assertIn("Unable to fetch", result)

    def test_value_error_refresh_only_returns_none(self):
        os.environ.pop('OPENWEATHERMAP_API_KEY', None)
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        result = process("weather", {"refresh_only": True}, s)
        self.assertIsNone(result)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_generic_exception_returns_error(self, MockReader):
        MockReader.side_effect = RuntimeError("unexpected error")
        s = _make_sandvoice(cache=None, debug=False)
        from plugins.weather import process
        result = process("weather", {}, s)
        self.assertIn("Unable to fetch", result)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_generic_exception_refresh_only_returns_none(self, MockReader):
        MockReader.side_effect = RuntimeError("unexpected error")
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        result = process("weather", {"refresh_only": True}, s)
        self.assertIsNone(result)


class TestOpenWeatherReader(unittest.TestCase):
    """Direct tests of OpenWeatherReader (mocking HTTP layer)."""

    def setUp(self):
        os.environ['OPENWEATHERMAP_API_KEY'] = 'test-key'

    def tearDown(self):
        os.environ.pop('OPENWEATHERMAP_API_KEY', None)

    def test_missing_api_key_raises_value_error(self):
        os.environ.pop('OPENWEATHERMAP_API_KEY', None)
        from plugins.weather import OpenWeatherReader
        with self.assertRaises(ValueError):
            OpenWeatherReader("London")

    @patch('plugins.weather.plugin.requests.get')
    def test_get_current_weather_success(self, mock_get):
        mock_resp = Mock()
        mock_resp.json.return_value = _WEATHER_DATA
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp
        from plugins.weather import OpenWeatherReader
        reader = OpenWeatherReader("London", "metric", timeout=5)
        result = reader.get_current_weather()
        self.assertEqual(result, _WEATHER_DATA)

    @patch('plugins.weather.plugin.requests.get')
    def test_get_current_weather_request_exception(self, mock_get):
        mock_get.side_effect = req_lib.exceptions.RequestException("network error")
        from plugins.weather import OpenWeatherReader
        reader = OpenWeatherReader("London", "metric", timeout=5)
        result = reader.get_current_weather()
        self.assertIn("error", result)

    @patch('plugins.weather.plugin.requests.get')
    def test_get_current_weather_generic_exception(self, mock_get):
        mock_get.side_effect = RuntimeError("unexpected")
        from plugins.weather import OpenWeatherReader
        reader = OpenWeatherReader("London", "metric", timeout=5)
        result = reader.get_current_weather()
        self.assertIn("error", result)
