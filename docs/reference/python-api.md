# Python API reference

The public API is `snaffle.HTTPClient` and three exception classes. The package
ships a PEP 561 `py.typed` marker, so downstream type checkers use its
annotations without extra configuration.

```python
from snaffle import HTTPClient, HTTPClientError, HTTPConnectionError, ResponseError
```

`snaffle.__version__` holds the distribution version as a string.

`HTTPClient` is resolved through a module-level `__getattr__` (PEP 562), so
`import snaffle` does not import `requests`. The import happens on first
attribute access. `from snaffle import HTTPClient` behaves as it would with a
direct import; only the timing differs.

## `HTTPClient`

```python
HTTPClient(
    timeout: int = 30,
    retries: int = 3,
    verbose: bool = False,
    show_progress: bool = False,
) -> HTTPClient
```

A client owns a pooled `requests.Session` for its lifetime. Repeated requests
to the same host reuse the established TCP/TLS connection. Because the client
holds an operating-system resource, close it — use it as a context manager or
call `close()`.

### Constructor arguments

| Argument | Type | Default | Effect |
| --- | --- | --- | --- |
| `timeout` | `int` | `30` | Seconds before a request times out. Must be `> 0`; `ValueError` otherwise. |
| `retries` | `int` | `3` | Total attempts for a failed request, not retries after the first. Must be `> 0`; `ValueError` otherwise. Translated to `urllib3.util.retry.Retry(total=retries - 1)`. |
| `verbose` | `bool` | `False` | Print the outgoing request, and the response status and headers, prefixed `[VERBOSE]`. |
| `show_progress` | `bool` | `False` | Stream `GET` responses and draw a `tqdm` bar once `Content-Length` reaches `MIN_SIZE_FOR_PROGRESS`. |

Validation runs in `__init__`, before any network access.

### Instance attributes

| Attribute | Type | Notes |
| --- | --- | --- |
| `timeout` | `int` | As constructed. |
| `retries` | `int` | As constructed. |
| `verbose` | `bool` | As constructed. |
| `show_progress` | `bool` | As constructed. |
| `allowed_methods` | `frozenset[str]` | Copy of `ALLOWED_METHODS`. |
| `session` | `requests.Session` | The pooled session, with the retrying adapter mounted on `http://` and `https://`. |

The class defines no `__slots__`: instances stay weak-referenceable and accept
arbitrary attributes.

### Class constants

| Constant | Value | Effect |
| --- | --- | --- |
| `ALLOWED_METHODS` | `frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})` | Any other method raises `ValueError` before a socket is opened. |
| `DOWNLOAD_CHUNK_SIZE` | `65536` (64 KiB) | Chunk size for streamed reads. Larger chunks mean fewer syscalls and fewer progress-bar refreshes per megabyte, at the cost of a larger in-flight working set. |
| `MIN_SIZE_FOR_PROGRESS` | `5 * 1024 * 1024` (5 MiB) | Minimum `Content-Length` before a progress bar is drawn. The comparison is `>=`. |
| `RETRY_STATUSES` | `frozenset({408, 425, 429, 500, 502, 503, 504})` | Statuses eligible for retry. See [ADR 0001](../architecture/decisions/0001-selective-retries-and-connection-pooling.md). |
| `POOL_SIZE` | `16` | `pool_connections` and `pool_maxsize` on the mounted adapter. |

These are class attributes, so subclassing overrides them for all instances of
the subclass:

```python
class BigChunkClient(HTTPClient):
    DOWNLOAD_CHUNK_SIZE = 1024 * 1024
```

`RETRY_STATUSES` and `POOL_SIZE` are read by `_build_session` during
`__init__`, so an override must be in place before the client is constructed.

### Methods

#### `get`, `post`, `put`, `patch`, `delete`, `head`, `options`

```python
client.get(url: str, **kwargs: Any) -> requests.Response
```

Thin wrappers over `make_request` with the method fixed. Every keyword argument
is forwarded to `requests.Session.request` — `json=`, `data=`, `headers=`,
`params=`, `stream=`, `allow_redirects=`, and the rest of the `requests`
surface all work.

#### `make_request`

```python
client.make_request(method: str, url: str, **kwargs: Any) -> requests.Response
```

The single path all seven wrappers take. It validates and upper-cases `method`,
sets `stream=True` when `show_progress` is on and the method is `GET`, sends the
request with the client's `timeout`, calls `raise_for_status()`, and translates
`requests` exceptions into this package's hierarchy.

When progress tracking is active it drains the body into `response._content` and
marks it consumed, so `.text` and `.json()` serve the buffer rather than
re-reading a drained socket.

Passing `stream=True` yourself does not trigger that draining: you get an
unconsumed response to iterate. Passing `stream=True` on a `GET` while
`show_progress` is on has no additional effect — the client sets it anyway.

Raises:

| Exception | When |
| --- | --- |
| `ValueError` | `method` is not in `ALLOWED_METHODS`. Raised before any network access. |
| `ResponseError` | The response carried a 4xx or 5xx status. |
| `HTTPConnectionError` | The connection failed, or the adapter exhausted its retries. |
| `HTTPClientError` | Any other `requests.RequestException`, including timeouts. |

#### `close`

```python
client.close() -> None
```

Closes the session and releases pooled connections. Idempotent.

#### `__enter__` / `__exit__`

`HTTPClient` is a context manager. `__enter__` returns the client; `__exit__`
calls `close()` and suppresses nothing.

```python
with HTTPClient() as client:
    client.get("https://example.com")
```

### `ProgressBar`

A `typing.Protocol` describing the two `tqdm` methods the client uses —
`update(n)` and `close()`. Exported from `snaffle.http_client` for typing
purposes; the client does not accept an injected progress bar.

## Exceptions

Defined in `snaffle.exceptions` and re-exported from `snaffle`.

```
Exception
└── HTTPClientError          base for everything this package raises
    ├── HTTPConnectionError  the connection failed or retries were exhausted
    └── ResponseError        the server answered with a 4xx or 5xx status
```

Catching `HTTPClientError` catches all three. Each carries a message string; the
original `requests` exception is attached as `__cause__`.

```python
try:
    response = client.get(url)
except ResponseError as error:
    print(f"Bad status: {error}")
    print(f"Underlying: {error.__cause__!r}")
except HTTPConnectionError as error:
    print(f"Unreachable: {error}")
```

`ValueError` from an unsupported method or an invalid constructor argument is
*not* part of this hierarchy.

## Retry behaviour

Retries live on the session's `HTTPAdapter` as a `urllib3.util.retry.Retry`
with `backoff_factor=0.3`, `respect_retry_after_header=True`, and
`raise_on_status=False`. Which failures are retried depends on the method:

| Failure | `GET`, `HEAD`, `PUT`, `DELETE`, `OPTIONS` | `POST`, `PATCH` |
| --- | --- | --- |
| Connection never established | retried | **retried** |
| Read failure after the request landed | retried | not retried |
| Status in `RETRY_STATUSES` | retried | not retried |
| Any other status (404, 401, ...) | not retried | not retried |

The rationale is in [ADR 0001](../architecture/decisions/0001-selective-retries-and-connection-pooling.md).

Because retries happen inside the adapter, mocking `requests.Session.request`
cannot observe them — see [contributing](../../CONTRIBUTING.md#testing-notes).
