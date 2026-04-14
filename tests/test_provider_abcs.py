import unittest
from types import SimpleNamespace

from common.providers import LLMProvider, TTSProvider, STTProvider


class TestLLMProviderABC(unittest.TestCase):
    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            LLMProvider()

    def test_missing_generate_response_raises(self):
        class Incomplete(LLMProvider):
            def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
                pass
            def define_route(self, user_input, model=None, extra_routes=None):
                pass
            def text_summary(self, user_input, extra_info=None, words="100", model=None):
                pass
            def one_shot(self, prompt, model=None):
                pass
            def web_search(self, query, instructions, model=None, include=None):
                pass

        with self.assertRaises(TypeError):
            Incomplete()

    def test_missing_stream_response_deltas_raises(self):
        class Incomplete(LLMProvider):
            def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
                pass
            def define_route(self, user_input, model=None, extra_routes=None):
                pass
            def text_summary(self, user_input, extra_info=None, words="100", model=None):
                pass
            def one_shot(self, prompt, model=None):
                pass
            def web_search(self, query, instructions, model=None, include=None):
                pass

        with self.assertRaises(TypeError):
            Incomplete()

    def test_missing_define_route_raises(self):
        class Incomplete(LLMProvider):
            def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
                pass
            def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
                pass
            def text_summary(self, user_input, extra_info=None, words="100", model=None):
                pass
            def one_shot(self, prompt, model=None):
                pass
            def web_search(self, query, instructions, model=None, include=None):
                pass

        with self.assertRaises(TypeError):
            Incomplete()

    def test_missing_text_summary_raises(self):
        class Incomplete(LLMProvider):
            def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
                pass
            def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
                pass
            def define_route(self, user_input, model=None, extra_routes=None):
                pass
            def one_shot(self, prompt, model=None):
                pass
            def web_search(self, query, instructions, model=None, include=None):
                pass

        with self.assertRaises(TypeError):
            Incomplete()

    def test_missing_one_shot_raises(self):
        class Incomplete(LLMProvider):
            def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
                pass
            def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
                pass
            def define_route(self, user_input, model=None, extra_routes=None):
                pass
            def text_summary(self, user_input, extra_info=None, words="100", model=None):
                pass
            def web_search(self, query, instructions, model=None, include=None):
                pass

        with self.assertRaises(TypeError):
            Incomplete()

    def test_missing_web_search_raises(self):
        class Incomplete(LLMProvider):
            def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
                pass
            def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
                pass
            def define_route(self, user_input, model=None, extra_routes=None):
                pass
            def text_summary(self, user_input, extra_info=None, words="100", model=None):
                pass
            def one_shot(self, prompt, model=None):
                pass

        with self.assertRaises(TypeError):
            Incomplete()

    def test_concrete_implementation_instantiates(self):
        class ConcreteLLM(LLMProvider):
            def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
                return SimpleNamespace(content="ok")
            def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
                yield "ok"
            def define_route(self, user_input, model=None, extra_routes=None):
                return {"route": "default-route", "reason": "test"}
            def text_summary(self, user_input, extra_info=None, words="100", model=None):
                return {"title": "t", "text": "s"}
            def one_shot(self, prompt, model=None):
                return SimpleNamespace(content="ok")
            def web_search(self, query, instructions, model=None, include=None):
                return SimpleNamespace(output_text="ok")

        provider = ConcreteLLM()
        self.assertIsInstance(provider, LLMProvider)

    def test_concrete_generate_response_returns_content(self):
        class ConcreteLLM(LLMProvider):
            def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
                return SimpleNamespace(content="hello")
            def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
                yield "hello"
            def define_route(self, user_input, model=None, extra_routes=None):
                return {"route": "default-route", "reason": "test"}
            def text_summary(self, user_input, extra_info=None, words="100", model=None):
                return {"title": "t", "text": "s"}
            def one_shot(self, prompt, model=None):
                return SimpleNamespace(content="ok")
            def web_search(self, query, instructions, model=None, include=None):
                return SimpleNamespace(output_text="ok")

        provider = ConcreteLLM()
        result = provider.generate_response("hi", [])
        self.assertEqual(result.content, "hello")

    def test_concrete_stream_response_deltas_yields(self):
        class ConcreteLLM(LLMProvider):
            def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
                return SimpleNamespace(content="")
            def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
                yield "chunk1"
                yield "chunk2"
            def define_route(self, user_input, model=None, extra_routes=None):
                return {"route": "default-route", "reason": "test"}
            def text_summary(self, user_input, extra_info=None, words="100", model=None):
                return {"title": "t", "text": "s"}
            def one_shot(self, prompt, model=None):
                return SimpleNamespace(content="ok")
            def web_search(self, query, instructions, model=None, include=None):
                return SimpleNamespace(output_text="ok")

        provider = ConcreteLLM()
        chunks = list(provider.stream_response_deltas("hi", []))
        self.assertEqual(chunks, ["chunk1", "chunk2"])


class TestTTSProviderABC(unittest.TestCase):
    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            TTSProvider()

    def test_missing_text_to_speech_raises(self):
        class Incomplete(TTSProvider):
            pass

        with self.assertRaises(TypeError):
            Incomplete()

    def test_concrete_implementation_instantiates(self):
        class ConcreteTTS(TTSProvider):
            def text_to_speech(self, text, model=None, voice=None) -> list:
                return ["/tmp/tts.mp3"]

        provider = ConcreteTTS()
        self.assertIsInstance(provider, TTSProvider)

    def test_concrete_text_to_speech_returns_list(self):
        class ConcreteTTS(TTSProvider):
            def text_to_speech(self, text, model=None, voice=None) -> list:
                return ["/tmp/tts.mp3"]

        provider = ConcreteTTS()
        result = provider.text_to_speech("hello")
        self.assertIsInstance(result, list)
        self.assertEqual(result, ["/tmp/tts.mp3"])


class TestSTTProviderABC(unittest.TestCase):
    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            STTProvider()

    def test_missing_transcribe_raises(self):
        class Incomplete(STTProvider):
            pass

        with self.assertRaises(TypeError):
            Incomplete()

    def test_concrete_implementation_instantiates(self):
        class ConcreteSTT(STTProvider):
            def transcribe(self, audio_file_path=None, model=None) -> str:
                return "hello"

        provider = ConcreteSTT()
        self.assertIsInstance(provider, STTProvider)

    def test_transcribe_accepts_none_path(self):
        class ConcreteSTT(STTProvider):
            def transcribe(self, audio_file_path=None, model=None) -> str:
                return "default path used" if audio_file_path is None else "custom path"

        provider = ConcreteSTT()
        self.assertEqual(provider.transcribe(), "default path used")
        self.assertEqual(provider.transcribe(audio_file_path="/tmp/audio.mp3"), "custom path")


class TestImports(unittest.TestCase):
    def test_importable_from_common_providers(self):
        from common.providers import LLMProvider, TTSProvider, STTProvider
        self.assertTrue(issubclass(LLMProvider, object))
        self.assertTrue(issubclass(TTSProvider, object))
        self.assertTrue(issubclass(STTProvider, object))


if __name__ == "__main__":
    unittest.main()
