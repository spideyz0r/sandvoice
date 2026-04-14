import unittest
from unittest.mock import MagicMock

from plugins.realtime_websearch.plugin import _strip_urls, process


class TestStripUrls(unittest.TestCase):
    def test_removes_parenthesised_markdown_link(self):
        text = "Brazil plays June 13. ([fifa.com](https://fifa.com/schedule))"
        self.assertEqual(_strip_urls(text), "Brazil plays June 13.")

    def test_removes_parenthesised_url(self):
        text = "First game is vs Morocco (https://fifa.com/match)."
        result = _strip_urls(text)
        self.assertNotIn("https://", result)

    def test_removes_bare_url(self):
        text = "See https://example.com for more."
        result = _strip_urls(text)
        self.assertNotIn("https://", result)

    def test_markdown_link_keeps_label(self):
        text = "Check the [FIFA schedule](https://fifa.com) for details."
        result = _strip_urls(text)
        self.assertIn("FIFA schedule", result)
        self.assertNotIn("https://", result)

    def test_preserves_plain_text_reference(self):
        text = "According to FIFA, Brazil plays on June 13."
        self.assertEqual(_strip_urls(text), text)

    def test_preserves_plain_text(self):
        text = "Brazil's first match is on June 13, 2026."
        self.assertEqual(_strip_urls(text), text)


class TestRealtimeWebsearchProcess(unittest.TestCase):
    def _make_sv(self):
        sv = MagicMock()
        sv.config.debug = False
        sv.config.llm_response_model = "gpt-5-mini"
        return sv

    def test_returns_output_text(self):
        sv = self._make_sv()
        sv.ai.openai_client.responses.create.return_value = MagicMock(
            output_text="Brazil plays on June 13.",
            output=[],
        )
        result = process("Quando é o primeiro jogo?", {"query": "Brazil first game 2026"}, sv)
        self.assertEqual(result, "Brazil plays on June 13.")

    def test_strips_urls_from_output(self):
        sv = self._make_sv()
        sv.ai.openai_client.responses.create.return_value = MagicMock(
            output_text="Brazil plays June 13. ([fifa.com](https://fifa.com/schedule))",
            output=[],
        )
        result = process("Quando?", {"query": "Brazil first game"}, sv)
        self.assertNotIn("https://", result)
        self.assertIn("Brazil plays June 13", result)

    def test_falls_back_to_user_input_when_no_query(self):
        sv = self._make_sv()
        sv.ai.openai_client.responses.create.return_value = MagicMock(
            output_text="Some answer.",
            output=[],
        )
        process("When is the game?", {}, sv)
        call_input = sv.ai.openai_client.responses.create.call_args[1]["input"]
        self.assertIn("When is the game?", call_input)

    def test_instructions_include_language_hint(self):
        sv = self._make_sv()
        sv.ai.openai_client.responses.create.return_value = MagicMock(
            output_text="Resposta.",
            output=[],
        )
        process("Quando é o jogo?", {"query": "Brazil game date"}, sv)
        instructions = sv.ai.openai_client.responses.create.call_args[1]["instructions"]
        self.assertIn("Quando é o jogo?", instructions)

    def test_instructions_prohibit_urls(self):
        sv = self._make_sv()
        sv.ai.openai_client.responses.create.return_value = MagicMock(
            output_text="Answer.",
            output=[],
        )
        process("query", {"query": "q"}, sv)
        instructions = sv.ai.openai_client.responses.create.call_args[1]["instructions"]
        self.assertIn("URL", instructions)

    def test_returns_fallback_on_empty_output(self):
        sv = self._make_sv()
        sv.ai.openai_client.responses.create.return_value = MagicMock(
            output_text="",
            output=[],
        )
        result = process("query", {"query": "q"}, sv)
        self.assertIn("couldn't find", result)

    def test_returns_error_message_on_exception(self):
        sv = self._make_sv()
        sv.ai.openai_client.responses.create.side_effect = Exception("network error")
        result = process("query", {}, sv)
        self.assertIn("error", result.lower())


if __name__ == "__main__":
    unittest.main()
