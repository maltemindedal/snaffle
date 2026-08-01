"""Test cases for the CLI module."""

from __future__ import annotations

import io
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from snaffle.cli import EXAMPLES, main
from snaffle.exceptions import HTTPClientError

MAKE_REQUEST = "snaffle.http_client.HTTPClient.make_request"


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

        `-t 0` passes argparse — it is a valid int — and is refused by
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

    def test_usage_line_is_stable_across_entry_points(self) -> None:
        """Test help output names the command, not whatever launched it."""
        from snaffle.cli import create_parser

        self.assertTrue(create_parser().format_usage().startswith("usage: snaffle"))

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


if __name__ == "__main__":
    unittest.main()
