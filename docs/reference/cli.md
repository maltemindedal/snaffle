# CLI reference

Every command, alias, and flag accepted by `snaffle`. Help text below is
reproduced from the program's own `--help` output, as rendered by the `argparse`
in Python 3.13 and later. On 3.10 through 3.12 — both supported — argparse
repeats the metavar after each short option, so `-t, --timeout TIMEOUT` appears
as `-t TIMEOUT, --timeout TIMEOUT`. Nothing else differs.

## Invocation

Three entry points run the same code:

```bash
snaffle GET https://httpbin.org/get       # console script
python -m snaffle GET https://httpbin.org/get
uv run snaffle GET https://httpbin.org/get  # inside the uv-managed environment
```

The console script points at `snaffle.__main__:run`, not `cli:main`, so all
three handle `Ctrl+C` identically — printing `Operation cancelled by user` and
exiting `0` rather than raising a traceback.

## Commands

```
usage: snaffle [-h]
               {HELP,help,GET,get,POST,post,PUT,put,PATCH,patch,DELETE,delete,HEAD,head,OPTIONS,options} ...
```

| Command | Aliases | Body flag (`-d`) | `--progress` |
| --- | --- | --- | --- |
| `GET` | `get` | no | yes |
| `POST` | `post` | yes | no |
| `PUT` | `put` | yes | no |
| `PATCH` | `patch` | yes | no |
| `DELETE` | `delete` | no | no |
| `HEAD` | `head` | no | no |
| `OPTIONS` | `options` | no | no |
| `HELP` | `help` | — | — |

Every command has a lowercase alias. `snaffle get` and `snaffle GET` are
equivalent.

Running `snaffle` with no command, `snaffle HELP`, or `snaffle help` prints the
top-level help followed by the numbered examples. None of these paths import
`requests` — see [ADR 0002](../architecture/decisions/0002-lazy-imports-on-the-cli-help-path.md).

## Options

### Common to every request command

Applied by `add_common_arguments` to all seven method subcommands.

| Flag | Type | Default | Effect |
| --- | --- | --- | --- |
| `url` (positional) | string | required | Target URL. |
| `-t`, `--timeout` | int | `30` | Request timeout in seconds. Passed to `requests` as the `timeout` argument. |
| `-H`, `--header` | string | none | HTTP header in `Key: Value` format. Repeatable; each occurrence adds one header. A value without a `:` exits `1` with `Error: Invalid header format. Use 'Key: Value'.` |
| `-v`, `--verbose` | flag | off | Log the outgoing request, the response status and headers, and the underlying `requests` exception behind any failure, to stdout, prefixed `[VERBOSE]`. |
| `-h`, `--help` | flag | — | Print this subcommand's help and exit. |

### `-d`, `--data` — `POST`, `PUT`, `PATCH` only

A JSON document sent as the request body. The string is parsed with
`json.loads` and handed to `requests` as `json=`, so the `Content-Type:
application/json` header is set automatically; passing it explicitly with `-H`
is harmless but redundant.

Malformed JSON exits `1` with `Error: Invalid JSON data`.

The help text shows a per-method example: `{"key": "value"}` for `POST`,
`{"name": "New Name"}` for `PUT`, `{"email": "user@example.com"}` for `PATCH`.

There is no flag for a non-JSON body. Sending form data or raw bytes requires
the [Python API](python-api.md).

### `--progress` — `GET` only

Draw a `tqdm` progress bar while the body downloads. The bar appears only when
the response's `Content-Length` header is at least 5 MiB
(`HTTPClient.MIN_SIZE_FOR_PROGRESS`); below that the download proceeds
silently. `tqdm` writes to stderr, so piping stdout is unaffected.

Passing `--progress` switches the request to streaming mode. Without it, `GET`
does not stream — see [ADR 0001](../architecture/decisions/0001-selective-retries-and-connection-pooling.md).

Passing `--progress` to any other command is an argparse error and exits `2`.

## Per-command help

### `GET`

```
usage: snaffle GET [-h] [-t TIMEOUT] [-H HEADER] [-v] [--progress] url

positional arguments:
  url                   Target URL

options:
  -h, --help            show this help message and exit
  -t, --timeout TIMEOUT
                        Request timeout in seconds (default: 30)
  -H, --header HEADER   HTTP header in 'Key: Value' format. Can be used
                        multiple times.
  -v, --verbose         Enable verbose logging for debugging.
  --progress            Show progress bar for downloads larger than 5MB
```

### `POST`, `PUT`, `PATCH`

Identical apart from the example shown in the `-d` help text.

```
usage: snaffle POST [-h] [-t TIMEOUT] [-H HEADER] [-v] [-d DATA] url

positional arguments:
  url                   Target URL

options:
  -h, --help            show this help message and exit
  -t, --timeout TIMEOUT
                        Request timeout in seconds (default: 30)
  -H, --header HEADER   HTTP header in 'Key: Value' format. Can be used
                        multiple times.
  -v, --verbose         Enable verbose logging for debugging.
  -d, --data DATA       JSON data for request body. Example: '{"key":
                        "value"}'
```

### `DELETE`, `HEAD`, `OPTIONS`

```
usage: snaffle DELETE [-h] [-t TIMEOUT] [-H HEADER] [-v] url

positional arguments:
  url                   Target URL

options:
  -h, --help            show this help message and exit
  -t, --timeout TIMEOUT
                        Request timeout in seconds (default: 30)
  -H, --header HEADER   HTTP header in 'Key: Value' format. Can be used
                        multiple times.
  -v, --verbose         Enable verbose logging for debugging.
```

## Output format

A successful request writes the status line, every response header, and the
body — pretty-printed with 4-space indentation if it parses as JSON, verbatim
otherwise. An empty or whitespace-only body omits the `Response Body:` section
entirely. The whole response is assembled in memory and written to stdout in
one call.

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

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Request succeeded, help was printed, or the user pressed `Ctrl+C`. |
| `1` | Invalid JSON body, malformed `-H` header, or any `HTTPClientError` — connection failure, non-2xx status, or timeout. |
| `2` | argparse rejected the command line (unknown command, missing URL, `--progress` on a non-`GET`). |

A non-2xx status is an error: `raise_for_status()` runs before the response is
printed, so a `404` exits `1` and prints `Error: HTTP error occurred: ...`
rather than rendering the response body.

## What the CLI does not expose

These are available only through the [Python API](python-api.md):

- `retries` — the CLI always uses the default of 3 attempts.
- Non-JSON request bodies (`data=`, `files=`).
- Query parameters as a mapping (`params=`) — put them in the URL instead.
- Response objects. The CLI prints and discards.
