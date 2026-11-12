"""Guard: tracked text follows the owner's prose rules from AGENTS.md."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUFFIXES = (".py", ".md", ".toml", ".yml")

#: AGENTS.md states the rules, so it must name the banned words. This file holds
#: the patterns.
EXEMPT = frozenset({"AGENTS.md", "tests/test_guard_prose.py"})

#: Each rule: a pattern for the banned text and what to write instead.
RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"—|(?<=\w) -- (?=\w)|^\s*-- (?=\w)"),
        (
            "an em dash (or ` -- ` standing in for one); join the clauses with a "
            "full stop, a colon or parentheses"
        ),
    ),
    (
        re.compile(r"\bseams?\b", re.IGNORECASE),
        'the word "seam"; write "boundary"',
    ),
    (
        re.compile(r"\bdeliberately\b", re.IGNORECASE),
        'the word "deliberately"; drop it, or write "on purpose"',
    ),
    (
        # The noun only: "surfaces a closed pipe" and "to surface" are verbs.
        re.compile(
            r"\b(?:the|a|an|its|their|our|this|that|public|whole|entire|api|cli"
            r"|[\w`]+'s)\s+surface\b|\bsurface area\b",
            re.IGNORECASE,
        ),
        '"surface" for an API; write "API"',
    ),
)


def _tracked_text_files() -> list[str]:
    """Returns the tracked paths this guard reads."""
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [
        path
        for path in listing.split("\0")
        if path.endswith(SUFFIXES) and path not in EXEMPT
    ]


def findings() -> list[str]:
    """Returns one `path:line: message` entry per banned phrase in tracked text."""
    found = []
    for path in _tracked_text_files():
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            for pattern, instead in RULES:
                if pattern.search(line):
                    found.append(f"{path}:{number}: uses {instead}")
    return found


class TestProse(unittest.TestCase):
    """The owner rewrote 27 files of agent prose by hand to get these rules."""

    def test_tracked_text_has_no_banned_phrasing(self) -> None:
        """Test no tracked .py, .md, .toml or .yml file breaks the prose rules."""
        found = findings()

        self.assertEqual(
            found, [], "Rewrite these (AGENTS.md, Prose):\n" + "\n".join(found)
        )

    def test_each_rule_matches_what_it_names(self) -> None:
        """Test the patterns catch the phrasing and spare the verb forms."""
        samples = {
            "a — b": True,
            "a -- b": True,
            "git log -- path": True,
            "    -- retries happen": True,
            "snaffle --help and --verbose": False,
            "the seam here": True,
            "seamless": False,
            "done deliberately": True,
            "the public surface": True,
            "Snaffle's surface is small": True,
            "to surface a closed pipe": False,
            "a failure surfaced as an error": False,
        }
        for text, banned in samples.items():
            with self.subTest(text=text):
                hit = any(pattern.search(text) for pattern, _ in RULES)

                self.assertEqual(hit, banned)


if __name__ == "__main__":
    unittest.main()
