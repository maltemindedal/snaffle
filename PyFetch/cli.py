"""Command-line interface for making HTTP requests.

This module provides a command-line interface (CLI) for making HTTP requests
using the PyFetch HTTP client. It supports common HTTP methods, custom headers,
JSON data, and other features.
"""

import argparse
import json
import sys
import textwrap

from PyFetch.exceptions import HTTPClientError
from PyFetch.http_client import HTTPClient


def show_examples(suppress_output=False):
    """Prints usage examples for the PyFetch CLI.

    This function displays a list of common commands to guide the user.

    Args:
        suppress_output (bool, optional): If True, the output is not printed
            to the console. Defaults to False.

    Returns:
        str: A string containing the usage examples.
    """
    examples = """
Examples:
    1. Normal GET request:
       pyfetch GET https://httpbin.org/get

    2. GET request with progress bar (for files larger than 5MB):
       pyfetch GET https://example.com/large-file.zip --progress

    3. GET request with verbose mode to see retry logs and detailed output:
       pyfetch GET https://httpbin.org/get --verbose

    4. GET request with a custom header (e.g., Authorization token):
       pyfetch GET https://httpbin.org/headers -H "Authorization: Bearer your_token_here"

    5. POST request with JSON data and custom Content-Type header:
       pyfetch POST https://httpbin.org/post -d '{"key": "value"}' -H "Content-Type: application/json"

    6. PUT request example to update a resource:
       pyfetch PUT https://httpbin.org/put -d '{"name": "New Name"}' -H "Content-Type: application/json"

    7. PATCH request example to partially update a resource:
       pyfetch PATCH https://httpbin.org/patch -d '{"email": "user@example.com"}' -H "Content-Type: application/json"

    8. DELETE request to remove a resource:
       pyfetch DELETE https://httpbin.org/delete

    9. HEAD request to fetch only headers:
       pyfetch HEAD https://httpbin.org/get

    10. OPTIONS request to check allowed methods:
       pyfetch OPTIONS https://httpbin.org/get

    11. Show help message:
       pyfetch HELP
    """
    if not suppress_output:
        print(textwrap.dedent(examples))
    return textwrap.dedent(examples)


def add_common_arguments(parser):
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


def create_parser():
    """Creates and configures the argument parser for the CLI.

    This function sets up the main parser and subparsers for each supported
    HTTP method, defining the available commands and their arguments.

    Returns:
        argparse.ArgumentParser: The configured argument parser.
    """

    class CustomFormatter(argparse.HelpFormatter):
        """Custom help formatter to support multi-line help messages.

        This formatter allows help text to be split into multiple lines
        by prefixing it with "R|".
        """

        def _split_lines(self, text, width):
            if text.startswith("R|"):
                return text[2:].splitlines()
            return super()._split_lines(text, width)

    parser = argparse.ArgumentParser(
        description="HTTP CLI client supporting GET, POST, PUT, PATCH, DELETE, HEAD, and OPTIONS methods",
        formatter_class=CustomFormatter,
        add_help=True,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # HELP command
    subparsers.add_parser(
        "HELP", help="Show detailed help and examples", aliases=["help"]
    )

    # GET command
    get_parser = subparsers.add_parser(
        "GET", help="Make a GET request", aliases=["get"]
    )
    add_common_arguments(get_parser)
    get_parser.add_argument(
        "--progress",
        action="store_true",
        help="Show progress bar for downloads larger than 5MB",
    )

    # POST command
    post_parser = subparsers.add_parser(
        "POST", help="Make a POST request", aliases=["post"]
    )
    add_common_arguments(post_parser)
    post_parser.add_argument(
        "-d",
        "--data",
        help='R|JSON data for request body.\nExample: \'{"key": "value"}\'',
    )

    # PUT command
    put_parser = subparsers.add_parser(
        "PUT", help="Make a PUT request", aliases=["put"]
    )
    add_common_arguments(put_parser)
    put_parser.add_argument(
        "-d",
        "--data",
        help='R|JSON data for request body.\nExample: \'{"key": "value"}\'',
    )

    # PATCH command
    patch_parser = subparsers.add_parser(
        "PATCH", help="Make a PATCH request", aliases=["patch"]
    )
    add_common_arguments(patch_parser)
    patch_parser.add_argument(
        "-d",
        "--data",
        help='R|JSON data for request body.\nExample: \'{"email": "user@example.com"}\'',
    )

    # DELETE command
    delete_parser = subparsers.add_parser(
        "DELETE", help="Make a DELETE request", aliases=["delete"]
    )
    add_common_arguments(delete_parser)

    # HEAD command
    head_parser = subparsers.add_parser(
        "HEAD", help="Make a HEAD request", aliases=["head"]
    )
    add_common_arguments(head_parser)

    # OPTIONS command
    options_parser = subparsers.add_parser(
        "OPTIONS", help="Make an OPTIONS request", aliases=["options"]
    )
    add_common_arguments(options_parser)

    return parser


def main(suppress_output=False):
    """The main entry point for the PyFetch CLI.

    This function parses command-line arguments, initializes the HTTP client,
    and executes the requested HTTP command. It also handles response printing
    and error reporting.

    Args:
        suppress_output (bool, optional): If True, suppresses all output to the
            console, which is useful for testing. Defaults to False.
    """
    parser = create_parser()
    args = parser.parse_args()

    command = args.command.upper() if args.command else None

    if not command or command == "HELP":
        if not suppress_output:
            parser.print_help()
            print("\n")
        show_examples(suppress_output)
        return

    client = HTTPClient(
        timeout=args.timeout,
        verbose=args.verbose,
        show_progress=args.progress if hasattr(args, "progress") else False,
    )

    try:
        # Prepare request kwargs
        kwargs = {}
        if hasattr(args, "data") and args.data:
            kwargs["json"] = json.loads(args.data)
        # Parse headers if provided
        if hasattr(args, "header") and args.header:
            headers = {}
            for item in args.header:
                if ":" in item:
                    key, value = item.split(":", 1)
                    headers[key.strip()] = value.strip()
            if headers:
                kwargs["headers"] = headers

        # Make the request based on the command
        response = getattr(client, command.lower())(args.url, **kwargs)

        # Print response
        print(f"Status Code: {response.status_code}")
        print("\nHeaders:")
        for key, value in response.headers.items():
            print(f"{key}: {value}")

        # Only print Response Body if there is content
        if response.text.strip():
            print("\nResponse Body:")
            try:
                json_data = json.loads(response.text)
                pretty_response = json.dumps(json_data, indent=4)
                print(pretty_response)
            except ValueError:
                print(response.text)

    except json.JSONDecodeError:
        print("Error: Invalid JSON data")
        print("Make sure your JSON data is properly formatted.")
        print('Example: \'{"key": "value"}\'')
        sys.exit(1)
    except HTTPClientError as e:
        print(f"Error: {str(e)}")
        sys.exit(1)
