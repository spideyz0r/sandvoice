import importlib
import unittest
from unittest.mock import Mock, patch


hn_plugin = importlib.import_module('plugins.hacker-news')


class TestHackerNewsPlugin(unittest.TestCase):
    def test_process_returns_friendly_message_when_no_stories(self):
        s = Mock()
        s.config = Mock(api_timeout=10, debug=False)
        s.ai = Mock()

        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', return_value=[]):
            result = hn_plugin.process('gimme the hacker news', {'route': 'hacker-news'}, s)

        self.assertIn('couldn\'t fetch', result.lower())

    def test_process_calls_generate_response_with_briefs(self):
        s = Mock()
        s.config = Mock(api_timeout=10, debug=False)
        s.ai = Mock()
        s.ai.generate_response.return_value = Mock(content='ok')

        briefs = [
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

        with patch.object(hn_plugin.HackerNews, 'get_best_story_briefs', return_value=briefs):
            result = hn_plugin.process('gimme the hacker news', {'route': 'hacker-news'}, s)

        self.assertEqual(result, 'ok')
        self.assertTrue(s.ai.generate_response.called)
        args, _kwargs = s.ai.generate_response.call_args
        self.assertEqual(args[0], 'gimme the hacker news')
        self.assertIn('Hacker News', args[1])
        self.assertIn('podcast', args[1])
        self.assertIn('take away', args[1])


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

        with patch.object(hn_plugin.requests, 'get', side_effect=fake_get):
            briefs = hn.get_best_story_briefs()

        self.assertEqual(len(briefs), 2)
        self.assertEqual(briefs[0]['id'], 10)
        self.assertEqual(briefs[0]['title'], 'A')
        self.assertIn('score', briefs[0])
        self.assertIn('comments', briefs[0])


if __name__ == '__main__':
    unittest.main()
