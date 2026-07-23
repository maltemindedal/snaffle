"""Command-line interface for making HTTP requests.

This module provides a command-line interface (CLI) for making HTTP requests
using the snaffle HTTP client. It supports common HTTP methods, custom headers,
JSON data, and other features.

The HTTP client (and with it ``requests``) is imported lazily so that ``--help``,
``HELP`` and argument errors do not pay for the network stack they never use.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from collections.abc import Sequence
from typing import Any, NamedTuple, TypedDict

from snaffle.exceptions import HTTPClientError


class RequestKwargs(TypedDict, total=False):
    """Typed keyword arguments passed to the HTTP client."""

    json: Any
    headers: dict[str, str]


EXAMPLES = textwrap.dedent(
    """
     Examples:
          1. Normal GET request:
              snaffle GET https://httpbin.org/get

          2. GET request with progress bar (for files larger than 5MB):
              snaffle GET https://example.com/large-file.zip --progress

          3. GET request with verbose mode to see retry logs and detailed output:
              snaffle GET https://httpbin.org/get --verbose

          4. GET request with a custom header (e.g., Authorization token):
              snaffle GET https://httpbin.org/headers -H "Authorization: Bearer your_token_here"

          5. POST request with JSON data and custom Content-Type header:
              snaffle POST https://httpbin.org/post -d '{"key": "value"}' -H "Content-Type: application/json"

          6. PUT request example to update a resource:
              snaffle PUT https://httpbin.org/put -d '{"name": "New Name"}' -H "Content-Type: application/json"

          7. PATCH request example to partially update a resource:
              snaffle PATCH https://httpbin.org/patch -d '{"email": "user@example.com"}' -H "Content-Type: application/json"

          8. DELETE request to remove a resource:
              snaffle DELETE https://httpbin.org/delete

          9. HEAD request to fetch only headers:
              snaffle HEAD https://httpbin.org/get

          10. OPTIONS request to check allowed methods:
              snaffle OPTIONS https://httpbin.org/get

          11. Show help message:
              snaffle HELP
     """
)


class Command(NamedTuple):
    """A supported HTTP method and the optional arguments its subcommand takes."""

    method: str
    #: Example body shown in `-d/--data` help; None means the method takes no body.
    data_example: str | None = None
    accepts_progress: bool = False


COMMANDS: tuple[Command, ...] = (
    Command("GET", accepts_progress=True),
    Command("POST", data_example='{"key": "value"}'),
    Command("PUT", data_example='{"name": "New Name"}'),
    Command("PATCH", data_example='{"email": "user@example.com"}'),
    Command("DELETE"),
    Command("HEAD"),
    Command("OPTIONS"),
)


def show_examples(suppress_output: bool = False) -> str:
    """Prints usage examples for the snaffle CLI.

    This function displays a list of common commands to guide the user.

    Args:
        suppress_output (bool, optional): If True, the output is not printed
            to the console. Defaults to False.

    Returns:
        str: A string containing the usage examples.
    """
    if not suppress_output:
        print(EXAMPLES)
    return EXAMPLES


def _parse_headers(header_args: Sequence[str] | None) -> dict[str, str] | None:
    """Parses repeated header arguments into a dictionary."""
    if not header_args:
        return None

    headers: dict[str, str] = {}
    for item in header_args:
        if ":" not in item:
            raise ValueError("Invalid header format. Use 'Key: Value'.")

        key, value = item.split(":", 1)
        headers[key.strip()] = value.strip()

    return headers or None


def _parse_request_kwargs(args: argparse.Namespace) -> RequestKwargs:
    """Builds keyword arguments for the HTTP client call."""
    kwargs: RequestKwargs = {}

    data = getattr(args, "data", None)
    if data:
        kwargs["json"] = json.loads(data)

    headers = _parse_headers(getattr(args, "header", None))
    if headers:
        kwargs["headers"] = headers

    return kwargs


def _emit_response(response: Any) -> None:
    """Prints a formatted HTTP response using a single buffered write."""
    parts = [f"Status Code: {response.status_code}\n", "\nHeaders:\n"]
    parts.extend(f"{key}: {value}\n" for key, value in response.headers.items())

    text = response.text
    if text.strip():
        parts.append("\nResponse Body:\n")
        try:
            parts.append(json.dumps(json.loads(text), indent=4))
        except ValueError:
            parts.append(text)
        parts.append("\n")

    sys.stdout.write("".join(parts))


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds common command-line arguments to the given parser.

    This function standardizes the arguments for URL, timeout, headers, and verbosity
    across different sub-commands.

    Args:
        parser (argparse.ArgumentParser): The parser to which the arguments will be added.
    """
    parser.add_argument("url", help="Target URL")
    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "-H",
        "--header",
        action="append",
        help="HTTP header in 'Key: Value' format. Can be used multiple times.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging for debugging.",
    )


class CustomFormatter(argparse.HelpFormatter):
    """Custom help formatter to support multi-line help messages.

    This formatter allows help text to be split into multiple lines
    by prefixing it with "R|".
    """

    def _split_lines(self, text: str, width: int) -> list[str]:
        if text.startswith("R|"):
            return text[2:].splitlines()
        return super()._split_lines(text, width)


def create_parser() -> argparse.ArgumentParser:
    """Creates and configures the argument parser for the CLI.

    This function sets up the main parser and subparsers for each supported
    HTTP method, defining the available commands and their arguments.

    Returns:
        argparse.ArgumentParser: The configured argument parser.
    """
    parser = argparse.ArgumentParser(
        # Pinned so `snaffle`, `python -m snaffle`, and a direct script call all
        # print the same usage line instead of echoing the interpreter path.
        prog="snaffle",
        description="HTTP CLI client supporting GET, POST, PUT, PATCH, DELETE, HEAD, and OPTIONS methods",
        formatter_class=CustomFormatter,
        add_help=True,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.add_parser(
        "HELP", help="Show detailed help and examples", aliases=["help"]
    )

    for command in COMMANDS:
        method = command.method
        article = "an" if method == "OPTIONS" else "a"
        sub = subparsers.add_parser(
            method,
            help=f"Make {article} {method} request",
            aliases=[method.lower()],
        )
        add_common_arguments(sub)
        if command.data_example is not None:
            sub.add_argument(
                "-d",
                "--data",
                help=f"R|JSON data for request body.\nExample: '{command.data_example}'",
            )
        if command.accepts_progress:
            sub.add_argument(
                "--progress",
                action="store_true",
                help="Show progress bar for downloads larger than 5MB",
            )

    return parser


def main(argv: Sequence[str] | None = None, suppress_output: bool = False) -> None:
    """The main entry point for the snaffle CLI.

    This function parses command-line arguments, initializes the HTTP client,
    and executes the requested HTTP command. It also handles response printing
    and error reporting.

    Args:
        argv (Sequence[str], optional): Arguments to parse. Defaults to ``sys.argv``.
        suppress_output (bool, optional): If True, suppresses all output to the
            console, which is useful for testing. Defaults to False.
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    command = args.command.upper() if args.command else None

    if not command or command == "HELP":
        if not suppress_output:
            parser.print_help()
            print("\n")
        show_examples(suppress_output)
        return

    # Deferred so the help paths above never import the HTTP stack.
    from snaffle.http_client import HTTPClient

    try:
        kwargs = _parse_request_kwargs(args)

        with HTTPClient(
            timeout=args.timeout,
            verbose=args.verbose,
            show_progress=getattr(args, "progress", False),
        ) as client:
            response = getattr(client, command.lower())(args.url, **kwargs)

            if not suppress_output:
                _emit_response(response)

    except json.JSONDecodeError:
        if not suppress_output:
            print("Error: Invalid JSON data")
            print("Make sure your JSON data is properly formatted.")
            print('Example: \'{"key": "value"}\'')
        sys.exit(1)
    except (ValueError, HTTPClientError) as error:
        # json.JSONDecodeError is a ValueError, so it must be caught above this.
        if not suppress_output:
            print(f"Error: {error}")
        sys.exit(1)
