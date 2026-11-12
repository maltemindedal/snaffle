"""The one place that decides which machine settings the tests may see.

Every test module imports `setUpModule` from here:

    from tests._isolation import setUpModule  # noqa: F401

`tests/test_guard_isolation.py` fails for a module that does not. The names
cleared here are the ones that have made tests fail for reasons about the
developer's machine and not about the code.
"""

from __future__ import annotations

import os
import unittest
from collections.abc import MutableMapping
from unittest.mock import patch

PROXY_VARIABLES = frozenset({"http_proxy", "https_proxy", "all_proxy"})

#: `tqdm` reads its `TQDM_*` settings, such as `TQDM_DISABLE`, once, when it is
#: first imported.
PREFIXES = ("TQDM_",)


def is_machine_setting(name: str) -> bool:
    """Returns whether `name` is a setting the tests must not inherit.

    Args:
        name (str): An environment variable name, in any case.

    Returns:
        bool: True for a proxy variable or a `TQDM_*` setting.
    """
    return name.lower() in PROXY_VARIABLES or name.startswith(PREFIXES)


def isolate(environ: MutableMapping[str, str]) -> None:
    """Removes the machine settings from `environ`, in place.

    Args:
        environ (MutableMapping[str, str]): The mapping to clean, normally
            `os.environ`.
    """
    for name in [name for name in environ if is_machine_setting(name)]:
        del environ[name]


def setUpModule() -> None:
    """Keeps the machine's settings out of this module's tests.

    `requests` reads `HTTP_PROXY`, `HTTPS_PROXY` and `ALL_PROXY` from the
    environment. On a machine that sets them, loopback requests, and even
    urllib3's URL errors, go through the proxy and fail for reasons that say
    nothing about the code. The same goes for a child process, which inherits
    `os.environ`. The environment is restored when the module finishes.
    """
    saved = patch.dict(os.environ)
    saved.start()
    unittest.addModuleCleanup(saved.stop)
    isolate(os.environ)
