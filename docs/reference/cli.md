# CLI reference

How `snaffle` behaves beyond what its help text says. The help text is the
reference for commands and flags, because it is generated from the code:

```bash
snaffle --help          # every command
snaffle GET --help      # the flags and defaults of one command
snaffle HELP            # the top-level help and worked examples
```

The examples on this page are run by `tests/test_docs.py`, so they show what
the program does.

## Invocation

Three entry points run the same code:

```bash
snaffle GET https://httpbin.org/get       # console script
python -m snaffle GET https://httpbin.org/get
uv run snaffle GET https://httpbin.org/get  # inside the uv-managed environment
```

The console script points at `snaffle.__main__:run`, not `cli:main`, so all
three handle `Ctrl+C` identically. They print `Operation cancelled by user` and
exit `0` rather than raising a traceback.

## Commands

A command is spelled in upper case or in lower case. Other spellings are
rejected:

```console
$ snaffle get http://127.0.0.1:9/ -t 0
Error: timeout must be greater than 0
$ echo $?
1
$ snaffle Get http://127.0.0.1:9/
usage: snaffle [-h]
...
snaffle: error: argument command: invalid choice: 'Get' ...
$ echo $?
2
```

Running `snaffle` with no command, `snaffle HELP`, or `snaffle help` prints the
top-level help followed by the numbered examples. None of these paths import
`requests`. See [ADR 0002](../architecture/decisions/0002-lazy-imports-on-the-cli-help-path.md).

## Options

### `-d`, `--data`

A JSON document sent as the request body. The string is parsed with
`json.loads` and handed to `requests` as `json=`, so the `Content-Type:
application/json` header is set automatically; passing it explicitly with `-H`
is harmless but redundant.

```console
$ snaffle POST http://127.0.0.1:9/ -d '{bad'
Error: Invalid JSON data
...
$ echo $?
1
```

There is no flag for a non-JSON body. Sending form data or raw bytes requires
the [Python API](python-api.md).

### `-H`, `--header`

Repeat it to send several headers. A value without a `:` is refused:

```console
$ snaffle GET http://127.0.0.1:9/ -H nocolon
Error: Invalid header format. Use 'Key: Value'.
$ echo $?
1
```

### `--progress`

Draw a `tqdm` progress bar while the body downloads, once the response's
`Content-Length` reaches `HTTPClient.MIN_SIZE_FOR_PROGRESS`; below that the
download proceeds silently. `tqdm` writes to stderr, so piping stdout is
unaffected.

Passing `--progress` switches the request to streaming mode. Without it, `GET`
does not stream. See [ADR 0001](../architecture/decisions/0001-selective-retries-and-connection-pooling.md).

Only the commands whose help lists `--progress` accept it:

```console
$ snaffle POST http://127.0.0.1:9/ --progress
usage: snaffle [-h]
...
snaffle: error: unrecognized arguments: --progress
$ echo $?
2
```

## Output format

A successful request writes the status line, every response header, and the
body. A JSON body is pretty-printed; other bodies are printed verbatim. So is
JSON whose indentation alone would be many times the size of the body, because
every line starts with four spaces per level of depth and a deeply nested body
can need thousands of times its own size to print. Ordinary JSON never gets near
that. An empty or whitespace-only body omits the `Response Body:` section. The
whole response is assembled in memory and written to stdout in one call.

A character that the encoding of stdout cannot represent, such as `→` when
output is redirected on a system whose encoding is cp1252 or ASCII, is written
as a backslash escape (`→`) instead of failing the whole response, unless
you chose another handler, such as `PYTHONIOENCODING=ascii:replace`, which is
kept. On a terminal, control characters in text the server chose are escaped
too; see the [security notes](#security-notes).

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
| `0` | The request succeeded, help was printed, or the user pressed `Ctrl+C`. |
| `1` | The input or the request failed: Snaffle prints `Error: ...` and why. |
| `2` | argparse rejected the command line and printed the usage. |

The examples above show each code. A non-2xx status is an error:
`raise_for_status()` runs before the response is printed, so the CLI exits `1`
with `Error: HTTP error occurred: ...` rather than rendering the body. A
response that cannot be printed because the reader closed the pipe early also
exits `1`, and prints nothing to stderr.

`snaffle.cli.main` returns `0` and `1`, which is where the mapping is decided;
`snaffle.__main__.run` passes that return value to `sys.exit`. The closed pipe
is the one `1` that `run` decides itself, by catching `BrokenPipeError`. `2`
never passes through `main`, because argparse exits from inside `parse_args`.

## Security notes

Snaffle is a thin layer over `requests`, so it inherits `requests` defaults.
Some of them surprise people who put credentials on the command line.

- **Environment and `~/.netrc`.** `requests` reads `HTTP_PROXY`, `HTTPS_PROXY`,
  `NO_PROXY`, `REQUESTS_CA_BUNDLE` and `CURL_CA_BUNDLE` from the environment,
  and credentials from `~/.netrc`. A `~/.netrc` entry for the host replaces an
  `Authorization` header passed with `-H`, without a message, so the request is
  made as the `.netrc` identity.
- **Redirects.** Redirects are followed, to any `http` or `https` address,
  including internal ones. When a redirect leaves the origin, `requests` drops
  the `Authorization` header but forwards every other `-H` header, such as
  `X-Api-Key`, to the new origin. A `Cookie` header passed with `-H` is dropped
  on any redirect.
- **Terminal output.** A server chooses its headers, a plain-text body and the
  reason phrase in an error message, and an escape sequence in them can retitle
  your terminal window, clear or rewrite the screen, or write to the clipboard.
  When stdout is a terminal, control characters in them (C0 and C1 controls and
  DEL, and a carriage return that does not start a CRLF) are shown as `\xNN`
  instead of being obeyed; tab, newline and CRLF are kept. This applies to the
  response, to the `Error:` line and to the exception lines of `-v`. When stdout
  is not a terminal, a pipe or a file, nothing is escaped and the output is what
  it always was. That is the response as decoded and written in the encoding of
  stdout, not the server's own bytes: a body that is JSON is re-serialized, which
  already escapes control characters, and a Latin-1 body is written as UTF-8.
- **Response size.** Nothing limits how large a response can be, and a small
  compressed one can decode to hundreds of megabytes. A server you do not trust
  can use that to exhaust your memory. There is no option for it on the command
  line; the Python API can cap what it reads, see
  [Limit how much you read](../guides/downloading-large-files.md#limit-how-much-you-read).
- **Secrets on the command line.** Values passed with `-H` and `-d` are visible
  in your shell history and, while the command runs, in the process list.
- **Verbose output.** `-v` prints the request's headers and JSON body and the
  response's headers to stdout, prefixed `[VERBOSE]`. The values of the
  `Authorization`, `Proxy-Authorization` and `Cookie` request headers are
  replaced by `<redacted>` (and so are the `auth`, `cookies` and `proxies`
  arguments of the Python API), but nothing else is: the JSON body, `data`,
  `params`, other headers, `X-Api-Key` among them, the URL and the response's
  headers, `Set-Cookie` included, are shown as they are. Because it shares
  stdout with the response, `snaffle GET URL -v > file` writes them to the file.
  Edit the output before pasting it into an issue or a log.
  `HTTPClient(verbose=True)` behaves the same way.

## What the CLI does not expose

These are available only through the [Python API](python-api.md):

- `retries`. The CLI always uses the client's default.
- Non-JSON request bodies (`data=`, `files=`).
- Query parameters as a mapping (`params=`). Put them in the URL instead.
- Response objects. The CLI prints and discards.
