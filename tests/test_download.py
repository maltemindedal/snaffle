"""Test cases for the progress-bar download buffering."""

from __future__ import annotations

import io
import unittest
from typing import Any, cast
from unittest.mock import MagicMock, call, patch

import requests

from snaffle._download import buffer_into, should_buffer

MIB = 1024 * 1024


def _unread_response(content_length: str | None, chunks: list[bytes]) -> Any:
    """Builds a stand-in for an unread response that yields `chunks`."""
    response = MagicMock()
    response.headers = (
        {} if content_length is None else {"content-length": content_length}
    )
    response.iter_content.return_value = chunks
    return response


class TestShouldBuffer(unittest.TestCase):
    """Test cases for deciding whether the client drains a body itself."""

    def test_get_with_progress_buffers(self) -> None:
        """Test the one case worth streaming for: a GET that can draw a bar."""
        self.assertTrue(should_buffer("GET", True, {}))

    def test_get_without_progress_does_not_buffer(self) -> None:
        """Test nothing is streamed when there is no bar to feed."""
        self.assertFalse(should_buffer("GET", False, {}))

    def test_other_methods_do_not_buffer(self) -> None:
        """Test the progress bar is a GET feature only."""
        for method in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            with self.subTest(method=method):
                self.assertFalse(should_buffer(method, True, {}))

    def test_explicit_stream_opts_out(self) -> None:
        """Test a caller who asked to stream keeps the body: no drain, no bar."""
        self.assertFalse(should_buffer("GET", True, {"stream": True}))

    def test_explicit_stream_false_still_buffers(self) -> None:
        """Test `stream=False` is not an opt-out: it asks for a read response."""
        self.assertTrue(should_buffer("GET", True, {"stream": False}))


class TestBufferInto(unittest.TestCase):
    """Test cases for draining a body through a progress bar."""

    def test_body_is_attached_to_the_response_and_marked_consumed(self) -> None:
        """Test `.text` serves the buffer rather than re-reading a drained socket."""
        response = requests.Response()
        response.status_code = 200
        response.headers["content-length"] = "8"
        cast(Any, response).raw = io.BytesIO(b"payload!")

        buffer_into(response, chunk_size=4, min_size=MIB, desc="Downloading")

        self.assertEqual(response._content, b"payload!")
        self.assertTrue(cast(Any, response)._content_consumed)
        self.assertEqual(response.text, "payload!")

    def test_chunks_are_read_at_the_requested_size(self) -> None:
        """Test the client's chunk size reaches `iter_content` unchanged."""
        response = _unread_response("4", [b"data"])

        buffer_into(response, chunk_size=1234, min_size=MIB, desc="Downloading")

        response.iter_content.assert_called_once_with(chunk_size=1234)

    def test_empty_chunks_are_skipped(self) -> None:
        """Test keep-alive chunks neither reach the buffer nor advance the bar."""
        response = _unread_response(str(6 * MIB), [b"ab", b"", b"cd"])

        with patch("tqdm.tqdm") as mock_tqdm:
            buffer_into(response, chunk_size=8, min_size=5 * MIB, desc="Downloading")

        self.assertEqual(response._content, b"abcd")
        self.assertEqual(
            mock_tqdm.return_value.update.call_args_list, [call(2), call(2)]
        )

    def test_bar_is_drawn_at_the_threshold(self) -> None:
        """Test the size comparison is inclusive: exactly the minimum draws a bar."""
        response = _unread_response(str(5 * MIB), [b"data"])

        with patch("tqdm.tqdm") as mock_tqdm:
            buffer_into(response, chunk_size=8, min_size=5 * MIB, desc="Downloading x")

        mock_tqdm.assert_called_once_with(
            total=5 * MIB, unit="B", unit_scale=True, desc="Downloading x"
        )
        mock_tqdm.return_value.close.assert_called_once()

    def test_body_below_the_threshold_is_buffered_without_a_bar(self) -> None:
        """Test a small download is drained silently."""
        response = _unread_response(str(4 * MIB), [b"data"])

        with patch("tqdm.tqdm") as mock_tqdm:
            buffer_into(response, chunk_size=8, min_size=5 * MIB, desc="Downloading")

        mock_tqdm.assert_not_called()
        self.assertEqual(response._content, b"data")

    def test_missing_content_length_draws_no_bar(self) -> None:
        """Test a server that sends no length reads as 0, and the body still lands."""
        response = _unread_response(None, [b"data"])

        with patch("tqdm.tqdm") as mock_tqdm:
            buffer_into(response, chunk_size=8, min_size=5 * MIB, desc="Downloading")

        mock_tqdm.assert_not_called()
        self.assertEqual(response._content, b"data")

    def test_bar_is_closed_when_the_body_fails_midway(self) -> None:
        """Test a broken download does not leave the terminal owned by tqdm."""
        response = _unread_response(str(6 * MIB), [])
        response.iter_content.side_effect = requests.exceptions.ChunkedEncodingError(
            "boom"
        )

        with (
            patch("tqdm.tqdm") as mock_tqdm,
            self.assertRaises(requests.exceptions.ChunkedEncodingError),
        ):
            buffer_into(response, chunk_size=8, min_size=5 * MIB, desc="Download")

        mock_tqdm.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
