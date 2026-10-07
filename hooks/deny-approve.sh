#!/bin/sh
# PreToolUse (Bash, Monitor, PowerShell): deny any call that runs `antstreet approve` / `boss
# approve`, in any wrapper (uvx, uv run, python -m boss.cli, env prefixes, `;` `&&` `|` `$(...)`,
# quotes, backslashes). Approving the term sheet is the investor's act; the agent being checked
# must not do it. The user's own `!` commands skip PreToolUse, which is how the human approves.
#
# It reads the whole hook input instead of parsing out tool_input.command: jq is not on every
# machine and python3 on macOS can be an install stub, and a hook that cannot run fails open. The
# whole input is a superset of the command, so this only errs toward denying.
# ponytail: a tripwire, not a sandbox: `X=appr; antstreet ${X}ove`, xargs or a script file get past
# it, and nothing here stops a process outside Claude Code. The `--sheet` value binds what is
# approved; who approves is the human's discipline.
LC_ALL=C awk '
{ text = text " " $0 }
END {
    gsub(/\\[nrt]/, " ", text)             # JSON escapes for newline, CR, tab: command separators
    text = tolower(text)
    gsub(/[\\"\047`]/, "", text)           # quotes and backslashes join words in the shell
    gsub(/[^a-z0-9._\/@=+~-]/, " ", text)  # everything else separates words: ; & | ( ) $ { } , :
    n = split(text, word, " ")
    for (i = 1; i <= n; i++) {
        w = word[i]
        sub(/(@|==|~=|>=).*$/, "", w)       # antstreet@latest, antstreet==0.1
        # a bare name, an installed script or the module; not any path ending in boss (the cwd)
        if (w ~ /^(antstreet|boss|boss\.cli)$/ || w ~ /(bin\/(antstreet|boss)|boss\/cli\.py)$/)
            program = 1
        else if (program && word[i] == "approve")
            exit 1
    }
}' && exit 0

reason="Approving an AntStreet term sheet is the investor's own act, so this agent may not run \`approve\` in any form. Show the user the term sheet and checks that \`fund\` printed, and ask them to type this themselves at the Claude Code prompt (the ! runs it as the user, outside the agent): ! uvx antstreet approve RUN --sheet VALUE, with the run id and value fund printed. Once they have approved, you may run \`uvx antstreet resume RUN\`."
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
printf '%s\n' "$reason" >&2
exit 2 # blocks even where an allow rule or bypass mode would let the call run
