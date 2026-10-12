#!/usr/bin/env bash
# Drive Snaffle the way a contributor and a CLI user do, and keep the evidence.
# Usage: verify.sh <doctor|test|cli|cleanup|all>
set -uo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
RUN_ID="${VERIFY_RUN:-$(date +%Y%m%d-%H%M%S)}"
ART="${VERIFY_ARTIFACTS:-/tmp/snaffle-verify/$RUN_ID}"
mkdir -p "$ART"
cd "$ROOT" || exit 1

# run <name> <cmd...>: records command, stdout, stderr and exit code under $ART/<name>.*
run() {
  local name="$1"; shift
  printf '%q ' "$@" > "$ART/$name.cmd"; echo >> "$ART/$name.cmd"
  "$@" > "$ART/$name.stdout" 2> "$ART/$name.stderr"
  local rc=$?
  echo "$rc" > "$ART/$name.exit"
  echo "[$name] exit=$rc  ($ART/$name.*)"
  return "$rc"
}

expect() {
  local desc="$1" file="$2" pattern="$3"
  if grep -E -- "$pattern" "$file" >/dev/null; then echo "  PASS $desc"; else echo "  FAIL $desc (no /$pattern/ in $file)"; FAILED=1; fi
}

# gate <name> <cmd...>: one pre-PR gate step that must exit 0
gate() {
  local name="$1"; shift
  if run "$name" "$@"; then echo "  PASS $name"; else echo "  FAIL $name (see $ART/$name.stdout/.stderr)"; FAILED=1; fi
}

FAILED=0
SKIPPED=0

doctor_common() {
  echo "artifacts: $ART"
  echo "repo: $ROOT @ $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
  command -v uv >/dev/null || { echo "  FAIL uv not on PATH (https://docs.astral.sh/uv/)"; return 1; }
  echo "  PASS uv $(uv --version | cut -d' ' -f2)"
}

result() {
  if [ "$FAILED" != 0 ]; then echo "RESULT: FAIL ($1)"; elif [ "$SKIPPED" != 0 ]; then echo "RESULT: PASS with SKIP ($1): skipped features are unverified"; else echo "RESULT: PASS ($1)"; fi
  exit "$FAILED"
}

doctor() {
  doctor_common || return 1
  run sync uv sync --locked --group dev --extra speedups || { echo "  FAIL uv sync --locked (stale uv.lock?)"; return 1; }
  echo "  PASS synced as CI does (dev group, speedups extra)"
  local pv; pv="$(uv run --no-sync python -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  if uv run --no-sync python -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then echo "  PASS python $pv >= 3.10"; else echo "  FAIL python $pv < 3.10"; return 1; fi
}

# CI's test job in order, then the wheel's py.typed check.
test_gate() {
  gate lint uv run --no-sync ruff check .
  gate format uv run --no-sync ruff format --check .
  gate ty uv run --no-sync ty check
  gate unittest uv run --no-sync python -X dev -W error -m unittest discover tests
  expect "unittest reports OK" "$ART/unittest.stderr" '^OK'
  grep -E '^Ran [0-9]+ tests' "$ART/unittest.stderr" | sed 's/^/  /'
  if grep -E 'ResourceWarning' "$ART/unittest.stderr" >/dev/null; then echo "  FAIL unclosed-resource warning in test output"; FAILED=1; fi
  rm -rf "$ART/dist"
  gate build uv build --out-dir "$ART/dist"
  if unzip -l "$ART"/dist/*.whl 2>/dev/null | grep -E 'snaffle/py\.typed$' >/dev/null; then echo "  PASS wheel ships snaffle/py.typed"; else echo "  FAIL wheel lacks snaffle/py.typed"; FAILED=1; fi
}

# The real user path: `snaffle <METHOD> <url>` against a local server this run starts.
cli() {
  run cli-help uv run --no-sync snaffle --help
  expect "--help exits 0" "$ART/cli-help.exit" '^0$'
  expect "--help lists GET" "$ART/cli-help.stdout" 'GET \(get\) +Make a GET request'

  local www="$ART/www" port
  mkdir -p "$www"; echo "hello-from-verify-$RUN_ID" > "$www/hello.txt"
  port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  (cd "$www" && exec python3 -m http.server "$port" --bind 127.0.0.1 > "$ART/server.log" 2>&1) &
  echo $! > "$ART/server.pid"
  for _ in $(seq 50); do curl -s "http://127.0.0.1:$port/" >/dev/null && break; sleep 0.1; done

  run cli-get uv run --no-sync snaffle GET "http://127.0.0.1:$port/hello.txt"
  expect "GET exits 0" "$ART/cli-get.exit" '^0$'
  expect "GET prints Status Code: 200" "$ART/cli-get.stdout" '^Status Code: 200$'
  expect "GET prints the served body" "$ART/cli-get.stdout" "^hello-from-verify-$RUN_ID$"
  run cli-404 uv run --no-sync snaffle GET "http://127.0.0.1:$port/missing"
  expect "404 exits 1" "$ART/cli-404.exit" '^1$'
  expect "404 error printed (stdout)" "$ART/cli-404.stdout" '^Error: HTTP error occurred: 404'
  expect "server saw the GET requests" "$ART/server.log" '"GET /hello.txt HTTP/1.1" 200'
  stop_server
}

stop_server() {
  # Kill only the PID this run recorded; never by name.
  if [ -f "$ART/server.pid" ]; then kill "$(cat "$ART/server.pid")" 2>/dev/null; rm -f "$ART/server.pid"; fi
}

cleanup() {
  stop_server
  echo "cleanup done; evidence kept in $ART"
}

case "${1:-}" in
  doctor) doctor || FAILED=1 ;;
  test) test_gate ;;
  cli) cli ;;
  cleanup) cleanup ;;
  all) if doctor; then test_gate; cli; else FAILED=1; echo "  doctor failed: not driving this checkout"; fi; cleanup ;;
  *) sed -n '2,3p' "$0"; exit 2 ;;
esac
result "$1"
