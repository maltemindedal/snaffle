"""Keep text a server chose from driving the user's terminal.

Headers, a plain-text body and the reason phrase in an error message are all
chosen by the server. Written raw to a terminal, an escape sequence in them can
retitle the window, clear or rewrite what is on screen, or write to the
clipboard. `for_stdout` shows such characters instead of obeying them.

It changes nothing when stdout is not a terminal, so piped and redirected output
stays byte for byte what the server sent.

The module is private and imports only `re` and `sys`, so the CLI's help paths
stay as light as ADR 0002 requires.
"""

from __future__ import annotations

import re
import sys

#: C0 controls except tab and newline, DEL, and C1 controls, plus a carriage
#: return that does not start a CRLF. A lone carriage return lets a server
#: overwrite text already printed on the same line.
_CONTROLS = re.compile(r"\r(?!\n)|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def for_stdout(text: str) -> str:
    """Returns `text` with terminal control characters escaped, if stdout is one.

    Each escaped character is shown as `\\xNN`. Tab, newline and a CRLF pair are
    kept, so ordinary text and Windows line endings look as they did. When stdout
    is not a terminal, or is closed, `text` is returned unchanged.

    Args:
        text (str): Text about to be written to stdout.

    Returns:
        str: `text`, made safe to show on a terminal.
    """
    isatty = getattr(sys.stdout, "isatty", None)
    try:
        if isatty is None or not isatty():
            return text
    except (OSError, ValueError):
        return text
    return _CONTROLS.sub(lambda match: f"\\x{ord(match.group()):02x}", text)
