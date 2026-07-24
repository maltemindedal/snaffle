"""Test cases for the package's public surface and lazy attribute resolution."""

from __future__ import annotations

import subprocess
import sys
import unittest
from importlib.metadata import version

import snaffle


class TestPublicAPI(unittest.TestCase):
    """Test cases for what `import snaffle` exposes."""

    def test_every_name_in_all_resolves(self) -> None:
        """Test `__all__` is honest: each entry is actually reachable."""
        for name in snaffle.__all__:
            with self.subTest(name=name):
                self.assertIsNotNone(getattr(snaffle, name))

    def test_http_client_resolves_lazily(self) -> None:
        """Test the PEP 562 hook returns the real class."""
        from snaffle.http_client import HTTPClient

        self.assertIs(snaffle.HTTPClient, HTTPClient)

    def test_version_comes_from_installed_metadata(self) -> None:
        """Test `__version__` is not a second, hand-maintained copy."""
        self.assertEqual(snaffle.__version__, version("snaffle"))

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        """Test the lazy hook still reports genuinely missing names."""
        with self.assertRaises(AttributeError):
            snaffle.does_not_exist  # noqa: B018

    def test_import_does_not_pull_in_requests(self) -> None:
        """Guard the start-up win at the package level, not just the CLI's."""
        probe = "import sys, snaffle; sys.exit(1 if 'requests' in sys.modules else 0)"
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True
        )
        self.assertEqual(
            result.returncode, 0, f"requests was imported by `import snaffle`: {result}"
        )


if __name__ == "__main__":
    unittest.main()
