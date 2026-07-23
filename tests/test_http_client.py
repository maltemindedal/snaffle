"""Test cases for the HTTP client class."""

from __future__ import annotations

import unittest
from typing import Any, cast
from unittest.mock import MagicMock, patch

import requests

from PyFetch.exceptions import HTTPConnectionError, ResponseError
from PyFetch.http_client import HTTPClient

SESSION_REQUEST = "requests.Session.request"


class TestHTTPClient(unittest.TestCase):
    """Test cases for the HTTP client class."""

    @patch(SESSION_REQUEST)
    def test_get_request_success(self, mock_request: MagicMock) -> None:
        """Test a successful GET request."""
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = "Success"

        client = HTTPClient()
        response = client.get("https://api.example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "Success")
        # No stream=True: without a progress bar, streaming only holds the
        # connection open for longer.
        mock_request.assert_called_once_with(
            method="GET",
            url="https://api.example.com",
            timeout=30,
        )

    @patch(SESSION_REQUEST, side_effect=requests.exceptions.ConnectionError("boom"))
    def test_get_request_connection_failure_maps_to_custom_exception(
        self, _: MagicMock
    ) -> None:
        """Test a connection failure is mapped to the custom exception."""
        client = HTTPClient()
        with self.assertRaises(HTTPConnectionError):
            client.get("https://api.example.com")

    @patch(SESSION_REQUEST, side_effect=requests.exceptions.RetryError("exhausted"))
    def test_retry_error_maps_to_connection_error(self, _: MagicMock) -> None:
        """Test adapter retry exhaustion is mapped to the connection exception."""
        client = HTTPClient()
        with self.assertRaises(HTTPConnectionError):
            client.get("https://api.example.com")

    @patch(SESSION_REQUEST)
    def test_head_request_success(self, mock_request: MagicMock) -> None:
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

    @patch(SESSION_REQUEST)
    def test_options_request_success(self, mock_request: MagicMock) -> None:
        """Test a successful OPTIONS request."""
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = ""
        client = HTTPClient()
        response = client.options("https://api.example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "")

    @patch(SESSION_REQUEST)
    def test_get_request_with_progress(self, mock_request: MagicMock) -> None:
        """Test GET request with progress enabled streams and buffers content."""
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
        self.assertTrue(cast(Any, response)._content_consumed)
        self.assertTrue(mock_request.call_args.kwargs["stream"])

    @patch(SESSION_REQUEST)
    def test_get_request_without_progress_does_not_stream(
        self, mock_request: MagicMock
    ) -> None:
        """Test GET request without progress skips streaming entirely."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": "1024"}
        mock_request.return_value = mock_response

        client = HTTPClient(show_progress=False)
        response = client.get("https://api.example.com")

        self.assertEqual(response.status_code, 200)
        mock_response.iter_content.assert_not_called()
        self.assertNotIn("stream", mock_request.call_args.kwargs)

    @patch(SESSION_REQUEST)
    def test_get_request_with_progress_large_file(
        self, mock_request: MagicMock
    ) -> None:
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

    @patch(SESSION_REQUEST)
    def test_get_request_with_progress_small_file(
        self, mock_request: MagicMock
    ) -> None:
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

    @patch(SESSION_REQUEST)
    def test_http_error_maps_to_response_error(self, mock_request: MagicMock) -> None:
        """Test HTTP errors are mapped to the custom response exception."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "bad status"
        )
        mock_request.return_value = mock_response

        client = HTTPClient(retries=1)
        with self.assertRaises(ResponseError):
            client.get("https://api.example.com")

    @patch(SESSION_REQUEST)
    def test_non_retryable_status_is_attempted_once(
        self, mock_request: MagicMock
    ) -> None:
        """Test a dead-end status is not re-sent; retrying a 404 only adds latency."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "404"
        )
        mock_request.return_value = mock_response

        client = HTTPClient(retries=5)
        with self.assertRaises(ResponseError):
            client.get("https://api.example.com")
        self.assertEqual(mock_request.call_count, 1)

    def test_unsupported_method_rejected(self) -> None:
        """Test an unsupported HTTP method raises before any network access."""
        client = HTTPClient()
        with self.assertRaises(ValueError):
            client.make_request("TRACE", "https://api.example.com")

    def test_init_rejects_non_positive_timeout(self) -> None:
        """Test timeout validation."""
        with self.assertRaises(ValueError):
            HTTPClient(timeout=0)

    def test_init_rejects_non_positive_retries(self) -> None:
        """Test retries validation."""
        with self.assertRaises(ValueError):
            HTTPClient(retries=0)


class TestSessionReuse(unittest.TestCase):
    """Test cases covering connection pooling and lifecycle."""

    def test_session_is_pooled_and_retry_configured(self) -> None:
        """Test adapters are mounted with pooling and a backoff retry policy."""
        client = HTTPClient(retries=4)
        adapter = cast(Any, client.session.get_adapter("https://api.example.com"))

        self.assertEqual(adapter._pool_maxsize, HTTPClient.POOL_SIZE)
        retry = adapter.max_retries
        self.assertEqual(retry.total, 3)  # 4 total attempts
        self.assertGreater(retry.backoff_factor, 0)
        self.assertIn(503, retry.status_forcelist)
        self.assertNotIn(404, retry.status_forcelist)
        client.close()

    @patch(SESSION_REQUEST)
    def test_requests_reuse_one_session(self, mock_request: MagicMock) -> None:
        """Test repeated calls go through a single pooled session."""
        mock_request.return_value.status_code = 200
        client = HTTPClient()
        session = client.session

        for _ in range(3):
            client.get("https://api.example.com")

        self.assertIs(client.session, session)
        self.assertEqual(mock_request.call_count, 3)

    def test_context_manager_closes_session(self) -> None:
        """Test the context manager releases the connection pool on exit."""
        client = HTTPClient()
        with patch.object(client.session, "close") as mock_close:
            with client as entered:
                self.assertIs(entered, client)
                mock_close.assert_not_called()
            mock_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
