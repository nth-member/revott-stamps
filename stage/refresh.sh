#!/usr/bin/env bash
# Bring the stamps up to date; with --push, publish them.
#
#   stage/refresh.sh [--push]
#
#   1  history.py     keep every JOMO SFO-WAM feed snapshot (they age out of its reflog in 30 days)
#   2  pagetime.py    read up to 300 new article pages for the time they state
#   3  archive.py     rebuild docs/data: one instant per item, filed on Nsukka's days; coverage
#   4  standing.py    stamp the standing requests' pairs whose windows have closed and settled
#   5  commit docs/data and docs/stamps only, as one rolling commit per Nsukka day
#   6  with --push, push (forced with lease when the day's commit was replaced)
#
# A failing step prints FAIL and the rest go on; only a failed archive stops the run. Anything else
# uncommitted is reported, never swept up.
set -u
cd "$(dirname "$0")/.." || exit 1
PUSH=0; [ "${1:-}" = "--push" ] && PUSH=1
exec 9>.git/stamps-refresh.lock
flock -n 9 || { echo "stamps: another refresh is running"; exit 0; }

python3 -B stage/history.py || echo "FAIL history"
python3 -B stage/pagetime.py new --limit 300 || echo "FAIL pagetime"
python3 -B stage/archive.py || { echo "FAIL archive: nothing committed"; exit 1; }
python3 -B stage/standing.py || echo "FAIL standing"

PATHS=(docs/data docs/stamps)
git add -A -- "${PATHS[@]}"
if git diff --cached --quiet -- "${PATHS[@]}"; then echo "stamps: unchanged"; exit 0; fi
SUBJECT="Archive through $(TZ=Africa/Lagos date +%F)"
rolling=0
if [ "$(git log -1 --format=%s 2>/dev/null)" = "$SUBJECT" ] && \
   [ -z "$(git diff-tree --no-commit-id --name-only -r HEAD | grep -v -E '^docs/(data|stamps)/')" ]; then
  rolling=1
fi
if [ $rolling = 1 ]; then
  git commit -q --amend --date=now -m "$SUBJECT" -- "${PATHS[@]}" && echo "stamps: the day's commit replaced"
else
  git commit -q -m "$SUBJECT" -- "${PATHS[@]}" && echo "stamps: committed"
fi
OTHER=$(git status --porcelain | grep -v -E ' docs/(data|stamps)/')
[ -n "$OTHER" ] && printf 'stamps: other uncommitted changes, left alone:\n%s\n' "$OTHER"

if [ $PUSH = 1 ]; then
  if [ $rolling = 1 ]; then git push -q --force-with-lease origin HEAD:main; else git push -q origin HEAD:main; fi \
    && echo "stamps: pushed" || { echo "FAIL stamps: push"; exit 1; }
fi
