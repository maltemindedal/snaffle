"""Test cases for the CLI module"""

import io
import unittest
from unittest.mock import patch

from PyFetch.cli import main, show_examples


class TestCLI(unittest.TestCase):
    """Test cases for the CLI module"""

    @patch("sys.argv", ["http_cli", "HELP"])
    def test_help_command(self):
        """Test the HELP command content"""
        # Run help command with output suppressed
        help_text = show_examples(suppress_output=True)
        self.assertIn("Examples:", help_text)
        self.assertIn("Normal GET request:", help_text)

        # Verify main function with suppressed output
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            main(suppress_output=True)
            self.assertEqual("", fake_stdout.getvalue())

    @patch("PyFetch.http_client.HTTPClient.get")
    @patch("sys.argv", ["http_cli", "GET", "https://api.example.com"])
    def test_get_command(self, mock_get):
        """Test the GET command"""
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "Success"

        with patch("builtins.print") as mocked_print:
            main()
            mocked_print.assert_called_with("Success")

    @patch("PyFetch.http_client.HTTPClient.post")
    @patch(
        "sys.argv",
        ["http_cli", "POST", "https://api.example.com", "-d", '{"key": "value"}'],
    )
    def test_post_command(self, mock_post):
        """Test the POST command"""
        mock_post.return_value.status_code = 201
        mock_post.return_value.text = "Created"

        with patch("builtins.print") as mocked_print:
            main()
            mocked_print.assert_called_with("Created")

    @patch("PyFetch.http_client.HTTPClient.post")
    @patch(
        "sys.argv",
        ["http_cli", "POST", "https://api.example.com", "--progress"],
    )
    def test_progress_is_not_available_for_post(self, mock_post):
        """Test that --progress is not available for POST command"""
        mock_post.return_value.text = "{}"
        with self.assertRaises(SystemExit):
            with patch("sys.stderr", new_callable=io.StringIO):
                main()


if __name__ == "__main__":
    unittest.main()
