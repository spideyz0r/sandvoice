import unittest
import time
import logging
import os
import tempfile
from unittest.mock import Mock
from common.error_handling import (
    retry_with_backoff,
    format_user_error,
    handle_api_error,
    handle_file_error,
    setup_error_logging
)


class TestRetryWithBackoff(unittest.TestCase):
    def test_success_on_first_attempt(self):
        """Test function succeeds on first attempt"""
        mock_func = Mock(return_value="success")
        decorated_func = retry_with_backoff(max_attempts=3)(mock_func)

        result = decorated_func()

        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 1)

    def test_success_on_second_attempt(self):
        """Test function succeeds on second attempt after one failure"""
        mock_func = Mock(side_effect=[Exception("error"), "success"])
        decorated_func = retry_with_backoff(max_attempts=3, initial_delay=0.01)(mock_func)

        result = decorated_func()

        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 2)

    def test_all_attempts_fail(self):
        """Test function fails after all retry attempts"""
        mock_func = Mock(side_effect=Exception("persistent error"))
        decorated_func = retry_with_backoff(max_attempts=3, initial_delay=0.01)(mock_func)

        with self.assertRaises(Exception) as context:
            decorated_func()

        self.assertEqual(str(context.exception), "persistent error")
        self.assertEqual(mock_func.call_count, 3)

    def test_exponential_backoff_timing(self):
        """Test that retry delays follow exponential backoff pattern"""
        call_times = []

        def failing_func():
            call_times.append(time.time())
            raise Exception("error")

        decorated_func = retry_with_backoff(max_attempts=3, initial_delay=0.1)(failing_func)

        with self.assertRaises(Exception):
            decorated_func()

        # Check that delays roughly double (0.1s, 0.2s)
        # Allow some tolerance for execution overhead
        self.assertEqual(len(call_times), 3)
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        self.assertAlmostEqual(delay1, 0.1, delta=0.05)
        self.assertAlmostEqual(delay2, 0.2, delta=0.05)

    def test_non_retryable_file_not_found(self):
        """Test that FileNotFoundError is raised immediately without retry"""
        mock_func = Mock(side_effect=FileNotFoundError("file not found"))
        decorated_func = retry_with_backoff(max_attempts=3, initial_delay=0.01)(mock_func)

        with self.assertRaises(FileNotFoundError):
            decorated_func()

        self.assertEqual(mock_func.call_count, 1)

    def test_non_retryable_permission_error(self):
        """Test that PermissionError is raised immediately without retry"""
        mock_func = Mock(side_effect=PermissionError("permission denied"))
        decorated_func = retry_with_backoff(max_attempts=3, initial_delay=0.01)(mock_func)

        with self.assertRaises(PermissionError):
            decorated_func()

        self.assertEqual(mock_func.call_count, 1)

    def test_non_retryable_value_error(self):
        """Test that ValueError is raised immediately without retry"""
        mock_func = Mock(side_effect=ValueError("invalid value"))
        decorated_func = retry_with_backoff(max_attempts=3, initial_delay=0.01)(mock_func)

        with self.assertRaises(ValueError):
            decorated_func()

        self.assertEqual(mock_func.call_count, 1)

    def test_non_retryable_key_error(self):
        """Test that KeyError is raised immediately without retry"""
        mock_func = Mock(side_effect=KeyError("missing key"))
        decorated_func = retry_with_backoff(max_attempts=3, initial_delay=0.01)(mock_func)

        with self.assertRaises(KeyError):
            decorated_func()

        self.assertEqual(mock_func.call_count, 1)

    def test_non_retryable_json_decode_error(self):
        """Test that json.JSONDecodeError is raised immediately without retry"""
        import json
        mock_func = Mock(side_effect=json.JSONDecodeError("invalid json", "", 0))
        decorated_func = retry_with_backoff(max_attempts=3, initial_delay=0.01)(mock_func)

        with self.assertRaises(json.JSONDecodeError):
            decorated_func()

        self.assertEqual(mock_func.call_count, 1)


class TestFormatUserError(unittest.TestCase):
    def test_basic_error_message(self):
        """Test basic error message formatting"""
        result = format_user_error("API Error", "Service unavailable")

        self.assertEqual(result, "API Error: Service unavailable")

    def test_error_with_debug_info(self):
        """Test error message with debug information"""
        result = format_user_error(
            "API Error",
            "Service unavailable",
            debug_info="Connection timeout after 10s"
        )

        self.assertIn("API Error: Service unavailable", result)
        self.assertIn("Debug info: Connection timeout after 10s", result)

    def test_error_without_debug_info(self):
        """Test error message without debug info doesn't include debug section"""
        result = format_user_error("File Error", "File not found")

        self.assertEqual(result, "File Error: File not found")
        self.assertNotIn("Debug info", result)


class TestHandleAPIError(unittest.TestCase):
    def test_connection_error(self):
        """Test handling of connection errors"""
        error = ConnectionError("Failed to connect")
        result = handle_api_error(error, service_name="TestAPI")

        self.assertIn("Network Error", result)
        self.assertIn("Unable to reach TestAPI", result)

    def test_timeout_error(self):
        """Test handling of timeout errors"""
        error = TimeoutError("Request timed out")
        result = handle_api_error(error, service_name="TestAPI")

        self.assertIn("Network Error", result)
        self.assertIn("Unable to reach TestAPI", result)

    def test_authentication_error_401(self):
        """Test handling of 401 authentication errors"""
        error = Exception("401 Unauthorized")
        result = handle_api_error(error, service_name="TestAPI")

        self.assertIn("Authentication Error", result)
        self.assertIn("Check your API key", result)

    def test_rate_limit_error_429(self):
        """Test handling of rate limit errors"""
        error = Exception("429 Too Many Requests")
        result = handle_api_error(error, service_name="TestAPI")

        self.assertIn("Rate Limit Error", result)
        self.assertIn("rate limit exceeded", result)

    def test_generic_api_error(self):
        """Test handling of generic API errors"""
        error = Exception("Unknown error")
        result = handle_api_error(error, service_name="TestAPI")

        self.assertIn("Service Error", result)
        self.assertIn("TestAPI encountered an error", result)


class TestHandleFileError(unittest.TestCase):
    def test_file_not_found_error(self):
        """Test handling of FileNotFoundError"""
        error = FileNotFoundError("test.txt not found")
        result = handle_file_error(error, operation="read", filename="test.txt")

        self.assertIn("File Error", result)
        self.assertIn("Could not find test.txt", result)

    def test_permission_error(self):
        """Test handling of PermissionError"""
        error = PermissionError("Permission denied")
        result = handle_file_error(error, operation="write", filename="test.txt")

        self.assertIn("Permission Error", result)
        self.assertIn("No permission to write test.txt", result)

    def test_generic_file_error(self):
        """Test handling of generic file errors"""
        error = IOError("Disk full")
        result = handle_file_error(error, operation="write", filename="test.txt")

        self.assertIn("File Error", result)
        self.assertIn("Could not write test.txt", result)


class TestSetupErrorLogging(unittest.TestCase):
    def setUp(self):
        """Clear root logger handlers before each test to avoid cross-test pollution."""
        root = logging.getLogger()
        root.handlers.clear()

    def tearDown(self):
        """Remove any handlers added during the test."""
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)

    def _make_config(self, log_level="warning", enable_error_logging=False, error_log_path=""):
        cfg = Mock()
        cfg.log_level = log_level
        cfg.enable_error_logging = enable_error_logging
        cfg.error_log_path = error_log_path
        return cfg

    def test_console_handler_always_installed(self):
        """Console handler is installed regardless of log level or file logging setting."""
        cfg = self._make_config(log_level="warning")
        setup_error_logging(cfg)
        root = logging.getLogger()
        console_handlers = [h for h in root.handlers if getattr(h, "_sandvoice_console", False)]
        self.assertEqual(len(console_handlers), 1)

    def test_log_level_warning_maps_correctly(self):
        """log_level='warning' sets root logger to WARNING."""
        cfg = self._make_config(log_level="warning")
        setup_error_logging(cfg)
        self.assertEqual(logging.getLogger().level, logging.WARNING)

    def test_log_level_info_maps_correctly(self):
        """log_level='info' sets root logger to INFO."""
        cfg = self._make_config(log_level="info")
        setup_error_logging(cfg)
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_log_level_debug_maps_correctly(self):
        """log_level='debug' sets root logger to DEBUG."""
        cfg = self._make_config(log_level="debug")
        setup_error_logging(cfg)
        self.assertEqual(logging.getLogger().level, logging.DEBUG)

    def test_idempotent_second_call_does_not_add_duplicate_console_handler(self):
        """Calling setup_error_logging twice does not install a second console handler."""
        cfg = self._make_config(log_level="warning")
        setup_error_logging(cfg)
        setup_error_logging(cfg)
        root = logging.getLogger()
        console_handlers = [h for h in root.handlers if getattr(h, "_sandvoice_console", False)]
        self.assertEqual(len(console_handlers), 1)

    def test_level_update_on_reconfigure(self):
        """Calling setup_error_logging again with a different level updates the handler level."""
        cfg_warn = self._make_config(log_level="warning")
        cfg_debug = self._make_config(log_level="debug")
        setup_error_logging(cfg_warn)
        setup_error_logging(cfg_debug)
        root = logging.getLogger()
        console = next(h for h in root.handlers if getattr(h, "_sandvoice_console", False))
        self.assertEqual(console.level, logging.DEBUG)

    def test_file_logging_enabled(self):
        """File handler is created when enable_error_logging is True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "test.log")
            cfg = self._make_config(enable_error_logging=True, error_log_path=log_path)
            setup_error_logging(cfg)

            test_logger = logging.getLogger("test_file")
            test_logger.error("Test error message")
            for h in logging.getLogger().handlers:
                h.flush()

            self.assertTrue(os.path.exists(log_path))
            with open(log_path) as f:
                self.assertIn("Test error message", f.read())

    def test_file_logging_disabled_no_file_handler(self):
        """No file handler added when enable_error_logging is False."""
        cfg = self._make_config(enable_error_logging=False)
        setup_error_logging(cfg)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if getattr(h, "_sandvoice_file", False)]
        self.assertEqual(len(file_handlers), 0)

    def test_logging_creates_directory(self):
        """File logging setup creates the log directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "subdir", "test.log")
            cfg = self._make_config(enable_error_logging=True, error_log_path=log_path)
            setup_error_logging(cfg)
            self.assertTrue(os.path.exists(os.path.dirname(log_path)))


if __name__ == '__main__':
    unittest.main()
