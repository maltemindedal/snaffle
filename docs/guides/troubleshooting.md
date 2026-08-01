# Troubleshooting

Symptoms and their causes, in rough order of how often they come up.

## `snaffle: command not found`

The console script is installed into the project environment, not onto your
`PATH`. Either run it through uv:

```bash
uv run snaffle HELP
```

or activate the environment first:

```bash
source .venv/bin/activate      # macOS, Linux
.venv\Scripts\Activate.ps1     # Windows PowerShell
snaffle HELP
```

If `uv run snaffle` also fails, the environment was never created. Run
`uv sync --group dev` from the repository root.

## `ModuleNotFoundError: No module named 'snaffle'`

Almost always a stale or missing environment. Re-sync:

```bash
uv sync --group dev
```

If it persists, check you are in the right interpreter — `uv run python -c
"import snaffle; print(snaffle.__file__)"` should print a path under
`src/snaffle/`.

Note the package is named `snaffle`, all lowercase. `import Snaffle` and
`import PyFetch` are both wrong: the project was renamed in 3.0.0 and the
import package was lowercased in 2.0.0. See the [changelog](../../CHANGELOG.md).

If a stale `PyFetch.egg-info/` or `Snaffle.egg-info/` directory is lying around
from an older build, delete it — `mypy` in particular can trip over a duplicate
package definition.

## `Error: Invalid JSON data`

`-d` takes a JSON document, parsed with `json.loads`. The usual causes:

- **Single quotes inside the document.** JSON requires double quotes:
  `'{"key": "value"}'`, not `"{'key': 'value'}"`.
- **A bare string.** `-d hello` is not JSON. `-d '"hello"'` is.
- **The shell ate the quotes.** On Windows `cmd.exe`, single quotes are not
  quoting characters. Use PowerShell, or escape for `cmd.exe`:
  `-d "{\"key\": \"value\"}"`.

Verify the document independently before blaming Snaffle:

```bash
echo '{"key": "value"}' | uv run python -m json.tool
```

## `Error: Invalid header format. Use 'Key: Value'.`

Every `-H` value needs a colon. `-H "Authorization"` fails; `-H "Authorization:
Bearer token"` works. Whitespace around the colon is stripped, and only the
first colon splits — so `-H "Referer: https://example.com"` keeps the URL
intact.

Repeat the flag for multiple headers rather than comma-joining them:

```bash
uv run snaffle GET https://httpbin.org/headers -H "Accept: application/json" -H "X-Trace: 1"
```

## `Error: HTTP error occurred: 404 Client Error...`

Not a bug. Snaffle calls `raise_for_status()`, so any 4xx or 5xx is an error:
it exits `1` and prints the message instead of the response body.

To inspect the body of an error response, use the Python API and catch it:

```python
from snaffle import HTTPClient, ResponseError

with HTTPClient() as client:
    try:
        client.get(url)
    except ResponseError as error:
        print(error.__cause__.response.text)
```

## `Error: Failed to connect to ...`

DNS failure, a refused connection, an unreachable host, or a timeout while the
connection was still being established. Check the URL, then run with `-v` to
see exactly what was attempted and which `requests` exception was behind it.

A connection failure is retried for every method, including `POST`: a request
that never reached the server cannot have been acted on twice.

A server that kept returning a transient status until the retries ran out does
*not* land here — that ends as `Error: HTTP error occurred: 503 ...`, because
the last response is reported rather than discarded. See the
[Python API reference](../reference/python-api.md#make_request).

## A request hangs, then fails

The default timeout is 30 seconds. Lower it to fail faster:

```bash
uv run snaffle GET https://slow.example.com -t 5
```

Note that the timeout is per attempt. With the default three attempts and
exponential backoff, a request against a server that keeps failing takes
noticeably longer than the timeout alone — roughly half a second of backoff on
top. The CLI has no flag for the retry count; use the
[Python API](../reference/python-api.md) with `retries=1` if you need one shot.

## `--progress` shows no bar

Three possibilities:

1. The response is smaller than 5 MiB (`MIN_SIZE_FOR_PROGRESS`).
2. The server sent no `Content-Length` header, so the total reads as `0`.
3. stderr is redirected — `tqdm` writes there, not to stdout.

The download completes either way.

## `--progress` is rejected

```
error: unrecognized arguments: --progress
```

`--progress` exists on `GET` only. No other method accepts it.

## Retries do not happen in my test

If you mocked `requests.Session.request`, they cannot. That mock sits *above*
the adapter where urllib3's retry logic lives, so it never observes a retry —
an earlier revision of this project shipped a false claim about `POST` retry
behaviour on exactly that mistake.

Substitute the transport at the client's interface instead: pass a session,
`HTTPClient(session=...)`, with your own adapter mounted on it. The adapter and
its retry loop stay in place, so retries happen and can be counted. Failing
that, test against a real socket (`TestRetryAgainstRealServer` in
`tests/test_http_client.py`) or assert on `urllib3.util.retry.Retry` directly.
See the [contributing notes](../../CONTRIBUTING.md#testing-notes) and
[Passing a session](../reference/python-api.md#passing-a-session).

## `mypy` fails with "Duplicate module named 'snaffle'"

A `build/` or `dist/` directory contains a copy of the package. Those are
excluded in `pyproject.toml`, so this means an artifact elsewhere — most likely
a stale `*.egg-info/`. Delete it and re-run.
