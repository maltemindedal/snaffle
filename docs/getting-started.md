# Getting started

By the end of this page you will have Snaffle installed, will have made
requests from the command line, and will have used the client from Python.
Budget about ten minutes.

## Before you begin

You need:

- **Python 3.10 or newer.** Check with `python --version`.
- **[uv](https://docs.astral.sh/uv/).** Snaffle is developed against uv, and
  every command here uses it. Install instructions are on the uv site.
- **Git**, to clone the repository.

Snaffle is not published to PyPI, so there is no `pip install snaffle`. You
install it from a clone.

## Step 1. Get the code

```bash
git clone https://github.com/maltemindedal/snaffle.git
cd snaffle
```

## Step 2. Create the environment

```bash
uv sync --group dev
```

This creates a `.venv/` in the project, installs `requests`, `tqdm`, and
`urllib3`, installs Snaffle itself in editable mode, and adds the development
tools (`ruff` and `ty`).

## Step 3. Check the install

```bash
uv run snaffle HELP
```

You should see the top-level usage line, the list of commands, and then
numbered examples:

```
usage: snaffle [-h]
...
```

If that printed, Snaffle works. Every command from here on is prefixed with
`uv run`, which runs it inside the environment you just created.

## Step 4. Make your first request

```bash
uv run snaffle GET https://httpbin.org/get
```

Snaffle prints the status, every response header, and the
body. Because httpbin answers with JSON, the body is pretty-printed:

```
Status Code: 200

Headers:
date: ...
content-type: application/json
content-length: 292

Response Body:
{
    "args": {},
    "headers": {
        "Host": "httpbin.org"
    },
    "url": "https://httpbin.org/get"
}
```

Every command also works in lower case. Mixed case, such as `Get`, is refused:

```console
$ uv run snaffle get --help
usage: snaffle GET ...
$ echo $?
0
$ uv run snaffle Get --help
usage: snaffle [-h]
...
snaffle: error: argument command: invalid choice: 'Get' ...
$ echo $?
2
```

## Step 5. Send a JSON body

A method that sends a body takes `-d` with a JSON document. Wrap the whole
document in single quotes so your shell leaves the double quotes alone:

```bash
uv run snaffle POST https://httpbin.org/post -d '{"key": "value"}'
```

httpbin echoes what it received, so the response contains your body back under
`"json"`. You did not need to set `Content-Type`. `-d` sends the body as JSON,
and the header follows automatically.

> On Windows `cmd.exe`, single quotes are not quoting characters. Use
> PowerShell (where the example above works as written) or escape the inner
> quotes for `cmd.exe`.

## Step 6. Add a header

`-H` takes one `Key: Value` pair and can be repeated:

```bash
uv run snaffle GET https://httpbin.org/headers -H "Authorization: Bearer token123"
```

The response shows the header arriving at the server.

## Step 7. See what is happening

`-v` logs the outgoing request and the response metadata before the normal
output:

```bash
uv run snaffle GET https://httpbin.org/get -v
```

```
[VERBOSE] Sending GET request to https://httpbin.org/get with {}
[VERBOSE] Received response with status 200 and headers {...}
Status Code: 200
...
```

Use this when a request behaves unexpectedly. It shows
what Snaffle sent.

## Step 8. Watch an error

Snaffle treats a non-2xx status as an error. It prints a message instead of
the body and exits with a failure code:

```bash
uv run snaffle GET https://httpbin.org/status/404
```

```
Error: HTTP error occurred: 404 Client Error: NOT FOUND for url: https://httpbin.org/status/404
```

A `404` is not retried. Only connection failures and the transient statuses in
`HTTPClient.RETRY_STATUSES` are. Retrying a `404` would only multiply the
latency of an answer that will not change.

## Step 9. Use it from Python

The same client backs the CLI. Create one, use it, close it:

```python
from snaffle import HTTPClient

with HTTPClient(timeout=10) as client:
    response = client.get("https://httpbin.org/get")
    print(response.status_code)
    print(response.json()["url"])
```

```
200
https://httpbin.org/get
```

`response` is an ordinary `requests.Response`, so everything you know about
`requests` applies to it.

The `with` block matters. A client owns a pooled connection, and the context
manager releases it on exit. Keeping one client for a batch of requests is also
what makes pooling useful. The second request to a host skips the TCP and
TLS handshake entirely.

## Where to go next

- [Using Snaffle as a library](guides/using-as-a-library.md) covers batching,
  error handling, and custom bodies.
- [Downloading large files](guides/downloading-large-files.md) covers progress
  bars and streaming.
- [CLI reference](reference/cli.md) covers exit codes and security notes.
- [Python API reference](reference/python-api.md) covers the arguments,
  constants, and exceptions.
- [Troubleshooting](guides/troubleshooting.md) covers common failures.
