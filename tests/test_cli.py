"""Test cases for the CLI module."""

from __future__ import annotations

import io
import re
import subprocess
import sys
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from typing_extensions import override

from snaffle.cli import COMMANDS, EXAMPLES, _indent_exceeds, main
from snaffle.exceptions import HTTPClientError
from snaffle.http_client import HTTPClient

MAKE_REQUEST = "snaffle.http_client.HTTPClient.make_request"


class _Terminal(io.StringIO):
    """A stdout that reports being a terminal."""

    @override
    def isatty(self) -> bool:
        """Says this is a terminal."""
        return True


class TestCLI(unittest.TestCase):
    """Test cases for the CLI module."""

    @staticmethod
    def _build_response(
        status_code: int = 200,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            status_code=status_code,
            text=text,
            headers=headers or {"content-type": "text/plain"},
        )

    def test_help_command(self) -> None:
        """Test the HELP command prints the usage examples and returns 0."""
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            exit_code = main(["HELP"])

        output = fake_stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Examples:", output)
        self.assertIn("Normal GET request:", output)
        self.assertIn(EXAMPLES, output)

    def test_no_command_prints_help(self) -> None:
        """Test a bare invocation falls back to the same help path."""
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        self.assertIn("Examples:", fake_stdout.getvalue())

    @patch(MAKE_REQUEST)
    def test_get_command(self, mock_request: MagicMock) -> None:
        """Test the GET command."""
        mock_request.return_value = self._build_response(text="Success")

        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            exit_code = main(["GET", "https://api.example.com"])

        output = fake_stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Status Code: 200", output)
        self.assertIn("Headers:", output)
        self.assertIn("Response Body:", output)
        self.assertIn("Success", output)
        mock_request.assert_called_once_with("GET", "https://api.example.com")

    @patch(MAKE_REQUEST)
    def test_post_command(self, mock_request: MagicMock) -> None:
        """Test the POST command."""
        mock_request.return_value = self._build_response(
            status_code=201,
            text='{"created": true}',
            headers={"content-type": "application/json"},
        )

        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            main(["POST", "https://api.example.com", "-d", '{"key": "value"}'])

        output = fake_stdout.getvalue()
        self.assertIn("Status Code: 201", output)
        self.assertIn('"created": true', output)
        mock_request.assert_called_once_with(
            "POST",
            "https://api.example.com",
            json={"key": "value"},
        )

    @patch(MAKE_REQUEST)
    def test_a_too_deeply_nested_json_body_is_printed_as_text(
        self, mock_request: MagicMock
    ) -> None:
        """Test a body the JSON parser cannot handle falls back to plain text.

        Regression: nesting deep enough to exhaust the parser raises
        `RecursionError`, which is not a `ValueError`, so the CLI died with a
        traceback and printed neither the status nor the body. A server chooses
        the body. 100,000 levels fails on every supported Python.
        """
        body = "[" * 100_000 + "]" * 100_000
        mock_request.return_value = self._build_response(
            text=body, headers={"content-type": "application/json"}
        )

        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            exit_code = main(["GET", "https://api.example.com"])

        output = fake_stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Status Code: 200", output)
        self.assertIn(body, output)

    def _print_body(self, body: str) -> str:
        """Prints a JSON `body` through the CLI and returns what it wrote."""
        with patch(MAKE_REQUEST) as mock_request:
            mock_request.return_value = self._build_response(
                text=body, headers={"content-type": "application/json"}
            )
            with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
                exit_code = main(["GET", "https://api.example.com"])

        self.assertEqual(exit_code, 0)
        return fake_stdout.getvalue()

    def test_a_body_nested_past_the_indent_budget_is_not_indented(self) -> None:
        """Test deep JSON is printed as received rather than pretty-printed.

        Regression: Python 3.13 and 3.14 parse this body, and `indent=4` then
        writes a line per level with four spaces of indent per level before it.
        That is about 100 MB for 5,000 levels and gigabytes for 20,000, which
        ran the CI runner out of memory. Python 3.10 to 3.12 refuse to print it,
        so the assertion holds on all of them.
        """
        body = "[" * 5_000 + "]" * 5_000

        output = self._print_body(body)

        self.assertIn(body, output)
        self.assertLess(len(output), 3 * len(body))

    def test_a_wide_body_that_is_also_deep_is_not_indented(self) -> None:
        """Test depth alone is not the limit: width multiplies it.

        Regression: a cap on the depth let through 990 levels holding 100,000
        scalars, a 202 KB body that printed as 400 MB, since every scalar line
        starts with as many as 3,960 spaces. This one is 41 KB and would print
        as 40 MB.
        """
        body = "[" * 500 + "1," * 20_000 + "1" + "]" * 500

        output = self._print_body(body)

        self.assertIn(body, output)
        self.assertLess(len(output), 3 * len(body))

    def test_ordinary_nested_json_is_still_indented(self) -> None:
        """Test a document of realistic shape is pretty-printed as before."""
        body = '{"a": {"b": [{"c": [1, 2, {"d": null}]}, "x"]}}'

        output = self._print_body(body)

        self.assertIn('{\n    "a": {\n        "b": [', output)
        self.assertNotIn(body, output)

    @patch(MAKE_REQUEST)
    def test_lowercase_alias_sends_the_uppercase_method(
        self, mock_request: MagicMock
    ) -> None:
        """Test `snaffle get` reaches the client as a normalized `GET`."""
        mock_request.return_value = self._build_response(text="Success")

        with patch("sys.stdout", new=io.StringIO()):
            main(["get", "https://api.example.com"])

        mock_request.assert_called_once_with("GET", "https://api.example.com")

    def test_progress_is_not_available_for_post(self) -> None:
        """Test --progress on POST is an argparse error, which still exits 2.

        argparse exits from inside `parse_args`, so this code never reaches
        `main`'s return value; see the CLI reference on exit codes.
        """
        with (
            self.assertRaises(SystemExit) as caught,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            main(["POST", "https://api.example.com", "--progress"])

        self.assertEqual(caught.exception.code, 2)

    def test_invalid_header_value_returns_one(self) -> None:
        """Test invalid header formatting returns a CLI error."""
        fake_stdout = io.StringIO()
        with patch("sys.stdout", new=fake_stdout):
            exit_code = main(["GET", "https://api.example.com", "-H", "Authorization"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Invalid header format", fake_stdout.getvalue())

    def test_invalid_json_value_returns_one(self) -> None:
        """Test invalid JSON data returns a CLI error."""
        fake_stdout = io.StringIO()
        with patch("sys.stdout", new=fake_stdout):
            exit_code = main(["POST", "https://api.example.com", "-d", "{not-json}"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Invalid JSON data", fake_stdout.getvalue())

    def test_invalid_timeout_returns_one(self) -> None:
        """Test a timeout the client rejects returns a CLI error.

        `-t 0` passes argparse because it is a valid int, then is refused by
        `HTTPClient.__init__` with a plain ValueError.
        """
        fake_stdout = io.StringIO()
        with patch("sys.stdout", new=fake_stdout):
            exit_code = main(["GET", "https://api.example.com", "-t", "0"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Error: timeout must be greater than 0", fake_stdout.getvalue())

    @patch(MAKE_REQUEST, side_effect=HTTPClientError("Connection error occurred"))
    def test_client_error_returns_one(self, _: MagicMock) -> None:
        """Test any HTTPClientError is reported and returns a CLI error."""
        fake_stdout = io.StringIO()
        with patch("sys.stdout", new=fake_stdout):
            exit_code = main(["GET", "https://api.example.com"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Error: Connection error occurred", fake_stdout.getvalue())

    @patch(MAKE_REQUEST)
    def test_a_hostile_response_cannot_drive_a_terminal(
        self, mock_request: MagicMock
    ) -> None:
        """Test control characters from the server are escaped on a terminal.

        A server chooses the header values and a text body. On a terminal they
        could retitle the window, clear or rewrite the screen, or write the
        clipboard, so the raw escape is never written there.
        """
        mock_request.return_value = self._build_response(
            text="hello \x1b[2J\x1b]0;pwned\x07 world",
            headers={"content-type": "text/plain", "x-evil": "\x1b[31mred\r\x9b"},
        )

        with patch("sys.stdout", new=_Terminal()) as terminal:
            exit_code = main(["GET", "https://api.example.com"])

        output = terminal.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertNotIn("\x1b", output)
        self.assertNotIn("\x07", output)
        self.assertIn("x-evil: \\x1b[31mred\\x0d\\x9b", output)
        self.assertIn("hello \\x1b[2J\\x1b]0;pwned\\x07 world", output)

    @patch(MAKE_REQUEST)
    def test_the_same_response_is_written_untouched_when_piped(
        self, mock_request: MagicMock
    ) -> None:
        """Test output that is not a terminal keeps every byte the server sent."""
        mock_request.return_value = self._build_response(
            text="hello \x1b[2J world", headers={"x-evil": "\x1b[31mred"}
        )

        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            main(["GET", "https://api.example.com"])

        self.assertIn("x-evil: \x1b[31mred", fake_stdout.getvalue())
        self.assertIn("hello \x1b[2J world", fake_stdout.getvalue())

    @patch(
        MAKE_REQUEST, side_effect=HTTPClientError("HTTP error occurred: 500 \x1b[2J")
    )
    def test_an_error_message_cannot_drive_a_terminal(self, _: MagicMock) -> None:
        """Test the `Error:` line, which carries the server's reason phrase, is safe."""
        with patch("sys.stdout", new=_Terminal()) as terminal:
            exit_code = main(["GET", "https://api.example.com"])

        self.assertEqual(exit_code, 1)
        self.assertNotIn("\x1b", terminal.getvalue())
        self.assertIn("500 \\x1b[2J", terminal.getvalue())

    def test_usage_line_is_stable_across_entry_points(self) -> None:
        """Test help output names the command, not whatever launched it."""
        from snaffle.cli import create_parser

        # Python 3.14 styles argparse output on a colour terminal, which puts an
        # escape code in front of "usage:". Only the text is under test.
        usage = re.sub(r"\x1b\[[0-9;]*m", "", create_parser().format_usage())
        self.assertTrue(usage.startswith("usage: snaffle"), usage)

    def test_every_command_is_a_method_the_client_accepts(self) -> None:
        """Test the CLI's subcommands and the client's methods are the same set.

        The methods are listed twice, in `COMMANDS` and in
        `HTTPClient.ALLOWED_METHODS`, because the CLI cannot import the client on
        its help path (ADR 0002). A subcommand the client rejects fails only when
        it is run, and a method missing from `COMMANDS` cannot be sent from the
        command line.
        """
        self.assertEqual(
            {command.method for command in COMMANDS}, HTTPClient.ALLOWED_METHODS
        )

    def test_help_path_does_not_import_requests(self) -> None:
        """Guard the start-up win: help must not drag in the HTTP stack."""
        # The help text lands in the subprocess's captured stdout; only the
        # exit status matters here.
        probe = (
            "import sys; from snaffle.cli import main; main(['HELP']);"
            " sys.exit(1 if 'requests' in sys.modules else 0)"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True
        )
        self.assertEqual(
            result.returncode, 0, f"requests was imported on the help path: {result}"
        )


class TestIndentBudget(unittest.TestCase):
    """Test cases for the limit on how much indentation a body may need."""

    @staticmethod
    def _nested(depth: int, *, wrap: bool = False) -> Any:
        """Builds a value whose deepest container sits `depth` levels down."""
        value: Any = []
        for _ in range(depth - 1):
            value = {"k": value} if wrap else [value]
        return value

    def test_it_counts_four_spaces_per_level_on_every_line(self) -> None:
        """Test the total for a small value, worked out by hand.

        `[[1, 2, 3]]` prints one item at depth 1 (4 spaces) and three at depth 2
        (8 spaces each), 28 in all.
        """
        value = [[1, 2, 3]]

        self.assertFalse(_indent_exceeds(value, 28))
        self.assertTrue(_indent_exceeds(value, 27))

    def test_objects_count_like_lists(self) -> None:
        """Test the walk follows dict values, one line per key."""
        value = {"a": {"b": 1, "c": 2, "d": 3}}

        self.assertFalse(_indent_exceeds(value, 28))
        self.assertTrue(_indent_exceeds(value, 27))

    def test_the_deepest_branch_counts_however_narrow(self) -> None:
        """Test one deep branch among shallow items is found."""
        deep = self._nested(1_000)

        self.assertFalse(_indent_exceeds([1, "x", deep, None], 10_000_000))
        self.assertTrue(_indent_exceeds([1, "x", deep, None], 1_000_000))

    def test_dicts_and_lists_nest_alike(self) -> None:
        """Test both container types are followed to the bottom."""
        for wrap in (False, True):
            with self.subTest(wrap=wrap):
                deep = self._nested(1_000, wrap=wrap)
                self.assertFalse(_indent_exceeds(deep, 2_000_000))
                self.assertTrue(_indent_exceeds(deep, 1_000_000))

    def test_scalars_and_empty_containers_need_no_indentation(self) -> None:
        """Test top-level values that hold no lines are never over budget."""
        for value in (0, "text" * 2_000, None, True, [], {}):
            with self.subTest(value=value):
                self.assertFalse(_indent_exceeds(value, 0))


if __name__ == "__main__":
    unittest.main()
