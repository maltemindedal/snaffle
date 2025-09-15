"""Main entry point for the PyFetch command-line application.

This module allows the PyFetch application to be executed as a package
by running `python -m PyFetch`. It handles the initial execution and
catches common exceptions like `KeyboardInterrupt`.
"""

import sys

from PyFetch.cli import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(0)
