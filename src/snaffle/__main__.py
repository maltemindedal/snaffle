"""Main entry point for the snaffle command-line application.

This module allows the snaffle application to be executed as a package
by running `python -m snaffle`. It handles the initial execution and
catches common exceptions like `KeyboardInterrupt`.

`cli.main` reports its outcome as a return value rather than raising
`SystemExit`, so this is where that code becomes the process exit status. The
one exit that still happens elsewhere is argparse's `2` for a bad command line.
"""

import sys

from snaffle.cli import main


def run() -> None:
    """Run the package entrypoint, exiting with the code the CLI returns.

    `Ctrl+C` is the one outcome the CLI does not report as a return value; it
    is caught here and reported as a clean exit `0`.
    """

    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(0)


if __name__ == "__main__":
    run()
