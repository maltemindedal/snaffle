"""Keep text a server chose from driving the user's terminal.

Headers, a plain-text body and the reason phrase in an error message are all
chosen by the server. Written raw to a terminal, an escape sequence in them can
retitle the window, clear or rewrite what is on screen, or write to the
clipboard. `for_stdout` shows such characters instead of obeying them.

It changes nothing when stdout is not a terminal, so piped and redirected output
stays byte for byte what the server sent.

The module is private and imports only `sys`, so the CLI's help paths stay as
light as ADR 0002 requires.
"""

from __future__ import annotations

import sys

#: Each C0 control except tab and newline, DEL, and each C1 control, with its
#: `\xNN` spelling. That includes the carriage return, which `for_stdout` keeps
#: only where it starts a CRLF: a lone one lets a server overwrite text already
#: printed on the same line.
_ESCAPES = {
    code: f"\\x{code:02x}"
    for code in (*range(0x20), *range(0x7F, 0xA0))
    if code not in (0x09, 0x0A)
}


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
    # A table applied by `str.translate` runs in C. Replacing matches with a
    # callback did a Python call per character, so a 30 MB body of NULs took 22 s
    # and 1.7 GB on a terminal, and a 30 KB gzip could ask for it.
    return "\r\n".join(part.translate(_ESCAPES) for part in text.split("\r\n"))
