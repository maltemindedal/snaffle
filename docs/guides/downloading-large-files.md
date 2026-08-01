# Download large files

Snaffle can show a progress bar while a body downloads, and can hand you an
unread response to stream yourself.

## Show a progress bar

`--progress` is available on `GET` only:

```bash
uv run snaffle GET https://example.com/large-file.zip --progress
```

The bar appears only if the response's `Content-Length` header is at least
5 MiB. Smaller responses download without one. If the server sends no
`Content-Length`, the size reads as `0` and no bar is drawn — the download
still completes.

The bar is drawn by `tqdm` on stderr, so redirecting stdout leaves it visible:

```bash
uv run snaffle GET https://example.com/large-file.zip --progress > /dev/null
```

## The CLI is not a file downloader

`snaffle GET --progress` buffers the whole body in memory and prints it to
stdout in the standard three-section format. It does not write a file, and it
does not stream to stdout as bytes arrive. For binary payloads that is rarely
what you want.

For actually saving a file, use the Python API, or use a purpose-built tool
(`curl -O`, `wget`).

## Stream from Python

Pass `stream=True` yourself and the client returns the response without reading
the body, so you can iterate it:

```python
from snaffle import HTTPClient

with HTTPClient() as client:
    response = client.get("https://example.com/large-file.zip", stream=True)
    with open("large-file.zip", "wb") as handle:
        for chunk in response.iter_content(chunk_size=65536):
            handle.write(chunk)
```

Memory stays bounded at one chunk. `HTTPClient.DOWNLOAD_CHUNK_SIZE` is 64 KiB,
which is the size the client itself uses; you can pick anything for your own
loop.

The connection is not returned to the pool until the body is fully read or the
response is closed. Consume it promptly, or close it.

## Combine your own progress bar with streaming

`show_progress` only drives the client's internal bar, which buffers. Passing
`stream=True` switches that bar off, so the two never contend for the body. To
stream *and* display progress, drive `tqdm` yourself:

```python
from snaffle import HTTPClient
from tqdm import tqdm

with HTTPClient() as client:
    response = client.get(url, stream=True)
    total = int(response.headers.get("content-length", 0))

    with (
        open("large-file.zip", "wb") as handle,
        tqdm(total=total, unit="B", unit_scale=True) as bar,
    ):
        for chunk in response.iter_content(chunk_size=65536):
            handle.write(chunk)
            bar.update(len(chunk))
```

## What `show_progress=True` does

Setting `show_progress=True` on the client (or passing `--progress` on the CLI)
changes `GET` in three ways:

1. The request is sent with `stream=True`.
2. The body is drained through `iter_content` in `DOWNLOAD_CHUNK_SIZE` chunks,
   updating the bar, and buffered into memory.
3. The buffer is attached to the response and marked consumed, so `.text` and
   `.json()` serve it rather than re-reading a drained socket.

The result is a fully-read response, identical in behaviour to a non-streamed
one. The memory cost is the whole body.

Passing `stream=True` yourself opts out of all three. The body is left unread
for you to iterate and no bar is drawn — a bar is fed by reading the body, and
reading it is what you asked to do yourself. See
[Combine your own progress bar with streaming](#combine-your-own-progress-bar-with-streaming)
for having both.

Without `show_progress`, `GET` does not stream at all: letting `requests` read
the body in one pass is faster and returns the connection to the pool
immediately. See
[ADR 0001](../architecture/decisions/0001-selective-retries-and-connection-pooling.md).

## Make large text responses smaller

The optional `speedups` extra installs `zstandard` and `brotli`. urllib3
negotiates those content encodings automatically once the codecs are present,
so large text and JSON responses arrive compressed:

```bash
uv sync --extra speedups
```

This affects transfer size, not the decoded body. It does nothing for content
that is already compressed — a `.zip` or a `.jpg` gains nothing.
