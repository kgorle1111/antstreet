"""`boss mcp`: a read-only MCP server on stdio, so any MCP client can read a project's runs.

It is a front door, not the engine: every tool reads what the CLI's `status`, `report` and `doctor`
read, through the same code, and none can fund, resume, top up or approve. Spending and approval
stay the investor's acts at a terminal. A tool never takes a path: the project is the folder the
server was started in (`--dir`), and a run is named by a single word that must be one of its runs.

Wire format, from the MCP specification: one JSON-RPC 2.0 message per line on stdin and stdout,
nothing else on stdout. It answers both eras: the `initialize` handshake (2025-11-25 and earlier)
and `server/discover` with per-request `_meta` (2026-07-28). Stdlib only, so the runtime
dependency set stays {pytest}.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import IO, Any

from antstreet import __version__, cli
from antstreet.context import verify
from antstreet.ledger import LedgerCorruptError
from antstreet.rundir import RunPaths

MODERN = ("2026-07-28",)
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
MAX_LINE = 1 << 20  # characters of one request line; a longer one is refused, not parsed
MAX_TEXT = 60_000  # characters of one tool result; the rest is cut with a note saying how much
MAX_RUNS = 200  # run ids `list_runs` returns, newest first
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

PARSE_ERROR, INVALID_REQUEST, NO_METHOD, INVALID_PARAMS = -32700, -32600, -32601, -32602
UNSUPPORTED_VERSION = -32022

_RUN_ARG = {
    "type": "object",
    "properties": {
        "run": {
            "type": "string",
            "pattern": f"^{RUN_ID.pattern}$",
            "description": "run id, one word as `list_runs` prints it (default: the latest run)",
        }
    },
    "additionalProperties": False,
}
_NO_ARGS = {"type": "object", "additionalProperties": False}
_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}

TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "list_runs",
        "title": "List runs",
        "description": f"The ids of this project's runs, newest first (at most {MAX_RUNS}).",
        "inputSchema": _NO_ARGS,
    },
    {
        "name": "status",
        "title": "Run status",
        "description": "One line for a run: its last event, checks passing, estimated spend. "
        "Reads the ledger only after its hash chain and investor signatures verify.",
        "inputSchema": _RUN_ARG,
    },
    {
        "name": "report",
        "title": "Board report",
        "description": "The board report of a run: tasks, checks, spend, and what the gate "
        "decided, from its verified ledger.",
        "inputSchema": _RUN_ARG,
    },
    {
        "name": "verify_ledger",
        "title": "Verify a run's ledger",
        "description": "Check that a run's ledger is intact: every line chains to the one before "
        "it, the investor's events carry valid signatures, no line was dropped, and each saved "
        "worker prompt still matches its recorded hash.",
        "inputSchema": _RUN_ARG,
    },
    {
        "name": "doctor",
        "title": "Preflight checks",
        "description": "Check that this machine can run AntStreet, with a fix line per failure. "
        "Makes no model call (never `--live`); writes and removes one probe file in .boss/.",
        "inputSchema": _NO_ARGS,
    },
)


class _ToolError(Exception):
    """A call the model can correct: reported as a tool result with isError, not a protocol
    error. The message says what failed, why, and what to try."""


def serve(
    project: Path,
    stdin: IO[str],
    stdout: IO[str],
    environ: Mapping[str, str],
) -> int:
    """Answer requests until stdin closes. Exit 0."""
    while (line := stdin.readline(MAX_LINE + 1)) != "":
        if len(line) > MAX_LINE and not line.endswith("\n"):
            while (rest := stdin.readline(MAX_LINE)) and not rest.endswith("\n"):
                pass  # drop the rest of the oversized line
            reply: dict[str, Any] | None = _error(
                None, INVALID_REQUEST, f"a message is over {MAX_LINE} characters"
            )
        elif not line.strip():
            continue
        else:
            reply = handle(line, project, environ)
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=True) + "\n")
            stdout.flush()
    return 0


def handle(line: str, project: Path, environ: Mapping[str, str]) -> dict[str, Any] | None:
    """The reply to one message, or None for a notification."""
    try:
        msg = json.loads(line)
    except ValueError:
        return _error(None, PARSE_ERROR, "not valid JSON")
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "expected one JSON-RPC 2.0 object (no batches)")
    method, rid = msg.get("method"), msg.get("id")
    if "id" not in msg:
        return None  # a notification (initialized, cancelled): nothing to answer
    if not isinstance(method, str) or not isinstance(rid, str | int) or isinstance(rid, bool):
        return _error(rid, INVALID_REQUEST, "a request needs a string method and an id")
    params = msg.get("params", {})
    if not isinstance(params, dict):
        return _error(rid, INVALID_PARAMS, "params must be an object")
    meta = params.get("_meta")
    wanted = meta.get(VERSION_KEY) if isinstance(meta, dict) else None
    if wanted is not None and wanted not in MODERN:
        data = {"supported": [*MODERN, *LEGACY], "requested": wanted}
        return _error(rid, UNSUPPORTED_VERSION, "Unsupported protocol version", data)
    done = {"resultType": "complete"} if wanted is not None else {}
    if method == "initialize":
        asked = params.get("protocolVersion")
        return _result(rid, {
            "protocolVersion": asked if asked in LEGACY else LEGACY[0],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "antstreet", "version": __version__},
            "instructions": _INSTRUCTIONS,
        })  # fmt: skip
    if method == "server/discover":
        return _result(rid, done | {
            "supportedVersions": [*MODERN, *LEGACY],
            "capabilities": {"tools": {}},
            "_meta": {"io.modelcontextprotocol/serverInfo": {
                "name": "antstreet", "version": __version__,
            }},
            "instructions": _INSTRUCTIONS,
        })  # fmt: skip
    if method == "ping":
        return _result(rid, done)
    if method == "tools/list":
        return _result(rid, done | {"tools": list(TOOLS)})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        tool = _HANDLERS.get(name) if isinstance(name, str) else None
        if tool is None or not isinstance(name, str):
            return _error(rid, INVALID_PARAMS, f"Unknown tool: {name!r}; see tools/list")
        if not isinstance(args, dict):
            return _error(rid, INVALID_PARAMS, "arguments must be an object")
        return _result(rid, done | _call(tool, name, args, project, environ))
    return _error(rid, NO_METHOD, f"Method not found: {method}")


_INSTRUCTIONS = (
    "Read-only view of AntStreet runs in one project: list_runs, status, report, verify_ledger, "
    "doctor. Funding, resuming, topping up and approving are the investor's acts at a terminal "
    "(`antstreet fund`, `resume`, `topup`); no tool here can do them."
)


def _call(
    tool: Callable[[dict[str, Any], Path, Mapping[str, str]], tuple[str, bool]],
    name: str,
    args: dict[str, Any],
    project: Path,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    try:
        # Whatever the reused code prints must not reach stdout, the protocol channel.
        with contextlib.redirect_stdout(sys.stderr):
            text, failed = tool(args, project, environ)
    except _ToolError as exc:
        text, failed = str(exc), True
    except Exception as exc:  # one broken run must not take the server down with it
        text = (
            f"{name} failed because of {type(exc).__name__}: {exc}; try `antstreet {name}` in "
            "a terminal for the full trace"
        )
        failed = True
    if len(text) > MAX_TEXT:
        cut = len(text) - MAX_TEXT
        text = text[:MAX_TEXT] + f"\n[cut {cut} characters; run `antstreet {name}` in a terminal]"
    return {"content": [{"type": "text", "text": text}], "isError": failed}


def _run_arg(args: dict[str, Any], allowed: tuple[str, ...]) -> str | None:
    extra = sorted(set(args) - set(allowed))
    if extra:
        raise _ToolError(
            f"the call failed because it has unknown arguments {extra}; try again with only "
            f"{list(allowed) or 'no arguments'}"
        )
    run = args.get("run")
    if run is None:
        return None
    if not isinstance(run, str) or RUN_ID.fullmatch(run) is None:
        raise _ToolError(
            f"run {run!r} was refused because a run id is one word of letters, digits, '.', '_' "
            "or '-' starting with a letter or digit (no paths); try list_runs for the ids"
        )
    return run


def _via_cli(command: str) -> Callable[[dict[str, Any], Path, Mapping[str, str]], tuple[str, bool]]:
    def tool(args: dict[str, Any], project: Path, environ: Mapping[str, str]) -> tuple[str, bool]:
        run = _run_arg(args, ("run",))
        said: list[str] = []
        argv = [command, *([run] if run else []), "--dir", str(project)]
        code = cli.main(argv, ask=_no_input, say=said.append, environ=environ)
        return "\n".join(said), code != cli.EXIT_OK

    return tool


def _no_input(prompt: str) -> str:
    raise _ToolError("the tool failed because it asked for input; nothing here can answer it")


def _list_runs(args: dict[str, Any], project: Path, environ: Mapping[str, str]) -> tuple[str, bool]:
    _run_arg(args, ())
    runs = project / cli.RUNS_DIR
    found = runs.iterdir() if runs.is_dir() else iter(())
    names = sorted((p.name for p in found if p.is_dir()), reverse=True)
    if not names:
        return f"No runs under {runs}. Start one with `antstreet fund` in a terminal.", False
    more = f"\n({len(names) - MAX_RUNS} older not shown)" if len(names) > MAX_RUNS else ""
    return "\n".join(names[:MAX_RUNS]) + more, False


def _verify_ledger(
    args: dict[str, Any], project: Path, environ: Mapping[str, str]
) -> tuple[str, bool]:
    said: list[str] = []
    run = cli._find_run(argparse.Namespace(run=_run_arg(args, ("run",))), project, said.append)
    if run is None:
        return "\n".join(said), True
    paths = RunPaths(project / cli.RUNS_DIR / run)
    try:
        events = paths.events()
    except LedgerCorruptError as exc:  # LedgerUnverifiedError included: a signature or anchor
        return f"Run {run}: the ledger does NOT verify: {exc}", True
    key = paths.investor_key
    signed = (
        "every investor event's signature and the anchor check out against .boss/investor.key"
        if key is not None and key.exists()
        else "this project has no investor key, so no signature could be checked"
    )
    lines = [f"Run {run}: the ledger verifies: {len(events)} lines chained in order; {signed}."]
    problems = verify(paths, events)
    lines += [f"CONTEXT CHECK FAILED: {p}" for p in problems]
    return "\n".join(lines), bool(problems)


def _doctor(args: dict[str, Any], project: Path, environ: Mapping[str, str]) -> tuple[str, bool]:
    _run_arg(args, ())
    return _via_cli("doctor")({}, project, environ)  # no `--live`: a live check is paid


_HANDLERS: dict[str, Callable[[dict[str, Any], Path, Mapping[str, str]], tuple[str, bool]]] = {
    "list_runs": _list_runs,
    "status": _via_cli("status"),
    "report": _via_cli("report"),
    "verify_ledger": _verify_ledger,
    "doctor": _doctor,
}


def _result(rid: object, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid: object, code: int, message: str, data: object = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": error}
