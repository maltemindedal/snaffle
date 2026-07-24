"""Test cases for the CLI module."""

from __future__ import annotations

import io
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from snaffle.cli import EXAMPLES, main

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
        """Test the HELP command prints the usage examples."""
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            main(["HELP"])

        output = fake_stdout.getvalue()
        self.assertIn("Examples:", output)
        self.assertIn("Normal GET request:", output)
        self.assertIn(EXAMPLES, output)

    def test_no_command_prints_help(self) -> None:
        """Test a bare invocation falls back to the same help path."""
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            main([])

        self.assertIn("Examples:", fake_stdout.getvalue())

    @patch(MAKE_REQUEST)
    def test_get_command(self, mock_request: MagicMock) -> None:
        """Test the GET command."""
        mock_request.return_value = self._build_response(text="Success")

        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            main(["GET", "https://api.example.com"])

        output = fake_stdout.getvalue()
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
        """Test that --progress is not available for POST command."""
        with (
            self.assertRaises(SystemExit),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            main(["POST", "https://api.example.com", "--progress"])

    def test_invalid_header_value_exits_with_error(self) -> None:
        """Test invalid header formatting returns a CLI error."""
        fake_stdout = io.StringIO()
        with self.assertRaises(SystemExit), patch("sys.stdout", new=fake_stdout):
            main(["GET", "https://api.example.com", "-H", "Authorization"])

        self.assertIn("Invalid header format", fake_stdout.getvalue())

    def test_invalid_json_value_exits_with_error(self) -> None:
        """Test invalid JSON data returns a CLI error."""
        fake_stdout = io.StringIO()
        with self.assertRaises(SystemExit), patch("sys.stdout", new=fake_stdout):
            main(["POST", "https://api.example.com", "-d", "{not-json}"])

        self.assertIn("Invalid JSON data", fake_stdout.getvalue())

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
