import importlib
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from common.cache import VoiceCache

news_plugin = importlib.import_module('plugins.news')
news_plugin_module = importlib.import_module('plugins.news.plugin')

_RSS_URL = 'https://feeds.bbci.co.uk/news/rss.xml'
_CACHE_KEY = f'news:{_RSS_URL}'

_NEWS_ITEMS = [
    {
        'title': 'Breaking News',
        'link': 'https://bbc.co.uk/news/1',
        'description': 'Something happened',
        'published': None,
    }
]


def _make_s(cache=None, rss_url=_RSS_URL):
    s = Mock()
    s.config = Mock(
        api_timeout=10,
        debug=False,
        rss_news=rss_url,
        rss_news_max_items='5',
    )
    s.ai = Mock()
    s.ai.generate_response.return_value = Mock(content='Here are the latest headlines...')
    s.cache = cache
    return s


class TestNewsPluginNoCache(unittest.TestCase):
    def test_returns_response_on_success(self):
        s = _make_s()
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            result = news_plugin.process('latest news', {'route': 'news'}, s)
        self.assertEqual(result, 'Here are the latest headlines...')

    def test_returns_friendly_message_when_no_news(self):
        s = _make_s()
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=[]):
            result = news_plugin.process('latest news', {'route': 'news'}, s)
        self.assertIn("couldn't fetch", result.lower())

    def test_uses_rss_url_from_route(self):
        s = _make_s()
        custom_url = 'https://custom.feed/rss.xml'
        with patch.object(news_plugin_module.RSSReader, '__init__', return_value=None) as mock_init, \
             patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            news_plugin.process('news', {'route': 'news', 'rss_url': custom_url}, s)
        mock_init.assert_called_once_with(custom_url, 5)

    def test_falls_back_to_config_rss_url(self):
        s = _make_s(rss_url=_RSS_URL)
        with patch.object(news_plugin_module.RSSReader, '__init__', return_value=None) as mock_init, \
             patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            news_plugin.process('news', {'route': 'news'}, s)
        mock_init.assert_called_once_with(_RSS_URL, 5)

    def test_whitespace_rss_url_falls_back_to_config(self):
        s = _make_s(rss_url=_RSS_URL)
        with patch.object(news_plugin_module.RSSReader, '__init__', return_value=None) as mock_init, \
             patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            news_plugin.process('news', {'route': 'news', 'rss_url': '   '}, s)
        mock_init.assert_called_once_with(_RSS_URL, 5)

    def test_rss_url_from_route_stripped(self):
        padded_url = f'  {_RSS_URL}  '
        s = _make_s(rss_url='https://fallback.example.com/rss')
        with patch.object(news_plugin_module.RSSReader, '__init__', return_value=None) as mock_init, \
             patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            news_plugin.process('news', {'route': 'news', 'rss_url': padded_url}, s)
        mock_init.assert_called_once_with(_RSS_URL, 5)

    def test_non_string_rss_url_falls_back_to_config(self):
        s = _make_s(rss_url=_RSS_URL)
        with patch.object(news_plugin_module.RSSReader, '__init__', return_value=None) as mock_init, \
             patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            news_plugin.process('news', {'route': 'news', 'rss_url': 123}, s)
        mock_init.assert_called_once_with(_RSS_URL, 5)

    def test_refresh_only_returns_none(self):
        s = _make_s()
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            result = news_plugin.process('news', {'route': 'news', 'refresh_only': True}, s)
        self.assertIsNone(result)

    def test_refresh_only_no_news_returns_none(self):
        s = _make_s()
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=[]):
            result = news_plugin.process('news', {'route': 'news', 'refresh_only': True}, s)
        self.assertIsNone(result)


class TestNewsPluginWithCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache = VoiceCache(os.path.join(self.tmp, 'cache.db'))

    def tearDown(self):
        self.cache.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_cache_hit_skips_fetch_and_llm(self):
        self.cache.set(_CACHE_KEY, 'Cached news response', ttl_s=7200, max_stale_s=14400)
        s = _make_s(cache=self.cache)
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news') as mock_fetch:
            result = news_plugin.process('latest news', {'route': 'news'}, s)
        mock_fetch.assert_not_called()
        s.ai.generate_response.assert_not_called()
        self.assertEqual(result, 'Cached news response')

    def test_cache_miss_fetches_and_populates_cache(self):
        s = _make_s(cache=self.cache)
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            result = news_plugin.process('latest news', {'route': 'news'}, s)
        self.assertEqual(result, 'Here are the latest headlines...')
        entry = self.cache.get(_CACHE_KEY)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, 'Here are the latest headlines...')

    def test_refresh_only_updates_cache_and_returns_none(self):
        s = _make_s(cache=self.cache)
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            result = news_plugin.process(
                'latest news', {'route': 'news', 'refresh_only': True}, s
            )
        self.assertIsNone(result)
        entry = self.cache.get(_CACHE_KEY)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, 'Here are the latest headlines...')

    def test_cache_keyed_by_rss_url(self):
        custom_url = 'https://example.com/feed.rss'
        custom_key = f'news:{custom_url}'
        s = _make_s(cache=self.cache)
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            news_plugin.process(
                'latest news', {'route': 'news', 'rss_url': custom_url}, s
            )
        # Should be stored under the custom URL key, not the default
        self.assertIsNotNone(self.cache.get(custom_key))
        self.assertIsNone(self.cache.get(_CACHE_KEY))

    def test_route_ttl_overrides_default(self):
        s = _make_s(cache=self.cache)
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            news_plugin.process(
                'news', {'route': 'news', 'ttl_s': 999, 'max_stale_s': 1999}, s
            )
        entry = self.cache.get(_CACHE_KEY)
        self.assertEqual(entry.ttl_s, 999)
        self.assertEqual(entry.max_stale_s, 1999)


class TestNewsPluginExceptions(unittest.TestCase):
    def test_cache_read_exception_falls_through_to_live(self):
        bad_cache = Mock()
        bad_cache.get.side_effect = RuntimeError("db locked")
        s = _make_s(cache=bad_cache)
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            result = news_plugin.process('news', {'route': 'news'}, s)
        self.assertEqual(result, 'Here are the latest headlines...')

    def test_cache_write_exception_still_returns_response(self):
        bad_cache = Mock()
        bad_cache.get.return_value = None
        bad_cache.set.side_effect = RuntimeError("db locked")
        s = _make_s(cache=bad_cache)
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', return_value=_NEWS_ITEMS):
            result = news_plugin.process('news', {'route': 'news'}, s)
        self.assertEqual(result, 'Here are the latest headlines...')

    def test_outer_exception_returns_error_string(self):
        s = _make_s()
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', side_effect=Exception("boom")):
            result = news_plugin.process('news', {'route': 'news'}, s)
        self.assertIn('Unable to fetch', result)

    def test_outer_exception_with_refresh_only_returns_none(self):
        s = _make_s()
        with patch.object(news_plugin_module.RSSReader, 'get_latest_news', side_effect=Exception("boom")):
            result = news_plugin.process('news', {'route': 'news', 'refresh_only': True}, s)
        self.assertIsNone(result)


class TestRSSReader(unittest.TestCase):
    def test_get_latest_news_parses_entries(self):
        reader = news_plugin_module.RSSReader('https://example.com/rss', max_items=2)
        mock_feed = Mock()
        mock_feed.bozo_exception = None
        mock_feed.entries = [
            Mock(**{'get.side_effect': lambda k, d=None: {'title': 'Story 1', 'link': 'https://a.com', 'description': 'desc', 'published_parsed': None}.get(k, d)}),
        ]
        with patch.object(news_plugin_module.feedparser, 'parse', return_value=mock_feed):
            items = reader.get_latest_news()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'Story 1')

    def test_get_latest_news_returns_empty_on_error(self):
        reader = news_plugin_module.RSSReader('https://bad.url/rss')
        with patch.object(news_plugin_module.feedparser, 'parse', side_effect=Exception("network error")):
            items = reader.get_latest_news()
        self.assertEqual(items, [])


class TestNewsCacheKey(unittest.TestCase):
    def test_cache_key_includes_url(self):
        key = news_plugin_module._cache_key('https://example.com/rss')
        self.assertEqual(key, 'news:https://example.com/rss')

    def test_different_urls_produce_different_keys(self):
        key1 = news_plugin_module._cache_key('https://bbc.co.uk/rss')
        key2 = news_plugin_module._cache_key('https://reuters.com/rss')
        self.assertNotEqual(key1, key2)


if __name__ == '__main__':
    unittest.main()
