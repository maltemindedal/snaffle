# Snaffle

A command-line HTTP client, and the Python library behind it.

> **snaffle** _(verb, informal, British)_ — to take something for oneself,
> typically quickly or without permission.
>
> _"Snaffle it off the server."_

Snaffle makes one-off HTTP requests from a terminal readable: send a request,
get the status, headers, and a pretty-printed body. The same client is
importable, so a script that outgrows the command line does not have to change
tools. It supports GET, POST, PUT, PATCH, DELETE, HEAD, and OPTIONS, pools
connections across requests, and retries only the failures that are worth
retrying.

```bash
snaffle GET https://httpbin.org/get
```

## Quick start

Requires **Python 3.10+** and **[uv](https://docs.astral.sh/uv/)**. Snaffle is
not on PyPI; install it from a clone.

```bash
git clone https://github.com/maltemindedal/snaffle.git
cd snaffle
uv sync --group dev
uv run snaffle HELP
```

That last command prints the usage line, the seven method commands, and eleven
worked examples. If you see it, Snaffle works.

Then make a request:

```bash
uv run snaffle GET https://httpbin.org/get
```

```
Status Code: 200

Headers:
content-type: application/json
content-length: 292

Response Body:
{
    "args": {},
    "url": "https://httpbin.org/get"
}
```

Full walkthrough: [Getting started](docs/getting-started.md).

## Usage

Commands are case-insensitive. `-H` repeats for multiple headers; `-d` takes a
JSON body and sets `Content-Type` for you.

```bash
snaffle POST https://httpbin.org/post \
  -d '{"key": "value"}' \
  -H "Authorization: Bearer token123" \
  -v
```

The same request from Python:

```python
from snaffle import HTTPClient

with HTTPClient(timeout=10) as client:
    response = client.post(
        "https://httpbin.org/post",
        json={"key": "value"},
        headers={"Authorization": "Bearer token123"},
    )
    print(response.json())
```

`response` is a `requests.Response`. Use the client as a context manager — it
owns a connection pool, and every request after the first to a given host
reuses the open connection.

## Documentation

| | |
| --- | --- |
| [Getting started](docs/getting-started.md) | Clone to first request, in about ten minutes. |
| [Use as a library](docs/guides/using-as-a-library.md) | Batching, error handling, custom bodies, tuning. |
| [Download large files](docs/guides/downloading-large-files.md) | Progress bars and streaming. |
| [Troubleshooting](docs/guides/troubleshooting.md) | Symptom-first fixes. |
| [CLI reference](docs/reference/cli.md) | Every command, flag, and exit code. |
| [Python API reference](docs/reference/python-api.md) | `HTTPClient`, constants, exceptions. |
| [Architecture](docs/architecture/overview.md) | How it fits together, and why. |

The full index is [docs/README.md](docs/README.md).

## Project structure

```
src/snaffle/   The package (import name: snaffle). src-layout, so tests
               exercise the installed distribution.
tests/         One unittest module per source module.
docs/          All documentation. Start at docs/README.md.
.github/       CI: lint, format, mypy, tests on Python 3.10-3.14, wheel build.
.agents/       Skill definitions for LLM coding assistants.
```

The package is fully typed and ships a PEP 561 `py.typed` marker, so downstream
type checkers use its annotations without extra configuration.

## Contributing

Setup, conventions, and the four checks CI runs are in
[CONTRIBUTING.md](CONTRIBUTING.md). Changes are recorded in
[CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE).
