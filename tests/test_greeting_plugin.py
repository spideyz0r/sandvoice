import unittest
from unittest.mock import MagicMock, patch


def _make_s(cache=None):
    s = MagicMock()
    s.cache = cache
    s.config.location = "Toronto,ON,CA"
    s._plugin_manifests = []
    return s


class TestGreetingCacheKey(unittest.TestCase):
    def _key_for_hour(self, hour):
        from plugins.greeting.plugin import _cache_key
        config = MagicMock()
        config.timezone = None
        with patch("plugins.greeting.plugin.datetime") as mock_dt:
            mock_dt.now.return_value.hour = hour
            return _cache_key(config)

    def test_morning_bucket(self):
        for hour in range(5, 12):
            self.assertEqual(self._key_for_hour(hour), "greeting:morning")

    def test_afternoon_bucket(self):
        for hour in range(12, 18):
            self.assertEqual(self._key_for_hour(hour), "greeting:afternoon")

    def test_evening_bucket(self):
        for hour in range(18, 22):
            self.assertEqual(self._key_for_hour(hour), "greeting:evening")

    def test_night_bucket_late(self):
        for hour in range(22, 24):
            self.assertEqual(self._key_for_hour(hour), "greeting:night")

    def test_night_bucket_early(self):
        for hour in range(0, 5):
            self.assertEqual(self._key_for_hour(hour), "greeting:night")

    def test_valid_timezone_used_when_available(self):
        """_cache_key resolves the bucket using config.timezone when it is a valid IANA zone."""
        from plugins.greeting.plugin import _cache_key
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            self.skipTest("zoneinfo not available")

        config = MagicMock()
        config.timezone = "UTC"
        # Just verify no exception is raised and the result is a valid bucket.
        result = _cache_key(config)
        self.assertIn(result, [
            "greeting:morning", "greeting:afternoon",
            "greeting:evening", "greeting:night",
        ])

    def test_invalid_timezone_falls_back_to_local(self):
        """_cache_key logs a warning and falls back to local time for an unresolvable TZ."""
        from plugins.greeting.plugin import _cache_key
        try:
            from zoneinfo import ZoneInfo  # noqa: F401
        except ImportError:
            self.skipTest("zoneinfo not available")

        config = MagicMock()
        config.timezone = "INVALID/TIMEZONE"

        with self.assertLogs("plugins.greeting.plugin", level="WARNING"):
            result = _cache_key(config)

        self.assertIn(result, [
            "greeting:morning", "greeting:afternoon",
            "greeting:evening", "greeting:night",
        ])


class TestGreetingCacheHit(unittest.TestCase):
    def test_cache_hit_returns_cached_text_without_llm(self):
        from plugins.greeting.plugin import process

        cache = MagicMock()
        entry = MagicMock()
        entry.value = "Bom dia! Está 12°C e parcialmente nublado."
        cache.get.return_value = entry
        cache.can_serve.return_value = True

        s = _make_s(cache=cache)
        route = {}

        with patch("plugins.greeting.plugin._cache_key", return_value="greeting:morning"):
            result = process("bom dia", route, s)

        self.assertEqual(result, "Bom dia! Está 12°C e parcialmente nublado.")
        s.ai.generate_response.assert_not_called()

    def test_cache_miss_calls_llm_and_stores_result(self):
        from plugins.greeting.plugin import process

        cache = MagicMock()
        cache.get.return_value = None

        s = _make_s(cache=cache)
        s.ai.define_route.return_value = {"route": "weather"}
        s.route_message.return_value = "12°C, partly cloudy"
        s.ai.generate_response.return_value.content = "Good morning! It's 12°C outside."

        route = {}

        with patch("plugins.greeting.plugin._cache_key", return_value="greeting:morning"), \
             patch("plugins.greeting.plugin.build_extra_routes_text", return_value=""):
            result = process("bom dia", route, s)

        self.assertEqual(result, "Good morning! It's 12°C outside.")
        cache.set.assert_called_once()
        args = cache.set.call_args
        self.assertEqual(args[0][0], "greeting:morning")
        self.assertEqual(args[0][1], "Good morning! It's 12°C outside.")

    def test_stale_entry_served_from_cache(self):
        from plugins.greeting.plugin import process

        cache = MagicMock()
        entry = MagicMock()
        entry.value = "Boa tarde!"
        cache.get.return_value = entry
        cache.can_serve.return_value = True

        s = _make_s(cache=cache)

        with patch("plugins.greeting.plugin._cache_key", return_value="greeting:afternoon"):
            result = process("boa tarde", {}, s)

        self.assertEqual(result, "Boa tarde!")
        s.ai.generate_response.assert_not_called()


class TestGreetingRefreshOnly(unittest.TestCase):
    def test_refresh_only_stores_and_returns_none(self):
        from plugins.greeting.plugin import process

        cache = MagicMock()
        cache.get.return_value = None

        s = _make_s(cache=cache)
        s.ai.define_route.return_value = {"route": "weather"}
        s.route_message.return_value = "12°C"
        s.ai.generate_response.return_value.content = "Boa noite! Está fresco."

        route = {"refresh_only": True}

        with patch("plugins.greeting.plugin._cache_key", return_value="greeting:night"), \
             patch("plugins.greeting.plugin.build_extra_routes_text", return_value=""):
            result = process("boa noite", route, s)

        self.assertIsNone(result)
        cache.set.assert_called_once()

    def test_refresh_only_skips_cache_read(self):
        from plugins.greeting.plugin import process

        cache = MagicMock()
        cache.get.return_value = MagicMock()
        cache.can_serve.return_value = True

        s = _make_s(cache=cache)
        s.ai.define_route.return_value = {"route": "weather"}
        s.route_message.return_value = "12°C"
        s.ai.generate_response.return_value.content = "Bom dia!"

        route = {"refresh_only": True}

        with patch("plugins.greeting.plugin._cache_key", return_value="greeting:morning"), \
             patch("plugins.greeting.plugin.build_extra_routes_text", return_value=""):
            result = process("bom dia", route, s)

        self.assertIsNone(result)
        # LLM was called despite cache having an entry (refresh_only bypasses read)
        s.ai.generate_response.assert_called_once()


class TestGreetingCacheFailure(unittest.TestCase):
    def test_cache_read_failure_falls_through_to_live(self):
        from plugins.greeting.plugin import process

        cache = MagicMock()
        cache.get.side_effect = Exception("db locked")

        s = _make_s(cache=cache)
        s.ai.define_route.return_value = {"route": "weather"}
        s.route_message.return_value = "12°C"
        s.ai.generate_response.return_value.content = "Bom dia!"

        with patch("plugins.greeting.plugin._cache_key", return_value="greeting:morning"), \
             patch("plugins.greeting.plugin.build_extra_routes_text", return_value=""), \
             self.assertLogs("plugins.greeting.plugin", level="WARNING"):
            result = process("bom dia", {}, s)

        self.assertEqual(result, "Bom dia!")

    def test_cache_write_failure_still_returns_response(self):
        from plugins.greeting.plugin import process

        cache = MagicMock()
        cache.get.return_value = None
        cache.set.side_effect = Exception("disk full")

        s = _make_s(cache=cache)
        s.ai.define_route.return_value = {"route": "weather"}
        s.route_message.return_value = "12°C"
        s.ai.generate_response.return_value.content = "Boa tarde!"

        with patch("plugins.greeting.plugin._cache_key", return_value="greeting:afternoon"), \
             patch("plugins.greeting.plugin.build_extra_routes_text", return_value=""), \
             self.assertLogs("plugins.greeting.plugin", level="WARNING"):
            result = process("boa tarde", {}, s)

        self.assertEqual(result, "Boa tarde!")


class TestGreetingLiveGenerationFailure(unittest.TestCase):
    def test_llm_error_returns_friendly_message(self):
        """When the LLM call raises, process() returns a friendly string and does not re-raise."""
        from plugins.greeting.plugin import process

        s = _make_s(cache=None)
        s.ai.define_route.return_value = {"route": "weather"}
        s.route_message.return_value = "12°C"
        s.ai.generate_response.side_effect = Exception("API timeout")

        with patch("plugins.greeting.plugin._cache_key", return_value="greeting:morning"), \
             patch("plugins.greeting.plugin.build_extra_routes_text", return_value=""), \
             self.assertLogs("plugins.greeting.plugin", level="ERROR"):
            result = process("bom dia", {}, s)

        self.assertIsInstance(result, str)
        self.assertNotEqual(result, "")

    def test_llm_error_with_refresh_only_returns_none(self):
        """When the LLM call raises during a background refresh, process() returns None."""
        from plugins.greeting.plugin import process

        s = _make_s(cache=None)
        s.ai.define_route.return_value = {"route": "weather"}
        s.route_message.return_value = "12°C"
        s.ai.generate_response.side_effect = Exception("API timeout")

        with patch("plugins.greeting.plugin._cache_key", return_value="greeting:morning"), \
             patch("plugins.greeting.plugin.build_extra_routes_text", return_value=""), \
             self.assertLogs("plugins.greeting.plugin", level="ERROR"):
            result = process("bom dia", {"refresh_only": True}, s)

        self.assertIsNone(result)


class TestGreetingNoCacheConfigured(unittest.TestCase):
    def test_no_cache_still_generates_response(self):
        from plugins.greeting.plugin import process

        s = _make_s(cache=None)
        s.ai.define_route.return_value = {"route": "weather"}
        s.route_message.return_value = "12°C"
        s.ai.generate_response.return_value.content = "Boa noite!"

        with patch("plugins.greeting.plugin._cache_key", return_value="greeting:night"), \
             patch("plugins.greeting.plugin.build_extra_routes_text", return_value=""):
            result = process("boa noite", {}, s)

        self.assertEqual(result, "Boa noite!")


if __name__ == "__main__":
    unittest.main()
