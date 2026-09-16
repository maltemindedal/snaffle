"""Exceptions raised by the Snaffle HTTP client."""


class HTTPClientError(Exception):
    """Base class for errors raised by the Snaffle client."""

    pass


class HTTPConnectionError(HTTPClientError):
    """Raised when the client cannot connect to the target server."""

    pass


class ResponseError(HTTPClientError):
    """Raised when the server returns a 4xx or 5xx status code."""

    pass
