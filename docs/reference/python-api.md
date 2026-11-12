# Python API reference

The public API is `snaffle.HTTPClient` and the exception classes in
`snaffle.__all__`. The package
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
holds an operating-system resource, close it. Use it as a context manager or
call `close()`.

### Constructor arguments

The defaults are in the signature above.

| Argument | Type | Effect |
| --- | --- | --- |
| `timeout` | `int` | Seconds before a request times out. Must be `> 0`; `ValueError` otherwise. |
| `retries` | `int` | Total attempts for a failed request, not retries after the first. Must be `> 0`; `ValueError` otherwise. Translated to `urllib3.util.retry.Retry(total=retries - 1)`. |
| `verbose` | `bool` | Print the outgoing request, the response status and headers, and the underlying `requests` exception behind any failure, each prefixed `[VERBOSE]`. The values of `Authorization`, `Proxy-Authorization` and `Cookie` headers and of the `auth`, `cookies` and `proxies` arguments are shown as `<redacted>`; everything else, including `data`, `params` and the URL, is shown as given. |
| `show_progress` | `bool` | Stream `GET` responses and draw a `tqdm` bar once `Content-Length` reaches `MIN_SIZE_FOR_PROGRESS`. A caller who passes `stream=True` opts out; see [`make_request`](#make_request). |
| `session` | `requests.Session \| None` | The session to send through. `None` builds the pooled, retrying session described above. A session passed here is used exactly as it arrives; see below. |

Validation runs in `__init__`, before any network access.

#### Passing a session

Two rules apply to a session you supply, and neither is guessed at:

- **`retries` does not apply to it.** The retry policy and the connection pool
  both come from the session's mounted adapters, so they arrive with the
  session. `retries` builds the default session and nothing else. It is still
  validated, still stored on `client.retries`, and has no effect on a session
  you passed. Passing both is not an error: a caller who mounts a five-attempt
  adapter may reasonably want `client.retries` to say `5`.
- **The client will not close it.** `close()` and `__exit__` close only a
  session the client built, because one you passed may be shared with other
  clients or outlive this one. Closing it is yours to do.

It is the last parameter, so existing positional calls are unaffected; pass it
by keyword. Use it to substitute the transport. In tests, mounting an
adapter on a session you pass is the only substitution above the socket that
leaves urllib3's retry loop in place, and it needs no patching. See
[ADR 0004](../architecture/decisions/0004-inject-the-session.md).

```python
session = requests.Session()
session.mount("https://", my_adapter)

with HTTPClient(session=session) as client:  # client sends through my_adapter
    client.get("https://example.com")

session.close()  # the client did not
```

### Instance attributes

| Attribute | Type | Notes |
| --- | --- | --- |
| `timeout` | `int` | As constructed. |
| `retries` | `int` | As constructed. Applied to the default session only; see [Passing a session](#passing-a-session). |
| `verbose` | `bool` | As constructed. |
| `show_progress` | `bool` | As constructed. |
| `allowed_methods` | `frozenset[str]` | The methods this instance accepts. Initialised from `ALLOWED_METHODS` and read on every request. |
| `session` | `requests.Session` | The session used for requests: the one passed to the constructor, or a pooled one with the retrying adapter mounted on `http://` and `https://`. |

The class defines no `__slots__`: instances stay weak-referenceable and accept
arbitrary attributes.

### Class constants

The values are generated from the class by
`uv run python -m tests.test_docs_sync --write`.

| Constant | Value | Effect |
| --- | --- | --- |
| `ALLOWED_METHODS` | <!-- generated: const-ALLOWED_METHODS -->`frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})`<!-- end --> | The methods a client accepts. Any other method raises `ValueError` before a socket is opened. |
| `DOWNLOAD_CHUNK_SIZE` | <!-- generated: const-DOWNLOAD_CHUNK_SIZE -->`65536` (64 KiB)<!-- end --> | Chunk size for streamed reads. Larger chunks mean fewer syscalls and fewer progress-bar refreshes per megabyte, at the cost of a larger in-flight working set. |
| `MIN_SIZE_FOR_PROGRESS` | <!-- generated: const-MIN_SIZE_FOR_PROGRESS -->`5242880` (5 MiB)<!-- end --> | Minimum `Content-Length` before a progress bar is drawn. The comparison is `>=`. |
| `RETRY_STATUSES` | <!-- generated: const-RETRY_STATUSES -->`frozenset({408, 425, 429, 500, 502, 503, 504})`<!-- end --> | Statuses eligible for retry. See [ADR 0001](../architecture/decisions/0001-selective-retries-and-connection-pooling.md). |
| `POOL_SIZE` | <!-- generated: const-POOL_SIZE -->`16`<!-- end --> | `pool_connections` and `pool_maxsize` on the mounted adapter. |

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

Thin wrappers over `make_request` with the method fixed. They take the same
keyword arguments, such as `json=`, `data=`, `headers=` and `params=`.

#### `make_request`

```python
client.make_request(method: str, url: str, **kwargs: Any) -> requests.Response
```

The single path every verb wrapper takes. It validates and upper-cases `method`,
sets `stream=True` when it is going to feed a progress bar, sends the request
with the client's `timeout`, calls `raise_for_status()`, and translates
`requests` exceptions into this package's hierarchy.

Every other keyword argument is passed to `requests.Session.request`. `timeout`
is the exception: it is set once, on the client, and passing it to a call raises
`TypeError` (`got multiple values for keyword argument 'timeout'`), as does
`method` or `url` by keyword. To use a different timeout for a request, build a
client with that `timeout`.

When progress tracking is active it drains the body into `response._content` and
marks it consumed, so `.text` and `.json()` serve the buffer rather than
re-reading a drained socket.

Passing `stream=True` yourself opts out of that draining, whatever
`show_progress` says: you get an unconsumed response to iterate, and no bar is
drawn. The two cannot both hold. A bar advances by reading the body, and reading
the body is what you asked to do yourself. To have both, drive `tqdm` from your
own loop; see
[Download large files](../guides/downloading-large-files.md#combine-your-own-progress-bar-with-streaming).

Raises:

| Exception | When |
| --- | --- |
| `ValueError` | `method` is not in `allowed_methods`. Raised before any network access. |
| `ResponseError` | The response carried a 4xx or 5xx status. |
| `HTTPConnectionError` | `requests` reported a connection error, or the retries for one ran out. |
| `HTTPClientError` | Any other failure `requests` reports, and urllib3's `LocationValueError` for a host it cannot parse. |

A retryable status that is still failing on the last attempt is a
`ResponseError` carrying that status. The adapter is built with
`raise_on_status=False`, so urllib3 returns the last response rather than a
generic retry error, and the real status is more useful to a caller.

A timeout is the case that is easy to get wrong. Which exception it becomes
depends on the method and on when it strikes, because a `POST` or `PATCH` is
never replayed after a read failure and so never exhausts its retries. These
examples run in the test suite:

```pycon
>>> import socket
>>> from snaffle import HTTPClient
>>> silent = socket.create_server(("127.0.0.1", 0))  # accepts, never answers
>>> url = "http://127.0.0.1:%d/" % silent.getsockname()[1]
>>> with HTTPClient(timeout=1, retries=1) as client:
...     client.get(url)
Traceback (most recent call last):
HTTPConnectionError: Failed to connect to ...
>>> with HTTPClient(timeout=1, retries=1) as client:
...     client.post(url)
Traceback (most recent call last):
HTTPClientError: Request failed: ...
>>> silent.close()
>>> with HTTPClient(timeout=1, retries=1) as client:  # now nothing listens
...     client.post(url)
Traceback (most recent call last):
HTTPConnectionError: Failed to connect to ...
```

A server that sends the headers and then goes silent part-way through the body
raises `requests.exceptions.ConnectionError` from the body read, for every
method, and is not retried. It happens inside `make_request` for an ordinary
call, which reads the body before returning, and while draining the body when
`show_progress` is on. With `stream=True` you read the body yourself, after
`make_request` has returned, and the exception is `requests`' own.

#### `close`

```python
client.close() -> None
```

Closes the session and releases pooled connections. Idempotent.

Only a session the client built. A session passed to the constructor is left
open. See [Passing a session](#passing-a-session).

#### `__enter__` / `__exit__`

`HTTPClient` is a context manager. `__enter__` returns the client; `__exit__`
calls `close()` and suppresses nothing. It leaves an
injected session open.

```python
with HTTPClient() as client:
    client.get("https://example.com")
```

### `ProgressBar`

A `typing.Protocol` describing the two `tqdm` methods the client uses:
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
original exception is attached as `__cause__`. It comes from `requests`, or from
urllib3 when a host cannot be parsed.

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

Retries live on the session's `HTTPAdapter` as a `urllib3.util.retry.Retry`,
built in `HTTPClient._build_session`. They back off with a `backoff_factor` of
<!-- generated: retry-backoff-factor -->`0.3`<!-- end -->, and honour a `Retry-After`
header of up to <!-- generated: retry-after-cap -->120<!-- end --> seconds per
retry. Which failures are retried depends on the method. This table shows what a
default client does with each failure. It is generated by sending each request
through urllib3's retry loop
(`uv run python -m tests.test_docs_sync --write`). The rationale is in
[ADR 0001](../architecture/decisions/0001-selective-retries-and-connection-pooling.md),
and `TestRetryPolicy` in `tests/test_http_client.py` pins it.

<!-- generated: errors -->

| Failure | `GET`, `PUT`, `DELETE`, `HEAD`, `OPTIONS` | `POST`, `PATCH` |
| --- | --- | --- |
| Connection never established | `HTTPConnectionError` after 3 attempts | `HTTPConnectionError` after 3 attempts |
| Read timeout while waiting for the response | `HTTPConnectionError` after 3 attempts | `HTTPClientError` after 1 attempt |
| Status in `RETRY_STATUSES` (504) on every attempt | `ResponseError` after 3 attempts | `ResponseError` after 1 attempt |
| Any other error status (404) | `ResponseError` after 1 attempt | `ResponseError` after 1 attempt |

<!-- end -->

Because retries happen inside the adapter, mocking `requests.Session.request`
cannot observe them. A test that needs to see them substitutes the session
instead, which leaves the adapter underneath it. See
[Passing a session](#passing-a-session) and
[contributing](../../CONTRIBUTING.md#testing-notes).

The policy in this table is the one `HTTPClient` builds. A session you pass
carries whatever policy its own adapters were mounted with.
