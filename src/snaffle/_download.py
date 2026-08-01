"""Progress-bar buffering for downloads.

`snaffle.http_client` delegates a single decision here: whether the client
should ask for an unread body and drain it itself, so that a progress bar can be
fed as the bytes arrive. Everything that decision entails lives in this module
-- the size threshold, the deferred `tqdm` import, the chunk loop, and the
write-back of the buffered body onto the response.

The module is private. It is reachable only through `snaffle.http_client`, which
is itself imported lazily, so importing `requests` at module scope here does not
undo the start-up win recorded in ADR 0002. `tests/test_init.py` guards that.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, cast

import requests


class ProgressBar(Protocol):
    """Protocol for the subset of progress-bar methods used by the client."""

    def update(self, n: float | None = 1) -> bool | None:
        """Advance the progress display by the provided number of bytes."""

    def close(self) -> None:
        """Close the progress display and release any related resources."""


def should_buffer(method: str, show_progress: bool, kwargs: Mapping[str, Any]) -> bool:
    """Reports whether the client should stream the body itself to feed a bar.

    Streaming a body that nothing reads holds a connection open for the lifetime
    of the response, so the client only does it on its own initiative when there
    is a progress bar to feed: a `GET` with `show_progress` on.

    A caller who passed `stream=True` is going to read the body themselves and
    must get it unconsumed, so their request wins and no bar is drawn. An
    explicit `stream=False` does not opt out -- buffering ends in a fully-read
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
    below that -- and when the server sends no length at all, which reads as
    `0` -- the body is still drained, just silently.

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
    total = int(response.headers.get("content-length", 0))
    progress_bar = _create_progress_bar(total, min_size, desc)

    chunks: list[bytes] = []
    append = chunks.append
    update = progress_bar.update if progress_bar is not None else None

    try:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if not chunk:
                continue

            append(chunk)
            if update is not None:
                update(len(chunk))
    finally:
        if progress_bar is not None:
            progress_bar.close()

    response._content = b"".join(chunks)
    # Mark the body as fully read so `.text`/`.json()` serve the buffer we just
    # built instead of re-reading a drained socket.
    cast(Any, response)._content_consumed = True


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

    return cast(
        ProgressBar,
        tqdm(total=total, unit="B", unit_scale=True, desc=desc),
    )
