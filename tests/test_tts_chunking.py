import unittest
from unittest.mock import MagicMock

from common.ai import AI, split_text_for_tts
from common.providers.base import LLMProvider, TTSProvider, STTProvider


class TestSplitTextForTTS(unittest.TestCase):
    def test_none_and_empty(self):
        self.assertEqual(split_text_for_tts(None), [])
        self.assertEqual(split_text_for_tts(""), [])
        self.assertEqual(split_text_for_tts("   \n\n  "), [])

    def test_short_text_no_split(self):
        text = "Hello world."
        self.assertEqual(split_text_for_tts(text, max_chars=100), [text])

    def test_hard_cut_for_long_word(self):
        text = "a" * 50
        chunks = split_text_for_tts(text, max_chars=10)
        self.assertTrue(all(len(c) <= 10 for c in chunks))
        self.assertEqual("".join(chunks), text)

    def test_prefers_paragraph_boundary(self):
        text = ("a" * 15) + "\n\n" + ("b" * 15)
        chunks = split_text_for_tts(text, max_chars=16)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(len(c) <= 16 for c in chunks))
        self.assertTrue(chunks[0].startswith("a"))
        self.assertTrue(chunks[1].startswith("b"))

    def test_prefers_single_newline_boundary(self):
        text = ("a" * 20) + "\n" + ("b" * 20)
        chunks = split_text_for_tts(text, max_chars=25)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(len(c) <= 25 for c in chunks))
        self.assertEqual(chunks[0], "a" * 20)
        self.assertEqual(chunks[1], "b" * 20)

    def test_prefers_space_boundary(self):
        text = "hello worldagain"
        chunks = split_text_for_tts(text, max_chars=8)
        self.assertEqual(chunks[0], "hello")

    def test_prefers_sentence_boundary(self):
        text = "One. Two. Three. Four."
        chunks = split_text_for_tts(text, max_chars=10)
        # Ensure we split without exceeding max_chars, and the first chunk ends on a sentence.
        self.assertTrue(all(len(c) <= 10 for c in chunks))
        self.assertTrue(chunks[0].endswith("."))


class TestTextToSpeechChunking(unittest.TestCase):
    """Tests that AI.text_to_speech delegates correctly to the TTS provider.

    Detailed chunking, file naming, and cleanup behaviour is tested in
    tests/test_openai_providers.py::TestOpenAITTSProviderTextToSpeech.
    """

    def _make_ai(self, tts_return_value):
        config = MagicMock()
        config.debug = False
        llm = MagicMock(spec=LLMProvider)
        tts = MagicMock(spec=TTSProvider)
        stt = MagicMock(spec=STTProvider)
        tts.text_to_speech.return_value = tts_return_value
        return AI(llm, tts, stt, config), tts

    def test_text_to_speech_returns_file_list(self):
        ai, tts = self._make_ai(["/tmp/tts-001.mp3"])
        files = ai.text_to_speech("Hello world")
        self.assertEqual(files, ["/tmp/tts-001.mp3"])
        tts.text_to_speech.assert_called_once_with("Hello world", model=None, voice=None)

    def test_text_to_speech_multi_chunk(self):
        ai, tts = self._make_ai(["/tmp/chunk-001.mp3", "/tmp/chunk-002.mp3"])
        files = ai.text_to_speech("long text")
        self.assertEqual(len(files), 2)
        tts.text_to_speech.assert_called_once_with("long text", model=None, voice=None)

    def test_text_to_speech_returns_empty_on_failure(self):
        ai, tts = self._make_ai([])
        result = ai.text_to_speech("hello")
        self.assertEqual(result, [])
        tts.text_to_speech.assert_called_once_with("hello", model=None, voice=None)



if __name__ == '__main__':
    unittest.main()
