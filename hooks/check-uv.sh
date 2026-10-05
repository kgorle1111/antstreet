#!/bin/sh
# SessionStart: when uvx is missing, say the one command that installs uv. Installs nothing itself.
command -v uvx >/dev/null 2>&1 && exit 0
fix='curl -LsSf https://astral.sh/uv/install.sh | sh'
printf '{"systemMessage":"AntStreet needs uv, and uvx is not on PATH. Install it with: %s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"uvx is not on PATH, so the AntStreet commands cannot run until the user installs uv with: %s (tell the user; do not run it)."}}\n' "$fix" "$fix"
