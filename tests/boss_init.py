"""The `system/init` line of a boss or role call that started isolated, for fake executables.

Recorded from a real no-tool call (CLI 2.1.285, the exact `build_boss_command` argv, Haiku):
it lists only `StructuredOutput`, no MCP servers, mode `dontAsk`. The installed plugins, skills,
commands and agents are blanked in the fixture (personal setup; the isolation check reads none of
them), and the paths are placeholders.
"""

import json
from pathlib import Path

_RECORDED = Path(__file__).parent / "fixtures" / "stream_boss_no_tools_2.1.285.jsonl"
BOSS_INIT = next(
    json.loads(line) for line in _RECORDED.read_text().splitlines() if '"subtype": "init"' in line
)
BOSS_INIT_LINE = json.dumps(BOSS_INIT)
