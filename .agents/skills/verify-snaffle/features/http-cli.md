# HTTP CLI

## Sub-features

- `snaffle GET <url>` prints status, headers and body; HTTP errors exit 1.
- `--help`. Not driven yet: POST, PUT, PATCH, DELETE, HEAD, OPTIONS, `-H`, `-d`, `--progress`, retries.

## How to get to it (user POV)

`uv run snaffle GET https://example.com`.

## Driving it with verify.sh

`verify.sh cli` against a local `http.server`. End state: the GET prints
`Status Code: 200` and the served body, the server log shows the request, and
`/missing` exits 1 with the 404 error.

## Gotchas

- Error messages go to stdout, not stderr.
- The server is plain HTTP on 127.0.0.1; TLS, redirects and hostile-server escaping are covered by unit tests only.
