"""Guard: every test module runs with the machine's settings cleared."""

from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

from tests._isolation import is_machine_setting, isolate, setUpModule  # noqa: F401

TESTS = Path(__file__).resolve().parent


def _imports_the_isolation(source: str) -> bool:
    """Returns whether `source` imports `setUpModule` from `tests._isolation`."""
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "tests._isolation"
        and "setUpModule" in {alias.name for alias in node.names}
        for node in ast.walk(ast.parse(source))
    )


class TestEveryModuleIsIsolated(unittest.TestCase):
    """`unittest discover` runs `setUpModule` per module, so each must have it."""

    def test_every_test_module_imports_the_shared_set_up(self) -> None:
        """Test no test module is left to clear the environment by itself."""
        missing = [
            f"tests/{path.name}"
            for path in sorted(TESTS.glob("test_*.py"))
            if not _imports_the_isolation(path.read_text(encoding="utf-8"))
        ]

        self.assertEqual(
            missing,
            [],
            "Add `from tests._isolation import setUpModule  # noqa: F401` to "
            "each of these, and delete any setUpModule or proxy filtering of "
            "their own:\n" + "\n".join(missing),
        )

    def test_the_environment_a_test_sees_has_no_machine_settings(self) -> None:
        """Test the running process has no proxy or `TQDM_*` variable."""
        leaked = [name for name in os.environ if is_machine_setting(name)]

        self.assertEqual(leaked, [])

    def test_isolate_removes_each_spelling_and_nothing_else(self) -> None:
        """Test lower and upper case proxy names and `TQDM_*` go; others stay."""
        environ = {
            "http_proxy": "x",
            "HTTPS_PROXY": "x",
            "All_Proxy": "x",
            "TQDM_DISABLE": "1",
            "NO_PROXY": "localhost",
            "PATH": "/bin",
        }

        isolate(environ)

        self.assertEqual(environ, {"NO_PROXY": "localhost", "PATH": "/bin"})


if __name__ == "__main__":
    unittest.main()
