"""Test cases for the package entry point."""

from __future__ import annotations

import io
import unittest
from unittest.mock import MagicMock, patch

from snaffle.__main__ import run

CLI_MAIN = "snaffle.__main__.main"


class TestRun(unittest.TestCase):
    """Test cases for `run`, the console script and `python -m` entry point."""

    @patch(CLI_MAIN)
    def test_run_delegates_to_the_cli(self, mock_main: MagicMock) -> None:
        """Test the entry point calls the CLI and exits with the code it returns."""
        mock_main.return_value = 0

        with self.assertRaises(SystemExit) as caught:
            run()

        mock_main.assert_called_once_with()
        self.assertEqual(caught.exception.code, 0)

    @patch(CLI_MAIN)
    def test_run_exits_with_the_cli_error_code(self, mock_main: MagicMock) -> None:
        """Test a non-zero code from the CLI reaches the process exit status."""
        mock_main.return_value = 1

        with self.assertRaises(SystemExit) as caught:
            run()

        self.assertEqual(caught.exception.code, 1)

    @patch(CLI_MAIN, side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt_exits_zero(self, _: MagicMock) -> None:
        """Test Ctrl+C is a clean exit, not a traceback.

        The console script points at `run` rather than `cli:main` precisely so
        that it gets this handling; see the CLI reference on exit codes.
        """
        with (
            patch("sys.stdout", new=io.StringIO()) as fake_stdout,
            self.assertRaises(SystemExit) as caught,
        ):
            run()

        self.assertEqual(caught.exception.code, 0)
        self.assertIn("Operation cancelled by user", fake_stdout.getvalue())

    @patch(CLI_MAIN, side_effect=ValueError("boom"))
    def test_other_exceptions_are_not_swallowed(self, _: MagicMock) -> None:
        """Test only KeyboardInterrupt is special-cased."""
        with self.assertRaises(ValueError):
            run()


if __name__ == "__main__":
    unittest.main()
