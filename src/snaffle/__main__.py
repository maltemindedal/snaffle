"""Main entry point for the snaffle command-line application.

This module allows the snaffle application to be executed as a package
by running `python -m snaffle`. It handles the initial execution and
catches common exceptions like `KeyboardInterrupt`.
"""

import sys

from snaffle.cli import main


def run() -> None:
    """Run the package entrypoint and handle user cancellation cleanly."""

    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(0)


if __name__ == "__main__":
    run()
