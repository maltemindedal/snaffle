"""Check that the uv version pinned for CI and for Cursor cloud agents agree."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
CLOUD_ENV = ROOT / ".cursor" / "environment.json"


def ci_uv_version(text: str) -> str:
    """Return the ``version`` given to astral-sh/setup-uv in the CI workflow."""
    match = re.search(
        r"uses: astral-sh/setup-uv@\S+.*?\n\s+with:\n(?:\s+\S.*\n)*?\s+version: \"([^\"]+)\"",
        text,
    )
    if match is None:
        raise AssertionError("no setup-uv version in ci.yml")
    return str(match.group(1))


def cloud_env_uv_versions(text: str) -> set[str]:
    """Return every uv version named in the cloud agent install script."""
    install = str(json.loads(text)["install"])
    found = re.findall(r"astral\.sh/uv/([0-9][^/]*)/install\.sh", install)
    found += re.findall(r'!= "([0-9][^"]*)"', install)
    versions = {str(v) for v in found}
    if not versions:
        raise AssertionError("no uv version in .cursor/environment.json")
    return set(versions)


class TestUvPins(unittest.TestCase):
    def test_cloud_env_installs_the_uv_version_ci_uses(self) -> None:
        ci = ci_uv_version(CI.read_text(encoding="utf-8"))
        cloud = cloud_env_uv_versions(CLOUD_ENV.read_text(encoding="utf-8"))
        self.assertEqual(cloud, {ci})


if __name__ == "__main__":
    unittest.main()
