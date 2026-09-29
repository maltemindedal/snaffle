"""Test cases for keeping server-chosen text from driving the terminal."""

from __future__ import annotations

import io
import tracemalloc
import unittest
from unittest.mock import MagicMock, patch

from typing_extensions import override

from snaffle._terminal import for_stdout


class _Terminal(io.StringIO):
    """A stdout that reports being a terminal."""

    @override
    def isatty(self) -> bool:
        """Says this is a terminal."""
        return True


class TestForStdout(unittest.TestCase):
    """Test cases for `for_stdout`."""

    def test_control_characters_are_escaped_on_a_terminal(self) -> None:
        """Test an escape sequence, a CSI, a NUL and DEL are shown, not obeyed."""
        hostile = "a\x1b]0;pwned\x07b\x1b[2Jc\x9b31md\x00e\x7f"

        with patch("sys.stdout", new=_Terminal()):
            shown = for_stdout(hostile)

        self.assertEqual(shown, "a\\x1b]0;pwned\\x07b\\x1b[2Jc\\x9b31md\\x00e\\x7f")

    def test_every_control_character_but_tab_and_newline_is_escaped(self) -> None:
        """Test C0, DEL and C1 are all covered, and only tab and newline pass."""
        allowed = {"\t", "\n"}
        controls = [chr(c) for c in (*range(0x00, 0x20), *range(0x7F, 0xA0))]

        with patch("sys.stdout", new=_Terminal()):
            for char in controls:
                with self.subTest(char=hex(ord(char))):
                    expected = char if char in allowed else f"\\x{ord(char):02x}"
                    # A lone carriage return is a control; it is checked below.
                    self.assertEqual(for_stdout(f"a{char}b"), f"a{expected}b")

    def test_a_carriage_return_line_feed_pair_is_kept(self) -> None:
        """Test CRLF, the line ending of a great many bodies, is left alone.

        A lone carriage return is not: it lets a server overwrite text it has
        already printed on the same line.
        """
        with patch("sys.stdout", new=_Terminal()):
            self.assertEqual(for_stdout("one\r\ntwo\rthree"), "one\r\ntwo\\x0dthree")

    def test_carriage_returns_at_the_edges_and_side_by_side(self) -> None:
        """Test only a carriage return that starts a CRLF is kept.

        The text is split on CRLF, so these are the places that could go wrong:
        the two ends, a run of carriage returns, and a line feed before one.
        """
        cases = {
            "\r": "\\x0d",
            "a\r": "a\\x0d",
            "\r\n": "\r\n",
            "\r\r\n": "\\x0d\r\n",
            "\r\n\r": "\r\n\\x0d",
            "\n\r\n": "\n\r\n",
            "\n\r": "\n\\x0d",
            "\r\r": "\\x0d\\x0d",
            "\r\n\r\n": "\r\n\r\n",
        }

        with patch("sys.stdout", new=_Terminal()):
            for text, expected in cases.items():
                with self.subTest(text=text):
                    self.assertEqual(for_stdout(text), expected)

    def test_a_body_of_control_characters_does_not_multiply_memory(self) -> None:
        """Test escaping costs about the size of its result, not sixty times it.

        Regression: replacing each match through a callback held a string per
        character until the end. A 30 KB gzip that decodes to 30 MB of NULs then
        took 1.7 GB and 22 s on a terminal. Memory is measured rather than time,
        which would depend on the machine.
        """
        text = "\x00" * 3_000_000

        with patch("sys.stdout", new=_Terminal()):
            tracemalloc.start()
            try:
                shown = for_stdout(text)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()

        self.assertEqual(shown, "\\x00" * 3_000_000)
        self.assertLess(peak, 4 * len(shown))

    def test_printable_text_is_untouched(self) -> None:
        """Test ordinary text, including non-ASCII, passes through unchanged."""
        text = "café → 日本\tok\n"

        with patch("sys.stdout", new=_Terminal()):
            self.assertEqual(for_stdout(text), text)

    def test_a_stdout_that_cannot_say_what_it_is_is_left_alone(self) -> None:
        """Test `isatty` failing with either error it can raise means "no".

        A stdout closed under the process raises `ValueError`, and one whose
        descriptor has gone bad raises `OSError`. Neither may reach the caller.
        """
        for error in (OSError("bad descriptor"), ValueError("closed file")):
            stdout = MagicMock()
            stdout.isatty.side_effect = error
            with self.subTest(error=type(error).__name__), patch("sys.stdout", stdout):
                self.assertEqual(for_stdout("a\x1bb"), "a\x1bb")

    def test_nothing_changes_when_stdout_is_not_a_terminal(self) -> None:
        """Test piped and redirected output is exactly what it was without escaping."""
        hostile = "a\x1b[2Jb\x00c\r\nd\re"

        for name, stdout in (("pipe or file", io.StringIO()), ("closed", None)):
            with self.subTest(stdout=name), patch("sys.stdout", new=stdout):
                self.assertEqual(for_stdout(hostile), hostile)


if __name__ == "__main__":
    unittest.main()
