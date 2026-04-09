"""Test cases for the HTTP client class."""

import unittest
from unittest.mock import MagicMock, patch

import requests

from PyFetch.exceptions import HTTPConnectionError, ResponseError
from PyFetch.http_client import HTTPClient


class TestHTTPClient(unittest.TestCase):
    """Test cases for the HTTP client class."""

    @patch("PyFetch.http_client.requests.request")
    def test_get_request_success(self, mock_request):
        """Test a successful GET request."""
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = "Success"

        client = HTTPClient()
        response = client.get("https://api.example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "Success")
        mock_request.assert_called_once_with(
            method="GET",
            url="https://api.example.com",
            timeout=30,
            stream=True,
        )

    @patch(
        "PyFetch.http_client.requests.request",
        side_effect=requests.exceptions.ConnectionError("boom"),
    )
    def test_get_request_connection_failure_maps_to_custom_exception(self, _):
        """Test a connection failure is mapped to the custom exception."""
        client = HTTPClient()
        with self.assertRaises(HTTPConnectionError):
            client.get("https://api.example.com")

    @patch("PyFetch.http_client.requests.request")
    def test_head_request_success(self, mock_request):
        """Test a successful HEAD request."""
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = ""
        client = HTTPClient()
        response = client.head("https://api.example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "")
        mock_request.assert_called_once_with(
            method="HEAD",
            url="https://api.example.com",
            timeout=30,
        )

    @patch("PyFetch.http_client.requests.request")
    def test_options_request_success(self, mock_request):
        """Test a successful OPTIONS request."""
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = ""
        client = HTTPClient()
        response = client.options("https://api.example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "")

    @patch("PyFetch.http_client.requests.request")
    def test_get_request_with_progress(self, mock_request):
        """Test GET request with progress enabled."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": "1024"}
        mock_response.iter_content.return_value = [b"data"] * 4
        mock_request.return_value = mock_response

        client = HTTPClient(show_progress=True)
        response = client.get("https://api.example.com")

        self.assertEqual(response.status_code, 200)
        mock_response.iter_content.assert_called_once()
        self.assertEqual(response._content, b"datadatadatadata")

    @patch("PyFetch.http_client.requests.request")
    def test_get_request_without_progress(self, mock_request):
        """Test GET request with progress bar disabled."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": "1024"}
        mock_request.return_value = mock_response

        client = HTTPClient(show_progress=False)
        response = client.get("https://api.example.com")

        self.assertEqual(response.status_code, 200)

    @patch("PyFetch.http_client.requests.request")
    def test_get_request_with_progress_large_file(self, mock_request):
        """Test GET request with progress for a large file."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": str(6 * 1024 * 1024)}  # 6MB file
        mock_response.iter_content.return_value = [b"data"] * 4
        mock_request.return_value = mock_response

        client = HTTPClient(show_progress=True)
        response = client.get("https://api.example.com")

        self.assertEqual(response.status_code, 200)
        mock_response.iter_content.assert_called_once()

    @patch("PyFetch.http_client.requests.request")
    def test_get_request_with_progress_small_file(self, mock_request):
        """Test GET request with progress enabled for a small file."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": str(4 * 1024 * 1024)}  # 4MB file
        mock_response.iter_content.return_value = [b"data"] * 4
        mock_request.return_value = mock_response

        client = HTTPClient(show_progress=True)
        response = client.get("https://api.example.com")

        self.assertEqual(response.status_code, 200)
        mock_response.iter_content.assert_called_once()

    @patch("PyFetch.http_client.requests.request")
    def test_http_error_maps_to_response_error(self, mock_request):
        """Test HTTP errors are mapped to the custom response exception."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "bad status"
        )
        mock_request.return_value = mock_response

        client = HTTPClient(retries=1)
        with self.assertRaises(ResponseError):
            client.get("https://api.example.com")

    def test_init_rejects_non_positive_timeout(self):
        """Test timeout validation."""
        with self.assertRaises(ValueError):
            HTTPClient(timeout=0)

    def test_init_rejects_non_positive_retries(self):
        """Test retries validation."""
        with self.assertRaises(ValueError):
            HTTPClient(retries=0)


if __name__ == "__main__":
    unittest.main()
