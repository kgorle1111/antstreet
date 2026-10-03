"""The `system/init` line of a boss or role call that started isolated, for fake executables.

The real shape is the recorded worker init (probe P4 with a schema); only `tools` differs, set to
the one tool a no-tool call should list. That list is NOT recorded from a real no-tool call yet:
the probe is named in docs/BACKLOG.md B21.
"""

import json
from pathlib import Path

_RECORDED = Path(__file__).parent / "fixtures" / "stream_structured_status_blocked_2.1.285.jsonl"
BOSS_INIT = next(
    json.loads(line) | {"tools": ["StructuredOutput"]}
    for line in _RECORDED.read_text().splitlines()
    if '"subtype": "init"' in line
)
BOSS_INIT_LINE = json.dumps(BOSS_INIT)
