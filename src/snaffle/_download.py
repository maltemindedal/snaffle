"""Progress-bar buffering for downloads.

`snaffle.http_client` delegates a single decision here: whether the client
should ask for an unread body and drain it itself, so that a progress bar can be
fed as the bytes arrive. Everything that follows from a yes lives in this module
too: the size threshold, the deferred `tqdm` import, the chunk loop, the
write-back of the buffered body onto the response, and the read of an error
body that the stream left on the socket.

The module is private. It is reachable only through `snaffle.http_client`, which
is itself imported lazily, so importing `requests` at module scope here does not
undo the start-up win recorded in ADR 0002. `tests/test_init.py` guards that.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, cast

import requests

if TYPE_CHECKING:
    # Type-only, so the run-time dependency still runs one way. `http_client`
    # imports this module, never the reverse. `ProgressBar` is documented as
    # part of `http_client`'s API, so it is defined there.
    from snaffle.http_client import ProgressBar


def should_buffer(method: str, show_progress: bool, kwargs: Mapping[str, Any]) -> bool:
    """Reports whether the client should stream the body itself to feed a bar.

    Streaming a body that nothing reads holds a connection open for the lifetime
    of the response, so the client only does it on its own initiative when there
    is a progress bar to feed: a `GET` with `show_progress` on.

    A caller who passed `stream=True` is going to read the body themselves and
    must get it unconsumed, so their request wins and no bar is drawn. An
    explicit `stream=False` does not opt out. Buffering ends in a fully-read
    response, which is what that caller asked for either way.

    Args:
        method (str): The normalized HTTP method.
        show_progress (bool): The client's `show_progress` setting.
        kwargs (Mapping[str, Any]): The keyword arguments bound for `requests`.

    Returns:
        bool: True when the client should request a stream and drain it itself.
    """
    return method == "GET" and show_progress and not kwargs.get("stream", False)


def buffer_into(
    response: requests.Response, *, chunk_size: int, min_size: int, desc: str
) -> None:
    """Drains the body through a progress bar and attaches it to the response.

    A bar is drawn only once the response's `Content-Length` reaches `min_size`;
    below that, or when the server sends no length at all, the body is still
    drained without a bar. A missing or unparsable length reads as `0`.

    The bar counts bytes as they crossed the wire, which is what `Content-Length`
    counts, so a gzip or Brotli body finishes at 100% rather than running past
    it. urllib3 reports that through `raw.tell()`. Wherever that is missing or
    does not behave like a byte count, the bar counts the decoded chunks instead;
    see `_WireMeter`.

    The buffer is written back onto the response and the body marked consumed, so
    `.text` and `.json()` serve it rather than re-reading a drained socket. The
    result is indistinguishable from a response `requests` read in one pass; the
    cost is holding the whole body in memory.

    Args:
        response (requests.Response): The unread response to drain.
        chunk_size (int): Bytes to read per `iter_content` chunk.
        min_size (int): Minimum `Content-Length` before a bar is drawn.
        desc (str): The description displayed alongside the bar.
    """
    try:
        total = int(response.headers.get("content-length", 0))
    except ValueError:
        total = 0
    progress_bar = _create_progress_bar(total, min_size, desc)

    buffer = io.BytesIO()
    write = buffer.write
    update = progress_bar.update if progress_bar is not None else None
    meter = _WireMeter(getattr(response, "raw", None))

    try:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if not chunk:
                continue

            write(chunk)
            if update is not None and (step := meter.advance(len(chunk))):
                update(step)

        # A decoder can hold bytes back until the stream ends.
        if update is not None and (step := meter.remainder()):
            update(step)
    finally:
        if progress_bar is not None:
            progress_bar.close()

    # `getvalue` hands back the buffer itself, trimmed in place, where joining a
    # list of chunks would build a second body-sized copy.
    response._content = buffer.getvalue()
    # Mark the body as fully read so `.text`/`.json()` serve the buffer we just
    # built instead of re-reading a drained socket.
    response._content_consumed = True


def release(response: requests.Response) -> None:
    """Reads the body of an error response so its connection returns to the pool.

    A request that `should_buffer` approved is sent with `stream=True`, so when
    its status is an error the body is still on the socket and the connection is
    still checked out. Reading the body frees the connection and keeps `.text`
    readable on the response that the error carries.

    The status is what the caller needs to hear, so a body that cannot be read
    only costs the connection: the response is closed and nothing is raised.

    Args:
        response (requests.Response): The unread error response.
    """
    try:
        _ = response.content
    except requests.exceptions.RequestException:
        response.close()


class _WireMeter:
    """Turns decoded chunks into how far the progress bar should advance.

    The bar's total is the `Content-Length`, which counts bytes on the wire, so
    the bar should advance by wire bytes too. urllib3 reports them through
    `raw.tell()`, but not always usefully: it stays at zero for a chunked body,
    and for a response served by a caching session. A stand-in transport may have
    no `tell()` at all, or one that returns something that is not a count.

    The meter trusts `tell()` only while it behaves like a byte count that has
    moved: an integer, never decreasing, and above zero once data has arrived.
    The first time it does not, the meter stops asking and counts decoded bytes.
    """

    def __init__(self, raw: object) -> None:
        tell = getattr(raw, "tell", None)
        self._tell: Callable[[], object] | None = tell if callable(tell) else None
        self._reported = 0

    def advance(self, decoded: int) -> int:
        """Returns how far to advance the bar for a chunk of `decoded` bytes."""
        position = self._wire_position()
        if position is None:
            position = self._reported + decoded
        step = position - self._reported
        self._reported = position
        return step

    def remainder(self) -> int:
        """Returns wire bytes read after the last chunk, such as a trailer."""
        position = self._wire_position()
        if position is None:
            return 0
        step = position - self._reported
        self._reported = position
        return step

    def _wire_position(self) -> int | None:
        """Returns the byte count from `raw.tell()`, or None if it cannot be trusted."""
        if self._tell is None:
            return None
        try:
            position = self._tell()
        except Exception:
            position = None
        if not isinstance(position, int) or not position >= max(self._reported, 1):
            self._tell = None
            return None
        return position


def _create_progress_bar(total: int, min_size: int, desc: str) -> ProgressBar | None:
    """Creates a `tqdm` bar, or None when the transfer is too small to warrant one.

    Args:
        total (int): The total size of the transfer in bytes.
        min_size (int): The size at or above which a bar is drawn.
        desc (str): A description to display with the progress bar.

    Returns:
        ProgressBar or None: A `tqdm` instance, or None below the threshold.
    """
    if total < min_size:
        return None

    # Imported lazily: tqdm costs ~15ms of startup that a run without a progress
    # bar should never pay. See ADR 0002.
    from tqdm import tqdm

    # The target is quoted: `ProgressBar` is imported for type checking only, so
    # the name does not exist when `cast` evaluates its arguments at run time.
    return cast(
        "ProgressBar",
        tqdm(total=total, unit="B", unit_scale=True, desc=desc),
    )
