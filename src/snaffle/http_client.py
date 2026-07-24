"""HTTP client for making HTTP requests with retries.

This module provides a flexible HTTP client for making RESTful API calls,
with support for customizable timeouts, automatic retries on failures,
and optional progress bars for large downloads.

The client keeps a pooled :class:`requests.Session` alive for its lifetime, so
repeated calls to the same host reuse an established TCP/TLS connection instead
of paying for a fresh handshake each time.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol, cast

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from snaffle.exceptions import HTTPClientError, HTTPConnectionError, ResponseError


class ProgressBar(Protocol):
    """Protocol for the subset of progress-bar methods used by the client."""

    def update(self, n: float | None = 1) -> bool | None:
        """Advance the progress display by the provided number of bytes."""

    def close(self) -> None:
        """Close the progress display and release any related resources."""


class HTTPClient:
    """A versatile HTTP client for making requests to a web server.

    This client supports common HTTP methods (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)
    and includes features like configurable timeouts, retries, and verbose logging.

    Connections are pooled across requests, so a client owns an operating-system
    resource. Use it as a context manager, or call :meth:`close`, to release the
    pool when you are done with it::

        with HTTPClient() as client:
            client.get("https://example.com")

    Retries use exponential backoff and are applied to:

    * connection failures, for every method -- a request that never reached the
      server cannot have been acted on twice;
    * read failures and the statuses in :attr:`RETRY_STATUSES`, for idempotent
      methods only, so a ``POST`` that may already have been processed is never
      replayed.

    The backoff means a request that is going to fail takes longer to say so
    (roughly half a second extra across the default three attempts) in exchange
    for not hammering a server that is already struggling.

    Attributes:
        timeout (int): The request timeout in seconds.
        retries (int): The total number of attempts made for a failed request.
        verbose (bool): If True, enables detailed logging of requests and responses.
        show_progress (bool): If True, displays a progress bar for large downloads.
        allowed_methods (frozenset): The methods this instance accepts, read by
            every request. Initialised from :attr:`ALLOWED_METHODS`.
        MIN_SIZE_FOR_PROGRESS (int): The minimum file size in bytes to trigger the progress bar.
    """

    ALLOWED_METHODS = frozenset(
        {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    )
    #: Raised from 8 KiB: larger reads mean fewer syscalls and fewer progress-bar
    #: refreshes per megabyte.
    DOWNLOAD_CHUNK_SIZE = 65536
    MIN_SIZE_FOR_PROGRESS = 5 * 1024 * 1024  # 5MB
    #: Status codes worth retrying. Retrying anything else (a 404, a 401) only
    #: multiplies the latency of a request that was never going to succeed.
    RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
    POOL_SIZE = 16

    def __init__(
        self,
        timeout: int = 30,
        retries: int = 3,
        verbose: bool = False,
        show_progress: bool = False,
    ) -> None:
        """Initializes the HTTPClient with configuration options.

        Args:
            timeout (int, optional): The timeout for HTTP requests in seconds. Defaults to 30.
            retries (int, optional): The total number of attempts for failed requests. Defaults to 3.
            verbose (bool, optional): Whether to enable verbose logging. Defaults to False.
            show_progress (bool, optional): Whether to show a progress bar for large downloads. Defaults to False.
        """
        if timeout <= 0:
            raise ValueError("timeout must be greater than 0")
        if retries <= 0:
            raise ValueError("retries must be greater than 0")

        self.timeout = timeout
        self.retries = retries
        self.verbose = verbose
        self.show_progress = show_progress
        self.allowed_methods = self.ALLOWED_METHODS
        self.session = self._build_session(retries)

    @classmethod
    def _build_session(cls, retries: int) -> requests.Session:
        """Builds a session whose adapters pool connections and retry with backoff.

        urllib3 applies its idempotent-method filter to read errors and to
        retryable statuses, but not to connection errors -- a request that never
        left the machine cannot have been processed twice, so retrying it is safe
        for every method. That asymmetry is deliberate; see the class docstring.
        """
        # `retries` counts total attempts; urllib3 counts retries after the first.
        retry = Retry(
            total=retries - 1,
            status_forcelist=sorted(cls.RETRY_STATUSES),
            backoff_factor=0.3,
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=cls.POOL_SIZE,
            pool_maxsize=cls.POOL_SIZE,
        )
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def close(self) -> None:
        """Closes the underlying session and releases pooled connections."""
        self.session.close()

    def __enter__(self) -> HTTPClient:
        """Returns the client itself, for use as a context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Closes the session on exit, suppressing nothing."""
        self.close()

    def _validate_method(self, method: str) -> str:
        """Normalizes and validates an HTTP method name."""
        normalized_method = method.upper()
        if normalized_method not in self.allowed_methods:
            allowed_methods = ", ".join(sorted(self.allowed_methods))
            raise ValueError(
                f"Unsupported HTTP method. Allowed methods: {allowed_methods}"
            )
        return normalized_method

    def _create_progress_bar(self, total: int, desc: str) -> ProgressBar | None:
        """Creates a `tqdm` progress bar if conditions are met.

        A progress bar is created if `show_progress` is True and the file size (`total`)
        is greater than or equal to `MIN_SIZE_FOR_PROGRESS`.

        Args:
            total (int): The total size of the file transfer in bytes.
            desc (str): A description to display with the progress bar.

        Returns:
            ProgressBar or None: A `tqdm` progress bar instance or `None` if the conditions are not met.
        """
        if self.show_progress and total >= self.MIN_SIZE_FOR_PROGRESS:
            # Imported lazily: tqdm costs ~15ms of startup that a CLI run
            # without --progress should never pay.
            from tqdm import tqdm

            return cast(
                ProgressBar,
                tqdm(total=total, unit="B", unit_scale=True, desc=desc),
            )
        return None

    def _stream_response(
        self,
        response: requests.Response,
        progress_bar: ProgressBar | None = None,
    ) -> bytes:
        """Streams the response content and updates the progress bar.

        This method iterates over the response content in chunks, allowing for efficient
        handling of large responses and real-time progress updates.

        Args:
            response (requests.Response): The HTTP response object.
            progress_bar (ProgressBar, optional): The progress bar instance to update. Defaults to None.

        Returns:
            bytes: The full response content as a byte string.
        """
        chunks: list[bytes] = []
        append = chunks.append
        update = progress_bar.update if progress_bar is not None else None

        try:
            for chunk in response.iter_content(chunk_size=self.DOWNLOAD_CHUNK_SIZE):
                if not chunk:
                    continue

                append(chunk)
                if update is not None:
                    update(len(chunk))
        finally:
            if progress_bar is not None:
                progress_bar.close()

        return b"".join(chunks)

    def make_request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Makes an HTTP request with retry logic and error handling.

        This is the core method for all HTTP operations performed by the client.
        Retries with exponential backoff are handled by the session's adapter;
        see the class docstring for which failures are retried for which methods.

        Args:
            method (str): The HTTP method to use (e.g., 'GET', 'POST').
            url (str): The URL to send the request to.
            **kwargs: Additional keyword arguments to pass to `requests.Session.request`.

        Returns:
            requests.Response: The HTTP response object.

        Raises:
            ValueError: If the specified HTTP method is not supported.
            HTTPConnectionError: If a connection error occurs after all retries.
            ResponseError: If an HTTP error status code is received after all retries.
            HTTPClientError: For other request-related errors.
        """
        normalized_method = self._validate_method(method)
        verbose = self.verbose

        # We only stream on our own initiative when there is a progress bar to
        # feed; otherwise letting requests read the body in one pass is faster
        # and returns the connection to the pool immediately. A caller who asked
        # for `stream=True` still gets an unconsumed response to iterate itself.
        track_progress = normalized_method == "GET" and self.show_progress
        if track_progress:
            kwargs["stream"] = True

        if verbose:
            print(
                f"[VERBOSE] Sending {normalized_method} request to {url} with {kwargs}"
            )

        try:
            response = self.session.request(
                method=normalized_method, url=url, timeout=self.timeout, **kwargs
            )
            response.raise_for_status()

            if verbose:
                print(
                    f"[VERBOSE] Received response with status {response.status_code} and headers {response.headers}"
                )

            if track_progress:
                total = int(response.headers.get("content-length", 0))
                progress_bar = self._create_progress_bar(total, f"Downloading {url}")
                response._content = self._stream_response(response, progress_bar)
                # Mark the body as fully read so `.text`/`.json()` serve the
                # buffer we just built instead of re-reading a drained socket.
                cast(Any, response)._content_consumed = True

            return response

        except requests.exceptions.HTTPError as e:
            if verbose:
                print(f"[VERBOSE] HTTPError: {e}")
            raise ResponseError(f"HTTP error occurred: {e!s}") from e
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.RetryError,
        ) as e:
            if verbose:
                print(f"[VERBOSE] ConnectionError: {e}")
            raise HTTPConnectionError(f"Failed to connect to {url}: {e!s}") from e
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"[VERBOSE] RequestException: {e}")
            raise HTTPClientError(f"Request failed: {e!s}") from e

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a GET request to the specified URL.

        Args:
            url (str): The URL to send the GET request to.
            **kwargs: Additional keyword arguments for the request.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a POST request to the specified URL.

        Args:
            url (str): The URL to send the POST request to.
            **kwargs: Additional keyword arguments for the request, such as `json` or `data`.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a PUT request to the specified URL.

        Args:
            url (str): The URL to send the PUT request to.
            **kwargs: Additional keyword arguments for the request, such as `json` or `data`.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a PATCH request to the specified URL.

        Args:
            url (str): The URL to send the PATCH request to.
            **kwargs: Additional keyword arguments for the request, such as `json` or `data`.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a DELETE request to the specified URL.

        Args:
            url (str): The URL to send the DELETE request to.
            **kwargs: Additional keyword arguments for the request.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a HEAD request to the specified URL.

        Args:
            url (str): The URL to send the HEAD request to.
            **kwargs: Additional keyword arguments for the request.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("HEAD", url, **kwargs)

    def options(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends an OPTIONS request to the specified URL.

        Args:
            url (str): The URL to send the OPTIONS request to.
            **kwargs: Additional keyword arguments for the request.

        Returns:
            requests.Response: The HTTP response object.
        """
        return self.make_request("OPTIONS", url, **kwargs)
