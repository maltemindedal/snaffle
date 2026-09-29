"""Run the Snaffle CLI with ``python -m snaffle``.

`cli.main` reports its outcome as a return value rather than raising
`SystemExit`, so this is where that code becomes the process exit status. The
one exit that still happens elsewhere is argparse's `2` for a bad command line.
"""

import contextlib
import os
import sys

from snaffle.cli import main


def run() -> None:
    """Run the package entrypoint, exiting with the code the CLI returns.

    `Ctrl+C` is the one outcome the CLI does not report as a return value; it
    is caught here and reported as a clean exit `0`. A reader that exits early,
    as in `snaffle GET url | head`, closes the pipe under the CLI's output; that
    is reported as exit `1` without a traceback.
    """

    try:
        code = main()
        # Flush inside the try, so a closed pipe surfaces here instead of at
        # interpreter shutdown, where it would become exit status 120. There may
        # be nothing to flush: `sys.stdout` is None when descriptor 1 is closed.
        flush = getattr(sys.stdout, "flush", None)
        if flush is not None:
            flush()
        sys.exit(code)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(0)
    except BrokenPipeError:
        # Point stdout at devnull so the flush Python makes on exit cannot fail
        # again. This is the recipe in the `signal` module's note on SIGPIPE.
        with contextlib.suppress(AttributeError, OSError, ValueError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(1)


if __name__ == "__main__":
    run()
