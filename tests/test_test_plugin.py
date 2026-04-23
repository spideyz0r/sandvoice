import unittest
from unittest.mock import MagicMock, patch

from plugins.test_plugin import fetch_data, process


class TestFetchData(unittest.TestCase):
    @patch("plugins.test_plugin.requests.get")
    def test_success_returns_value(self, mock_get):
        mock_get.return_value.json.return_value = {"value": "hello"}
        mock_get.return_value.raise_for_status = MagicMock()
        result = fetch_data("test query")
        self.assertEqual(result, "hello")
        mock_get.assert_called_once_with(
            "https://api.example.com/data",
            params={"q": "test query"},
            timeout=10,
        )
        mock_get.return_value.raise_for_status.assert_called_once_with()

    @patch("plugins.test_plugin.requests.get")
    def test_non_dict_response_returns_none(self, mock_get):
        mock_get.return_value.json.return_value = ["not", "a", "dict"]
        mock_get.return_value.raise_for_status = MagicMock()
        result = fetch_data("test")
        self.assertIsNone(result)

    @patch("plugins.test_plugin.requests.get")
    def test_missing_value_key_returns_none(self, mock_get):
        mock_get.return_value.json.return_value = {"other": "stuff"}
        mock_get.return_value.raise_for_status = MagicMock()
        result = fetch_data("test")
        self.assertIsNone(result)

    @patch("plugins.test_plugin.requests.get")
    def test_non_string_value_returns_none(self, mock_get):
        mock_get.return_value.json.return_value = {"value": 42}
        mock_get.return_value.raise_for_status = MagicMock()
        result = fetch_data("test")
        self.assertIsNone(result)

    @patch("plugins.test_plugin.requests.get")
    def test_http_error_returns_none(self, mock_get):
        import requests as req
        mock_get.return_value.raise_for_status.side_effect = req.exceptions.HTTPError("404")
        result = fetch_data("test")
        self.assertIsNone(result)

    @patch("plugins.test_plugin.requests.get")
    def test_connection_error_returns_none(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError("timeout")
        result = fetch_data("test")
        self.assertIsNone(result)

    @patch("plugins.test_plugin.requests.get")
    def test_timeout_param_passed_through(self, mock_get):
        mock_get.return_value.json.return_value = {"value": "ok"}
        mock_get.return_value.raise_for_status = MagicMock()
        fetch_data("test", timeout=5)
        mock_get.assert_called_once_with(
            "https://api.example.com/data",
            params={"q": "test"},
            timeout=5,
        )
        mock_get.return_value.raise_for_status.assert_called_once_with()


class TestProcess(unittest.TestCase):
    def _make_s(self, timeout=10):
        s = MagicMock()
        s.config.api_timeout = timeout
        return s

    @patch("plugins.test_plugin.fetch_data")
    def test_returns_result_on_success(self, mock_fetch):
        mock_fetch.return_value = "some answer"
        result = process("my query", {}, self._make_s())
        self.assertEqual(result, "some answer")

    @patch("plugins.test_plugin.fetch_data")
    def test_returns_error_message_on_none(self, mock_fetch):
        mock_fetch.return_value = None
        result = process("my query", {}, self._make_s())
        self.assertIn("couldn't fetch", result)

    @patch("plugins.test_plugin.fetch_data")
    def test_refresh_only_returns_none(self, mock_fetch):
        result = process("my query", {"refresh_only": True}, self._make_s())
        self.assertIsNone(result)
        mock_fetch.assert_not_called()

    @patch("plugins.test_plugin.fetch_data")
    def test_passes_api_timeout_from_config(self, mock_fetch):
        mock_fetch.return_value = "ok"
        process("query", {}, self._make_s(timeout=15))
        mock_fetch.assert_called_once_with("query", timeout=15)


if __name__ == "__main__":
    unittest.main()
