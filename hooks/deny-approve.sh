#!/bin/sh
# PreToolUse (Bash, Monitor, PowerShell, Read, Grep, Glob): deny the agent the human's acts and the
# audit store. For the commands, any call that runs `antstreet approve` / `boss approve`, or
# `antstreet audit` in any form (plan, check, report, or no step), in any wrapper (uvx, uv run,
# python -m antstreet.cli or boss.cli, env prefixes, `;` `&&` `|` `$(...)`, quotes, backslashes).
# Approving a term sheet, ruling on a dispute and sealing or reading an audit are the human's acts;
# an audit's output names failing checks, which the agent being audited must never see. For every
# tool, any input that names the audit store (`.boss-audit`, `$BOSS_AUDIT_HOME`, its value) or
# holds a path that resolves into it (a symlink, `..`). The user's own `!` commands skip
# PreToolUse, and so do the plugin's own hooks (they are not tool calls), which is how the human
# approves and audits and how the Stop hook audits HEAD.
#
# It reads the whole hook input instead of parsing out tool_input: jq is not on every machine and
# python3 on macOS can be an install stub, and a hook that cannot run fails open. The whole input
# is a superset of the command or path, so this only errs toward denying.
# ponytail: a tripwire, not a sandbox: `X=appr; antstreet ${X}ove`, a store path built at run time
# (`d=~/.boss-; cat ${d}audit/...`), xargs or a script file get past it, and nothing here stops a
# process outside Claude Code. The boundary for the store is another user or machine
# (docs/THREAT_MODEL.md T51).
input=$(cat)
store_reason="The audit store holds sealed checks that the agent being audited must never see, so this agent may not read, search or list it, name it in a command, or reach it through a link. Do not look for the checks another way: finish the change from the request and your own tests, commit, and stop (the Stop hook audits HEAD for the user). If the user wants the verdicts, ask them to type this themselves at the Claude Code prompt (the ! runs it as the user, outside the agent): ! uvx antstreet audit report"
printf '%s\n' "$input" | LC_ALL=C awk '
{ raw = raw " " $0 }
END {
    text = raw
    gsub(/\\[nrt]/, " ", text)             # JSON escapes for newline, CR, tab: command separators
    text = tolower(text)
    gsub(/[\\"\047`]/, "", text)           # quotes and backslashes join words in the shell
    # The store, by name, by variable or by its value. Any tool; `$` kept so that a bare mention of
    # the variable name (grep BOSS_AUDIT_HOME src) is not a read.
    if (index(text, ".boss-audit") || index(text, "$boss_audit_home") || index(text, "${boss_audit_home"))
        exit 4
    home = tolower(ENVIRON["BOSS_AUDIT_HOME"])
    sub(/\/+$/, "", home)
    if (home != "") {
        rest = text
        while ((at = index(rest, home)) > 0) {
            rest = substr(rest, at + length(home))
            if (rest !~ /^[a-z0-9._+@~-]/) exit 4  # the value itself, not a longer name it begins
        }
    }
    # Commands only for the tools that run one: a file read or a search of the repo can mention
    # `antstreet approve` (its docs, its tests) without running anything.
    if (raw ~ /"tool_name"[ \t\r\n]*:[ \t\r\n]*"(Read|Grep|Glob)"/) exit 0
    gsub(/[^a-z0-9._\/@=+~-]/, " ", text)  # everything else separates words: ; & | ( ) $ { } , :
    n = split(text, word, " ")
    for (i = 1; i <= n; i++) {
        w = word[i]
        sub(/(@|==|~=|>=).*$/, "", w)       # antstreet@latest, antstreet==0.1
        # a bare name, an installed script or either module name; not a path ending in boss (the cwd)
        if (w ~ /^(antstreet|boss)(\.cli)?$/ || w ~ /(bin\/(antstreet|boss)|(antstreet|boss)\/cli\.py)$/) {
            program = 1
            step = ""
        } else if (program && word[i] == "approve")
            exit 1
        else if (program && step == "" && word[i] !~ /^-/) {
            step = word[i]
            if (step == "audit") exit 3
        } else if (program && word[i] == "audit" && step !~ /^(doctor|fund|mcp|report|resume|roles|routing|status|topup|verify)$/)
            exit 3  # the step was built at run time (`antstreet $(echo audit)`)
    }
}'
case $? in
0)
    # A path that resolves into the store without naming it: a symlink, `..` from elsewhere.
    store=${BOSS_AUDIT_HOME:-$HOME/.boss-audit}
    real=$(realpath "$store" 2>/dev/null) || exit 0 # no store, nothing to read; no realpath, the names above are the guard
    cwd=$(printf '%s\n' "$input" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)
    hit=$(printf '%s\n' "$input" | sed -e 's/\\[nrt]/ /g' -e 's/[$][{]\{0,1\}HOME[}]\{0,1\}/~/g' | LC_ALL=C tr -d '"`\\'"'" |
        LC_ALL=C tr -c 'A-Za-z0-9._/@+~-' '\n' | sort -u | while IFS= read -r w; do
        case $w in
        ('') continue ;;
        ('~') p=$HOME ;;
        ('~/'*) p=$HOME/${w#'~/'} ;;
        (/*) p=$w ;;
        (*) p=${cwd:-.}/$w ;;
        esac
        [ -e "$p" ] || continue
        r=$(realpath "$p" 2>/dev/null) || continue
        case $r/ in ("$real"/*)
            echo hit
            break
            ;;
        esac
    done)
    [ -z "$hit" ] && exit 0
    reason=$store_reason
    ;;
1) reason="Approving an AntStreet term sheet is the investor's own act, so this agent may not run \`approve\` in any form. Show the user the term sheet and checks that \`fund\` printed, and ask them to type this themselves at the Claude Code prompt (the ! runs it as the user, outside the agent): ! uvx antstreet approve RUN --sheet VALUE, with the run id and value fund printed. A ruling on a disputed check is theirs too: ! uvx antstreet approve RUN --dispute CHECK --ruling drop|keep, as the run printed. Once they have approved or ruled, you may run \`uvx antstreet resume RUN\`." ;;
3) reason="Sealing and checking an AntStreet audit are the user's acts, and its output names sealed checks that the agent being audited must never see, so this agent may not run \`antstreet audit\` in any form (plan, check, report, or no step). Finish the change, commit, and stop: the Stop hook audits HEAD for the user. If the user wants to audit now, ask them to type this themselves at the Claude Code prompt (the ! runs it as the user, outside the agent): ! uvx antstreet audit" ;;
*) reason=$store_reason ;; # 4, or awk failed: deny
esac
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
printf '%s\n' "$reason" >&2
exit 2 # blocks even where an allow rule or bypass mode would let the call run
