"""A lightweight and flexible HTTP client library for Python.

This package provides the `HTTPClient` for making HTTP requests and custom
exceptions for handling errors. It is designed to be used both as a
command-line tool and as a library in other Python applications.

`HTTPClient` is resolved lazily (PEP 562) so that importing this package -- or
running the CLI's help paths -- does not pull in `requests`, which costs well
over 100 ms of interpreter start-up on its own. `from pyfetch import HTTPClient`
keeps working exactly as before and imports the stack on first access.

Public API:
    - `HTTPClient`: The main client for making HTTP requests.
    - `HTTPClientError`: Base exception for client errors.
    - `HTTPConnectionError`: Exception for connection-related issues.
    - `ResponseError`: Exception for bad HTTP responses.
"""

from typing import TYPE_CHECKING, Any

from pyfetch.exceptions import HTTPClientError, HTTPConnectionError, ResponseError

if TYPE_CHECKING:
    from pyfetch.http_client import HTTPClient

__version__ = "2.0.0"

__all__ = [
    "HTTPClient",
    "HTTPClientError",
    "HTTPConnectionError",
    "ResponseError",
    "__version__",
]


def __getattr__(name: str) -> Any:
    """Resolves `HTTPClient` on first access, deferring the `requests` import."""
    if name == "HTTPClient":
        from pyfetch.http_client import HTTPClient

        return HTTPClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
