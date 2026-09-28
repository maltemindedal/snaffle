"""Test cases for the HTTP client class."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import socketserver
import threading
import unittest
import weakref
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar, NoReturn, cast
from unittest.mock import MagicMock, patch

import requests
from requests.adapters import HTTPAdapter
from typing_extensions import override
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.exceptions import (
    ConnectTimeoutError,
    LocationParseError,
    ReadTimeoutError,
)
from urllib3.util.retry import Retry

from snaffle.exceptions import HTTPClientError, HTTPConnectionError, ResponseError
from snaffle.http_client import HTTPClient

SESSION_REQUEST = "requests.Session.request"
#: Patched where it is used, not where it is defined: `http_client` imports the
#: name. What it does with a body is `tests/test_download.py`'s business.
BUFFER_INTO = "snaffle.http_client.buffer_into"


def _adapter_of(client: HTTPClient, url: str = "http://x") -> Any:
    """Returns the adapter a client would send `url` through."""
    return client.session.get_adapter(url)


def _policy_for(attempts: int) -> Retry:
    """Returns the retry policy carried by a default client built for `attempts`.

    `attempts` counts total attempts, the same way `HTTPClient(retries=...)`
    does -- not the way urllib3's `Retry.total` does, which is one fewer.
    """
    with HTTPClient(retries=attempts) as client:
        return cast(Retry, _adapter_of(client).max_retries)


class _QuietHandler(BaseHTTPRequestHandler):
    """A keep-alive handler that does not log every request to stderr."""

    protocol_version = "HTTP/1.1"

    @override
    def log_message(self, format: str, *args: Any) -> None:
        """Discards the per-request log line the base class would print."""

    def send_body(self, code: int, body: bytes) -> None:
        """Sends one complete response, `Content-Length` included."""
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _LocalServerTestCase(unittest.TestCase):
    """Base for tests that need a real socket. Subclasses supply `handler`.

    A real server is the only way to observe some of what this package promises
    -- retries happen below `Session.request`, and only a socket has a body to
    drain, so two test classes need one. The shared setup lives here rather
    than in both.
    """

    handler: ClassVar[type[BaseHTTPRequestHandler]]
    server: ClassVar[ThreadingHTTPServer]
    base_url: ClassVar[str]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        """Starts the subclass's handler on an ephemeral port."""

        class Server(ThreadingHTTPServer):
            @override
            def handle_error(self, request: Any, client_address: Any) -> None:
                """Swallows the disconnect tracebacks these tests provoke."""

        cls.server = Server(("127.0.0.1", 0), cls.handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    @override
    def tearDownClass(cls) -> None:
        """Shuts the server down and releases its port."""
        cls.server.shutdown()
        cls.server.server_close()


class TestHTTPClient(unittest.TestCase):
    """Test cases for the HTTP client class."""

    @patch(SESSION_REQUEST)
    def test_verb_methods_forward_their_own_method_url_and_kwargs(
        self, mock_request: MagicMock
    ) -> None:
        """Test each verb method delegates with its own method name and the kwargs.

        The seven wrappers carry no behaviour, so this is their whole contract,
        stated once instead of once per verb. Driving the loop from
        `ALLOWED_METHODS` also asserts every accepted method has a wrapper.

        Asserting the entire call pins two things besides the delegation: the
        client's timeout reaches the session, and no `stream=True` is added
        without a progress bar -- streaming would only hold the connection open
        for longer.
        """
        mock_request.return_value.status_code = 200

        with HTTPClient() as client:
            for method in sorted(HTTPClient.ALLOWED_METHODS):
                with self.subTest(method=method):
                    mock_request.reset_mock()
                    send = getattr(client, method.lower())

                    response = send(
                        "https://api.example.com", headers={"X-Verb": method}
                    )

                    self.assertEqual(response.status_code, 200)
                    mock_request.assert_called_once_with(
                        method=method,
                        url="https://api.example.com",
                        timeout=30,
                        headers={"X-Verb": method},
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

    @patch(BUFFER_INTO)
    @patch(SESSION_REQUEST)
    def test_get_request_with_progress_streams_and_delegates_the_drain(
        self, mock_request: MagicMock, mock_buffer_into: MagicMock
    ) -> None:
        """Test a progress-enabled GET streams and hands the body to `_download`."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        client = HTTPClient(show_progress=True)
        response = client.get("https://api.example.com")

        self.assertIs(response, mock_response)
        self.assertTrue(mock_request.call_args.kwargs["stream"])
        mock_buffer_into.assert_called_once_with(
            mock_response,
            chunk_size=HTTPClient.DOWNLOAD_CHUNK_SIZE,
            min_size=HTTPClient.MIN_SIZE_FOR_PROGRESS,
            desc="Downloading https://api.example.com",
        )

    @patch(BUFFER_INTO)
    @patch(SESSION_REQUEST)
    def test_get_request_without_progress_does_not_stream(
        self, mock_request: MagicMock, mock_buffer_into: MagicMock
    ) -> None:
        """Test GET request without progress neither streams nor drains."""
        mock_request.return_value.status_code = 200

        client = HTTPClient(show_progress=False)
        response = client.get("https://api.example.com")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("stream", mock_request.call_args.kwargs)
        mock_buffer_into.assert_not_called()

    @patch(BUFFER_INTO)
    @patch(SESSION_REQUEST)
    def test_explicit_stream_suppresses_the_progress_drain(
        self, mock_request: MagicMock, mock_buffer_into: MagicMock
    ) -> None:
        """Test `stream=True` wins over `show_progress`, leaving the body unread.

        `TestProgressAgainstRealServer` proves the same thing against a socket;
        this asserts the client asked for it.
        """
        mock_request.return_value.status_code = 200

        client = HTTPClient(show_progress=True)
        client.get("https://api.example.com", stream=True)

        self.assertTrue(mock_request.call_args.kwargs["stream"])
        mock_buffer_into.assert_not_called()

    @patch(BUFFER_INTO)
    @patch(SESSION_REQUEST)
    def test_class_constant_overrides_reach_the_download(
        self, mock_request: MagicMock, mock_buffer_into: MagicMock
    ) -> None:
        """Test the documented subclassing hook still tunes the download."""

        class SmallBarClient(HTTPClient):
            """A subclass with the documented class-attribute overrides applied."""

            DOWNLOAD_CHUNK_SIZE = 1024
            MIN_SIZE_FOR_PROGRESS = 1

        mock_request.return_value.status_code = 200
        SmallBarClient(show_progress=True).get("https://api.example.com")

        self.assertEqual(mock_buffer_into.call_args.kwargs["chunk_size"], 1024)
        self.assertEqual(mock_buffer_into.call_args.kwargs["min_size"], 1)

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


class _PatientClient(HTTPClient):
    """The subclassing pattern `docs/guides/using-as-a-library.md` documents."""

    def patience(self) -> str:
        """A method only the subclass has."""
        return "patient"


class TestSubclassing(unittest.TestCase):
    """What a subclass can rely on."""

    def test_a_with_block_keeps_the_subclass_type(self) -> None:
        """Test `with Sub() as client` is typed as `Sub`, not as `HTTPClient`.

        The assertion here is the type checker's: `ty check` runs over the
        tests, and it rejects `client.patience()` if `__enter__` is annotated as
        returning the base class. At run time the test passes either way.
        """
        with _PatientClient() as client:
            self.assertEqual(client.patience(), "patient")


class TestSessionReuse(unittest.TestCase):
    """Test cases covering connection pooling and lifecycle."""

    def test_session_is_pooled_and_retry_configured(self) -> None:
        """Test adapters are mounted with pooling and a backoff retry policy."""
        client = HTTPClient(retries=4)
        adapter = _adapter_of(client, "https://api.example.com")

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
        client.custom_attribute = "allowed"  # ty: ignore[unresolved-attribute]
        client.close()


class _RecordingAdapter(HTTPAdapter):
    """A transport that answers from memory and records what it was asked for.

    Mounted on a session handed to `HTTPClient`, it replaces the network without
    patching anything.
    """

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[requests.PreparedRequest] = []

    @override
    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: Any = None,
        verify: bool | str = True,
        cert: Any = None,
        proxies: Any = None,
    ) -> requests.Response:
        """Records the request and answers it with a canned 200."""
        self.requests.append(request)
        response = requests.Response()
        response.status_code = 200
        response.url = request.url or ""
        response.request = request
        cast(Any, response)._content = b'{"ok": true}'
        return response


class TestInjectedSession(unittest.TestCase):
    """Session injection substitutes the transport at the client's interface.

    `patch("requests.Session.request")` substitutes below this interface and
    above the adapter, so it cannot see a retry. A session passed to the
    constructor is substituted at the interface and keeps urllib3's machinery
    underneath it -- which is what `TestRetryWithoutASocket` uses.
    """

    def test_an_injected_session_carries_the_request(self) -> None:
        """Test the client sends through the session it was given."""
        adapter = _RecordingAdapter()
        session = requests.Session()
        session.mount("https://", adapter)

        with HTTPClient(session=session) as client:
            self.assertIs(client.session, session)
            response = client.get("https://api.example.com/thing")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual([request.method for request in adapter.requests], ["GET"])
        self.assertEqual(adapter.requests[0].url, "https://api.example.com/thing")

    def test_an_injected_session_is_not_closed(self) -> None:
        """Test a session the client did not build stays the caller's to close.

        The caller may be sharing it with other clients, so closing it here
        would pull the pool out from under them.
        """
        session = requests.Session()
        with patch.object(session, "close") as mock_close:
            with HTTPClient(session=session) as client:
                client.close()
            mock_close.assert_not_called()

    def test_retries_do_not_reach_an_injected_session(self) -> None:
        """Test `retries` configures the default session and nothing else.

        The retry policy lives on the session's adapters, so a caller who
        supplies a session supplies the policy along with it. A bare
        `requests.Session` mounts adapters that do not retry at all.
        """
        session = requests.Session()
        client = HTTPClient(retries=5, session=session)

        self.assertEqual(client.retries, 5)
        adapter = _adapter_of(client, "https://api.example.com")
        self.assertEqual(adapter.max_retries.total, 0)


class TestRetryPolicy(unittest.TestCase):
    """Retry behaviour exercised against the real urllib3 machinery.

    These deliberately avoid mocking `Session.request`: that mock sits above the
    adapter, so it cannot observe retries at all. An earlier revision claimed
    "a POST is never silently re-sent" on the strength of such a mock, and the
    claim was wrong -- urllib3 filters read errors and statuses by method, but
    retries connection errors for every method.
    """

    def test_connection_errors_retry_for_non_idempotent_methods(self) -> None:
        """Test a POST is retried on connect failure: nothing reached the server."""
        retry = _policy_for(4)
        # Does not raise -> the attempt is retried.
        retry.increment(method="POST", error=ConnectTimeoutError())

    @staticmethod
    def _read_error() -> ReadTimeoutError:
        return ReadTimeoutError(cast(Any, None), "/", "read timed out")

    def test_read_errors_do_not_retry_for_non_idempotent_methods(self) -> None:
        """Test a POST is not replayed after a read failure: it may have landed."""
        retry = _policy_for(4)
        # urllib3 re-raises the original error rather than retrying.
        with self.assertRaises(ReadTimeoutError):
            retry.increment(method="POST", error=self._read_error())

    def test_read_errors_retry_for_idempotent_methods(self) -> None:
        """Test a GET is retried after a read failure."""
        retry = _policy_for(4)
        retry.increment(method="GET", error=self._read_error())

    def test_retryable_status_is_retried_only_for_idempotent_methods(self) -> None:
        """Test the 503 allowlist applies to GET but not to POST."""
        retry = _policy_for(4)
        self.assertTrue(retry.is_retry("GET", 503))
        self.assertFalse(retry.is_retry("POST", 503))

    def test_dead_end_status_is_never_retried(self) -> None:
        """Test a 404 is not retried for any method."""
        retry = _policy_for(4)
        self.assertFalse(retry.is_retry("GET", 404))
        self.assertFalse(retry.is_retry("POST", 404))


class _NoSocketPool(HTTPConnectionPool):
    """A real urllib3 pool whose every connection attempt fails, without a socket.

    urllib3 runs its retry loop inside `HTTPConnectionPool.urlopen`, so the loop
    only turns if the pool is real. `_new_conn` is the last step before a socket
    is opened; failing there counts attempts and opens nothing. It is private to
    urllib3, which is the price of watching the loop from outside.
    """

    def __init__(self) -> None:
        super().__init__("127.0.0.1", 9)
        self.attempts = 0

    @override
    def _new_conn(self) -> NoReturn:
        """Counts the attempt and fails it as if the connection had timed out."""
        self.attempts += 1
        raise ConnectTimeoutError("no socket is opened by this test double")


class _NoSocketAdapter(HTTPAdapter):
    """A real adapter, carrying a real retry policy, over `_NoSocketPool`."""

    def __init__(self, retry: Retry, pool: _NoSocketPool) -> None:
        super().__init__(max_retries=retry)
        self.no_socket_pool = pool

    @override
    def get_connection_with_tls_context(
        self,
        request: requests.PreparedRequest,
        verify: bool | str | None,
        proxies: Any = None,
        cert: Any = None,
    ) -> HTTPConnectionPool:
        """Hands `requests` the pool that never connects."""
        return self.no_socket_pool


class TestRetryWithoutASocket(unittest.TestCase):
    """Retry behaviour observed through an injected session, opening no socket.

    Retries happen below `Session.request` and above the socket, so neither a
    mock of the former nor an assertion about the `Retry` object shows them
    happening. Injecting a session lets a test put a double at the bottom of
    that gap instead of the top: the client's own policy, urllib3's real loop,
    and a pool that counts attempts. `TestRetryAgainstRealServer` proves the
    same behaviour end to end; this is the cheap version of the same question.
    """

    def _client(self, attempts: int, pool: _NoSocketPool) -> HTTPClient:
        """Returns a client sending through `pool` under the policy for `attempts`."""
        session = requests.Session()
        session.mount("http://", _NoSocketAdapter(_policy_for(attempts), pool))
        return HTTPClient(session=session)

    def test_post_is_retried_when_the_connection_never_opens(self) -> None:
        """Test a POST is re-attempted on connection failure: nothing was sent.

        This is the claim an earlier revision got wrong against a
        `Session.request` mock, checked here at the same cost as that mock.
        """
        pool = _NoSocketPool()
        # urllib3 logs a warning per retry; `assertLogs` captures it, which both
        # keeps the output clean and asserts the retry was announced.
        with (
            self.assertLogs("urllib3", "WARNING"),
            self._client(3, pool) as client,
            self.assertRaises(HTTPConnectionError),
        ):
            client.post("http://never.invalid/thing", json={"a": 1})

        self.assertEqual(pool.attempts, 3)

    def test_a_one_attempt_client_does_not_retry(self) -> None:
        """Test the attempt count follows the policy rather than the double."""
        pool = _NoSocketPool()
        with self._client(1, pool) as client, self.assertRaises(HTTPConnectionError):
            client.get("http://never.invalid/thing")

        self.assertEqual(pool.attempts, 1)


class _CountingHandler(_QuietHandler):
    """Answers `/flaky` with a 503 and everything else with a 404, counting hits."""

    hits: ClassVar[list[str]] = []
    #: One entry per TCP connection that reached the server, by client port.
    peers: ClassVar[set[tuple[str, int]]] = set()

    def _reply(self) -> None:
        """Records the request and answers it without ever succeeding."""
        self.hits.append(f"{self.command} {self.path}")
        self.peers.add(self.client_address)
        self.send_body(503 if self.path == "/flaky" else 404, b"{}")

    do_GET = _reply
    do_POST = _reply


class TestRetryAgainstRealServer(_LocalServerTestCase):
    """End-to-end retry behaviour against a real socket, counting real requests."""

    handler = _CountingHandler
    hits: ClassVar[list[str]] = _CountingHandler.hits
    peers: ClassVar[set[tuple[str, int]]] = _CountingHandler.peers

    @override
    def setUp(self) -> None:
        self.hits.clear()
        self.peers.clear()

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
        self.assertEqual(len(self.peers), 1, "one TCP connection, reused")

    def test_a_streamed_error_response_releases_its_connection(self) -> None:
        """Test a failing GET with a progress bar still returns its connection.

        Regression: `show_progress` sends a GET as `stream=True`, and a 4xx or
        5xx was raised without reading its body. The connection then stayed
        checked out until the exception was collected, so every failure opened
        a new socket, and `close()` could not release them. The errors are kept
        alive here on purpose, the way a batch script that collects them would.
        """
        errors: list[ResponseError] = []
        with HTTPClient(show_progress=True, retries=1) as client:
            for _ in range(3):
                with self.assertRaises(ResponseError) as caught:
                    client.get(f"{self.base_url}/missing")
                errors.append(caught.exception)

        self.assertEqual(len(self.peers), 1, "one TCP connection, reused")
        for error in errors:
            response = cast(Any, error.__cause__).response
            self.assertEqual(response.text, "{}", "the error body stays readable")


#: Deliberately over `MIN_SIZE_FOR_PROGRESS`, so the progress path is fully live.
LARGE_BODY = b"snaffle!" * (6 * 1024 * 1024 // 8)


class _LargeBodyHandler(_QuietHandler):
    """Serves `LARGE_BODY` with a `Content-Length`, for any GET."""

    def do_GET(self) -> None:
        """Answers with the large body."""
        self.send_body(200, LARGE_BODY)


class TestProgressAgainstRealServer(_LocalServerTestCase):
    """The streaming opt-out, verified against a real socket.

    A `Session.request` mock cannot show this. The defect it guards was a body
    drained out from under a caller who asked to stream it, and only a real
    socket has a body to drain.
    """

    handler = _LargeBodyHandler

    def test_explicit_stream_leaves_the_body_unread(self) -> None:
        """Test show_progress no longer drains a response asked to stream.

        Regression: the progress path ignored the caller's `stream=True` and
        consumed the body anyway, so the returned response had nothing left to
        iterate.

        `_content_consumed` is the assertion that separates the two cases.
        `iter_content` re-slices an already-buffered body, so it yields the full
        payload either way -- it cannot tell a live socket from a drained one.
        The flag is what the API reference documents, so it is the contract.
        The bar on stderr is the same difference, made visible.
        """
        stderr = io.StringIO()
        with HTTPClient(show_progress=True) as client:
            with contextlib.redirect_stderr(stderr):
                response = client.get(f"{self.base_url}/large", stream=True)

            self.assertFalse(cast(Any, response)._content_consumed)
            self.assertEqual(stderr.getvalue(), "", "no bar is drawn for a stream")
            self.assertEqual(b"".join(response.iter_content(65536)), LARGE_BODY)

    def test_progress_download_returns_a_read_response(self) -> None:
        """Test the buffering path still hands back a fully-read response."""
        stderr = io.StringIO()
        with HTTPClient(show_progress=True) as client:
            with contextlib.redirect_stderr(stderr):
                response = client.get(f"{self.base_url}/large")

            self.assertTrue(cast(Any, response)._content_consumed)
            self.assertIn("%", stderr.getvalue(), "a bar is drawn for a download")
            self.assertEqual(response.content, LARGE_BODY)


class _OversizedChunkLineHandler(_QuietHandler):
    """Answers with a chunked body whose size line is padded past 64 KiB."""

    def do_GET(self) -> None:
        """Sends one valid five-byte chunk, its size written with 70,000 zeros."""
        self.send_response(200)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.wfile.write(b"0" * 70_000 + b"5\r\nhello\r\n0\r\n\r\n")


class TestHostileResponses(_LocalServerTestCase):
    """What a server that misbehaves on purpose can and cannot do to a client."""

    handler = _OversizedChunkLineHandler

    def test_an_oversized_chunk_size_line_is_refused(self) -> None:
        """Test a chunk-size line over 64 KiB fails fast instead of being buffered.

        Regression for urllib3 < 2.8.0, which buffered a chunk-size line of any
        length, so one response could exhaust the client's memory. The body
        here is well-formed apart from the padding, so an unpatched urllib3
        returns `b"hello"` and this test fails.
        """
        with (
            HTTPClient(retries=1) as client,
            self.assertRaises(HTTPClientError) as caught,
        ):
            client.get(f"{self.base_url}/")

        self.assertIn("chunk size line", str(caught.exception))


class _EchoAcceptEncodingHandler(_QuietHandler):
    """Answers with the `Accept-Encoding` header the request carried."""

    def do_GET(self) -> None:
        """Sends the header's value back as the body."""
        self.send_body(200, self.headers.get("Accept-Encoding", "").encode())


@unittest.skipUnless(
    importlib.util.find_spec("brotli") is not None,
    "the speedups extra is not installed",
)
class TestSpeedupsExtra(_LocalServerTestCase):
    """The `speedups` extra must switch on every encoding it promises."""

    handler = _EchoAcceptEncodingHandler

    def test_the_extra_negotiates_brotli_and_zstd(self) -> None:
        """Test a client with the extra installed asks for `br` and `zstd`.

        Regression: the extra once named `zstandard`, which urllib3 stopped
        loading in 2.6.0, so zstd was silently never negotiated before
        Python 3.14. Only a request on the wire shows what the client offers.
        """
        with HTTPClient(retries=1) as client:
            offered = client.get(f"{self.base_url}/").text

        encodings = {token.strip() for token in offered.split(",")}
        self.assertLessEqual({"br", "zstd"}, encodings, offered)


class _RequestLineRecorder(socketserver.StreamRequestHandler):
    """Records the raw request line, then answers with an empty 200.

    `http.server` rewrites a request target that starts with `//` before a
    handler sees it, so only a raw socket shows what the client put on the wire.
    """

    lines: ClassVar[list[str]] = []

    @override
    def handle(self) -> None:
        """Reads the request line and closes the exchange."""
        self.lines.append(self.rfile.readline().decode("ascii").rstrip("\r\n"))
        self.wfile.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        )


class TestRequestTarget(unittest.TestCase):
    """What the client writes on the request line."""

    def test_duplicate_leading_slashes_are_sent_as_written(self) -> None:
        """Test `//a//b` reaches the server unchanged.

        requests 2.34 stopped collapsing a leading `//` to `/`, which broke some
        presigned URLs. The path is the caller's to choose, so it is sent as
        given.
        """
        _RequestLineRecorder.lines.clear()
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _RequestLineRecorder)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        with HTTPClient(retries=1) as client:
            client.get(f"http://127.0.0.1:{server.server_address[1]}//double//slash")

        self.assertEqual(_RequestLineRecorder.lines, ["GET //double//slash HTTP/1.1"])


class _RedirectToBadHostHandler(_QuietHandler):
    """Redirects every GET to a host that cannot be parsed."""

    def do_GET(self) -> None:
        """Answers with a 302 whose `Location` names `a..b`."""
        self.send_response(302)
        self.send_header("Location", "http://a..b/")
        self.send_header("Content-Length", "0")
        self.end_headers()


class TestServerChosenLocation(_LocalServerTestCase):
    """A redirect target is chosen by the server, so its errors are the client's."""

    handler = _RedirectToBadHostHandler

    def test_a_redirect_to_an_unparsable_host_is_a_client_error(self) -> None:
        """Test the failure is reported as `HTTPClientError`, not a raw urllib3 one."""
        with (
            HTTPClient(retries=1) as client,
            self.assertRaises(HTTPClientError) as caught,
        ):
            client.get(f"{self.base_url}/")

        self.assertIsInstance(caught.exception.__cause__, LocationParseError)


class TestMalformedHosts(unittest.TestCase):
    """Hosts urllib3 refuses to parse are the caller's mistake, not an outage."""

    def test_an_unparsable_host_is_a_client_error(self) -> None:
        """Test a host urllib3 cannot encode raises `HTTPClientError`.

        Regression: urllib3 raises `LocationParseError` while connecting for an
        empty label (`a..b`) or a label over 63 characters, and it is not a
        `requests` exception, so it left `make_request` unwrapped. The API
        reference promises `HTTPClientError` for a malformed URL. Nothing is sent:
        the failure comes before any lookup.
        """
        for host in ("a..b", "a" * 300 + ".com"):
            with self.subTest(host=host[:20]):
                with (
                    HTTPClient(retries=1) as client,
                    self.assertRaises(HTTPClientError) as caught,
                ):
                    client.get(f"http://{host}/")

                self.assertNotIsInstance(caught.exception, HTTPConnectionError)
                self.assertIsInstance(caught.exception.__cause__, LocationParseError)

    def test_a_host_with_a_space_is_a_client_error(self) -> None:
        """Test a raw space in the host is rejected before any connection attempt.

        urllib3 < 2.8.0 accepted it and looked the mangled name up, so the
        failure surfaced as an `HTTPConnectionError` after a DNS round trip.
        """
        with (
            HTTPClient(retries=1) as client,
            self.assertRaises(HTTPClientError) as caught,
        ):
            client.get("http://exa mple.com/")

        self.assertNotIsInstance(caught.exception, HTTPConnectionError)


if __name__ == "__main__":
    unittest.main()
