# Python API reference

The public API is `snaffle.HTTPClient` and three exception classes. The package
ships a PEP 561 `py.typed` marker, so downstream type checkers use its
annotations without extra configuration.

```python
from snaffle import HTTPClient, HTTPClientError, HTTPConnectionError, ResponseError
```

`snaffle.__version__` holds the distribution version as a string. It is read
from the installed distribution's metadata rather than hard-coded, so the
version is stated once, in `pyproject.toml`. Like `HTTPClient` it resolves on
first access, so `import snaffle` does not pay for the metadata lookup.

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
    session: requests.Session | None = None,
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
| `verbose` | `bool` | `False` | Print the outgoing request, the response status and headers, and the underlying `requests` exception behind any failure, each prefixed `[VERBOSE]`. |
| `show_progress` | `bool` | `False` | Stream `GET` responses and draw a `tqdm` bar once `Content-Length` reaches `MIN_SIZE_FOR_PROGRESS`. A caller who passes `stream=True` opts out; see [`make_request`](#make_request). |
| `session` | `requests.Session \| None` | `None` | The session to send through. `None` builds the pooled, retrying session described above. A session passed here is used exactly as it arrives; see below. |

Validation runs in `__init__`, before any network access.

#### Passing a session

Two rules apply to a session you supply, and neither is guessed at:

- **`retries` does not apply to it.** The retry policy and the connection pool
  both come from the session's mounted adapters, so they arrive with the
  session. `retries` builds the default session and nothing else — it is still
  validated, still stored on `client.retries`, and has no effect on a session
  you passed. Passing both is not an error: a caller who mounts a five-attempt
  adapter may reasonably want `client.retries` to say `5`.
- **The client will not close it.** `close()` and `__exit__` close only a
  session the client built, because one you passed may be shared with other
  clients or outlive this one. Closing it is yours to do.

It is the last parameter, so existing positional calls are unaffected; pass it
by keyword. Its use is substituting the transport — in tests, mounting an
adapter on a session you pass is the only substitution above the socket that
leaves urllib3's retry loop in place, and it needs no patching. See
[ADR 0004](../architecture/decisions/0004-inject-the-session.md).

```python
session = requests.Session()
session.mount("https://", my_adapter)

with HTTPClient(session=session) as client:   # client sends through my_adapter
    client.get("https://example.com")

session.close()                               # the client did not
```

### Instance attributes

| Attribute | Type | Notes |
| --- | --- | --- |
| `timeout` | `int` | As constructed. |
| `retries` | `int` | As constructed. Applied to the default session only; see [Passing a session](#passing-a-session). |
| `verbose` | `bool` | As constructed. |
| `show_progress` | `bool` | As constructed. |
| `allowed_methods` | `frozenset[str]` | The methods this instance accepts. Initialised from `ALLOWED_METHODS` and read on every request. |
| `session` | `requests.Session` | The session requests go through: the one passed to the constructor, or a pooled one with the retrying adapter mounted on `http://` and `https://`. |

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
sets `stream=True` when it is going to feed a progress bar, sends the request
with the client's `timeout`, calls `raise_for_status()`, and translates
`requests` exceptions into this package's hierarchy.

When progress tracking is active it drains the body into `response._content` and
marks it consumed, so `.text` and `.json()` serve the buffer rather than
re-reading a drained socket.

Passing `stream=True` yourself opts out of that draining, whatever
`show_progress` says: you get an unconsumed response to iterate, and no bar is
drawn. The two cannot both hold — a bar is fed by reading the body, and reading
the body is what you asked to do yourself. To have both, drive `tqdm` from your
own loop; see
[Download large files](../guides/downloading-large-files.md#combine-your-own-progress-bar-with-streaming).

Raises:

| Exception | When |
| --- | --- |
| `ValueError` | `method` is not in `allowed_methods`. Raised before any network access. |
| `ResponseError` | The response carried a 4xx or 5xx status — including a retryable status that was still failing on the last attempt. |
| `HTTPConnectionError` | The connection was refused, unresolvable, or timed out while being established, or the adapter exhausted its retries on a connection error. |
| `HTTPClientError` | Any other `requests.RequestException` — a read timeout, too many redirects, a malformed URL. |

Two boundaries are easy to get wrong:

- **Exhausted status retries surface as `ResponseError`, not `HTTPConnectionError`.**
  The adapter is built with `raise_on_status=False`, so when a `503` is still a
  `503` on the final attempt urllib3 returns that response rather than raising.
  `raise_for_status()` then turns it into a `ResponseError` carrying the real
  status, which is more useful than a generic connection failure. Only
  *connection* retries exhaust into `RetryError`, and that is what the
  `HTTPConnectionError` row above refers to.
- **A connect timeout is an `HTTPConnectionError`; a read timeout is an
  `HTTPClientError`.** `requests.exceptions.ConnectTimeout` subclasses
  `ConnectionError`, so it is caught as a connection failure — which is what it
  is. `ReadTimeout` does not, so it falls through to the general case.

#### `close`

```python
client.close() -> None
```

Closes the session and releases pooled connections. Idempotent.

Only a session the client built. A session passed to the constructor is left
open — see [Passing a session](#passing-a-session).

#### `__enter__` / `__exit__`

`HTTPClient` is a context manager. `__enter__` returns the client; `__exit__`
calls `close()` and suppresses nothing — including, therefore, leaving an
injected session open.

```python
with HTTPClient() as client:
    client.get("https://example.com")
```

### `ProgressBar`

A `typing.Protocol` describing the two `tqdm` methods the client uses —
`update(n)` and `close()`. It is defined in `snaffle.http_client`, which is its
supported import path. The private `snaffle._download` module builds the bars
and refers to the protocol under `TYPE_CHECKING` only, so the run-time
dependency between the two still runs one way. The client does not accept an
injected progress bar.

## Exceptions

Defined in `snaffle.exceptions` and re-exported from `snaffle`.

```
Exception
└── HTTPClientError          base for everything this package raises
    ├── HTTPConnectionError  the connection failed, timed out, or was refused
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

`raise_on_status=False` decides what a caller sees when retries run out: a
status that never recovered comes back as a response and becomes a
`ResponseError`, while a connection that never succeeded raises `RetryError`
inside the adapter and becomes an `HTTPConnectionError`. See
[Raises](#make_request) above.

Because retries happen inside the adapter, mocking `requests.Session.request`
cannot observe them. A test that needs to see them substitutes the session
instead, which leaves the adapter underneath it — see
[Passing a session](#passing-a-session) and
[contributing](../../CONTRIBUTING.md#testing-notes).

The policy in this table is the one `HTTPClient` builds. A session you pass
carries whatever policy its own adapters were mounted with.
