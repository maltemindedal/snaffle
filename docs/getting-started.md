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

## Step 1 — Get the code

```bash
git clone https://github.com/maltemindedal/snaffle.git
cd snaffle
```

## Step 2 — Create the environment

```bash
uv sync --group dev
```

This creates a `.venv/` in the project, installs `requests`, `tqdm`, and
`urllib3`, installs Snaffle itself in editable mode, and adds the development
tools (`ruff`, `mypy`, `types-requests`).

## Step 3 — Check the install

```bash
uv run snaffle HELP
```

You should see the top-level usage line, the list of commands, and then eleven
numbered examples:

```
usage: snaffle [-h]
               {HELP,help,GET,get,POST,post,PUT,put,PATCH,patch,DELETE,delete,HEAD,head,OPTIONS,options} ...

HTTP CLI client supporting GET, POST, PUT, PATCH, DELETE, HEAD, and OPTIONS
methods
...
```

If that printed, Snaffle works. Every command from here on is prefixed with
`uv run`, which runs it inside the environment you just created.

## Step 4 — Make your first request

```bash
uv run snaffle GET https://httpbin.org/get
```

Snaffle prints three sections — the status, every response header, and the
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

Commands are case-insensitive. `uv run snaffle get https://httpbin.org/get`
does the same thing.

## Step 5 — Send a JSON body

`POST`, `PUT`, and `PATCH` take `-d` with a JSON document. Wrap the whole
document in single quotes so your shell leaves the double quotes alone:

```bash
uv run snaffle POST https://httpbin.org/post -d '{"key": "value"}'
```

httpbin echoes what it received, so the response contains your body back under
`"json"`. You did not need to set `Content-Type` — `-d` sends the body as JSON
and the header follows automatically.

> On Windows `cmd.exe`, single quotes are not quoting characters. Use
> PowerShell (where the example above works as written) or escape the inner
> quotes for `cmd.exe`.

## Step 6 — Add a header

`-H` takes one `Key: Value` pair and can be repeated:

```bash
uv run snaffle GET https://httpbin.org/headers -H "Authorization: Bearer token123"
```

The response shows the header arriving at the server.

## Step 7 — See what is happening

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

Use this when a request behaves unexpectedly — it is the fastest way to confirm
what Snaffle actually sent.

## Step 8 — Watch an error

Snaffle treats a non-2xx status as an error. It exits `1` and prints a message
instead of the body:

```bash
uv run snaffle GET https://httpbin.org/status/404
```

```
Error: HTTP error occurred: 404 Client Error: NOT FOUND for url: https://httpbin.org/status/404
```

A `404` costs exactly one round trip. Only connection failures and the
transient statuses `408, 425, 429, 500, 502, 503, 504` are retried — retrying a
`404` would only multiply the latency of an answer that will not change.

## Step 9 — Use it from Python

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
what makes the pooling pay off — the second request to a host skips the TCP and
TLS handshake entirely.

## Where to go next

- [Using Snaffle as a library](guides/using-as-a-library.md) — patterns beyond
  the basics: batching, error handling, custom bodies.
- [Downloading large files](guides/downloading-large-files.md) — progress bars
  and streaming.
- [CLI reference](reference/cli.md) — every flag.
- [Python API reference](reference/python-api.md) — every argument, constant,
  and exception.
- [Troubleshooting](guides/troubleshooting.md) — when something goes wrong.
