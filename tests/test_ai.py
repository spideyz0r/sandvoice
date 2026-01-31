import unittest
import tempfile
import os
import json
from unittest.mock import Mock, patch, mock_open
from common.ai import AI, ErrorMessage


class TestErrorMessage(unittest.TestCase):
    def test_error_message_creation(self):
        """Test ErrorMessage object creation"""
        msg = ErrorMessage("Test error")
        self.assertEqual(msg.content, "Test error")


class TestAIInitialization(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_home = os.environ.get('HOME')
        self.original_api_key = os.environ.get('OPENAI_API_KEY')
        os.environ['HOME'] = self.temp_dir
        os.environ['OPENAI_API_KEY'] = 'test-api-key'
        os.makedirs(os.path.join(self.temp_dir, ".sandvoice"), exist_ok=True)

    def tearDown(self):
        """Clean up test environment"""
        if self.original_home is not None:
            os.environ['HOME'] = self.original_home
        else:
            del os.environ['HOME']

        if self.original_api_key is not None:
            os.environ['OPENAI_API_KEY'] = self.original_api_key
        else:
            if 'OPENAI_API_KEY' in os.environ:
                del os.environ['OPENAI_API_KEY']

        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_init_success(self, mock_setup_logging, mock_openai):
        """Test successful AI initialization"""
        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3

        ai = AI(mock_config)

        self.assertIsNotNone(ai.openai_client)
        self.assertEqual(ai.conversation_history, [])
        mock_setup_logging.assert_called_once_with(mock_config)
        mock_openai.assert_called_once_with(timeout=10)

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_init_missing_api_key(self, mock_setup_logging, mock_openai):
        """Test initialization fails without API key"""
        del os.environ['OPENAI_API_KEY']
        mock_config = Mock()
        mock_config.enable_error_logging = False
        mock_config.error_log_path = '/tmp/error.log'

        with self.assertRaises(ValueError) as context:
            AI(mock_config)

        self.assertIn("OPENAI_API_KEY", str(context.exception))


class TestTranscribeAndTranslate(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_home = os.environ.get('HOME')
        self.original_api_key = os.environ.get('OPENAI_API_KEY')
        os.environ['HOME'] = self.temp_dir
        os.environ['OPENAI_API_KEY'] = 'test-key'

    def tearDown(self):
        """Clean up"""
        import shutil
        # Restore original environment variables
        if self.original_home is not None:
            os.environ['HOME'] = self.original_home
        elif 'HOME' in os.environ:
            del os.environ['HOME']

        if self.original_api_key is not None:
            os.environ['OPENAI_API_KEY'] = self.original_api_key
        elif 'OPENAI_API_KEY' in os.environ:
            del os.environ['OPENAI_API_KEY']

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    @patch('builtins.open', new_callable=mock_open, read_data=b'fake audio data')
    def test_transcribe_success(self, mock_file, mock_setup, mock_openai_class):
        """Test successful transcription"""
        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.speech_to_text_model = 'whisper-1'
        mock_config.tmp_recording = '/tmp/recording'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_transcript = Mock()
        mock_transcript.text = "Hello world"
        mock_client.audio.translations.create.return_value = mock_transcript

        ai = AI(mock_config)
        result = ai.transcribe_and_translate()

        self.assertEqual(result, "Hello world")
        mock_client.audio.translations.create.assert_called_once()

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_transcribe_file_not_found(self, mock_setup, mock_openai_class):
        """Test transcription with missing file"""
        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.tmp_recording = '/nonexistent/recording'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        ai = AI(mock_config)

        with self.assertRaises(FileNotFoundError):
            ai.transcribe_and_translate()

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    @patch('builtins.open', new_callable=mock_open, read_data=b'fake audio data')
    def test_transcribe_generic_exception(self, mock_file, mock_setup, mock_openai_class):
        """Test transcription with generic API exception"""
        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.speech_to_text_model = 'whisper-1'
        mock_config.tmp_recording = '/tmp/recording'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.audio.translations.create.side_effect = Exception("API Error")

        ai = AI(mock_config)

        with self.assertRaises(Exception) as context:
            ai.transcribe_and_translate()

        self.assertIn("API Error", str(context.exception))


class TestGenerateResponse(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        self.original_api_key = os.environ.get('OPENAI_API_KEY')
        os.environ['OPENAI_API_KEY'] = 'test-key'

    def tearDown(self):
        """Restore environment"""
        if self.original_api_key is not None:
            os.environ['OPENAI_API_KEY'] = self.original_api_key
        else:
            os.environ.pop('OPENAI_API_KEY', None)

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_generate_response_success(self, mock_setup, mock_openai_class):
        """Test successful response generation"""
        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.gpt_response_model = 'gpt-3.5-turbo'
        mock_config.botname = 'TestBot'
        mock_config.language = 'English'
        mock_config.timezone = 'EST'
        mock_config.location = 'Test City'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_message = Mock()
        mock_message.content = "Hello! How can I help?"
        mock_completion = Mock()
        mock_completion.choices = [Mock(message=mock_message)]
        mock_client.chat.completions.create.return_value = mock_completion

        ai = AI(mock_config)
        result = ai.generate_response("Hello")

        self.assertEqual(result.content, "Hello! How can I help?")
        self.assertEqual(len(ai.conversation_history), 2)
        self.assertIn("User: Hello", ai.conversation_history[0])

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_generate_response_with_extra_info(self, mock_setup, mock_openai_class):
        """Test response generation with extra context"""
        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.gpt_response_model = 'gpt-3.5-turbo'
        mock_config.botname = 'TestBot'
        mock_config.language = 'English'
        mock_config.timezone = 'EST'
        mock_config.location = 'Test City'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_message = Mock()
        mock_message.content = "The weather is sunny"
        mock_completion = Mock()
        mock_completion.choices = [Mock(message=mock_message)]
        mock_client.chat.completions.create.return_value = mock_completion

        ai = AI(mock_config)
        result = ai.generate_response("What's the weather?", extra_info="Temperature: 72F")

        self.assertEqual(result.content, "The weather is sunny")

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_generate_response_api_error(self, mock_setup, mock_openai_class):
        """Test response generation with API error returns ErrorMessage"""
        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.gpt_response_model = 'gpt-3.5-turbo'
        mock_config.botname = 'TestBot'
        mock_config.language = 'English'
        mock_config.timezone = 'EST'
        mock_config.location = 'Test City'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        ai = AI(mock_config)
        result = ai.generate_response("Hello")

        self.assertIsInstance(result, ErrorMessage)
        self.assertIn("trouble", result.content)


class TestDefineRoute(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        self.original_api_key = os.environ.get('OPENAI_API_KEY')
        os.environ['OPENAI_API_KEY'] = 'test-key'
        self.routes_yaml = """
route_role: |
  You are a routing bot.
"""

    def tearDown(self):
        """Restore original OPENAI_API_KEY environment variable"""
        if self.original_api_key is not None:
            os.environ['OPENAI_API_KEY'] = self.original_api_key
        elif 'OPENAI_API_KEY' in os.environ:
            del os.environ['OPENAI_API_KEY']

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    @patch('builtins.open', new_callable=mock_open)
    def test_define_route_success(self, mock_file, mock_setup, mock_openai_class):
        """Test successful route definition"""
        mock_file.return_value.read.return_value = self.routes_yaml

        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.gpt_route_model = 'gpt-3.5-turbo'
        mock_config.location = 'Test City'
        mock_config.sandvoice_path = '/test/path'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_message = Mock()
        mock_message.content = '{"route": "weather", "reason": "User asked about weather"}'
        mock_completion = Mock()
        mock_completion.choices = [Mock(message=mock_message)]
        mock_client.chat.completions.create.return_value = mock_completion

        ai = AI(mock_config)
        result = ai.define_route("What's the weather?")

        self.assertEqual(result["route"], "weather")
        self.assertIn("reason", result)

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_define_route_file_not_found(self, mock_setup, mock_openai_class):
        """Test route definition with missing routes file"""
        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.sandvoice_path = '/nonexistent'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        ai = AI(mock_config)
        result = ai.define_route("Hello")

        self.assertEqual(result["route"], "default-route")
        self.assertIn("Error", result["reason"])

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    @patch('builtins.open', new_callable=mock_open)
    def test_define_route_json_parse_error(self, mock_file, mock_setup, mock_openai_class):
        """Test route definition with invalid JSON response"""
        mock_file.return_value.read.return_value = self.routes_yaml

        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.gpt_route_model = 'gpt-3.5-turbo'
        mock_config.location = 'Test City'
        mock_config.sandvoice_path = '/test/path'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_message = Mock()
        mock_message.content = 'invalid json'
        mock_completion = Mock()
        mock_completion.choices = [Mock(message=mock_message)]
        mock_client.chat.completions.create.return_value = mock_completion

        ai = AI(mock_config)
        result = ai.define_route("Hello")

        self.assertEqual(result["route"], "default-route")
        self.assertIn("Parse error", result["reason"])

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    @patch('builtins.open', new_callable=mock_open)
    def test_define_route_api_exception(self, mock_file, mock_setup, mock_openai_class):
        """Test route definition with API exception"""
        mock_file.return_value.read.return_value = self.routes_yaml

        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.gpt_route_model = 'gpt-3.5-turbo'
        mock_config.location = 'Test City'
        mock_config.sandvoice_path = '/test/path'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        ai = AI(mock_config)
        result = ai.define_route("Hello")

        self.assertEqual(result["route"], "default-route")
        self.assertIn("API error", result["reason"])


class TestTextSummary(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        self.original_api_key = os.environ.get('OPENAI_API_KEY')
        os.environ['OPENAI_API_KEY'] = 'test-key'

    def tearDown(self):
        """Restore environment"""
        if self.original_api_key is not None:
            os.environ['OPENAI_API_KEY'] = self.original_api_key
        else:
            os.environ.pop('OPENAI_API_KEY', None)

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_text_summary_success(self, mock_setup, mock_openai_class):
        """Test successful text summarization"""
        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.gpt_summary_model = 'gpt-3.5-turbo'
        mock_config.language = 'English'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_message = Mock()
        mock_message.content = '{"title": "Test Article", "text": "This is a summary"}'
        mock_completion = Mock()
        mock_completion.choices = [Mock(message=mock_message)]
        mock_client.chat.completions.create.return_value = mock_completion

        ai = AI(mock_config)
        result = ai.text_summary("Long text to summarize", words="50")

        self.assertEqual(result["title"], "Test Article")
        self.assertEqual(result["text"], "This is a summary")

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_text_summary_json_error(self, mock_setup, mock_openai_class):
        """Test summary with JSON parse error"""
        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.gpt_summary_model = 'gpt-3.5-turbo'
        mock_config.language = 'English'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_message = Mock()
        mock_message.content = 'invalid json'
        mock_completion = Mock()
        mock_completion.choices = [Mock(message=mock_message)]
        mock_client.chat.completions.create.return_value = mock_completion

        ai = AI(mock_config)
        result = ai.text_summary("Long text")

        self.assertEqual(result["title"], "Error")
        self.assertIn("Unable", result["text"])

    @patch('common.ai.OpenAI')
    @patch('common.ai.setup_error_logging')
    def test_text_summary_api_exception(self, mock_setup, mock_openai_class):
        """Test summary with API exception"""
        mock_config = Mock()
        mock_config.api_timeout = 10
        mock_config.api_retry_attempts = 3
        mock_config.gpt_summary_model = 'gpt-3.5-turbo'
        mock_config.language = 'English'
        mock_config.debug = False

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        ai = AI(mock_config)
        result = ai.text_summary("Long text")

        self.assertEqual(result["title"], "Error")
        self.assertIn("Unable", result["text"])


if __name__ == '__main__':
    unittest.main()
