import os
import shutil
import unittest
import tempfile
from unittest.mock import Mock, patch

from common.ai import AI, split_text_for_tts


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
        self.assertTrue(chunks[0].startswith("a"))
        self.assertTrue(chunks[1].startswith("b"))

    def test_prefers_sentence_boundary(self):
        text = "One. Two. Three. Four."
        chunks = split_text_for_tts(text, max_chars=10)
        # Ensure we split without exceeding max_chars, and the first chunk ends on a sentence.
        self.assertTrue(all(len(c) <= 10 for c in chunks))
        self.assertTrue(chunks[0].endswith("."))


class TestTextToSpeechChunking(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_api_key = os.environ.get('OPENAI_API_KEY')
        os.environ['OPENAI_API_KEY'] = 'test-key'

    def tearDown(self):
        if self.original_api_key is not None:
            os.environ['OPENAI_API_KEY'] = self.original_api_key
        else:
            del os.environ['OPENAI_API_KEY']

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    @patch('common.ai.uuid.uuid4')
    def test_text_to_speech_returns_file_list(self, mock_uuid4, mock_setup, mock_openai_class):
        mock_uuid4.return_value = Mock(hex='abc123')

        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 1
        mock_config.text_to_speech_model = 'tts-1'
        mock_config.bot_voice_model = 'nova'
        mock_config.tmp_files_path = self.temp_dir
        mock_config.fallback_to_text_on_audio_error = True
        mock_config.enable_error_logging = False
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_response.stream_to_file = Mock()
        mock_client.audio.speech.create.return_value = mock_response

        ai = AI(mock_config)
        files = ai.text_to_speech("Hello world")

        self.assertEqual(len(files), 1)
        expected_path = os.path.join(self.temp_dir, 'tts-response-abc123-chunk-001.mp3')
        self.assertEqual(files[0], expected_path)
        mock_response.stream_to_file.assert_called_once_with(expected_path)

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    @patch('common.ai.uuid.uuid4')
    @patch('common.ai.split_text_for_tts')
    def test_text_to_speech_multi_chunk(self, mock_split, mock_uuid4, mock_setup, mock_openai_class):
        mock_split.return_value = ["chunk1", "chunk2"]
        mock_uuid4.return_value = Mock(hex='abc123')

        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 1
        mock_config.text_to_speech_model = 'tts-1'
        mock_config.bot_voice_model = 'nova'
        mock_config.tmp_files_path = self.temp_dir
        mock_config.fallback_to_text_on_audio_error = True
        mock_config.enable_error_logging = False
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_response.stream_to_file = Mock()
        mock_client.audio.speech.create.return_value = mock_response

        ai = AI(mock_config)
        files = ai.text_to_speech("ignored")

        mock_split.assert_called_once_with("ignored")

        self.assertEqual(files, [
            os.path.join(self.temp_dir, 'tts-response-abc123-chunk-001.mp3'),
            os.path.join(self.temp_dir, 'tts-response-abc123-chunk-002.mp3'),
        ])
        self.assertEqual(mock_client.audio.speech.create.call_count, 2)
        self.assertEqual(mock_response.stream_to_file.call_count, 2)

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    @patch('common.ai.uuid.uuid4')
    @patch('common.ai.split_text_for_tts')
    def test_text_to_speech_cleanup_on_chunk_failure_with_fallback(self, mock_split, mock_uuid4, mock_setup, mock_openai_class):
        mock_split.return_value = ["chunk1", "chunk2"]
        mock_uuid4.return_value = Mock(hex='abc123')

        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 1
        mock_config.text_to_speech_model = 'tts-1'
        mock_config.bot_voice_model = 'nova'
        mock_config.tmp_files_path = self.temp_dir
        mock_config.fallback_to_text_on_audio_error = True
        mock_config.enable_error_logging = False
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        speech_response = Mock()

        def write_file(path):
            with open(path, 'wb') as f:
                f.write(b'fake mp3')

        speech_response.stream_to_file.side_effect = write_file

        # First chunk succeeds, second chunk raises before writing.
        mock_client.audio.speech.create.side_effect = [speech_response, Exception("boom")]

        ai = AI(mock_config)
        result = ai.text_to_speech("ignored")

        self.assertEqual(result, [])

        first_path = os.path.join(self.temp_dir, 'tts-response-abc123-chunk-001.mp3')
        self.assertFalse(os.path.exists(first_path))


if __name__ == '__main__':
    unittest.main()
