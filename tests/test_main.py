"""Test cases for the package entry point."""

from __future__ import annotations

import io
import os
import subprocess
import sys
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


@unittest.skipIf(sys.platform == "win32", "relies on POSIX pipe semantics")
class TestBrokenPipe(unittest.TestCase):
    """A reader that exits early, as in `snaffle GET url | head`, is not an error to report."""

    #: Runs `run()` with a `main` that writes `sys.argv[1]` bytes to stdout.
    PROBE = (
        "import sys\n"
        "from unittest.mock import patch\n"
        "from snaffle import __main__\n"
        "def fake_main():\n"
        "    sys.stdout.write('x' * int(sys.argv[1]))\n"
        "    return 0\n"
        "with patch.object(__main__, 'main', fake_main):\n"
        "    __main__.run()\n"
    )

    def _run_into_a_closed_pipe(self, size: int) -> subprocess.CompletedProcess[str]:
        """Runs the probe with stdout on a pipe whose reader has already gone."""
        read_end, write_end = os.pipe()
        os.close(read_end)
        # Unbuffered output would fail inside `main`, not at the final flush.
        env = {k: v for k, v in os.environ.items() if k != "PYTHONUNBUFFERED"}
        try:
            return subprocess.run(
                [sys.executable, "-c", self.PROBE, str(size)],
                stdout=write_end,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
        finally:
            os.close(write_end)

    def test_a_closed_pipe_exits_one_without_a_traceback(self) -> None:
        """Test neither a large nor a small write leaves noise behind.

        Regression: a large body raised `BrokenPipeError` with a 13-line
        traceback, and a small one, still buffered when `main` returned, failed at
        interpreter shutdown with `Exception ignored ...` and exit status 120.
        """
        for size in (300_000, 100):
            with self.subTest(size=size):
                result = self._run_into_a_closed_pipe(size)

                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stderr, "", "nothing may reach stderr")


if __name__ == "__main__":
    unittest.main()
