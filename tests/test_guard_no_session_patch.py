"""Guard: no test patches `requests.Session.request`.

That name sits above the adapter, where urllib3 retries, so a test that patches
it cannot see a retry. It let a false claim about `POST` retries ship. A session
handed to `HTTPClient(session=...)` replaces the transport below it instead
(ADR 0004).
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FIXTURE = (
    "Inject a session instead: mount `_RecordingAdapter` with `_session_over` "
    "in tests/test_http_client.py and pass it as `HTTPClient(session=...)`, or "
    "use a real loopback server (`_LocalServerTestCase`). See ADR 0004."
)

#: Test files that may patch it, each with the reason. Empty on purpose.
ALLOWED: dict[str, str] = {}

_TARGET = re.compile(r"(^|\.)Session\.request$")


def _string_constants(tree: ast.Module) -> dict[str, str]:
    """Returns the module-level `NAME = "text"` assignments."""
    constants = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value.value
    return constants


def _is_patch(func: ast.expr) -> bool:
    """Returns whether a call target is `patch(...)` or `mock.patch(...)`."""
    if isinstance(func, ast.Name):
        return func.id == "patch"
    return isinstance(func, ast.Attribute) and func.attr == "patch"


def _is_patch_object(func: ast.expr) -> bool:
    """Returns whether a call target is `patch.object(...)`."""
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "object"
        and _is_patch(func.value)
    )


def patches_of_session_request(source: str) -> list[int]:
    """Returns the line of each patch of `Session.request` in `source`."""
    tree = ast.parse(source)
    constants = _string_constants(tree)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        first = node.args[0]
        if _is_patch(node.func):
            if isinstance(first, ast.Name):
                text = constants.get(first.id, "")
            elif isinstance(first, ast.Constant) and isinstance(first.value, str):
                text = first.value
            else:
                continue
            if _TARGET.search(text):
                lines.append(node.lineno)
        elif _is_patch_object(node.func) and len(node.args) >= 2:
            name = node.args[1]
            owner = ast.unparse(first).lower()
            if (
                isinstance(name, ast.Constant)
                and name.value == "request"
                and "session" in owner
            ):
                lines.append(node.lineno)
    return lines


class TestNoSessionRequestPatch(unittest.TestCase):
    """Tests substitute the transport, not the method above the retry layer."""

    def test_no_test_file_patches_session_request(self) -> None:
        """Test no test patches `Session.request`, however it spells the name."""
        found = []
        for path in sorted(TESTS.glob("test_*.py")):
            if path.name in ALLOWED or path.name == Path(__file__).name:
                continue
            source = path.read_text(encoding="utf-8")
            found.extend(
                f"tests/{path.name}:{line}"
                for line in patches_of_session_request(source)
            )

        self.assertEqual(
            found,
            [],
            "These patch Session.request, which hides retries from the test. "
            + FIXTURE
            + "\n"
            + "\n".join(found),
        )

    def test_the_scan_sees_each_spelling(self) -> None:
        """Test the detector flags the ways a test can patch the method."""
        spellings = (
            '@patch("requests.Session.request")\ndef f(): ...',
            'S = "requests.Session.request"\n@patch(S)\ndef f(): ...',
            'with mock.patch("Session.request"): ...',
            'with patch.object(requests.Session, "request"): ...',
            'with patch.object(client.session, "request"): ...',
        )
        for source in spellings:
            with self.subTest(source=source):
                self.assertTrue(patches_of_session_request(source))

        for source in ('with patch.object(client.session, "close"): ...',):
            with self.subTest(source=source):
                self.assertEqual(patches_of_session_request(source), [])


if __name__ == "__main__":
    unittest.main()
