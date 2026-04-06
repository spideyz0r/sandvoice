import importlib
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from common.cache import VoiceCache

hn_plugin = importlib.import_module('plugins.hacker_news')
hn_plugin_module = importlib.import_module('plugins.hacker_news.plugin')

_BRIEFS = [
    {
        'id': 1,
        'title': 'Test Story',
        'url': 'https://example.com',
        'score': 123,
        'comments': 45,
        'by': 'alice',
        'time': '2026-02-03T12:00:00',
        'text': '',
    }
]


def _make_s(cache=None):
    s = Mock()
    s.config = Mock(api_timeout=10, debug=False)
    s.ai = Mock()
    s.ai.generate_response.return_value = Mock(content='Top HN stories today...')
    s.cache = cache
    return s


class TestHackerNewsPlugin(unittest.TestCase):
    def test_process_returns_friendly_message_when_no_stories(self):
        s = _make_s()
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', return_value=[]):
            result = hn_plugin.process('gimme the hacker news', {'route': 'hacker-news'}, s)
        self.assertIn('couldn\'t fetch', result.lower())

    def test_process_calls_generate_response_with_briefs(self):
        s = _make_s()
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', return_value=_BRIEFS):
            result = hn_plugin.process('gimme the hacker news', {'route': 'hacker-news'}, s)
        self.assertEqual(result, 'Top HN stories today...')
        self.assertTrue(s.ai.generate_response.called)
        args, _kwargs = s.ai.generate_response.call_args
        self.assertEqual(args[0], 'gimme the hacker news')
        self.assertIn('Hacker News', args[1])
        self.assertIn('podcast', args[1])
        self.assertIn('opinion', args[1])


class TestHackerNewsPluginCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache = VoiceCache(os.path.join(self.tmp, 'cache.db'))

    def tearDown(self):
        self.cache.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_cache_hit_skips_fetch_and_llm(self):
        self.cache.set(
            hn_plugin_module._CACHE_KEY, 'Cached HN response',
            ttl_s=28800, max_stale_s=43200,
        )
        s = _make_s(cache=self.cache)
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs') as mock_fetch:
            result = hn_plugin.process('hacker news', {'route': 'hacker-news'}, s)
        mock_fetch.assert_not_called()
        s.ai.generate_response.assert_not_called()
        self.assertEqual(result, 'Cached HN response')

    def test_cache_miss_fetches_and_populates_cache(self):
        s = _make_s(cache=self.cache)
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', return_value=_BRIEFS):
            result = hn_plugin.process('hacker news', {'route': 'hacker-news'}, s)
        self.assertEqual(result, 'Top HN stories today...')
        entry = self.cache.get(hn_plugin_module._CACHE_KEY)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, 'Top HN stories today...')

    def test_refresh_only_updates_cache_and_returns_none(self):
        s = _make_s(cache=self.cache)
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', return_value=_BRIEFS):
            result = hn_plugin.process(
                'hacker news', {'route': 'hacker-news', 'refresh_only': True}, s
            )
        self.assertIsNone(result)
        entry = self.cache.get(hn_plugin_module._CACHE_KEY)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, 'Top HN stories today...')

    def test_refresh_only_no_stories_returns_none(self):
        s = _make_s(cache=self.cache)
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', return_value=[]):
            result = hn_plugin.process(
                'hacker news', {'route': 'hacker-news', 'refresh_only': True}, s
            )
        self.assertIsNone(result)

    def test_route_ttl_overrides_default(self):
        s = _make_s(cache=self.cache)
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', return_value=_BRIEFS):
            hn_plugin.process(
                'hacker news',
                {'route': 'hacker-news', 'ttl_s': 999, 'max_stale_s': 1999},
                s,
            )
        entry = self.cache.get(hn_plugin_module._CACHE_KEY)
        self.assertEqual(entry.ttl_s, 999)
        self.assertEqual(entry.max_stale_s, 1999)

    def test_no_cache_still_returns_response(self):
        s = _make_s(cache=None)
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', return_value=_BRIEFS):
            result = hn_plugin.process('hacker news', {'route': 'hacker-news'}, s)
        self.assertEqual(result, 'Top HN stories today...')


class TestHackerNewsClient(unittest.TestCase):
    def test_get_best_story_briefs_uses_api_only(self):
        hn = hn_plugin.HackerNews(timeout=1)
        hn.limit = 2

        def fake_get(url, timeout=None):
            r = Mock()
            r.raise_for_status.return_value = None
            if url.endswith('beststories.json'):
                r.json.return_value = [10, 11]
            elif url.endswith('item/10.json'):
                r.json.return_value = {'id': 10, 'title': 'A', 'score': 1, 'descendants': 2, 'by': 'x', 'time': 1}
            elif url.endswith('item/11.json'):
                r.json.return_value = {'id': 11, 'title': 'B', 'url': 'https://b.example', 'score': 3, 'descendants': 4, 'by': 'y', 'time': 2}
            else:
                raise AssertionError(f'Unexpected URL: {url}')
            return r

        with patch.object(hn_plugin_module.requests, 'get', side_effect=fake_get):
            briefs = hn.get_best_story_briefs()

        self.assertEqual(len(briefs), 2)
        self.assertEqual(briefs[0]['id'], 10)
        self.assertEqual(briefs[0]['title'], 'A')
        self.assertIn('score', briefs[0])
        self.assertIn('comments', briefs[0])


class TestHackerNewsPluginExceptions(unittest.TestCase):
    def test_cache_read_exception_falls_through_to_live(self):
        bad_cache = Mock()
        bad_cache.get.side_effect = RuntimeError("db locked")
        s = _make_s(cache=bad_cache)
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', return_value=_BRIEFS):
            result = hn_plugin.process('hacker news', {'route': 'hacker-news'}, s)
        self.assertEqual(result, 'Top HN stories today...')

    def test_cache_write_exception_still_returns_response(self):
        bad_cache = Mock()
        bad_cache.get.return_value = None
        bad_cache.set.side_effect = RuntimeError("db locked")
        s = _make_s(cache=bad_cache)
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', return_value=_BRIEFS):
            result = hn_plugin.process('hacker news', {'route': 'hacker-news'}, s)
        self.assertEqual(result, 'Top HN stories today...')

    def test_outer_exception_returns_error_string(self):
        s = _make_s()
        s.config.api_timeout = 10
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', side_effect=Exception("boom")):
            result = hn_plugin.process('hacker news', {'route': 'hacker-news'}, s)
        self.assertIn('Unable to fetch', result)

    def test_outer_exception_with_refresh_only_returns_none(self):
        s = _make_s()
        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', side_effect=Exception("boom")):
            result = hn_plugin.process('hacker news', {'route': 'hacker-news', 'refresh_only': True}, s)
        self.assertIsNone(result)


class TestHackerNewsGetBestStories(unittest.TestCase):
    def test_get_best_stories_returns_titles_and_urls(self):
        hn = hn_plugin.HackerNews(timeout=1)
        hn.limit = 1

        def fake_get(url, timeout=None):
            r = Mock()
            r.raise_for_status.return_value = None
            if url.endswith('beststories.json'):
                r.json.return_value = [42]
            elif url.endswith('item/42.json'):
                r.json.return_value = {'id': 42, 'title': 'Story Title', 'url': 'https://example.com'}
            return r

        with patch.object(hn_plugin_module.requests, 'get', side_effect=fake_get):
            stories = hn.get_best_stories()

        self.assertEqual(len(stories), 1)
        self.assertIn('Story Title', stories[0])
        self.assertIn('https://example.com', stories[0])


class TestHackerNewsCacheKey(unittest.TestCase):
    def test_cache_key_is_stable(self):
        self.assertEqual(hn_plugin_module._cache_key(), 'hacker-news:best')

    def test_cache_key_matches_constant(self):
        self.assertEqual(hn_plugin_module._cache_key(), hn_plugin_module._CACHE_KEY)


if __name__ == '__main__':
    unittest.main()
