import unittest
from unittest.mock import Mock, patch, MagicMock
import requests
from common.common import WebTextExtractor


class TestWebTextExtractor(unittest.TestCase):
    def test_init(self):
        """Test WebTextExtractor initialization"""
        extractor = WebTextExtractor("https://example.com", timeout=15)
        self.assertEqual(extractor.url, "https://example.com")
        self.assertEqual(extractor.timeout, 15)
        self.assertIsNotNone(extractor.headers)

    def test_init_default_timeout(self):
        """Test WebTextExtractor initialization with default timeout"""
        extractor = WebTextExtractor("https://example.com")
        self.assertEqual(extractor.timeout, 10)

    def test_remove_non_ascii(self):
        """Test removing non-ASCII characters"""
        extractor = WebTextExtractor("https://example.com")

        # Test with ASCII-only text
        result = extractor.remove_non_ascii("Hello World")
        self.assertEqual(result, "Hello World")

        # Test with mixed ASCII and non-ASCII
        result = extractor.remove_non_ascii("Hello 世界 World")
        self.assertEqual(result, "Hello  World")

        # Test with emojis
        result = extractor.remove_non_ascii("Test 🚀 message")
        self.assertEqual(result, "Test  message")

        # Test with accented characters
        result = extractor.remove_non_ascii("Café résumé")
        self.assertEqual(result, "Caf rsum")

    @patch('common.common.BeautifulSoup')
    @patch('common.common.requests.get')
    def test_get_text_success(self, mock_get, mock_soup):
        """Test successful web text extraction"""
        # Mock the HTTP response
        mock_response = Mock()
        mock_response.text = "<html><body><p>Hello World</p></body></html>"
        mock_response.encoding = 'utf-8'
        mock_get.return_value = mock_response

        # Mock BeautifulSoup - first call for parsing
        mock_soup_instance = Mock()
        mock_soup_instance.get_text.return_value = "Hello World"
        # Mock the __call__ method to return empty list (no scripts/styles)
        mock_soup_instance.return_value = []

        # For the second BeautifulSoup call (text cleaning)
        mock_clean_soup = Mock()
        mock_clean_soup.text = "Hello World"

        # Configure mock to return different instances
        mock_soup.side_effect = [mock_soup_instance, mock_clean_soup]

        extractor = WebTextExtractor("https://example.com")
        result = extractor.get_text()

        self.assertEqual(result, "Hello World")
        mock_get.assert_called_once()

    @patch('common.common.requests.get')
    def test_get_text_request_exception(self, mock_get):
        """Test handling of requests.RequestException"""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        extractor = WebTextExtractor("https://example.com")
        result = extractor.get_text()

        self.assertIn("Error fetching content", result)
        self.assertIn("example.com", result)

    @patch('common.common.requests.get')
    def test_get_text_http_error(self, mock_get):
        """Test handling of HTTP errors"""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        extractor = WebTextExtractor("https://example.com")
        result = extractor.get_text()

        self.assertIn("Error fetching content", result)

    @patch('common.common.requests.get')
    def test_get_text_timeout(self, mock_get):
        """Test handling of request timeout"""
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

        extractor = WebTextExtractor("https://example.com", timeout=5)
        result = extractor.get_text()

        self.assertIn("Error fetching content", result)

    @patch('common.common.BeautifulSoup')
    @patch('common.common.requests.get')
    def test_get_text_parsing_error(self, mock_get, mock_soup):
        """Test handling of parsing errors"""
        mock_response = Mock()
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.encoding = 'utf-8'
        mock_get.return_value = mock_response

        # Make BeautifulSoup raise an exception
        mock_soup.side_effect = Exception("Parsing error")

        extractor = WebTextExtractor("https://example.com")
        result = extractor.get_text()

        self.assertEqual(result, "Error parsing web content")

    @patch('common.common.BeautifulSoup')
    @patch('common.common.requests.get')
    def test_get_text_removes_scripts_and_styles(self, mock_get, mock_soup):
        """Test that script and style tags are removed"""
        mock_response = Mock()
        mock_response.text = "<html><head><script>alert('hi')</script></head><body>Content</body></html>"
        mock_response.encoding = 'utf-8'
        mock_get.return_value = mock_response

        # Mock script and style elements
        mock_script = Mock()
        mock_style = Mock()

        mock_soup_instance = Mock()
        # Mock the __call__ method to return script and style elements
        mock_soup_instance.return_value = [mock_script, mock_style]
        mock_soup_instance.get_text.return_value = "Content"

        mock_clean_soup = Mock()
        mock_clean_soup.text = "Content"

        mock_soup.side_effect = [mock_soup_instance, mock_clean_soup]

        extractor = WebTextExtractor("https://example.com")
        result = extractor.get_text()

        # Verify extract was called on script and style elements
        mock_script.extract.assert_called_once()
        mock_style.extract.assert_called_once()

    @patch('common.common.BeautifulSoup')
    @patch('common.common.requests.get')
    def test_get_text_normalizes_whitespace(self, mock_get, mock_soup):
        """Test that newlines, tabs, and carriage returns are replaced with spaces"""
        mock_response = Mock()
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.encoding = 'utf-8'
        mock_get.return_value = mock_response

        mock_soup_instance = Mock()
        # Mock the __call__ method to return empty list (no scripts/styles)
        mock_soup_instance.return_value = []
        mock_soup_instance.get_text.return_value = "Line1\nLine2\tTab\rReturn"

        mock_clean_soup = Mock()
        mock_clean_soup.text = "Line1\nLine2\tTab\rReturn"

        mock_soup.side_effect = [mock_soup_instance, mock_clean_soup]

        extractor = WebTextExtractor("https://example.com")
        result = extractor.get_text()

        # All whitespace characters should be replaced with spaces
        self.assertEqual(result, "Line1 Line2 Tab Return")


if __name__ == '__main__':
    unittest.main()
