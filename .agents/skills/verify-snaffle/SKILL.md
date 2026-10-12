---
name: verify-snaffle
description: Verify Snaffle, the `requests`-based HTTP CLI and `HTTPClient` library, by running CI's gate and driving `snaffle GET` against a local server this skill starts. Use after changing src/, tests, packaging or the lockfile, or when you need evidence that the CLI still talks HTTP correctly.
---

# verify-snaffle

Snaffle's surface is a short-lived CLI (`snaffle <METHOD> <url>`) and the
importable `HTTPClient`. There is no long-running app: launch means
`uv sync --locked --group dev --extra speedups`, and each drive is one
`snaffle` process against a `python3 -m http.server` the script starts on a free
127.0.0.1 port, so runs never touch the network or each other.

## Launch

```bash
.agents/skills/verify-snaffle/scripts/verify.sh doctor
```

Ready means the sync exited 0 and Python is at least 3.10.

## Doctor

`verify.sh doctor` checks uv, syncs `.venv` exactly as CI does and checks the
interpreter. Run it first whenever a result looks odd. `all` stops if it fails.

## Drive

```bash
.agents/skills/verify-snaffle/scripts/verify.sh test     # ruff, format, ty, unittest -X dev -W error, build + py.typed
.agents/skills/verify-snaffle/scripts/verify.sh cli      # snaffle --help, GET 200, GET 404 on a local server
.agents/skills/verify-snaffle/scripts/verify.sh all      # doctor, test, cli, cleanup
```

`cli` serves `hello.txt` (its body names the run id) and asserts that
`snaffle GET` exits 0, prints `Status Code: 200` and the exact body, and that
the server log saw the request. It also asserts that a 404 exits 1 and prints
`Error: HTTP error occurred: 404` (on stdout, not stderr).

`RESULT: PASS` means every check passed.

## Evidence

Every step leaves `<name>.cmd`, `.stdout`, `.stderr` and `.exit` under
`/tmp/snaffle-verify/<run-id>/` (override with `VERIFY_RUN` or
`VERIFY_ARTIFACTS`), plus `server.log`, the served `www/` and the built
`dist/`. Quote the `RESULT:` line and the `Ran N tests` line.

The test step also fails on any `ResourceWarning` in the unittest output,
because `-W error` does not fail the run on an unclosed socket (see `AGENTS.md`).

## Cleanup

`verify.sh cleanup` (also run by `all`, and by `cli` itself) kills only the
server PID recorded in `server.pid`. Evidence stays.

## Feature map

See [features/README.md](features/README.md).
