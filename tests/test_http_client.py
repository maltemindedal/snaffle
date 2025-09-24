"""Test cases for the HTTP client class"""

import unittest
from unittest.mock import MagicMock, patch

from PyFetch.exceptions import HTTPClientError
from PyFetch.http_client import HTTPClient


class TestHTTPClient(unittest.TestCase):
    """Test cases for the HTTP client class"""

    @patch("requests.request")
    def test_get_request_success(self, mock_request):
        """Test a successful GET request"""
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = "Success"

        client = HTTPClient()
        response = client.get("https://api.example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "Success")

    @patch("requests.request", side_effect=HTTPClientError)
    def test_get_request_failure(self, _):
        """Test a failed GET request"""
        client = HTTPClient()
        with self.assertRaises(HTTPClientError):
            client.get("https://api.example.com")

    @patch("requests.request")
    def test_head_request_success(self, mock_request):
        """Test a successful HEAD request"""
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = ""
        client = HTTPClient()
        response = client.head("https://api.example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "")

    @patch("requests.request")
    def test_options_request_success(self, mock_request):
        """Test a successful OPTIONS request"""
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = ""
        client = HTTPClient()
        response = client.options("https://api.example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "")

    @patch("requests.request")
    def test_get_request_with_progress(self, mock_request):
        """Test GET request with progress bar"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": "1024"}
        mock_response.iter_content.return_value = [b"data"] * 4
        mock_request.return_value = mock_response

        client = HTTPClient(show_progress=True)
        response = client.get("https://api.example.com")

        self.assertEqual(response.status_code, 200)
        mock_response.iter_content.assert_called_once()

    @patch("requests.request")
    def test_get_request_without_progress(self, mock_request):
        """Test GET request with progress bar disabled"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": "1024"}
        mock_request.return_value = mock_response

        client = HTTPClient(show_progress=False)
        response = client.get("https://api.example.com")

        self.assertEqual(response.status_code, 200)

    @patch("requests.request")
    def test_get_request_with_progress_large_file(self, mock_request):
        """Test GET request with progress bar for large file (above threshold)"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": str(6 * 1024 * 1024)}  # 6MB file
        mock_response.iter_content.return_value = [b"data"] * 4
        mock_request.return_value = mock_response

        client = HTTPClient(show_progress=True)
        response = client.get("https://api.example.com")

        self.assertEqual(response.status_code, 200)
        mock_response.iter_content.assert_called_once()

    @patch("requests.request")
    def test_get_request_with_progress_small_file(self, mock_request):
        """Test GET request with progress bar for small file (below threshold, should not show progress)"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": str(4 * 1024 * 1024)}  # 4MB file
        mock_response.iter_content.return_value = [b"data"] * 4
        mock_request.return_value = mock_response

        client = HTTPClient(show_progress=True)
        response = client.get("https://api.example.com")

        self.assertEqual(response.status_code, 200)
        mock_response.iter_content.assert_called_once()


if __name__ == "__main__":
    unittest.main()
