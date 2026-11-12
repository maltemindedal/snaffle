"""Guard: the four hand-kept lists of public names in `snaffle/__init__.py` agree.

A lazy public name is written in `__all__`, the `TYPE_CHECKING` block, the
`__getattr__` hook and the module docstring. A name missing from one of them
works at run time and is wrong for type checkers or for readers.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from tests._isolation import setUpModule  # noqa: F401

INIT = Path(__file__).resolve().parent.parent / "src" / "snaffle" / "__init__.py"


def _is_type_checking(node: ast.stmt) -> bool:
    """Returns whether `node` is `if TYPE_CHECKING:`."""
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "TYPE_CHECKING"
    )


def public_name_lists(source: str) -> dict[str, set[str]]:
    """Reads the four lists of public names out of an `__init__.py` source.

    Args:
        source (str): The text of `snaffle/__init__.py`.

    Returns:
        dict[str, set[str]]: The names in `__all__`, the eager imports, the
            `TYPE_CHECKING` block, `__getattr__`, and the docstring.
    """
    tree = ast.parse(source)
    lists: dict[str, set[str]] = {
        "__all__": set(),
        "eager imports": set(),
        "TYPE_CHECKING block": set(),
        "__getattr__": set(),
        "docstring": set(),
    }
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            lists["__all__"] = set(ast.literal_eval(node.value))
        elif isinstance(node, ast.ImportFrom) and node.module != "typing":
            lists["eager imports"] |= {alias.name for alias in node.names}
        elif _is_type_checking(node):
            assert isinstance(node, ast.If)
            for inner in node.body:
                if isinstance(inner, ast.ImportFrom):
                    lists["TYPE_CHECKING block"] |= {a.name for a in inner.names}
                elif isinstance(inner, ast.AnnAssign) and isinstance(
                    inner.target, ast.Name
                ):
                    lists["TYPE_CHECKING block"].add(inner.target.id)
        elif isinstance(node, ast.FunctionDef) and node.name == "__getattr__":
            for compare in ast.walk(node):
                if (
                    isinstance(compare, ast.Compare)
                    and isinstance(compare.left, ast.Name)
                    and compare.left.id == "name"
                    and isinstance(compare.comparators[0], ast.Constant)
                    and isinstance(compare.comparators[0].value, str)
                ):
                    lists["__getattr__"].add(compare.comparators[0].value)
    docstring = ast.get_docstring(tree) or ""
    lists["docstring"] = set(re.findall(r"^\s+- `(\w+)`:", docstring, re.MULTILINE))
    return lists


def disagreements(source: str) -> list[str]:
    """Returns one sentence per place the lists in `source` disagree."""
    lists = public_name_lists(source)
    public = lists["__all__"]
    lazy = lists["TYPE_CHECKING block"]
    expected = {
        "the eager imports and the TYPE_CHECKING block": (
            lists["eager imports"] | lazy,
            public,
        ),
        "__getattr__": (lists["__getattr__"], lazy),
        "the docstring": (lists["docstring"], public),
    }
    problems = []
    for name, (found, wanted) in expected.items():
        problems.extend(f"{n!r} is missing from {name}" for n in sorted(wanted - found))
        problems.extend(f"{n!r} is only in {name}" for n in sorted(found - wanted))
    return problems


class TestPublicNameListsAgree(unittest.TestCase):
    """What `import snaffle` exposes is stated four times and must match."""

    def test_the_lists_agree(self) -> None:
        """Test every public name is in each list that must hold it."""
        problems = disagreements(INIT.read_text(encoding="utf-8"))

        self.assertEqual(
            problems,
            [],
            "A public name must be written in __all__, the TYPE_CHECKING block "
            "(or an eager import), __getattr__ if lazy, and the docstring list "
            "in src/snaffle/__init__.py:\n" + "\n".join(problems),
        )

    def test_a_lazy_name_added_to_one_list_only_is_reported(self) -> None:
        """Test the comparison fails for a name that skipped three of the lists."""
        source = INIT.read_text(encoding="utf-8").replace(
            '    "ResponseError",\n', '    "ResponseError",\n    "Newcomer",\n'
        )

        problems = disagreements(source)

        self.assertEqual(
            problems,
            [
                (
                    "'Newcomer' is missing from the eager imports and the "
                    "TYPE_CHECKING block"
                ),
                "'Newcomer' is missing from the docstring",
            ],
        )

    def test_a_name_missing_from_getattr_is_reported(self) -> None:
        """Test dropping the `__getattr__` branch of a lazy name is caught."""
        source = INIT.read_text(encoding="utf-8").replace(
            'if name == "HTTPClient":', 'if name == "Other":'
        )

        problems = disagreements(source)

        self.assertIn("'HTTPClient' is missing from __getattr__", problems)


if __name__ == "__main__":
    unittest.main()
