"""Run the examples in the documentation, so a claim in them cannot go stale.

Two kinds of block are run. A ``pycon`` block is a doctest. A ``console`` block
is a shell session: each ``$ snaffle ...`` or ``$ uv run snaffle ...`` line
runs the CLI in a subprocess, the lines after it are its expected output (stdout
and stderr together, with ``...`` matching anything), and ``$ echo $?`` is
followed by its exit code.
"""

import doctest
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

from tests._isolation import setUpModule  # noqa: F401

DOCS = Path(__file__).resolve().parent.parent / "docs"

#: The pages whose examples are run. A page added here needs no other change.
PAGES = ("getting-started.md", "reference/cli.md", "reference/python-api.md")

_BLOCK = re.compile(r"^```(pycon|console)\n(.*?)^```$", re.MULTILINE | re.DOTALL)
_FLAGS = doctest.ELLIPSIS | doctest.IGNORE_EXCEPTION_DETAIL


def _blocks(page: str, kind: str) -> list[tuple[int, str]]:
    """Return the line number and body of every ``kind`` block in ``page``.

    Args:
        page (str): A path under ``docs/``.
        kind (str): ``pycon`` or ``console``.

    Returns:
        list[tuple[int, str]]: The line each block's body starts on, and the body.
    """
    text = (DOCS / page).read_text(encoding="utf-8")
    return [
        (text.count("\n", 0, match.start(2)) + 1, match.group(2))
        for match in _BLOCK.finditer(text)
        if match.group(1) == kind
    ]


def _console_steps(body: str) -> list[tuple[str, str]]:
    """Split a console block into its commands and their expected output.

    Args:
        body (str): The text between the fences.

    Returns:
        list[tuple[str, str]]: Each command, without ``$ ``, and its output.
    """
    steps: list[tuple[str, str]] = []
    for line in body.splitlines(keepends=True):
        if line.startswith("$ "):
            steps.append((line[2:].strip(), ""))
        elif steps:
            command, output = steps[-1]
            steps[-1] = (command, output + line)
    return steps


class TestPyconExamples(unittest.TestCase):
    """Every ``pycon`` block on a page runs, in order, as one doctest."""

    def test_pycon_blocks_pass(self) -> None:
        """Each page's doctests report no failures."""
        for page in PAGES:
            blocks = _blocks(page, "pycon")
            if not blocks:
                continue
            with self.subTest(page=page):
                text = "\n".join(body for _, body in blocks)
                test = doctest.DocTestParser().get_doctest(
                    text, {}, page, str(DOCS / page), blocks[0][0]
                )
                runner = doctest.DocTestRunner(optionflags=_FLAGS)
                runner.run(test)
                self.assertEqual(runner.failures, 0, f"doctest failed in {page}")


class TestConsoleExamples(unittest.TestCase):
    """Every ``console`` block on a page prints and exits as it says."""

    def test_console_blocks_pass(self) -> None:
        """Each command's output and exit code match the page."""
        checker = doctest.OutputChecker()
        for page in PAGES:
            for lineno, body in _blocks(page, "console"):
                code = None
                for command, expected in _console_steps(body):
                    with self.subTest(page=page, line=lineno, command=command):
                        if command == "echo $?":
                            self.assertEqual(expected.strip(), str(code))
                            continue
                        argv = shlex.split(command)
                        if argv[:2] == ["uv", "run"]:
                            del argv[:2]
                        self.assertEqual(argv[0], "snaffle")
                        result = subprocess.run(
                            [sys.executable, "-m", "snaffle", *argv[1:]],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            timeout=60,
                            check=False,
                        )
                        code = result.returncode
                        self.assertTrue(
                            checker.check_output(
                                expected, result.stdout, doctest.ELLIPSIS
                            ),
                            f"{page}:{lineno}: {command}\n"
                            f"expected:\n{expected}\ngot:\n{result.stdout}",
                        )


if __name__ == "__main__":
    unittest.main()
