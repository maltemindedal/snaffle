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
from typing import Any, Protocol

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from snaffle._download import buffer_into, should_buffer
from snaffle.exceptions import HTTPClientError, HTTPConnectionError, ResponseError

__all__ = ["HTTPClient", "ProgressBar"]


class ProgressBar(Protocol):
    """Protocol for the subset of progress-bar methods used by the client.

    Defined here because it is documented as part of this module's surface.
    `_download` builds the bars and refers to this protocol under
    `TYPE_CHECKING` only, so the dependency between the two modules still runs
    one way at run time.
    """

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

    The session is built by :meth:`_build_session` unless one is passed to the
    constructor. **A client closes only a session it built**: one it was given
    belongs to the caller, who may be sharing it, and closing it would pull the
    pool out from under them.

    Passing a session is how the transport is substituted without patching
    `requests.Session.request` -- a mock there sits above the adapter and cannot
    observe a retry. An injected session brings its own adapters, so it also
    brings its own retry policy and connection pool; `retries` builds the default
    session and does not reach one supplied here.

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
        session: requests.Session | None = None,
    ) -> None:
        """Initializes the HTTPClient with configuration options.

        Args:
            timeout (int, optional): The timeout for HTTP requests in seconds. Defaults to 30.
            retries (int, optional): The total number of attempts for failed requests. Defaults to 3.
            verbose (bool, optional): Whether to enable verbose logging. Defaults to False.
            show_progress (bool, optional): Whether to show a progress bar for large downloads. Defaults to False.
            session (requests.Session, optional): A session to send through. Defaults
                to one built by :meth:`_build_session`. A session passed here is
                used as it arrives: `retries` builds the default session and is not
                applied to this one, because the retry policy and the connection
                pool both come from the session's mounted adapters. The client does
                not close a session it did not build; see :meth:`close`.
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
        self._owns_session = session is None
        self.session = self._build_session(retries) if session is None else session

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
        """Closes the session this client built, releasing pooled connections.

        A session passed to the constructor belongs to the caller, who may be
        sharing it with other clients, so it is left open. Closing it is theirs
        to do.
        """
        if self._owns_session:
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
        """Calls :meth:`close` on exit, suppressing nothing."""
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

    def make_request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Makes an HTTP request with retry logic and error handling.

        This is the core method for all HTTP operations performed by the client.
        Retries with exponential backoff are handled by the session's adapter;
        see the class docstring for which failures are retried for which methods.

        A `GET` sent while `show_progress` is on streams its body and drains it
        through a progress bar into a buffer, so the response that comes back is
        fully read. A caller who passes `stream=True` opts out of that: the body
        is left unread for them to iterate, and no bar is drawn.

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

        # Whether the body is worth streaming and draining ourselves is
        # `_download`'s decision, including the opt-out for a caller who passed
        # `stream=True` and will read the body themselves. All this method does
        # is switch the transport into streaming mode when the answer is yes.
        buffer_body = should_buffer(normalized_method, self.show_progress, kwargs)
        if buffer_body:
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

            if buffer_body:
                buffer_into(
                    response,
                    chunk_size=self.DOWNLOAD_CHUNK_SIZE,
                    min_size=self.MIN_SIZE_FOR_PROGRESS,
                    desc=f"Downloading {url}",
                )

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

    # The seven verb methods below are `make_request` with the method fixed.
    # They carry no behaviour of their own, so they do not restate its contract:
    # arguments, return value and exceptions are documented once, there and in
    # `docs/reference/python-api.md`, rather than seven times over here.

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a GET request. See :meth:`make_request` for the contract."""
        return self.make_request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a POST request. See :meth:`make_request` for the contract."""
        return self.make_request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a PUT request. See :meth:`make_request` for the contract."""
        return self.make_request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a PATCH request. See :meth:`make_request` for the contract."""
        return self.make_request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a DELETE request. See :meth:`make_request` for the contract."""
        return self.make_request("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends a HEAD request. See :meth:`make_request` for the contract."""
        return self.make_request("HEAD", url, **kwargs)

    def options(self, url: str, **kwargs: Any) -> requests.Response:
        """Sends an OPTIONS request. See :meth:`make_request` for the contract."""
        return self.make_request("OPTIONS", url, **kwargs)
