#!/usr/bin/env bash
# Replays today's guard tests against an older commit.
#
# Usage: replay.sh <sha> [guard-module ...]
#
# Checks <sha> out into a temporary detached worktree, copies in every
# tests/test_guard_*.py and tests/_isolation.py from the current tree, runs each
# guard there against that commit's own src/, and prints one line per guard:
# PASS or FAIL. A guard that FAILs on a commit that held a past mistake is proof
# the guard would have caught it. Pass module names (for example
# test_guard_prose) to run only those. The exit status is 0 whenever the replay
# itself ran, because a failing guard is the expected result on a bad commit.
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: replay.sh <sha> [guard-module ...]" >&2
    exit 2
fi
sha=$1
shift

root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
python="$root/.venv/bin/python"
if [ ! -x "$python" ]; then
    echo "replay.sh: $python missing; run uv sync --locked --group dev --extra speedups" >&2
    exit 2
fi

scratch=$(mktemp -d)
wt="$scratch/wt"
cleanup() {
    git -C "$root" worktree remove --force "$wt" >/dev/null 2>&1 || true
    rm -rf "$scratch"
    git -C "$root" worktree prune
}
trap cleanup EXIT

git -C "$root" worktree add --detach "$wt" "$sha" >/dev/null 2>&1
mkdir -p "$wt/tests"
cp "$root"/tests/test_guard_*.py "$wt/tests/"
[ -f "$root/tests/_isolation.py" ] && cp "$root/tests/_isolation.py" "$wt/tests/"

if [ $# -gt 0 ]; then
    guards=("$@")
else
    guards=()
    for f in "$root"/tests/test_guard_*.py; do
        guards+=("$(basename "$f" .py)")
    done
fi

echo "replaying $(git -C "$wt" log -1 --format='%h %s' "$sha")"
failed=0
for guard in "${guards[@]}"; do
    log="$scratch/$guard.log"
    if (cd "$wt" && PYTHONPATH="$wt/src" "$python" -X dev -W error \
        -m unittest "tests.$guard") >"$log" 2>&1; then
        echo "PASS $guard"
    else
        failed=$((failed + 1))
        echo "FAIL $guard"
        grep -E '^(FAIL|ERROR):|^[^ ]+:[0-9]+(: |$)|AssertionError: [^L]' "$log" | head -8 | sed 's/^/    /'
    fi
done
echo "replay of $sha: $failed guard(s) failed of ${#guards[@]}"
