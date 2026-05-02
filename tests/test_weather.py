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
                    cache_weather_max_stale_s=21600,
                    cache_weather_forecast_ttl_s=3600,
                    cache_weather_forecast_max_stale_s=7200,
                    timezone="UTC"):
    """Build a minimal SandVoice-like mock for weather plugin tests."""
    s = MagicMock()
    s.config.debug = debug
    s.config.location = location
    s.config.unit = unit
    s.config.api_timeout = api_timeout
    s.config.cache_weather_ttl_s = cache_weather_ttl_s
    s.config.cache_weather_max_stale_s = cache_weather_max_stale_s
    s.config.cache_weather_forecast_ttl_s = cache_weather_forecast_ttl_s
    s.config.cache_weather_forecast_max_stale_s = cache_weather_forecast_max_stale_s
    s.config.timezone = timezone
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
    def test_warmup_skips_fetch_when_fresh(self, MockReader):
        # Pre-populate cache with a fresh entry
        self.cache.set(
            _CACHE_KEY, "It is 20°C in London.",
            ttl_s=10800, max_stale_s=21600,
        )
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        result = process("weather", {"refresh_only": True}, s)
        # Fresh cache → API and LLM should be skipped entirely
        MockReader.assert_not_called()
        s.ai.generate_response.assert_not_called()
        self.assertIsNone(result)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_warmup_fetches_when_stale(self, MockReader):
        # Insert entry past TTL but within max_stale (stale-but-servable)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
        self.cache.set_with_timestamp(
            _CACHE_KEY, "It is 20°C in London.", ttl_s=3600, max_stale_s=21600,
            updated_at=old_ts,
        )
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        result = process("weather", {"refresh_only": True}, s)
        # Stale entry → live fetch should run and update cache
        MockReader.assert_called_once()
        self.assertIsNone(result)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_warmup_fetches_when_missing(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        result = process("weather", {"refresh_only": True}, s)
        # No cache entry → live fetch runs
        MockReader.assert_called_once()
        self.assertIsNone(result)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_warmup_fetches_when_fresh_legacy_entry(self, MockReader):
        # Seed cache with a fresh but legacy JSON entry (old raw weather payload format)
        self.cache.set(
            _CACHE_KEY, json.dumps(_WEATHER_DATA),
            ttl_s=10800, max_stale_s=21600,
        )
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import process
        result = process("weather", {"refresh_only": True}, s)
        # Legacy entry must NOT be skipped even though it is fresh — fetch and overwrite
        MockReader.assert_called_once()
        self.assertIsNone(result)
        # Cache should now contain response text, not raw JSON
        entry = self.cache.get(_CACHE_KEY)
        self.assertEqual(entry.value, "It is 20°C in London.")

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_warmup_cache_check_failure_falls_through_to_fetch(self, MockReader):
        MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
        s = _make_sandvoice(cache=self.cache)
        with patch.object(self.cache, 'get', side_effect=Exception("DB locked")):
            from plugins.weather import process
            result = process("weather", {"refresh_only": True}, s)
        # Cache check failed → should fall through to live fetch
        MockReader.assert_called_once()
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


class TestCacheKeyForecast(unittest.TestCase):
    """Tests for _cache_key with days_ahead parameter."""

    def test_cache_key_includes_days_ahead(self):
        from plugins.weather import _cache_key
        key0 = _cache_key("London", "metric", 0)
        key2 = _cache_key("London", "metric", 2)
        self.assertNotEqual(key0, key2)

    def test_forecast_cache_key_uses_user_timezone(self):
        # At 23:30 UTC, the local date in UTC+12 is already the next calendar day.
        # Keys must differ because their local date anchors differ, not merely
        # because their timezone names differ.
        import datetime as dt_mod
        from plugins.weather import _cache_key
        utc = dt_mod.timezone.utc
        # 2026-05-31 23:30 UTC = 2026-06-01 11:30 in UTC+12 (Etc/GMT-12)
        fixed_now = dt_mod.datetime(2026, 5, 31, 23, 30, 0, tzinfo=utc)
        key_utc = _cache_key("London", "metric", 1, timezone="UTC", _now=fixed_now)
        key_plus12 = _cache_key("London", "metric", 1, timezone="Etc/GMT-12", _now=fixed_now)
        # UTC date anchor = 2026-05-31; UTC+12 date anchor = 2026-06-01
        self.assertNotEqual(key_utc, key_plus12)
        self.assertIn("2026-05-31", key_utc)
        self.assertIn("2026-06-01", key_plus12)

    def test_forecast_cache_key_invalid_timezone_falls_back_to_utc(self):
        import datetime as dt_mod
        from plugins.weather import _cache_key
        utc = dt_mod.timezone.utc
        fixed_now = dt_mod.datetime(2026, 5, 31, 12, 0, 0, tzinfo=utc)
        # Clear the tz cache so the warning fires even if this tz was seen before
        with patch.dict('plugins.weather.plugin._TZ_CACHE', {}, clear=True), \
             patch('plugins.weather.plugin.logger') as mock_logger:
            key_invalid = _cache_key("London", "metric", 1, timezone="NOT_A_TZ", _now=fixed_now)
        key_utc = _cache_key("London", "metric", 1, timezone="UTC", _now=fixed_now)
        self.assertEqual(key_invalid, key_utc)
        # Invalid timezone must log a warning so misconfiguration is visible
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        self.assertTrue(any("NOT_A_TZ" in c for c in warning_calls))

    def test_cache_key_zero_differs_from_legacy(self):
        from plugins.weather import _cache_key
        new_key = _cache_key("London", "metric", 0)
        legacy_key = 'weather:["London","metric"]'
        self.assertNotEqual(new_key, legacy_key)

    def test_forecast_cache_key_includes_date(self):
        # Forecast keys must embed a date (YYYY-MM-DD) so a cached "tomorrow"
        # entry is never served on a different calendar day after local midnight.
        import re
        from plugins.weather import _cache_key
        key = _cache_key("London", "metric", 1, timezone="UTC")
        self.assertRegex(key, r'\d{4}-\d{2}-\d{2}', "forecast key should contain a date")
        # Current-weather key must NOT include a date (no cross-day issue for point-in-time data).
        key0 = _cache_key("London", "metric", 0)
        self.assertNotRegex(key0, r'\d{4}-\d{2}-\d{2}')


class TestWeatherForecastProcess(unittest.TestCase):
    """Tests for forecast code paths in process()."""

    def setUp(self):
        os.environ['OPENWEATHERMAP_API_KEY'] = 'test-key'
        self.tmp = tempfile.mkdtemp()
        self.cache = VoiceCache(os.path.join(self.tmp, "cache.db"))

    def tearDown(self):
        os.environ.pop('OPENWEATHERMAP_API_KEY', None)
        self.cache.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_days_ahead_gt_5_returns_friendly_message(self):
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        result = process("weather saturday", {"days_ahead": 6}, s)
        self.assertIn("5 days", result)

    def test_days_ahead_gt_5_refresh_only_returns_none(self):
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        result = process("weather", {"days_ahead": 6, "refresh_only": True}, s)
        self.assertIsNone(result)

    def test_days_ahead_non_int_defaults_to_zero(self):
        # Router may occasionally return a non-integer; plugin should default to 0
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        with patch('plugins.weather.plugin.OpenWeatherReader') as MockReader:
            MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
            process("weather", {"days_ahead": "tomorrow"}, s)
        # Should have called get_current_weather (days_ahead=0 path), not get_forecast
        MockReader.return_value.get_current_weather.assert_called_once()
        MockReader.return_value.get_forecast.assert_not_called()

    def test_days_ahead_negative_defaults_to_zero(self):
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        with patch('plugins.weather.plugin.OpenWeatherReader') as MockReader:
            MockReader.return_value.get_current_weather.return_value = _WEATHER_DATA
            process("weather", {"days_ahead": -1}, s)
        MockReader.return_value.get_current_weather.assert_called_once()
        MockReader.return_value.get_forecast.assert_not_called()

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_forecast_refresh_only_skips_llm_on_api_error(self, MockReader):
        # When refresh_only=True and the forecast API returns an error,
        # process() must return None without calling the LLM.
        MockReader.return_value.get_forecast.return_value = {"error": "network down"}
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        result = process("weather tomorrow", {"days_ahead": 1, "refresh_only": True}, s)
        self.assertIsNone(result)
        s.ai.generate_response.assert_not_called()

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_forecast_called_when_days_ahead_1(self, MockReader):
        forecast_slots = [{"dt": 1700000000, "main": {"temp": 15}, "weather": [{"description": "rain"}]}]
        MockReader.return_value.get_forecast.return_value = forecast_slots
        s = _make_sandvoice(cache=None)
        from plugins.weather import process
        process("weather tomorrow", {"days_ahead": 1}, s)
        MockReader.return_value.get_forecast.assert_called_once_with(1)

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_forecast_uses_forecast_ttl_config(self, MockReader):
        forecast_slots = [{"dt": 1700000000, "main": {"temp": 15}}]
        MockReader.return_value.get_forecast.return_value = forecast_slots
        s = _make_sandvoice(
            cache=self.cache,
            cache_weather_forecast_ttl_s=3600,
            cache_weather_forecast_max_stale_s=7200,
        )
        from plugins.weather import _cache_key as ck, process
        # Compute expected_key before process() so both use the same local date
        # (avoids a theoretical mismatch if the test straddles midnight).
        expected_key = ck("London", "metric", 1, timezone="UTC")
        with patch.object(self.cache, 'set', wraps=self.cache.set) as mock_set:
            process("weather tomorrow", {"days_ahead": 1}, s)
        mock_set.assert_called_once_with(
            expected_key,
            "It is 20°C in London.",
            ttl_s=s.config.cache_weather_forecast_ttl_s,
            max_stale_s=s.config.cache_weather_forecast_max_stale_s,
        )

    @patch('plugins.weather.plugin.OpenWeatherReader')
    def test_forecast_cache_key_includes_days_ahead(self, MockReader):
        forecast_slots = [{"dt": 1700000000, "main": {"temp": 15}}]
        MockReader.return_value.get_forecast.return_value = forecast_slots
        s = _make_sandvoice(cache=self.cache)
        from plugins.weather import _cache_key as ck, process
        # Compute expected_key before process() so both use the same local date.
        expected_key = ck("London", "metric", 1, timezone="UTC")
        with patch.object(self.cache, 'get', wraps=self.cache.get) as mock_get, \
             patch.object(self.cache, 'set', wraps=self.cache.set) as mock_set:
            process("weather tomorrow", {"days_ahead": 1}, s)
        mock_get.assert_called_with(expected_key)
        mock_set.assert_called_once()
        call_args = mock_set.call_args
        self.assertEqual(call_args[0][0], expected_key)


class TestGetForecast(unittest.TestCase):
    """Unit tests for OpenWeatherReader.get_forecast()."""

    def setUp(self):
        os.environ['OPENWEATHERMAP_API_KEY'] = 'test-key'

    def tearDown(self):
        os.environ.pop('OPENWEATHERMAP_API_KEY', None)

    def _make_forecast_payload(self, slots, tz_offset=0):
        """Build a minimal forecast API response payload."""
        return {
            "city": {"name": "London", "timezone": tz_offset},
            "list": slots,
        }

    def _make_slot(self, dt_unix, temp=15, desc="cloudy"):
        return {"dt": dt_unix, "main": {"temp": temp}, "weather": [{"description": desc}]}

    @patch('plugins.weather.plugin.requests.get')
    def test_get_forecast_filters_by_target_date(self, mock_get):
        import datetime as dt_mod
        # Freeze "now" via _now injection to avoid midnight flakiness
        tz = dt_mod.timezone.utc
        fixed_now = dt_mod.datetime(2026, 6, 1, 10, 0, 0, tzinfo=tz)

        # Slot on tomorrow at noon UTC
        tomorrow_noon = (fixed_now + dt_mod.timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
        # Slot on the day after tomorrow at noon UTC
        day_after = (fixed_now + dt_mod.timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0)

        tomorrow_slot = self._make_slot(int(tomorrow_noon.timestamp()), temp=10, desc="rain")
        other_slot = self._make_slot(int(day_after.timestamp()), temp=20, desc="sunny")
        payload = self._make_forecast_payload([tomorrow_slot, other_slot], tz_offset=0)

        mock_resp = Mock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        from plugins.weather import OpenWeatherReader
        reader = OpenWeatherReader("London", "metric", timeout=5)
        result = reader.get_forecast(1, _now=fixed_now)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["dt"], tomorrow_slot["dt"])

    @patch('plugins.weather.plugin.requests.get')
    def test_get_forecast_falls_back_to_full_list_if_no_match(self, mock_get):
        import datetime as dt_mod
        # Freeze "now" via _now injection to avoid midnight flakiness
        tz = dt_mod.timezone.utc
        fixed_now = dt_mod.datetime(2026, 6, 1, 10, 0, 0, tzinfo=tz)

        # Slot is on fixed_now's date (2026-06-01); filtering for days_ahead=5
        # finds nothing (target = 2026-06-06) → full-list fallback
        today_noon = fixed_now.replace(hour=12, minute=0, second=0, microsecond=0)
        slot = self._make_slot(int(today_noon.timestamp()))
        payload = self._make_forecast_payload([slot], tz_offset=0)

        mock_resp = Mock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        from plugins.weather import OpenWeatherReader
        reader = OpenWeatherReader("London", "metric", timeout=5)
        # Request days_ahead=5; slot is today so filtering finds nothing → full list returned
        result = reader.get_forecast(5, _now=fixed_now)
        self.assertEqual(result, [slot])

    @patch('plugins.weather.plugin.requests.get')
    def test_get_forecast_filters_by_local_date_non_utc_offset(self, mock_get):
        # Validate timezone-aware filtering with a non-zero city.timezone offset.
        # tz_offset = +36000s (UTC+10, e.g. Sydney).
        # _now is 2026-06-01 22:00 UTC = 2026-06-02 08:00 local.
        # days_ahead=1 → target local date = 2026-06-03.
        import datetime as dt_mod
        utc = dt_mod.timezone.utc
        fixed_now_utc = dt_mod.datetime(2026, 6, 1, 22, 0, 0, tzinfo=utc)
        tz_offset_s = 36000  # UTC+10
        local_tz = dt_mod.timezone(dt_mod.timedelta(seconds=tz_offset_s))

        # Slot on 2026-06-03 local (2026-06-02 14:00 UTC) — should be included
        target_local = dt_mod.datetime(2026, 6, 3, 10, 0, 0, tzinfo=local_tz)
        match_slot = self._make_slot(int(target_local.timestamp()), temp=22, desc="sunny")
        # Slot on 2026-06-02 local (today) — should be excluded
        today_local = dt_mod.datetime(2026, 6, 2, 10, 0, 0, tzinfo=local_tz)
        other_slot = self._make_slot(int(today_local.timestamp()), temp=15, desc="cloudy")

        payload = self._make_forecast_payload([match_slot, other_slot], tz_offset=tz_offset_s)

        mock_resp = Mock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        from plugins.weather import OpenWeatherReader
        reader = OpenWeatherReader("Sydney,AU", "metric", timeout=5)
        result = reader.get_forecast(1, _now=fixed_now_utc)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["dt"], match_slot["dt"])

    @patch('plugins.weather.plugin.requests.get')
    def test_get_forecast_returns_error_on_request_exception(self, mock_get):
        mock_get.side_effect = req_lib.exceptions.ConnectionError("network down")
        from plugins.weather import OpenWeatherReader
        reader = OpenWeatherReader("London", "metric", timeout=5)
        result = reader.get_forecast(1)
        self.assertIn("error", result)
