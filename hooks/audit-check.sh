#!/bin/sh
# Stop: in a git repo that a sealed `antstreet audit` run covers, check the commit at HEAD against
# the sealed checks (`antstreet audit --stop-hook`, claim: done, no model call). Only HEAD is
# checked: uncommitted changes are not, and the notice says so. Silent, and runs nothing, when the
# audit store has no run; silent when no run covers HEAD, HEAD is still the base, or this commit
# was already checked.
#
# By default the verdict goes to the human only (`systemMessage`) and the agent stops as usual. The
# plugin option `audit_on_refuted` = `block` instead keeps the agent working on a refuted verdict,
# telling it only how many sealed checks failed, never which or what they test; Claude Code then
# runs this again with `stop_hook_active`, and that time it only notifies. Any error, a missing
# `uvx` or a timeout fails open: the agent stops, and at most a generic notice reaches the human.
store="${BOSS_AUDIT_HOME:-$HOME/.boss-audit}"
[ -n "$(ls -A "$store/.boss/runs" 2>/dev/null)" ] || exit 0
command -v uvx >/dev/null 2>&1 || exit 0 # the SessionStart hook already said how to get uv
mode=notify
[ "${CLAUDE_PLUGIN_OPTION_AUDIT_ON_REFUTED:-}" = block ] && mode=block
# The hook input is JSON on stdin; jq is not on every machine, so match the one field we need with
# all whitespace removed (any valid layout). A false match only downgrades to notify, never blocks.
input=$(cat)
squeezed=
set -f # split on whitespace only; no globbing of the JSON's words
old_ifs=$IFS
IFS=$(printf ' \t\r\n_')
IFS=${IFS%_}
for word in $input; do squeezed=$squeezed$word; done
IFS=$old_ifs
set +f
case $squeezed in
*'"stop_hook_active":true'*) mode=notify ;;
esac
if out=$(uvx antstreet audit --repo "${CLAUDE_PROJECT_DIR:-.}" --stop-hook "$mode" 2>/dev/null); then
    [ -n "$out" ] && printf '%s\n' "$out"
else
    printf '%s\n' '{"systemMessage":"AntStreet: the audit of HEAD did not complete. Run `antstreet audit` in the repo to see why."}'
fi
exit 0
