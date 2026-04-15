import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock

from common.ai import (
    AI, ErrorMessage, pop_streaming_chunk,
    _build_llm_provider, _build_tts_provider, _build_stt_provider,
)
from common.providers import OpenAILLMProvider, OpenAITTSProvider, OpenAISTTProvider
from common.providers.base import LLMProvider, TTSProvider, STTProvider


def _make_config(**kwargs):
    config = Mock()
    config.botname = "TestBot"
    config.api_timeout = 10
    config.api_retry_attempts = 3
    config.llm_provider = "openai"
    config.tts_provider = "openai"
    config.stt_provider = "openai"
    config.debug = False
    config.enable_error_logging = False
    config.error_log_path = "/tmp/test-error.log"
    for k, v in kwargs.items():
        setattr(config, k, v)
    return config


def _make_providers():
    llm = MagicMock(spec=LLMProvider)
    tts = MagicMock(spec=TTSProvider)
    stt = MagicMock(spec=STTProvider)
    return llm, tts, stt


# ---------------------------------------------------------------------------
# ErrorMessage
# ---------------------------------------------------------------------------

class TestErrorMessage(unittest.TestCase):
    def test_content_stored(self):
        msg = ErrorMessage("Test error")
        self.assertEqual(msg.content, "Test error")


# ---------------------------------------------------------------------------
# AI.__init__
# ---------------------------------------------------------------------------

class TestAIInit(unittest.TestCase):
    def test_stores_providers_and_config(self):
        llm, tts, stt = _make_providers()
        config = _make_config()
        ai = AI(llm, tts, stt, config)
        self.assertIs(ai._llm, llm)
        self.assertIs(ai._tts, tts)
        self.assertIs(ai._stt, stt)
        self.assertIs(ai.config, config)

    def test_conversation_history_starts_empty(self):
        ai = AI(*_make_providers(), _make_config())
        self.assertEqual(ai.conversation_history, [])


# ---------------------------------------------------------------------------
# AI.from_config
# ---------------------------------------------------------------------------

class TestAIFromConfig(unittest.TestCase):
    def setUp(self):
        self.orig_key = os.environ.get('OPENAI_API_KEY')
        os.environ['OPENAI_API_KEY'] = 'test-key'

    def tearDown(self):
        if self.orig_key is not None:
            os.environ['OPENAI_API_KEY'] = self.orig_key
        else:
            os.environ.pop('OPENAI_API_KEY', None)

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_returns_ai_instance(self, mock_setup, mock_openai):
        config = _make_config()
        ai = AI.from_config(config)
        self.assertIsInstance(ai, AI)
        self.assertEqual(ai.conversation_history, [])

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_calls_setup_error_logging(self, mock_setup, mock_openai):
        config = _make_config()
        AI.from_config(config)
        mock_setup.assert_called_once_with(config)

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_creates_openai_client_with_timeout(self, mock_setup, mock_openai):
        config = _make_config(api_timeout=15)
        AI.from_config(config)
        mock_openai.assert_called_once_with(timeout=15)

    def test_raises_on_missing_api_key(self):
        del os.environ['OPENAI_API_KEY']
        config = _make_config()
        with self.assertRaises(ValueError) as ctx:
            AI.from_config(config)
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))

    def test_unknown_provider_raises_before_api_key_check(self):
        # Provider validation must happen before the API key check so a
        # misconfigured provider name gives the actionable error, not a
        # misleading "Missing OPENAI_API_KEY" message.
        del os.environ['OPENAI_API_KEY']
        config = _make_config(llm_provider="mistral")
        with self.assertRaises(ValueError) as ctx:
            AI.from_config(config)
        self.assertIn("llm_provider", str(ctx.exception))
        self.assertNotIn("OPENAI_API_KEY", str(ctx.exception))

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_whitespace_only_provider_defaults_to_openai(self, mock_setup, mock_openai):
        # Whitespace-only provider values must normalize to "openai", not raise
        # Unknown provider: '' — same as None/empty.
        config = _make_config(llm_provider="   ", tts_provider="   ", stt_provider="   ")
        ai = AI.from_config(config)
        self.assertIsInstance(ai, AI)

    def test_ai_has_no_openai_client_property(self):
        self.assertNotIn('openai_client', AI.__dict__)


# ---------------------------------------------------------------------------
# Provider factory helpers
# ---------------------------------------------------------------------------

class TestProviderFactories(unittest.TestCase):
    def setUp(self):
        self.client = Mock()

    def test_build_llm_openai(self):
        config = _make_config(llm_provider="openai")
        provider = _build_llm_provider(config, self.client)
        self.assertIsInstance(provider, OpenAILLMProvider)

    def test_build_tts_openai(self):
        config = _make_config(tts_provider="openai")
        provider = _build_tts_provider(config, self.client)
        self.assertIsInstance(provider, OpenAITTSProvider)

    def test_build_stt_openai(self):
        config = _make_config(stt_provider="openai")
        provider = _build_stt_provider(config, self.client)
        self.assertIsInstance(provider, OpenAISTTProvider)

    def test_unknown_llm_provider_raises(self):
        config = _make_config(llm_provider="unknown")
        with self.assertRaises(ValueError) as ctx:
            _build_llm_provider(config, self.client)
        self.assertIn("unknown", str(ctx.exception))

    def test_unknown_tts_provider_raises(self):
        config = _make_config(tts_provider="unknown")
        with self.assertRaises(ValueError) as ctx:
            _build_tts_provider(config, self.client)
        self.assertIn("unknown", str(ctx.exception))

    def test_unknown_stt_provider_raises(self):
        config = _make_config(stt_provider="unknown")
        with self.assertRaises(ValueError) as ctx:
            _build_stt_provider(config, self.client)
        self.assertIn("unknown", str(ctx.exception))


# ---------------------------------------------------------------------------
# AI.generate_response — history management
# ---------------------------------------------------------------------------

class TestAIGenerateResponse(unittest.TestCase):
    def setUp(self):
        self.llm, self.tts, self.stt = _make_providers()
        self.config = _make_config()
        self.ai = AI(self.llm, self.tts, self.stt, self.config)

    def _mock_result(self, content):
        msg = Mock()
        msg.content = content
        self.llm.generate_response.return_value = msg
        return msg

    def test_delegates_to_llm(self):
        self._mock_result("Hello!")
        result = self.ai.generate_response("hi")
        self.llm.generate_response.assert_called_once_with(
            "hi", [], extra_info=None, model=None
        )
        self.assertEqual(result.content, "Hello!")

    def test_appends_user_and_assistant_to_history(self):
        self._mock_result("Hello!")
        self.ai.generate_response("hi")
        self.assertEqual(len(self.ai.conversation_history), 2)
        self.assertEqual(self.ai.conversation_history[0], "User: hi")
        self.assertEqual(self.ai.conversation_history[1], "TestBot: Hello!")

    def test_passes_prior_history_to_provider(self):
        self.ai.conversation_history = ["User: prev", "TestBot: ok"]
        self._mock_result("Good")
        self.ai.generate_response("next")
        call_args = self.llm.generate_response.call_args
        history_passed = call_args[0][1]
        self.assertEqual(history_passed, ["User: prev", "TestBot: ok"])

    def test_does_not_duplicate_user_turn_on_retry(self):
        self.ai.conversation_history = ["User: hi"]
        self._mock_result("Hi again")
        self.ai.generate_response("hi")
        user_turns = [m for m in self.ai.conversation_history if m == "User: hi"]
        self.assertEqual(len(user_turns), 1)

    def test_extra_info_forwarded(self):
        self._mock_result("Sunny")
        self.ai.generate_response("weather?", extra_info="72F")
        call_kwargs = self.llm.generate_response.call_args[1]
        self.assertEqual(call_kwargs["extra_info"], "72F")

    def test_model_forwarded(self):
        self._mock_result("ok")
        self.ai.generate_response("hi", model="gpt-4")
        call_kwargs = self.llm.generate_response.call_args[1]
        self.assertEqual(call_kwargs["model"], "gpt-4")

    def test_error_message_still_updates_history(self):
        error = ErrorMessage("Sorry, having trouble.")
        self.llm.generate_response.return_value = error
        result = self.ai.generate_response("hi")
        self.assertIsInstance(result, ErrorMessage)
        self.assertEqual(len(self.ai.conversation_history), 2)


# ---------------------------------------------------------------------------
# AI.stream_response_deltas — history management
# ---------------------------------------------------------------------------

class TestAIStreamResponseDeltas(unittest.TestCase):
    def setUp(self):
        self.llm, self.tts, self.stt = _make_providers()
        self.config = _make_config()
        self.ai = AI(self.llm, self.tts, self.stt, self.config)

    def test_yields_deltas(self):
        self.llm.stream_response_deltas.return_value = iter(["Hello", " there", "!"])
        pieces = list(self.ai.stream_response_deltas("hi"))
        self.assertEqual(pieces, ["Hello", " there", "!"])

    def test_appends_user_and_assistant_to_history_on_success(self):
        self.llm.stream_response_deltas.return_value = iter(["Hello", " there"])
        list(self.ai.stream_response_deltas("hi"))
        self.assertEqual(len(self.ai.conversation_history), 2)
        self.assertEqual(self.ai.conversation_history[0], "User: hi")
        self.assertEqual(self.ai.conversation_history[1], "TestBot: Hello there")

    def test_user_turn_in_history_on_stream_failure(self):
        def _broken():
            yield "Hello"
            raise RuntimeError("boom")

        self.llm.stream_response_deltas.return_value = _broken()
        gen = self.ai.stream_response_deltas("hi")
        self.assertEqual(next(gen), "Hello")
        with self.assertRaises(RuntimeError):
            list(gen)
        # User turn present; assistant turn absent.
        self.assertEqual(len(self.ai.conversation_history), 1)
        self.assertEqual(self.ai.conversation_history[0], "User: hi")

    def test_provider_receives_history_without_current_user_turn(self):
        self.ai.conversation_history = ["User: prev", "TestBot: ok"]
        self.llm.stream_response_deltas.return_value = iter(["hi"])
        list(self.ai.stream_response_deltas("next"))
        call_args = self.llm.stream_response_deltas.call_args
        history_passed = call_args[0][1]
        # Should be prior turns only — not include "User: next"
        self.assertEqual(history_passed, ["User: prev", "TestBot: ok"])

    def test_does_not_duplicate_user_turn(self):
        self.ai.conversation_history = ["User: hi"]
        self.llm.stream_response_deltas.return_value = iter(["ok"])
        list(self.ai.stream_response_deltas("hi"))
        user_turns = [m for m in self.ai.conversation_history if m == "User: hi"]
        self.assertEqual(len(user_turns), 1)


# ---------------------------------------------------------------------------
# AI.transcribe_and_translate
# ---------------------------------------------------------------------------

class TestAITranscribeAndTranslate(unittest.TestCase):
    def test_delegates_to_stt(self):
        llm, tts, stt = _make_providers()
        stt.transcribe.return_value = "hello"
        ai = AI(llm, tts, stt, _make_config())
        result = ai.transcribe_and_translate(audio_file_path="/tmp/test.mp3")
        stt.transcribe.assert_called_once_with(audio_file_path="/tmp/test.mp3", model=None)
        self.assertEqual(result, "hello")

    def test_forwards_model(self):
        llm, tts, stt = _make_providers()
        stt.transcribe.return_value = "hello"
        ai = AI(llm, tts, stt, _make_config())
        ai.transcribe_and_translate(model="whisper-1", audio_file_path="/tmp/test.mp3")
        stt.transcribe.assert_called_once_with(audio_file_path="/tmp/test.mp3", model="whisper-1")


# ---------------------------------------------------------------------------
# AI.define_route
# ---------------------------------------------------------------------------

class TestAIDefineRoute(unittest.TestCase):
    def test_delegates_to_llm(self):
        llm, tts, stt = _make_providers()
        llm.define_route.return_value = {"route": "weather", "reason": "weather query"}
        ai = AI(llm, tts, stt, _make_config())
        result = ai.define_route("what is the weather?")
        llm.define_route.assert_called_once_with(
            "what is the weather?", model=None, extra_routes=None
        )
        self.assertEqual(result["route"], "weather")

    def test_forwards_extra_routes(self):
        llm, tts, stt = _make_providers()
        llm.define_route.return_value = {"route": "default-route", "reason": "fallback"}
        ai = AI(llm, tts, stt, _make_config())
        ai.define_route("hi", extra_routes="\n- custom-route: do stuff")
        call_kwargs = llm.define_route.call_args[1]
        self.assertIn("custom-route", call_kwargs["extra_routes"])


# ---------------------------------------------------------------------------
# AI.text_to_speech
# ---------------------------------------------------------------------------

class TestAITextToSpeech(unittest.TestCase):
    def test_delegates_to_tts(self):
        llm, tts, stt = _make_providers()
        tts.text_to_speech.return_value = ["/tmp/tts-001.mp3"]
        ai = AI(llm, tts, stt, _make_config())
        result = ai.text_to_speech("hello")
        tts.text_to_speech.assert_called_once_with("hello", model=None, voice=None)
        self.assertEqual(result, ["/tmp/tts-001.mp3"])

    def test_forwards_model_and_voice(self):
        llm, tts, stt = _make_providers()
        tts.text_to_speech.return_value = []
        ai = AI(llm, tts, stt, _make_config())
        ai.text_to_speech("hi", model="tts-1-hd", voice="nova")
        tts.text_to_speech.assert_called_once_with("hi", model="tts-1-hd", voice="nova")


# ---------------------------------------------------------------------------
# AI.text_summary
# ---------------------------------------------------------------------------

class TestAITextSummary(unittest.TestCase):
    def test_delegates_to_llm(self):
        llm, tts, stt = _make_providers()
        llm.text_summary.return_value = {"title": "T", "text": "S"}
        ai = AI(llm, tts, stt, _make_config())
        result = ai.text_summary("long article")
        llm.text_summary.assert_called_once_with(
            "long article", extra_info=None, words="100", model=None
        )
        self.assertEqual(result["title"], "T")

    def test_forwards_words_and_extra_info(self):
        llm, tts, stt = _make_providers()
        llm.text_summary.return_value = {"title": "T", "text": "S"}
        ai = AI(llm, tts, stt, _make_config())
        ai.text_summary("article", extra_info="recipe", words="50")
        call_kwargs = llm.text_summary.call_args[1]
        self.assertEqual(call_kwargs["words"], "50")
        self.assertEqual(call_kwargs["extra_info"], "recipe")


# ---------------------------------------------------------------------------
# AI.one_shot
# ---------------------------------------------------------------------------

class TestAIOneShot(unittest.TestCase):
    def test_delegates_to_llm(self):
        llm, tts, stt = _make_providers()
        llm.one_shot.return_value = SimpleNamespace(content="Paris")
        ai = AI(llm, tts, stt, _make_config())
        result = ai.one_shot("What is the capital of France?")
        llm.one_shot.assert_called_once_with("What is the capital of France?", model=None)
        self.assertEqual(result.content, "Paris")

    def test_forwards_model(self):
        llm, tts, stt = _make_providers()
        llm.one_shot.return_value = SimpleNamespace(content="ok")
        ai = AI(llm, tts, stt, _make_config())
        ai.one_shot("prompt", model="gpt-4")
        llm.one_shot.assert_called_once_with("prompt", model="gpt-4")

    def test_does_not_mutate_conversation_history(self):
        llm, tts, stt = _make_providers()
        llm.one_shot.return_value = SimpleNamespace(content="ok")
        ai = AI(llm, tts, stt, _make_config())
        ai.conversation_history = ["User: hi", "Bot: hello"]
        ai.one_shot("standalone prompt")
        self.assertEqual(ai.conversation_history, ["User: hi", "Bot: hello"])


# ---------------------------------------------------------------------------
# AI.web_search
# ---------------------------------------------------------------------------

class TestAIWebSearch(unittest.TestCase):
    def test_delegates_to_llm(self):
        llm, tts, stt = _make_providers()
        llm.web_search.return_value = SimpleNamespace(output_text="The answer is 42.")
        ai = AI(llm, tts, stt, _make_config())
        result = ai.web_search("What is the answer?", "Be brief.")
        llm.web_search.assert_called_once_with(
            "What is the answer?", "Be brief.", model=None, include=None
        )
        self.assertEqual(result.output_text, "The answer is 42.")

    def test_forwards_model_and_include(self):
        llm, tts, stt = _make_providers()
        llm.web_search.return_value = SimpleNamespace(output_text="ok")
        ai = AI(llm, tts, stt, _make_config())
        ai.web_search("query", "instr", model="gpt-4", include=["sources"])
        llm.web_search.assert_called_once_with(
            "query", "instr", model="gpt-4", include=["sources"]
        )

    def test_does_not_mutate_conversation_history(self):
        llm, tts, stt = _make_providers()
        llm.web_search.return_value = SimpleNamespace(output_text="ok")
        ai = AI(llm, tts, stt, _make_config())
        ai.conversation_history = ["User: hi", "Bot: hello"]
        ai.web_search("query", instructions="instr")
        self.assertEqual(ai.conversation_history, ["User: hi", "Bot: hello"])


# ---------------------------------------------------------------------------
# pop_streaming_chunk (unchanged utility)
# ---------------------------------------------------------------------------

class TestStreamingHelpers(unittest.TestCase):
    def test_pop_streaming_chunk_sentence_boundary(self):
        buf = "Hello world. This is the next sentence."
        chunk, rest = pop_streaming_chunk(buf, boundary="sentence", min_chars=5)
        self.assertEqual(chunk, "Hello world. ")
        self.assertTrue(rest.startswith("This is"))

    def test_pop_streaming_chunk_paragraph_boundary(self):
        buf = "Para one.\n\nPara two."
        chunk, rest = pop_streaming_chunk(buf, boundary="paragraph", min_chars=5)
        self.assertEqual(chunk, "Para one. ")
        self.assertEqual(rest, "Para two.")

    def test_pop_streaming_chunk_buffer_too_small(self):
        buf = "Hi"
        chunk, rest = pop_streaming_chunk(buf, boundary="sentence", min_chars=5)
        self.assertIsNone(chunk)
        self.assertEqual(rest, buf)

    def test_pop_streaming_chunk_none_buffer(self):
        chunk, rest = pop_streaming_chunk(None, boundary="sentence", min_chars=5)
        self.assertIsNone(chunk)
        self.assertEqual(rest, "")

    def test_pop_streaming_chunk_whitespace_only(self):
        buf = "   \n\t  "
        chunk, rest = pop_streaming_chunk(buf, boundary="sentence", min_chars=5)
        self.assertIsNone(chunk)
        self.assertEqual(rest, buf)

    def test_pop_streaming_chunk_exceeds_max_chars_soft_cut_preserves_text(self):
        buf = "This is a somewhat longer buffer used for testing soft cuts."
        max_chars = 20
        chunk, rest = pop_streaming_chunk(buf, boundary="sentence", min_chars=5, max_chars=max_chars)
        self.assertIsNotNone(chunk)
        chunk = chunk or ""
        self.assertLessEqual(len(chunk), max_chars)
        self.assertEqual((chunk + rest), buf)


if __name__ == '__main__':
    unittest.main()
