"""Test cases for the HTTP client class."""

from __future__ import annotations

import contextlib
import io
import threading
import unittest
import weakref
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar, cast
from unittest.mock import MagicMock, patch

import requests
from urllib3.exceptions import ConnectTimeoutError, ReadTimeoutError
from urllib3.util.retry import Retry

from snaffle.exceptions import HTTPConnectionError, ResponseError
from snaffle.http_client import HTTPClient

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
        with contextlib.redirect_stderr(io.StringIO()):  # silence the progress bar
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
        with contextlib.redirect_stderr(io.StringIO()):  # silence the progress bar
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
        with contextlib.redirect_stderr(io.StringIO()):  # silence the progress bar
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

    def test_client_stays_an_ordinary_object(self) -> None:
        """Test the client is still weak-referenceable and accepts attributes.

        An earlier revision added `__slots__` for a saving too small to measure
        and silently broke both of these for library users.
        """
        client = HTTPClient()
        weakref.ref(client)
        client.custom_attribute = "allowed"  # type: ignore[attr-defined]
        client.close()


class TestRetryPolicy(unittest.TestCase):
    """Retry behaviour exercised against the real urllib3 machinery.

    These deliberately avoid mocking `Session.request`: that mock sits above the
    adapter, so it cannot observe retries at all. An earlier revision claimed
    "a POST is never silently re-sent" on the strength of such a mock, and the
    claim was wrong -- urllib3 filters read errors and statuses by method, but
    retries connection errors for every method.
    """

    @staticmethod
    def _retry(total: int = 3) -> Retry:
        adapter = cast(
            Any, HTTPClient(retries=total + 1).session.get_adapter("http://x")
        )
        return cast(Retry, adapter.max_retries)

    def test_connection_errors_retry_for_non_idempotent_methods(self) -> None:
        """Test a POST is retried on connect failure: nothing reached the server."""
        retry = self._retry()
        # Does not raise -> the attempt is retried.
        retry.increment(method="POST", error=ConnectTimeoutError())

    @staticmethod
    def _read_error() -> ReadTimeoutError:
        return ReadTimeoutError(cast(Any, None), "/", "read timed out")

    def test_read_errors_do_not_retry_for_non_idempotent_methods(self) -> None:
        """Test a POST is not replayed after a read failure: it may have landed."""
        retry = self._retry()
        # urllib3 re-raises the original error rather than retrying.
        with self.assertRaises(ReadTimeoutError):
            retry.increment(method="POST", error=self._read_error())

    def test_read_errors_retry_for_idempotent_methods(self) -> None:
        """Test a GET is retried after a read failure."""
        retry = self._retry()
        retry.increment(method="GET", error=self._read_error())

    def test_retryable_status_is_retried_only_for_idempotent_methods(self) -> None:
        """Test the 503 allowlist applies to GET but not to POST."""
        retry = self._retry()
        self.assertTrue(retry.is_retry("GET", 503))
        self.assertFalse(retry.is_retry("POST", 503))

    def test_dead_end_status_is_never_retried(self) -> None:
        """Test a 404 is not retried for any method."""
        retry = self._retry()
        self.assertFalse(retry.is_retry("GET", 404))
        self.assertFalse(retry.is_retry("POST", 404))


class TestRetryAgainstRealServer(unittest.TestCase):
    """End-to-end retry behaviour against a real socket, counting real requests."""

    server: ClassVar[ThreadingHTTPServer]
    base_url: ClassVar[str]
    hits: ClassVar[list[str]] = []

    @classmethod
    def setUpClass(cls) -> None:
        hits = cls.hits

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def _reply(self) -> None:
                hits.append(f"{self.command} {self.path}")
                code = 503 if self.path == "/flaky" else 404
                body = b"{}"
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = _reply
            do_POST = _reply

        class Server(ThreadingHTTPServer):
            def handle_error(self, *args: Any) -> None:
                pass

        cls.server = Server(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.hits.clear()

    def test_get_on_503_is_retried(self) -> None:
        """Test a transient status really is re-sent for an idempotent method."""
        with HTTPClient(retries=3) as client, self.assertRaises(ResponseError):
            client.get(f"{self.base_url}/flaky")
        self.assertEqual(len(self.hits), 3, self.hits)

    def test_post_on_503_is_not_retried(self) -> None:
        """Test a transient status is not replayed for a non-idempotent method."""
        with HTTPClient(retries=3) as client, self.assertRaises(ResponseError):
            client.post(f"{self.base_url}/flaky", json={"a": 1})
        self.assertEqual(len(self.hits), 1, self.hits)

    def test_404_is_requested_once(self) -> None:
        """Test a dead-end status costs exactly one round trip."""
        with HTTPClient(retries=3) as client, self.assertRaises(ResponseError):
            client.get(f"{self.base_url}/missing")
        self.assertEqual(len(self.hits), 1, self.hits)

    def test_connection_is_reused_across_requests(self) -> None:
        """Test the pooled session survives across calls to the same host."""
        with HTTPClient(retries=1) as client:
            pool = client.session.get_adapter(self.base_url)
            for _ in range(4):
                with self.assertRaises(ResponseError):
                    client.get(f"{self.base_url}/missing")
            self.assertIs(client.session.get_adapter(self.base_url), pool)
        self.assertEqual(len(self.hits), 4)


if __name__ == "__main__":
    unittest.main()
