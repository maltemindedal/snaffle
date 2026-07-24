"""A lightweight and flexible HTTP client library for Python.

This package provides the `HTTPClient` for making HTTP requests and custom
exceptions for handling errors. It is designed to be used both as a
command-line tool and as a library in other Python applications.

`HTTPClient` is resolved lazily (PEP 562) so that importing this package -- or
running the CLI's help paths -- does not pull in `requests`, which costs well
over 100 ms of interpreter start-up on its own. `from snaffle import HTTPClient`
keeps working exactly as before and imports the stack on first access.

`__version__` is resolved the same way, from the installed distribution's
metadata, so the version is stated in exactly one place: `pyproject.toml`.

Public API:
    - `HTTPClient`: The main client for making HTTP requests.
    - `HTTPClientError`: Base exception for client errors.
    - `HTTPConnectionError`: Exception for connection-related issues.
    - `ResponseError`: Exception for bad HTTP responses.
    - `__version__`: The installed distribution version.
"""

from typing import TYPE_CHECKING, Any

from snaffle.exceptions import HTTPClientError, HTTPConnectionError, ResponseError

if TYPE_CHECKING:
    from snaffle.http_client import HTTPClient

    #: Resolved lazily at runtime; declared here so type checkers see a `str`.
    __version__: str

__all__ = [
    "HTTPClient",
    "HTTPClientError",
    "HTTPConnectionError",
    "ResponseError",
    "__version__",
]


def __getattr__(name: str) -> Any:
    """Resolves `HTTPClient` and `__version__` on first access.

    Both are deferred: `HTTPClient` so that `requests` is not imported, and
    `__version__` so that reading the installed distribution's metadata is not
    charged to every import of this package.
    """
    if name == "HTTPClient":
        from snaffle.http_client import HTTPClient

        return HTTPClient
    if name == "__version__":
        from importlib.metadata import version

        return version("snaffle")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
