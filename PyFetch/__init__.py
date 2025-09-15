"""A lightweight and flexible HTTP client library for Python.

This package provides the `HTTPClient` for making HTTP requests and custom
exceptions for handling errors. It is designed to be used both as a
command-line tool and as a library in other Python applications.

Public API:
    - `HTTPClient`: The main client for making HTTP requests.
    - `HTTPClientError`: Base exception for client errors.
    - `HTTPConnectionError`: Exception for connection-related issues.
    - `ResponseError`: Exception for bad HTTP responses.
"""

from PyFetch.exceptions import HTTPClientError, HTTPConnectionError, ResponseError
from PyFetch.http_client import HTTPClient

__all__ = ["HTTPClient", "HTTPClientError", "HTTPConnectionError", "ResponseError"]
