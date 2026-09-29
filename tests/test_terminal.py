"""Test cases for keeping server-chosen text from driving the terminal."""

from __future__ import annotations

import io
import unittest
from unittest.mock import patch

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

    def test_printable_text_is_untouched(self) -> None:
        """Test ordinary text, including non-ASCII, passes through unchanged."""
        text = "café → 日本\tok\n"

        with patch("sys.stdout", new=_Terminal()):
            self.assertEqual(for_stdout(text), text)

    def test_nothing_changes_when_stdout_is_not_a_terminal(self) -> None:
        """Test piped and redirected output stays byte for byte what it was."""
        hostile = "a\x1b[2Jb\x00c\r\nd\re"

        for name, stdout in (("pipe or file", io.StringIO()), ("closed", None)):
            with self.subTest(stdout=name), patch("sys.stdout", new=stdout):
                self.assertEqual(for_stdout(hostile), hostile)


if __name__ == "__main__":
    unittest.main()
