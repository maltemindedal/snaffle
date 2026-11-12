#!/usr/bin/env bash
# Fail when src/snaffle/ changed but CHANGELOG.md's [Unreleased] section did not.
# Usage: changelog.sh [BASE [HEAD]]
# BASE defaults to the merge-base of HEAD with origin/main, HEAD to HEAD.
# A change no user can notice says so in a commit trailer between BASE and HEAD:
#   Changelog: none (<reason>)
set -uo pipefail

cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)" || exit 1
head="${2:-HEAD}"
base="${1:-$(git merge-base origin/main "$head")}" || {
  echo "changelog: no merge-base with origin/main; fetch it or pass BASE"; exit 1; }

if git diff --quiet "$base" "$head" -- src/snaffle/; then
  echo "changelog: OK (src/snaffle/ unchanged since $(git rev-parse --short "$base"))"; exit 0
fi

unreleased() {
  git show "$1:CHANGELOG.md" 2>/dev/null | awk '/^## \[/{n++} n==1 && /^## \[Unreleased\]/{p=1} n>1{p=0} p'
}
if [ "$(unreleased "$base")" != "$(unreleased "$head")" ]; then
  echo "changelog: OK ([Unreleased] updated)"; exit 0
fi

reason="$(git log --format='%(trailers:key=Changelog,valueonly)' "$base..$head" | grep -E '^none \(.+\)$' | head -1)"
if [ -n "$reason" ]; then
  echo "changelog: OK (trailer: Changelog: $reason)"; exit 0
fi

echo "changelog: FAIL. src/snaffle/ changed since $(git rev-parse --short "$base"), but CHANGELOG.md [Unreleased] did not:"
git diff --stat "$base" "$head" -- src/snaffle/ | sed 's/^/  /'
echo "Add a paragraph under ## [Unreleased] (AGENTS.md, CHANGELOG), or, if no user"
echo "can notice the change, end a commit message with: Changelog: none (<reason>)"
exit 1
