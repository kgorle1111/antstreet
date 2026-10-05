#!/bin/sh
# Stop: in a project with AntStreet runs, read the latest run with `antstreet status`, which checks
# its ledger's hash chain and the investor's signatures and makes no model call. It never blocks the
# agent from stopping (exit 2 would hand the failure to the agent being checked); a failure is a
# non-blocking hook error the user sees. Silent in every project without `.boss/runs/`.
project="${CLAUDE_PROJECT_DIR:-.}"
[ -n "$(ls -A "$project/.boss/runs" 2>/dev/null)" ] || exit 0
command -v uvx >/dev/null 2>&1 || exit 0 # the SessionStart hook already said how to get uv
out=$(uvx antstreet status --dir "$project" 2>&1) && exit 0
printf 'AntStreet: the latest run did not verify (uvx antstreet status):\n%s\n' "$out" >&2
exit 1
