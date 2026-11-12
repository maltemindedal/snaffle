"""Guard: every public name is defined in the module the docs name for it."""

from __future__ import annotations

import importlib
import unittest

from tests._isolation import setUpModule  # noqa: F401

import snaffle

#: Public name to the module that defines it. `ProgressBar` is public through
#: `snaffle.http_client` and is not in `snaffle.__all__`.
DOCUMENTED_MODULE = {
    "HTTPClient": "snaffle.http_client",
    "ProgressBar": "snaffle.http_client",
    "HTTPClientError": "snaffle.exceptions",
    "HTTPConnectionError": "snaffle.exceptions",
    "ResponseError": "snaffle.exceptions",
}

#: Public names that are plain values, so they have no `__module__`.
VALUES = frozenset({"__version__"})


class TestPublicNamesLiveInTheirDocumentedModule(unittest.TestCase):
    """A public class defined in a private module shows that home in its repr."""

    def test_every_public_name_is_listed(self) -> None:
        """Test a new public name is added to `DOCUMENTED_MODULE` with its module."""
        public = (set(snaffle.__all__) - VALUES) | {"ProgressBar"}

        self.assertEqual(
            public,
            set(DOCUMENTED_MODULE),
            "Add the new public name to DOCUMENTED_MODULE in "
            "tests/test_guard_public_modules.py, with the module "
            "docs/reference/python-api.md documents for it.",
        )

    def test_dunder_module_names_the_documented_module(self) -> None:
        """Test `__module__` equals the documented module for each public name."""
        for name, expected in DOCUMENTED_MODULE.items():
            with self.subTest(name=name):
                obj = getattr(importlib.import_module(expected), name)

                self.assertEqual(
                    obj.__module__,
                    expected,
                    f"{name} is defined in {obj.__module__}, but its documented "
                    f"module is {expected}. Define the class in {expected} and "
                    f"import it from there (AGENTS.md, Public API and versions).",
                )

    def test_package_reexports_the_same_object(self) -> None:
        """Test `snaffle.<name>` is the object from the documented module."""
        for name in snaffle.__all__:
            if name in VALUES:
                continue
            with self.subTest(name=name):
                module = importlib.import_module(DOCUMENTED_MODULE[name])

                self.assertIs(getattr(snaffle, name), getattr(module, name))


if __name__ == "__main__":
    unittest.main()
