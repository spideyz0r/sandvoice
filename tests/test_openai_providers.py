import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch, mock_open

from common.providers import OpenAILLMProvider, OpenAITTSProvider, OpenAISTTProvider
from common.providers.base import LLMProvider, TTSProvider, STTProvider


def _make_config(**kwargs):
    config = Mock()
    config.botname = "Sandbot"
    config.language = "English"
    config.timezone = "UTC"
    config.location = "Somewhere"
    config.gpt_response_model = "gpt-5-mini"
    config.gpt_route_model = "gpt-5-mini"
    config.gpt_summary_model = "gpt-5-mini"
    config.text_to_speech_model = "tts-1"
    config.bot_voice_model = "alloy"
    config.speech_to_text_model = "whisper-1"
    config.speech_to_text_task = "translate"
    config.speech_to_text_language = ""
    config.speech_to_text_translate_provider = "whisper"
    config.speech_to_text_translate_model = "gpt-5-mini"
    config.tmp_recording = "/tmp/recording"
    config.tmp_files_path = "/tmp"
    config.sandvoice_path = "/fake/path"
    config.verbosity = "brief"
    config.stream_responses = False
    config.api_retry_attempts = 1
    for k, v in kwargs.items():
        setattr(config, k, v)
    return config


# ---------------------------------------------------------------------------
# OpenAILLMProvider
# ---------------------------------------------------------------------------

class TestOpenAILLMProviderInit(unittest.TestCase):
    def test_is_llm_provider(self):
        provider = OpenAILLMProvider(Mock(), _make_config())
        self.assertIsInstance(provider, LLMProvider)


class TestOpenAILLMProviderGenerateResponse(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.config = _make_config()
        self.provider = OpenAILLMProvider(self.client, self.config)

    def _mock_completion(self, content):
        msg = Mock()
        msg.content = content
        choice = Mock()
        choice.message = msg
        completion = Mock()
        completion.choices = [choice]
        return completion

    def test_returns_message_with_content(self):
        self.client.chat.completions.create.return_value = self._mock_completion("hello")
        result = self.provider.generate_response("hi", [])
        self.assertEqual(result.content, "hello")

    def test_passes_conversation_history_in_messages(self):
        self.client.chat.completions.create.return_value = self._mock_completion("ok")
        history = ["User: previous", "Sandbot: response"]
        self.provider.generate_response("hi", history)
        call_args = self.client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        # system message + history messages + current user prompt
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["content"], "User: previous")
        self.assertEqual(messages[2]["content"], "Sandbot: response")
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"], "User: hi")

    def test_does_not_mutate_conversation_history(self):
        self.client.chat.completions.create.return_value = self._mock_completion("ok")
        history = ["User: hi"]
        original_len = len(history)
        self.provider.generate_response("hi", history)
        self.assertEqual(len(history), original_len)

    def test_uses_model_from_config_when_not_specified(self):
        self.client.chat.completions.create.return_value = self._mock_completion("ok")
        self.provider.generate_response("hi", [])
        call_args = self.client.chat.completions.create.call_args
        self.assertEqual(call_args[1]["model"], "gpt-5-mini")

    def test_uses_explicit_model_when_provided(self):
        self.client.chat.completions.create.return_value = self._mock_completion("ok")
        self.provider.generate_response("hi", [], model="gpt-4")
        call_args = self.client.chat.completions.create.call_args
        self.assertEqual(call_args[1]["model"], "gpt-4")

    def test_returns_error_message_on_api_failure(self):
        self.client.chat.completions.create.side_effect = Exception("API error")
        result = self.provider.generate_response("hi", [])
        self.assertIn("trouble", result.content.lower())

    def test_streaming_mode_collects_and_returns(self):
        self.config.stream_responses = True

        def make_event(content):
            delta = Mock()
            delta.content = content
            choice = Mock()
            choice.delta = delta
            event = Mock()
            event.choices = [choice]
            return event

        self.client.chat.completions.create.return_value = [
            make_event("hello "), make_event("world")
        ]
        result = self.provider.generate_response("hi", [])
        self.assertEqual(result.content, "hello world")

    def test_extra_info_included_in_system_role(self):
        self.client.chat.completions.create.return_value = self._mock_completion("ok")
        self.provider.generate_response("hi", [], extra_info="weather is sunny")
        call_args = self.client.chat.completions.create.call_args
        system_content = call_args[1]["messages"][0]["content"]
        self.assertIn("weather is sunny", system_content)


class TestOpenAILLMProviderStreamResponseDeltas(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.config = _make_config()
        self.provider = OpenAILLMProvider(self.client, self.config)

    def _make_stream(self, pieces):
        events = []
        for piece in pieces:
            delta = Mock()
            delta.content = piece
            choice = Mock()
            choice.delta = delta
            event = Mock()
            event.choices = [choice]
            events.append(event)
        self.client.chat.completions.create.return_value = iter(events)

    def test_yields_deltas(self):
        self._make_stream(["hello ", "world"])
        result = list(self.provider.stream_response_deltas("hi", []))
        self.assertEqual(result, ["hello ", "world"])

    def test_does_not_mutate_history(self):
        self._make_stream(["ok"])
        history = ["User: hi"]
        list(self.provider.stream_response_deltas("hi", history))
        self.assertEqual(len(history), 1)

    def test_empty_stream_yields_nothing(self):
        self._make_stream([])
        result = list(self.provider.stream_response_deltas("hi", []))
        self.assertEqual(result, [])

    def test_skips_none_content_events(self):
        delta_none = Mock()
        delta_none.content = None
        choice_none = Mock()
        choice_none.delta = delta_none
        event_none = Mock()
        event_none.choices = [choice_none]

        delta_ok = Mock()
        delta_ok.content = "hello"
        choice_ok = Mock()
        choice_ok.delta = delta_ok
        event_ok = Mock()
        event_ok.choices = [choice_ok]

        self.client.chat.completions.create.return_value = iter([event_none, event_ok])
        result = list(self.provider.stream_response_deltas("hi", []))
        self.assertEqual(result, ["hello"])


class TestOpenAILLMProviderDefineRoute(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.config = _make_config()
        self.provider = OpenAILLMProvider(self.client, self.config)

    def _mock_route_response(self, route_dict):
        msg = Mock()
        msg.content = json.dumps(route_dict)
        choice = Mock()
        choice.message = msg
        completion = Mock()
        completion.choices = [choice]
        self.client.chat.completions.create.return_value = completion

    def test_returns_route_dict(self):
        routes_yaml = "route_role: 'You are a router.'"
        self._mock_route_response({"route": "weather", "reason": "weather query"})
        with patch("builtins.open", mock_open(read_data=routes_yaml)):
            with patch("common.providers.openai_llm.Template") as mock_tpl:
                mock_tpl.return_value.render.return_value = routes_yaml
                with patch("common.providers.openai_llm.yaml.safe_load") as mock_yaml:
                    mock_yaml.return_value = {"route_role": "You are a router."}
                    result = self.provider.define_route("what is the weather?")
        self.assertEqual(result["route"], "weather")
        self.assertEqual(result["reason"], "weather query")

    def test_returns_default_on_file_not_found(self):
        with patch("builtins.open", side_effect=FileNotFoundError("no file")):
            result = self.provider.define_route("what is the weather?")
        self.assertEqual(result["route"], "default-route")

    def test_returns_default_on_json_decode_error(self):
        msg = Mock()
        msg.content = "not json"
        choice = Mock()
        choice.message = msg
        completion = Mock()
        completion.choices = [choice]
        self.client.chat.completions.create.return_value = completion

        routes_yaml = "route_role: 'router'"
        with patch("builtins.open", mock_open(read_data=routes_yaml)):
            with patch("common.providers.openai_llm.Template") as mock_tpl:
                mock_tpl.return_value.render.return_value = routes_yaml
                with patch("common.providers.openai_llm.yaml.safe_load") as mock_yaml:
                    mock_yaml.return_value = {"route_role": "router"}
                    result = self.provider.define_route("hi")
        self.assertEqual(result["route"], "default-route")

    def test_returns_default_on_api_error(self):
        self.client.chat.completions.create.side_effect = Exception("API error")
        routes_yaml = "route_role: 'router'"
        with patch("builtins.open", mock_open(read_data=routes_yaml)):
            with patch("common.providers.openai_llm.Template") as mock_tpl:
                mock_tpl.return_value.render.return_value = routes_yaml
                with patch("common.providers.openai_llm.yaml.safe_load") as mock_yaml:
                    mock_yaml.return_value = {"route_role": "router"}
                    result = self.provider.define_route("hi")
        self.assertEqual(result["route"], "default-route")


class TestOpenAILLMProviderTextSummary(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.config = _make_config()
        self.provider = OpenAILLMProvider(self.client, self.config)

    def _mock_summary_response(self, summary_dict):
        msg = Mock()
        msg.content = json.dumps(summary_dict)
        choice = Mock()
        choice.message = msg
        completion = Mock()
        completion.choices = [choice]
        self.client.chat.completions.create.return_value = completion

    def test_returns_summary_dict(self):
        self._mock_summary_response({"title": "Test", "text": "A summary."})
        result = self.provider.text_summary("some long text")
        self.assertEqual(result["title"], "Test")
        self.assertEqual(result["text"], "A summary.")

    def test_returns_error_dict_on_json_error(self):
        msg = Mock()
        msg.content = "not json"
        choice = Mock()
        choice.message = msg
        completion = Mock()
        completion.choices = [choice]
        self.client.chat.completions.create.return_value = completion
        result = self.provider.text_summary("text")
        self.assertEqual(result["title"], "Error")

    def test_returns_error_dict_on_api_failure(self):
        self.client.chat.completions.create.side_effect = Exception("fail")
        result = self.provider.text_summary("text")
        self.assertEqual(result["title"], "Error")


# ---------------------------------------------------------------------------
# OpenAITTSProvider
# ---------------------------------------------------------------------------

class TestOpenAITTSProviderInit(unittest.TestCase):
    def test_is_tts_provider(self):
        provider = OpenAITTSProvider(Mock(), _make_config())
        self.assertIsInstance(provider, TTSProvider)


class TestOpenAITTSProviderTextToSpeech(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.client = MagicMock()
        self.config = _make_config(tmp_files_path=self._tmp_dir.name)
        self.provider = OpenAITTSProvider(self.client, self.config)

    def tearDown(self):
        self._tmp_dir.cleanup()

    def test_returns_list_of_file_paths(self):
        mock_response = Mock()
        mock_response.stream_to_file = Mock()
        self.client.audio.speech.create.return_value = mock_response
        result = self.provider.text_to_speech("hello world")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].endswith(".mp3"))

    def test_uses_model_and_voice_from_config(self):
        mock_response = Mock()
        mock_response.stream_to_file = Mock()
        self.client.audio.speech.create.return_value = mock_response
        self.provider.text_to_speech("hello")
        call_args = self.client.audio.speech.create.call_args
        self.assertEqual(call_args[1]["model"], "tts-1")
        self.assertEqual(call_args[1]["voice"], "alloy")

    def test_uses_explicit_model_and_voice(self):
        mock_response = Mock()
        mock_response.stream_to_file = Mock()
        self.client.audio.speech.create.return_value = mock_response
        self.provider.text_to_speech("hello", model="tts-1-hd", voice="nova")
        call_args = self.client.audio.speech.create.call_args
        self.assertEqual(call_args[1]["model"], "tts-1-hd")
        self.assertEqual(call_args[1]["voice"], "nova")

    def test_returns_empty_list_on_empty_text(self):
        result = self.provider.text_to_speech("")
        self.assertEqual(result, [])

    def test_returns_empty_list_on_api_failure(self):
        self.client.audio.speech.create.side_effect = Exception("API error")
        result = self.provider.text_to_speech("hello")
        self.assertEqual(result, [])

    def test_cleans_up_files_on_partial_failure(self):
        tmp_dir = self.config.tmp_files_path
        created_files = []

        def side_effect(**kwargs):
            if len(created_files) == 0:
                resp = Mock()
                path = os.path.join(tmp_dir, "tts-test-chunk-001.mp3")

                def stream_to_file(p):
                    open(p, "w").close()
                    created_files.append(p)

                resp.stream_to_file = stream_to_file
                return resp
            raise Exception("second chunk fails")

        # Use long text to force two chunks
        long_text = "Hello world. " * 400
        self.client.audio.speech.create.side_effect = side_effect
        result = self.provider.text_to_speech(long_text)
        self.assertEqual(result, [])
        for f in created_files:
            self.assertFalse(os.path.exists(f), f"File {f} should have been cleaned up")


# ---------------------------------------------------------------------------
# OpenAISTTProvider
# ---------------------------------------------------------------------------

class TestOpenAISTTProviderInit(unittest.TestCase):
    def test_is_stt_provider(self):
        provider = OpenAISTTProvider(Mock(), _make_config())
        self.assertIsInstance(provider, STTProvider)


class TestOpenAISTTProviderTranscribe(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.config = _make_config()
        self.provider = OpenAISTTProvider(self.client, self.config)

    def _make_audio_file(self):
        f = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        f.write(b"fake audio")
        f.close()
        return f.name

    def test_translate_via_whisper(self):
        self.config.speech_to_text_task = "translate"
        self.config.speech_to_text_translate_provider = "whisper"
        transcript = Mock()
        transcript.text = "hello"
        self.client.audio.translations.create.return_value = transcript

        audio_file = self._make_audio_file()
        try:
            result = self.provider.transcribe(audio_file_path=audio_file)
            self.assertEqual(result, "hello")
        finally:
            os.unlink(audio_file)

    def test_transcribe_task(self):
        self.config.speech_to_text_task = "transcribe"
        self.config.speech_to_text_language = "pt"
        transcript = Mock()
        transcript.text = "olá mundo"
        self.client.audio.transcriptions.create.return_value = transcript

        audio_file = self._make_audio_file()
        try:
            result = self.provider.transcribe(audio_file_path=audio_file)
            self.assertEqual(result, "olá mundo")
        finally:
            os.unlink(audio_file)

    def test_translate_via_chat_completions(self):
        self.config.speech_to_text_task = "translate"
        self.config.speech_to_text_translate_provider = "openai"
        transcript = Mock()
        transcript.text = "olá"
        self.client.audio.transcriptions.create.return_value = transcript

        msg = Mock()
        msg.content = "hello"
        choice = Mock()
        choice.message = msg
        completion = Mock()
        completion.choices = [choice]
        self.client.chat.completions.create.return_value = completion

        audio_file = self._make_audio_file()
        try:
            result = self.provider.transcribe(audio_file_path=audio_file)
            self.assertEqual(result, "hello")
        finally:
            os.unlink(audio_file)

    def test_raises_on_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.provider.transcribe(audio_file_path="/nonexistent/file.mp3")

    def test_uses_default_tmp_path_when_none(self):
        self.config.speech_to_text_task = "translate"
        self.config.speech_to_text_translate_provider = "whisper"
        self.config.tmp_recording = "/tmp/recording"
        transcript = Mock()
        transcript.text = "hello"
        self.client.audio.translations.create.return_value = transcript

        # /tmp/recording.mp3 doesn't exist — should raise FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            self.provider.transcribe(audio_file_path=None)

    def test_empty_transcript_returns_empty_string(self):
        self.config.speech_to_text_task = "translate"
        self.config.speech_to_text_translate_provider = "openai"
        transcript = Mock()
        transcript.text = "   "
        self.client.audio.transcriptions.create.return_value = transcript

        audio_file = self._make_audio_file()
        try:
            result = self.provider.transcribe(audio_file_path=audio_file)
            self.assertEqual(result, "")
        finally:
            os.unlink(audio_file)


# ---------------------------------------------------------------------------
# Import checks
# ---------------------------------------------------------------------------

class TestProviderImports(unittest.TestCase):
    def test_all_importable_from_common_providers(self):
        from common.providers import (
            OpenAILLMProvider, OpenAITTSProvider, OpenAISTTProvider,
            LLMProvider, TTSProvider, STTProvider,
        )
        self.assertTrue(issubclass(OpenAILLMProvider, LLMProvider))
        self.assertTrue(issubclass(OpenAITTSProvider, TTSProvider))
        self.assertTrue(issubclass(OpenAISTTProvider, STTProvider))


if __name__ == "__main__":
    unittest.main()
