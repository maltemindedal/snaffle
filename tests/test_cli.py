"""Test cases for the CLI module."""

from __future__ import annotations

import io
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PyFetch.cli import main, show_examples


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
        """Test the HELP command content."""
        # Run help command with output suppressed
        help_text = show_examples(suppress_output=True)
        self.assertIn("Examples:", help_text)
        self.assertIn("Normal GET request:", help_text)

        # Verify main function with suppressed output
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            main(["HELP"], suppress_output=True)
            self.assertEqual("", fake_stdout.getvalue())

    @patch("PyFetch.cli.HTTPClient.get")
    def test_get_command(self, mock_get: MagicMock) -> None:
        """Test the GET command."""
        mock_get.return_value = self._build_response(text="Success")

        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            main(["GET", "https://api.example.com"])

        output = fake_stdout.getvalue()
        self.assertIn("Status Code: 200", output)
        self.assertIn("Headers:", output)
        self.assertIn("Response Body:", output)
        self.assertIn("Success", output)

    @patch("PyFetch.cli.HTTPClient.post")
    def test_post_command(self, mock_post: MagicMock) -> None:
        """Test the POST command."""
        mock_post.return_value = self._build_response(
            status_code=201,
            text='{"created": true}',
            headers={"content-type": "application/json"},
        )

        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            main(["POST", "https://api.example.com", "-d", '{"key": "value"}'])

        output = fake_stdout.getvalue()
        self.assertIn("Status Code: 201", output)
        self.assertIn('"created": true', output)
        mock_post.assert_called_once_with(
            "https://api.example.com",
            json={"key": "value"},
        )

    @patch("PyFetch.cli.HTTPClient.post")
    def test_progress_is_not_available_for_post(self, mock_post: MagicMock) -> None:
        """Test that --progress is not available for POST command."""
        mock_post.return_value.text = "{}"
        with self.assertRaises(SystemExit):
            with patch("sys.stderr", new_callable=io.StringIO):
                main(["POST", "https://api.example.com", "--progress"])

    def test_invalid_header_value_exits_with_error(self) -> None:
        """Test invalid header formatting returns a CLI error."""
        fake_stdout = io.StringIO()
        with self.assertRaises(SystemExit):
            with patch("sys.stdout", new=fake_stdout):
                main(["GET", "https://api.example.com", "-H", "Authorization"])

        self.assertIn("Invalid header format", fake_stdout.getvalue())

    def test_invalid_json_value_exits_with_error(self) -> None:
        """Test invalid JSON data returns a CLI error."""
        fake_stdout = io.StringIO()
        with self.assertRaises(SystemExit):
            with patch("sys.stdout", new=fake_stdout):
                main(["POST", "https://api.example.com", "-d", "{not-json}"])

        self.assertIn("Invalid JSON data", fake_stdout.getvalue())

    @patch("PyFetch.cli.HTTPClient.get")
    def test_suppress_output_hides_response_text(self, mock_get: MagicMock) -> None:
        """Test suppress_output keeps stdout clean during command execution."""
        mock_get.return_value = self._build_response(text="Success")

        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            main(["GET", "https://api.example.com"], suppress_output=True)

        self.assertEqual("", fake_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
