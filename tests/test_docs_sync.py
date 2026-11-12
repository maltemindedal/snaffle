"""Generate the reference facts that the docs repeat from the code, and check them.

A Markdown file marks such a fact with a pair of comments::

    <!-- generated: methods -->GET, POST, ...<!-- end -->

The text between them is rendered from the running code by `RENDERERS`. The
test fails when a file differs from what the code renders, or lacks a block that
`BLOCKS` lists for it. Rewrite the blocks with::

    uv run python -m tests.test_docs_sync --write
"""

from __future__ import annotations

import argparse
import difflib
import json
import logging
import os
import re
import sys
import threading
import unittest
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, NoReturn, cast
from unittest.mock import patch

from requests.adapters import HTTPAdapter
from tests._isolation import isolate, setUpModule  # noqa: F401
from typing_extensions import override
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.exceptions import ConnectTimeoutError, ReadTimeoutError
from urllib3.util.retry import Retry

from snaffle import cli
from snaffle.exceptions import HTTPClientError
from snaffle.http_client import HTTPClient

ROOT = Path(__file__).resolve().parents[1]
WRITE = "uv run python -m tests.test_docs_sync --write"
MARKED = re.compile(r"(<!-- generated: ([\w-]+) -->).*?(<!-- end -->)", re.DOTALL)

#: The blocks each file must contain. A file that drops a marker fails the test.
BLOCKS: dict[str, set[str]] = {
    "README.md": {"methods"},
    "docs/reference/cli.md": {"cli-commands", "cli-flags"},
    "docs/reference/python-api.md": {
        "const-ALLOWED_METHODS",
        "const-DOWNLOAD_CHUNK_SIZE",
        "const-MIN_SIZE_FOR_PROGRESS",
        "const-RETRY_STATUSES",
        "const-POOL_SIZE",
        "retry-backoff-factor",
        "retry-after-cap",
        "errors",
    },
}

METHODS = [command.method for command in cli.COMMANDS]


def _code(names: list[str]) -> str:
    """Returns `names` as a comma-separated list of inline code."""
    return ", ".join(f"`{name}`" for name in names)


def _block(body: str) -> str:
    """Returns `body` set off by blank lines, as a block-level element needs."""
    return f"\n\n{body.strip()}\n\n"


def _methods() -> str:
    """Returns the methods as an English list."""
    *others, last = METHODS
    return f"{', '.join(others)}, and {last}"


def _commands() -> dict[str, argparse.ArgumentParser]:
    """Returns the parser's subcommands by name, aliases included."""
    return next(
        action.choices
        for action in cli.create_parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    )


def _cli_commands() -> str:
    """Returns the table of commands, their aliases and their optional flags.

    The table is read from the parser's actions. They are the same on every
    supported Python, unlike the text argparse prints for them, so the table
    renders the same on 3.10 and on 3.14.
    """
    commands = _commands()
    rows = [
        "| Command | Alias | Takes `-d` | Takes `--progress` |",
        "| --- " * 4 + "|",
    ]
    for name in ["HELP", *METHODS]:
        sub = commands[name]
        aliases = [alias for alias, p in commands.items() if p is sub and alias != name]
        dests = {action.dest for action in sub._actions}
        body = "yes" if "data" in dests else "no"
        progress = "yes" if "progress" in dests else "no"
        rows.append(f"| `{name}` | {_code(aliases)} | {body} | {progress} |")
    return _block("\n".join(rows))


def _cli_flags() -> str:
    """Returns the table of flags, read from the parser's actions."""
    commands = _commands()
    flags: dict[tuple[str, ...], tuple[argparse.Action, list[str]]] = {}
    for method in METHODS:
        for action in commands[method]._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            names = tuple(action.option_strings) or (action.dest,)
            flags.setdefault(names, (action, []))[1].append(method)

    rows = ["| Flag | Value | Default | Commands |", "| --- " * 4 + "|"]
    for names, (action, methods) in flags.items():
        if action.nargs == 0:
            value = "none"
        else:
            value = f"`{action.metavar or action.dest.upper()}`"
            if action.type is int:
                value += ", an integer"
            if isinstance(action, argparse._AppendAction):
                value += ", repeatable"
        if not action.option_strings:
            default = "required"
        elif action.default is False:
            default = "off"
        elif action.default is None:
            default = "not set"
        else:
            default = f"`{action.default}`"
        commands = "every method" if methods == METHODS else _code(methods)
        rows.append(f"| {_code(list(names))} | {value} | {default} | {commands} |")
    return _block("\n".join(rows))


def _constant(name: str) -> str:
    """Returns the value of `HTTPClient.<name>` as inline code."""
    value = getattr(HTTPClient, name)
    if isinstance(value, frozenset):
        items = sorted(value, key=lambda item: (item not in METHODS, item))
        if value <= set(METHODS):
            items = [method for method in METHODS if method in value]
        return f"`frozenset({{{', '.join(json.dumps(item) for item in items)}}})`"
    for unit, size in (("MiB", 1024 * 1024), ("KiB", 1024)):
        if isinstance(value, int) and value >= size and value % size == 0:
            return f"`{value!r}` ({value // size} {unit})"
    return f"`{value!r}`"


def _retry() -> Retry:
    """Returns the retry policy of the session a default client builds."""
    with HTTPClient() as client:
        adapter = client.session.get_adapter("http://")
    assert isinstance(adapter, HTTPAdapter)
    return adapter.max_retries


def _errors() -> str:
    """Returns what a default client does with each failure, for every method.

    Each cell is observed: a real client sends the request through urllib3's
    retry loop. A connection or read failure is raised where urllib3 would open
    the socket, as `TestRetryWithoutASocket` does. A status comes from a server
    on loopback.
    """
    attempts: list[str] = []

    class Reply(BaseHTTPRequestHandler):
        """Answers every request with the status named in its path."""

        def reply(self) -> None:
            """Sends the status in the path, with an empty body."""
            attempts.append(self.path)
            self.send_response(int(self.path[1:]))
            self.send_header("Content-Length", "0")
            self.end_headers()

        @override
        def log_message(self, format: str, *args: Any) -> None:
            """Keeps the request log out of the test output."""

    for method in METHODS:
        setattr(Reply, f"do_{method}", Reply.reply)

    def fail_with(error: Exception) -> Callable[[HTTPConnectionPool], NoReturn]:
        """Returns a `_new_conn` that counts an attempt and raises `error`."""

        def new_conn(_: HTTPConnectionPool) -> NoReturn:
            attempts.append("no socket")
            raise error

        return new_conn

    def outcomes(url: str) -> list[str]:
        """Returns, per method, the exception raised and the attempts made."""
        cells = []
        for method in METHODS:
            attempts.clear()
            with HTTPClient() as client:
                try:
                    client.make_request(method, url)
                except HTTPClientError as error:
                    plural = "s" if len(attempts) > 1 else ""
                    cells.append(
                        f"`{type(error).__name__}` after {len(attempts)} attempt{plural}"
                    )
                else:
                    raise AssertionError(f"{method} {url} raised nothing")
        return cells

    retried = max(HTTPClient.RETRY_STATUSES)
    read_timeout = ReadTimeoutError(cast(Any, None), "/", "read timed out")
    rows: dict[str, list[str]] = {}
    server = HTTPServer(("127.0.0.1", 0), Reply)
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with (
            patch("urllib3.util.retry.time.sleep"),
            patch.object(logging.getLogger("urllib3.connectionpool"), "disabled", True),
        ):
            with patch.object(
                HTTPConnectionPool, "_new_conn", fail_with(ConnectTimeoutError())
            ):
                rows["Connection never established"] = outcomes(base)
            with patch.object(HTTPConnectionPool, "_new_conn", fail_with(read_timeout)):
                rows["Read timeout while waiting for the response"] = outcomes(base)
            rows[f"Status in `RETRY_STATUSES` ({retried}) on every attempt"] = outcomes(
                f"{base}/{retried}"
            )
            rows["Any other error status (404)"] = outcomes(f"{base}/404")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    # Methods that behave the same in every row share a column.
    columns: dict[tuple[str, ...], list[str]] = {}
    for index, method in enumerate(METHODS):
        columns.setdefault(tuple(row[index] for row in rows.values()), []).append(
            method
        )
    lines = [
        "| Failure | " + " | ".join(_code(names) for names in columns.values()) + " |",
        "| --- " * (len(columns) + 1) + "|",
    ]
    for index, label in enumerate(rows):
        cells = " | ".join(column[index] for column in columns)
        lines.append(f"| {label} | {cells} |")
    return _block("\n".join(lines))


RENDERERS: dict[str, Callable[[], str]] = {
    "methods": _methods,
    "cli-commands": _cli_commands,
    "cli-flags": _cli_flags,
    "retry-backoff-factor": lambda: f"`{_retry().backoff_factor}`",
    "retry-after-cap": lambda: f"{_retry().retry_after_max}",
    "errors": _errors,
}


def _render(name: str, cache: dict[str, str]) -> str:
    """Returns the text of block `name`, rendering it once per run."""
    if name not in cache:
        if name.startswith("const-"):
            cache[name] = _constant(name.removeprefix("const-"))
        else:
            cache[name] = RENDERERS[name]()
    return cache[name]


def generated() -> dict[str, tuple[str, str]]:
    """Render every block in every file listed in `BLOCKS`.

    Returns:
        dict[str, tuple[str, str]]: For each path, the text on disk and the text
        with its blocks rendered from the code.

    Raises:
        AssertionError: If a file's markers are not the ones `BLOCKS` lists.
    """
    cache: dict[str, str] = {}
    result = {}
    for path, names in BLOCKS.items():
        current = (ROOT / path).read_text(encoding="utf-8")
        found = {match.group(2) for match in MARKED.finditer(current)}
        if found != names:
            raise AssertionError(
                f"{path} must hold the generated blocks {sorted(names)} but holds "
                f"{sorted(found)}. Wrap each fact in `<!-- generated: NAME -->` and "
                f"`<!-- end -->`, then regenerate it with: {WRITE}"
            )

        def replace(match: re.Match[str]) -> str:
            return f"{match.group(1)}{_render(match.group(2), cache)}{match.group(3)}"

        result[path] = (current, MARKED.sub(replace, current))
    return result


class TestDocsMatchTheCode(unittest.TestCase):
    """The facts that the docs repeat from the code are the code's."""

    def test_generated_blocks_are_current(self) -> None:
        """Test every marked block holds what the code renders today."""
        for path, (current, expected) in generated().items():
            with self.subTest(path=path):
                if current != expected:
                    diff = difflib.unified_diff(
                        current.splitlines(keepends=True),
                        expected.splitlines(keepends=True),
                        path,
                        "generated from the code",
                        n=1,
                    )
                    self.fail(
                        f"{path} states a fact that the code no longer agrees "
                        f"with.\nRegenerate it with: {WRITE}\n{''.join(diff)}"
                    )


if __name__ == "__main__":
    if sys.argv[1:] == ["--write"]:
        isolate(os.environ)
        for name, (before, after) in generated().items():
            if before != after:
                (ROOT / name).write_text(after, encoding="utf-8")
                print(f"rewrote {name}")
    else:
        unittest.main()
