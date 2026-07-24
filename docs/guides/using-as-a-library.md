# Use Snaffle as a library

How to drive `HTTPClient` from Python code. For the exhaustive argument list,
see the [Python API reference](../reference/python-api.md).

## Create and release a client

A client owns a pooled connection. Use a context manager so it is released:

```python
from snaffle import HTTPClient

with HTTPClient() as client:
    response = client.get("https://httpbin.org/get")
```

If the client's lifetime does not fit a `with` block — one held on a
long-lived object, for instance — call `close()` when you are done:

```python
class ApiWrapper:
    def __init__(self) -> None:
        self._client = HTTPClient(timeout=10)

    def close(self) -> None:
        self._client.close()
```

A client that is never closed holds sockets open until garbage collection.

## Reuse one client for a batch

Creating a client per request throws away the connection pool, which is the
main thing the client buys you. Create one, loop inside it:

```python
with HTTPClient() as client:
    for page in range(10):
        # Every iteration after the first reuses the open connection.
        response = client.get(f"https://httpbin.org/get?page={page}")
        print(response.status_code)
```

The pool holds up to `HTTPClient.POOL_SIZE` (16) connections, so a client
talking to several hosts keeps a connection to each.

`HTTPClient` is not documented as thread-safe. The underlying
`requests.Session` is generally safe for concurrent use across threads, but
Snaffle has no tests covering it — give each thread its own client if you need
concurrency.

## Handle errors

Three exceptions, one base class:

```python
from snaffle import HTTPClient, HTTPClientError, HTTPConnectionError, ResponseError

with HTTPClient() as client:
    try:
        response = client.get("https://httpbin.org/status/500")
    except ResponseError as error:
        # 4xx or 5xx. raise_for_status() fired. A transient status that was
        # retried and never recovered arrives here too, carrying the real code.
        print(f"Server said no: {error}")
    except HTTPConnectionError as error:
        # DNS failure, refused connection, or a connect timeout.
        print(f"Could not reach it: {error}")
    except HTTPClientError as error:
        # Anything else from requests -- a read timeout, too many redirects.
        print(f"Request failed: {error}")
```

Catch `HTTPClientError` alone if the distinction does not matter. The original
`requests` exception is always on `__cause__`:

```python
except ResponseError as error:
    original = error.__cause__          # requests.exceptions.HTTPError
    status = original.response.status_code
```

An unsupported method raises plain `ValueError`, not `HTTPClientError`, and
does so before any socket is opened:

```python
client.make_request("TRACE", url)  # ValueError: Unsupported HTTP method...
```

## Send bodies the CLI cannot

Every keyword argument passes straight through to
`requests.Session.request`, so the whole `requests` surface is available.

```python
with HTTPClient() as client:
    # JSON — the same thing the CLI's -d flag does
    client.post("https://httpbin.org/post", json={"key": "value"})

    # Form-encoded
    client.post("https://httpbin.org/post", data={"field": "value"})

    # Raw bytes with an explicit type
    client.post(
        "https://httpbin.org/post",
        data=b"\x00\x01\x02",
        headers={"Content-Type": "application/octet-stream"},
    )

    # File upload
    with open("report.pdf", "rb") as handle:
        client.post("https://httpbin.org/post", files={"file": handle})

    # Query parameters as a mapping
    client.get("https://httpbin.org/get", params={"q": "search term"})
```

## Tune timeouts and retries

Both are per-client, set at construction:

```python
# Fail fast: 5-second timeout, one attempt, no retry.
with HTTPClient(timeout=5, retries=1) as client:
    client.get(url)

# Patient: 60 seconds, five attempts with exponential backoff.
with HTTPClient(timeout=60, retries=5) as client:
    client.get(url)
```

`retries` counts *total attempts*, not retries after the first. `retries=1`
means one attempt and no retry. Both arguments must be greater than zero.

Retries carry a `backoff_factor` of 0.3 and honour `Retry-After`. Which
failures are retried depends on the method — a `POST` is never replayed once
the request is on the wire. The table is in the
[API reference](../reference/python-api.md#retry-behaviour); the reasoning is in
[ADR 0001](../architecture/decisions/0001-selective-retries-and-connection-pooling.md).

## Change the defaults for a whole application

The tunable constants are class attributes, so subclassing overrides them:

```python
class PatientClient(HTTPClient):
    RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504, 521})
    POOL_SIZE = 64
    MIN_SIZE_FOR_PROGRESS = 1024 * 1024  # bar from 1 MiB up
```

`RETRY_STATUSES` and `POOL_SIZE` are read while the session is built during
`__init__`, so overriding them on an existing instance has no effect.

## Log what is being sent

`verbose=True` prints the request and the response metadata to stdout:

```python
with HTTPClient(verbose=True) as client:
    client.get("https://httpbin.org/get")
```

```
[VERBOSE] Sending GET request to https://httpbin.org/get with {}
[VERBOSE] Received response with status 200 and headers {...}
```

This is `print`, not the `logging` module — there is no way to redirect it to a
logger short of capturing stdout. For structured logging, enable
`requests`/`urllib3` logging instead:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.DEBUG)
```

## Keep imports cheap

`import snaffle` does not import `requests`. The package resolves `HTTPClient`
on first attribute access (PEP 562), which keeps start-up fast for code paths
that may never make a request.

```python
import snaffle                 # requests not imported
client = snaffle.HTTPClient()  # imported now
```

If you want the type without triggering the import, guard it:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from snaffle import HTTPClient
```

See [ADR 0002](../architecture/decisions/0002-lazy-imports-on-the-cli-help-path.md).
