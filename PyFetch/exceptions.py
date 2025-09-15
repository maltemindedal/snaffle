"""Custom exceptions for the PyFetch HTTP client.

This module defines a hierarchy of custom exceptions to provide more specific
error information when using the PyFetch client.
"""


class HTTPClientError(Exception):
    """Base exception for all errors raised by the PyFetch client.

    This exception serves as the base for more specific client-related errors,
    allowing for consolidated error handling.
    """


class HTTPConnectionError(HTTPClientError):
    """Raised when a connection to the target server fails.

    This error typically occurs due to network issues, DNS failures, or if the
    server is unreachable.
    """


class ResponseError(HTTPClientError):
    """Raised when the server returns an unsuccessful HTTP status code.

    This error is triggered for responses with 4xx (client error) or 5xx
    (server error) status codes.
    """
