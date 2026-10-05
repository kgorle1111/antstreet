#!/usr/bin/env bash
# Plug-and-play acceptance test: from an empty folder to a first real verdict with two typed
# commands (fund, then the approval) and no file edits. Runs ONE paid funding round.
#
# Not measured: the PyPI download. The package comes from a wheel built here, so the install
# step is a local-wheel install, not a network one. Needs: uv, a logged-in `claude`.
#
# usage: scripts/plug_and_play.sh [IDEA] [BUDGET]
set -euo pipefail

IDEA=${1:-"a Python function slugify(text) that lowercases text and joins its words with hyphens"}
BUDGET=${2:-0.40}
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
WORK=$(mktemp -d)
WHEELS="$WORK/wheels"
PROJECT="$WORK/fresh-project"
mkdir -p "$WHEELS" "$PROJECT"

names=() secs=() codes=()
total_start=$(date +%s)

# step NAME CMD...: run in the fresh project, echo its full output, record seconds and exit code.
step() {
  local name=$1; shift
  echo; echo "=== $name: $*"
  local start rc=0
  start=$(date +%s)
  "$@" || rc=$?
  names+=("$name"); secs+=($(( $(date +%s) - start ))); codes+=("$rc")
}

ant() { (cd "$PROJECT" && uvx --from "$WHEELS"/antstreet-*.whl antstreet "$@"); }

fund() { echo a | ant fund "$IDEA" --budget "$BUDGET"; }

step build uv build --wheel --out-dir "$WHEELS" "$REPO"
step doctor ant doctor
# The approval prompt reads a line from stdin; "a" (approve) is the investor's one answer;
# "y" is NOT accepted at this prompt and counts as reject.
step fund fund
step report ant report
step status ant status

total=$(( $(date +%s) - total_start ))
files=$(cd "$PROJECT" && find . -type f -not -path './.boss/*' | sort | tr '\n' ' ')
report=$(cd "$PROJECT" && uvx --from "$WHEELS"/antstreet-*.whl antstreet report 2>&1 || true)
verdict=$(sed -n 's/^ *Delivered: //p' <<<"$report" | head -1)
cost=$(sed -n 's/^ *Cost: //p' <<<"$report" | head -1)

echo; echo "=== SUMMARY (PyPI download NOT measured; wheel built locally)"
printf '%-8s %6s  %s\n' step secs exit
for i in "${!names[@]}"; do printf '%-8s %6s  %s\n' "${names[$i]}" "${secs[$i]}" "${codes[$i]}"; done
printf '%-22s %s\n' "total seconds" "$total"
printf '%-22s %s\n' "commands typed" "2 (fund, approve)"
printf '%-22s %s\n' "file edits needed" "0 (script edits nothing)"
printf '%-22s %s\n' "files outside .boss/" "${files:-none}"
printf '%-22s %s\n' "verdict (Delivered)" "${verdict:-unknown}"
printf '%-22s %s\n' "spent (Cost)" "${cost:-unknown}"
printf '%-22s %s\n' "project dir" "$PROJECT"
