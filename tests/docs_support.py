"""Helpers for the tests that keep the documents true. Not a test module."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    """The body of a `## heading` section, up to the next `## ` heading."""
    match = re.search(rf"^## {re.escape(heading)}\s*$", text, re.M)
    assert match, f"no '## {heading}' heading"
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, re.M)
    return rest[: end.start()] if end else rest


def table(body: str) -> list[list[str]]:
    """Rows of the first markdown table in `body`, header and rule rows excluded."""
    rows: list[list[str]] = []
    for line in body.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue
        rows.append(cells)
    return rows[1:]


def money(micros: int) -> str:
    """Micro-dollars as the documents write them: $0.10, $0.005."""
    whole, _, frac = f"{micros / 1_000_000:.6f}".rstrip("0").partition(".")
    return f"${whole}.{frac.ljust(2, '0')}"


def code_spans(text: str) -> list[str]:
    return re.findall(r"`([^`\n]+)`", text)


# --- a fake `claude` that plays boss and worker, so the real CLI can run without a model -------

CHECK = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
DRAFT = {
    "tasks": [{"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]}],
    "checks": [{"description": "reverses a word", "task": "t1", "code": CHECK}],
}
INIT = {
    "type": "system", "subtype": "init", "tools": ["Read", "Write", "Edit", "StructuredOutput"],
    "mcp_servers": [], "permissionMode": "dontAsk", "claude_code_version": "2.1.285",
    "session_id": "s-1",
}  # fmt: skip
FAKE_CLAUDE = f"""#!{sys.executable}
import json, os, sys
argv = sys.argv[1:]
say = lambda e: print(json.dumps(e), flush=True)
usage = {{"m": {{"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 0}}}}
result = {{"type": "result", "subtype": "success", "is_error": False,
          "terminal_reason": "completed", "modelUsage": usage, "session_id": "s-1"}}
if argv[:1] == ["--version"]:
    print("2.1.285")
elif argv[:2] == ["auth", "status"]:
    print(json.dumps({{"loggedIn": True}}))
elif argv[argv.index("--output-format") + 1] == "json":
    say(result | {{"total_cost_usd": 0.004, "structured_output": {DRAFT!r}}})
else:
    say({INIT!r})
    wrong = os.path.exists(os.path.join(os.environ["HOME"], "break"))
    expr = "s" if wrong else "s[::-1]"
    open("rev.py", "w").write("def reverse(s):\\n    return " + expr + "\\n")
    say(result | {{"total_cost_usd": 0.006,
                  "structured_output": {{"status": "done", "reason": "wrote rev.py"}}}})
"""


def fake_claude(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "fake-claude"
    path.write_text(FAKE_CLAUDE)
    path.chmod(0o755)
    return path


def run_cli(
    folder: Path, argv: list[str], *, answers=("a",), binary: str | None = None, broken=False
):
    """Run `boss <argv>` in a fresh project folder. Returns (exit code, the run folder or None,
    everything printed). `broken` makes the fake worker write a wrong product."""
    from boss.cli import main

    project = folder / "project"
    project.mkdir(parents=True, exist_ok=True)
    if broken:
        (folder / "break").write_text("1")
    environ = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(folder),
        "BOSS_CLAUDE_BIN": binary or str(fake_claude(folder)),
    }
    replies, said = iter(answers), []
    code = main(
        [*argv, "--dir", str(project)],
        ask=lambda prompt: next(replies),
        say=said.append,
        environ=environ,
    )
    runs = project / ".boss" / "runs"
    found = sorted(runs.iterdir()) if runs.is_dir() else []
    return code, (found[-1] if found else None), said
