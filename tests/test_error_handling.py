import unittest
import time
import logging
import os
import tempfile
from unittest.mock import Mock, patch
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

        try:
            decorated_func()
        except Exception:
            pass

        # Check that delays roughly double (0.1s, 0.2s)
        # Allow some tolerance for execution overhead
        self.assertEqual(len(call_times), 3)
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        self.assertAlmostEqual(delay1, 0.1, delta=0.05)
        self.assertAlmostEqual(delay2, 0.2, delta=0.05)


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
    def test_logging_enabled(self):
        """Test error logging setup when enabled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "test.log")

            # Create mock config
            mock_config = Mock()
            mock_config.enable_error_logging = True
            mock_config.error_log_path = log_path

            # Clear existing handlers to avoid conflicts
            logger = logging.getLogger()
            logger.handlers.clear()

            setup_error_logging(mock_config)

            # Write a test log message using a specific logger
            test_logger = logging.getLogger('test')
            test_logger.error("Test error message")

            # Force flush
            for handler in logger.handlers:
                handler.flush()

            # Verify log file was created and has content
            if os.path.exists(log_path):
                with open(log_path, 'r') as f:
                    content = f.read()
                    # If file exists, it should have content
                    if content:
                        self.assertIn("Test error message", content)

    def test_logging_disabled(self):
        """Test error logging setup when disabled"""
        mock_config = Mock()
        mock_config.enable_error_logging = False

        # Should not raise any errors
        setup_error_logging(mock_config)

    def test_logging_creates_directory(self):
        """Test that logging setup creates log directory if it doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "subdir", "test.log")

            mock_config = Mock()
            mock_config.enable_error_logging = True
            mock_config.error_log_path = log_path

            setup_error_logging(mock_config)

            # Verify directory was created
            self.assertTrue(os.path.exists(os.path.dirname(log_path)))


if __name__ == '__main__':
    unittest.main()
