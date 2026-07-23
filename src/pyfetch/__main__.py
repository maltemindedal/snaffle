"""Main entry point for the pyfetch command-line application.

This module allows the pyfetch application to be executed as a package
by running `python -m pyfetch`. It handles the initial execution and
catches common exceptions like `KeyboardInterrupt`.
"""

import sys

from pyfetch.cli import main


def run() -> None:
    """Run the package entrypoint and handle user cancellation cleanly."""

    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(0)


if __name__ == "__main__":
    run()
