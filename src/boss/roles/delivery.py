"""The demo writer: a script that shows the finished product working, and a usage note.

A product that passes its checks is still a folder of files. The model drafts a script that uses
the product the way the idea describes; nothing it writes is trusted until code has checked it.
The script is parsed and screened statically, then RUN through the gate against a copy of the
product, and the investor is shown only what that run printed. The usage note is the model's
text, and the only output anyone sees is the captured one: a note that describes output the code
does not produce cannot exist, because the note never carries output.

How the run's output comes back: the gate returns a `CheckResult` with the last
`OUTPUT_TAIL_CHARS` of pytest's output, and deletes its run folder afterwards, so a file written
there cannot be read later. The generated check therefore runs the script as a child, reads at
most `MAX_OUTPUT_BYTES` of what it writes (stdout and stderr, in the order written), and prints one
base64 line to the real stdout. The line always fits the tail; a demo that prints more is rejected.
"""

from __future__ import annotations

import ast
import base64
import binascii
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boss.errors import Outcome
from boss.gate import Check, CheckStatus, GateError, run_gate
from boss.handoff import SKIPPED_NAMES
from boss.redact import safe_text
from boss.roles.base import RoleError, RoleOutputError, RoleSpec, call_role
from boss.roles.stories import fragment_problem
from boss.sandbox import SandboxMode
from boss.stream import Usage
from boss.worker import CLI

DEMO_FILE = "demo.py"
USAGE_FILE = "USAGE.md"
MAX_STEPS = 6
MAX_CODE_CHARS = 6_000
MAX_SAYS_CHARS = 200
MAX_USAGE_CHARS = 1_200
MAX_USAGE_LINES = 12
MAX_OUTPUT_BYTES = 2_000  # base64 of this plus a failing pytest report must fit the gate's tail
DEFAULT_TIMEOUT_S = 20.0
SOURCE_BUDGET_CHARS = 24_000
MAX_PRODUCT_FILES = 500
MAX_PRODUCT_BYTES = 50_000_000
_MAX_LEFT_OUT_LISTED = 20
_EXCERPT_CHARS = 400
_MARK = "BOSS-DEMO-RESULT"
_TEXT = {"type": "string", "minLength": 1}

DEMO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "demo_code": _TEXT,
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_STEPS,
            "items": {
                "type": "object",
                "properties": {"says": _TEXT, "quote": _TEXT},
                "required": ["says", "quote"],
            },
        },
        "usage": _TEXT,
    },
    "required": ["demo_code", "steps", "usage"],
}

SPECS = (
    RoleSpec(
        name="demo_writer",
        department="delivery",
        reports_to="boss",
        purpose="a demo script and usage note that show the finished product working",
        gate=(
            "the script parses, imports only the standard library and the product, quotes the "
            "idea word for word, and RUNS through the gate against a copy of the product: exit 0, "
            "bounded non-empty output. Only that captured output is shown"
        ),
        prompt="demo_writer_v1.md",
        skills=(
            "demo_writer/smallest-convincing-example",
            "demo_writer/show-dont-assert",
            "demo_writer/usage-note",
        ),
    ),
)
SPEC = SPECS[0]

# Deliberately minimal: the sandbox is the control (docs/SANDBOX.md); these lists only catch the
# obvious. Not a jail: `getattr(__builtins__, ...)` and friends get past them, and the run
# contains them.
_ESCAPE_MODULES = frozenset(
    {"subprocess", "ctypes", "socket", "multiprocessing", "pty", "webbrowser"}
)
_INPUT_MODULES = frozenset({"fileinput", "getpass"})
_DYNAMIC_IMPORT_MODULES = frozenset({"importlib", "runpy"})  # they would defeat the import check
_BANNED_CALLS = frozenset({"input", "__import__", "eval", "exec", "compile", "breakpoint"})
_OS_EXITS = frozenset({"system", "popen", "fork", "forkpty", "kill", "killpg"})
_OS_EXIT_PREFIXES = ("exec", "spawn")
_OUTPUT_CLAIM = re.compile(r"^\s*(?:>>>|=>|(?:\w+ ){0,2}(?:output|results?)s?\s*:)", re.I | re.M)
_RESULT = re.compile(rf"{_MARK}:(-?\d+):([01]):(\d+):([A-Za-z0-9+/=]*):END")

# The generated check. Its text is computed here from constants, never taken from the model.
_WRAPPER_BODY = """
import base64
import os
import subprocess
import sys

import pytest


def test_demo(capfd):
    proc = subprocess.Popen(
        [sys.executable, "-u", "-B", "-X", "utf8", SCRIPT],
        cwd=os.getcwd(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    data = proc.stdout.read(LIMIT + 1)
    over = len(data) > LIMIT
    if over:
        proc.kill()
    code = proc.wait()
    data = data[:LIMIT]
    blob = base64.b64encode(data).decode()
    with capfd.disabled():
        print(f"{MARK}:{code}:{int(over)}:{len(data)}:{blob}:END", flush=True)
    if over:
        pytest.fail(f"the demo printed more than {LIMIT} bytes", pytrace=False)
    if code != 0:
        pytest.fail(f"the demo exited {code}", pytrace=False)
"""


@dataclass(frozen=True, slots=True)
class Step:
    says: str  # one line: what the demo shows here (the model's claim; never shown as output)
    quote: str  # the fragment of the idea it demonstrates, word for word


@dataclass(frozen=True, slots=True)
class Draft:
    """What the model returned, shaped but not yet checked."""

    code: str
    steps: tuple[Step, ...]
    usage: str


@dataclass(frozen=True, slots=True)
class Demo:
    """A demo that has run. `output` is what the run printed and nothing the model said."""

    code: str
    steps: tuple[Step, ...]
    usage: str
    output: str
    sandboxed: bool  # the run was inside an OS sandbox; False also means none was available


@dataclass(frozen=True, slots=True)
class DemoRun:
    output: str  # empty unless the run passed
    sandboxed: bool
    problems: tuple[str, ...]  # empty means the demo ran, exited 0 and printed a bounded output


class DemoShapeError(ValueError):
    """The data is not shaped like a demo at all (as opposed to a demo with problems)."""


def parse_draft(data: object) -> Draft:
    """Build a Draft from schema-shaped data. Raises DemoShapeError on a wrong shape; whether the
    demo is any good is `draft_problems`' job. Keys the schema does not name are ignored."""
    try:
        if not isinstance(data, Mapping):
            raise TypeError("not an object")
        steps = data["steps"]
        if not isinstance(steps, list):
            raise TypeError("steps is not a list")
        return Draft(
            _text(data, "demo_code"),
            tuple(Step(_text(s, "says"), _text(s, "quote")) for s in steps),
            _text(data, "usage"),
        )
    except (KeyError, TypeError) as exc:
        raise DemoShapeError(f"not shaped like a demo: {exc}") from exc


def draft_problems(draft: Draft, idea: str, modules: Collection[str]) -> list[str]:
    """Everything wrong with a draft that code can see without running it, one line each.
    `modules` are the product's own top-level names, the only non-stdlib imports allowed."""
    problems = _code_problems(draft.code, modules)
    if not 1 <= len(draft.steps) <= MAX_STEPS:
        problems.append(f"needs 1 to {MAX_STEPS} steps, has {len(draft.steps)}")
    for n, step in enumerate(draft.steps, start=1):
        if not step.says.strip() or "\n" in step.says.strip():
            problems.append(f"step {n}: says must be one line of text")
        elif len(step.says) > MAX_SAYS_CHARS:
            problems.append(f"step {n}: says is over {MAX_SAYS_CHARS} characters")
        if problem := fragment_problem(step.quote, idea):
            problems.append(f"step {n}: quote {problem}")
    return problems + _usage_problems(draft.usage)


def wrapper_source() -> str:
    """The text of the check that runs the demo. Constants only: nothing of the model's."""
    head = f"MARK = {_MARK!r}\nLIMIT = {MAX_OUTPUT_BYTES}\nSCRIPT = {DEMO_FILE!r}\n"
    return head + _WRAPPER_BODY


def run_demo(
    code: str,
    product_dir: Path,
    scratch_dir: Path,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    sandbox: SandboxMode | None = None,
) -> DemoRun:
    """Run `code` as demo.py against a copy of the product, through the gate.

    The product is never touched: the gate copies again from the copy in `scratch_dir`, which is
    removed afterwards. Raises GateError when the gate cannot run, and OSError when the product
    cannot be copied.
    """
    product = Path(product_dir)
    regular, _ = _scan(product)
    Path(scratch_dir).mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="demo_", dir=scratch_dir))
    try:
        workspace, checks = work / "ws", work / "checks"
        workspace.mkdir()
        for rel in regular:
            (workspace / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(product / rel, workspace / rel)
        (workspace / DEMO_FILE).write_text(code, encoding="utf-8")
        checks.mkdir()
        (checks / "test_demo.py").write_text(wrapper_source(), encoding="utf-8")
        result = run_gate(
            workspace, checks, [Check("demo", "test_demo.py")], timeout_s=timeout_s, sandbox=sandbox
        )[0]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    problems: list[str] = []
    got = _recover(result.output_tail)
    if result.status is CheckStatus.TIMEOUT:
        problems.append(f"the demo did not finish within {timeout_s:g}s")
    elif got is None:
        excerpt = safe_text(result.output_tail.strip()[-_EXCERPT_CHARS:])
        problems.append(f"the demo run gave no recoverable output ({result.detail}): {excerpt}")
    else:
        status, over, output = got
        if over:
            problems.append(f"the demo printed more than {MAX_OUTPUT_BYTES} bytes")
        elif status != 0:
            excerpt = safe_text(output.strip()[-_EXCERPT_CHARS:])
            problems.append(f"the demo exited {status}; its output ended: {excerpt}")
        elif not output.strip():
            problems.append("the demo printed nothing")
    if not problems and not result.passed:
        problems.append(f"the gate failed the demo run ({result.detail})")
    output = got[2] if got and not problems else ""
    return DemoRun(output, result.sandboxed, tuple(problems))


def write_demo(
    idea: str,
    product_dir: Path,
    scratch_dir: Path,
    *,
    env: Mapping[str, str],
    model: str,
    executable: str = CLI,
    thinking_tokens: int | None = None,
    call_timeout_s: float = 300.0,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    sandbox: SandboxMode | None = None,
    budget_chars: int = SOURCE_BUDGET_CHARS,
) -> tuple[Demo, Usage]:
    """One model call, then the static gate, then the real run. Returns a demo that has run.

    Raises ValueError or FileExistsError before any spend when the request is unusable, RoleError
    when the call or the gate itself fails, and RoleOutputError (every problem, plus the usage)
    when the demo is rejected. No retry: a rejected demo cost a call and produced nothing.
    """
    product = Path(product_dir)
    if not idea.strip():
        raise ValueError("the idea is empty")
    for name in (DEMO_FILE, USAGE_FILE):
        if os.path.lexists(product / name):
            raise FileExistsError(f"{product / name} exists; a demo never replaces a product file")
    regular, links = _scan(product)
    shown, left_out = _select(product, regular, links, budget_chars)
    if not shown:
        raise ValueError("the product has no readable Python source to demo")
    out = call_role(
        SPEC,
        _prompt(idea, shown, left_out),
        DEMO_SCHEMA,
        env=env,
        model=model,
        executable=executable,
        thinking_tokens=thinking_tokens,
        timeout_s=call_timeout_s,
    )
    try:
        draft = parse_draft(out.data)
    except DemoShapeError as exc:
        raise RoleOutputError(SPEC.name, [str(exc)], out.usage, out.data) from exc
    problems = draft_problems(draft, idea, _own_modules(regular))
    if problems:
        raise RoleOutputError(SPEC.name, problems, out.usage, out.data)
    try:
        ran = run_demo(draft.code, product, scratch_dir, timeout_s=timeout_s, sandbox=sandbox)
    except (GateError, OSError) as exc:
        raise RoleError(
            SPEC.name, f"the demo could not be run: {exc}", Outcome.COMPLETED, out.usage
        ) from exc
    if ran.problems:
        raise RoleOutputError(SPEC.name, list(ran.problems), out.usage, out.data)
    demo = Demo(draft.code, draft.steps, draft.usage, ran.output, ran.sandboxed)
    return demo, out.usage


def render_usage(demo: Demo) -> str:
    """USAGE.md: the usage note, the script, and the output exactly as the run captured it."""
    where = "inside the gate's OS sandbox" if demo.sandboxed else "WITHOUT an OS sandbox"
    output = safe_text(demo.output)
    parts = [
        "# Usage",
        safe_text(demo.usage.strip()),
        "## Demo",
        f"`{DEMO_FILE}` uses the product the way the idea describes. "
        f"Run it from this folder with `python {DEMO_FILE}`.",
        _block("python", safe_text(demo.code)),
        "## Output",
        f"What `{DEMO_FILE}` printed when the system ran it {where}: stdout and stderr in the "
        "order written, control characters shown as escapes, credential-like text masked. "
        "Nothing here was written by the model.",
        _block("text", output),
    ]
    return "\n\n".join(parts) + "\n"


def install_demo(demo: Demo, product_dir: Path) -> list[Path]:
    """Write demo.py and USAGE.md into the product folder; return the paths written.

    Never replaces a file: the product's own files were approved by checks, and a demo must not
    displace them. Raises FileExistsError if either exists, leaving both untouched (a file this
    call created before the failure is removed again).
    """
    root = Path(product_dir)
    files = ((root / DEMO_FILE, demo.code), (root / USAGE_FILE, render_usage(demo)))
    made: list[Path] = []
    try:
        for path, text in files:
            with path.open("x", encoding="utf-8", newline="\n") as handle:  # "x": never replace
                made.append(path)
                handle.write(text if text.endswith("\n") else text + "\n")
    except BaseException:
        for path in made:
            path.unlink(missing_ok=True)
        raise
    return made


def _code_problems(code: str, modules: Collection[str]) -> list[str]:
    if not code.strip():
        return ["demo_code is empty"]
    if len(code) > MAX_CODE_CHARS:
        return [f"demo_code is {len(code)} characters, over {MAX_CODE_CHARS}"]
    try:
        tree = ast.parse(code, filename=DEMO_FILE)
    except SyntaxError as exc:
        where = f"line {exc.lineno}: " if exc.lineno else ""
        return [f"demo_code has a syntax error: {where}{exc.msg}"]
    except (ValueError, RecursionError, MemoryError) as exc:
        return [f"demo_code cannot be parsed: {exc}"]
    problems: dict[str, None] = {}  # ordered, without repeats
    for node in ast.walk(tree):
        for problem in _node_problems(node, modules):
            problems[problem] = None
    return list(problems)


def _node_problems(node: ast.AST, modules: Collection[str]) -> list[str]:
    """Imports as `bench/tasks.py` checks them (standard library or the product's own, nothing
    else), plus relative imports, which have no package to resolve against in a script."""
    if isinstance(node, ast.Import):
        return [p for a in node.names if (p := _import_problem(a.name.split(".")[0], modules))]
    if isinstance(node, ast.ImportFrom):
        if node.level:
            return ["relative imports do not work in a script"]
        top = (node.module or "").split(".")[0]
        found = [p] if (p := _import_problem(top, modules)) else []
        if top == "sys" and any(a.name == "stdin" for a in node.names):
            found.append("demo_code reads input (sys.stdin)")
        if top == "os":
            found += [f"demo_code uses os.{a.name}" for a in node.names if _os_exit(a.name)]
        return found
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _BANNED_CALLS
    ):
        return [f"demo_code calls {node.func.id}()"]
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "sys" and node.attr == "stdin":
            return ["demo_code reads input (sys.stdin)"]
        if node.value.id == "os" and _os_exit(node.attr):
            return [f"demo_code uses os.{node.attr}"]
    return []


def _os_exit(name: str) -> bool:
    return name in _OS_EXITS or name.startswith(_OS_EXIT_PREFIXES)


def _import_problem(name: str, modules: Collection[str]) -> str | None:
    if name in modules:
        return None
    if name in _ESCAPE_MODULES | _INPUT_MODULES | _DYNAMIC_IMPORT_MODULES:
        return f"demo_code imports {name!r}, which a demo does not need"
    if name not in sys.stdlib_module_names:
        return f"demo_code imports {name!r}, which is neither standard library nor the product"
    return None


def _usage_problems(usage: str) -> list[str]:
    problems = []
    if not usage.strip():
        return ["usage is empty"]
    if len(usage) > MAX_USAGE_CHARS:
        problems.append(f"usage is {len(usage)} characters, over {MAX_USAGE_CHARS}")
    if len(usage.strip().splitlines()) > MAX_USAGE_LINES:
        problems.append(f"usage is over {MAX_USAGE_LINES} lines")
    if "```" in usage or "~~~" in usage:
        problems.append("usage must be plain text, with no code fences")
    if _OUTPUT_CLAIM.search(usage):
        problems.append("usage claims output; the real output is attached by the system")
    return problems


def _recover(tail: str) -> tuple[int, bool, str] | None:
    """(exit status, printed too much, output) from the generated check's line, else None."""
    found = _RESULT.findall(tail)
    if len(found) != 1:
        return None
    status, over, size, blob = found[0]
    try:
        data = base64.b64decode(blob, validate=True)
    except binascii.Error:
        return None
    if len(data) != int(size):
        return None
    return int(status), over == "1", data.decode("utf-8", errors="replace")


def _scan(product: Path) -> tuple[list[str], list[str]]:
    """Sorted posix paths of the product's regular files and of its symlinks. Symlinks are never
    followed; sockets, pipes and devices are ignored; SKIPPED_NAMES are agent configuration and
    caches, not product."""
    regular: list[str] = []
    links: list[str] = []
    total = 0
    for root, dirs, files in os.walk(product):  # followlinks=False: a linked dir is not entered
        base = Path(root)
        kept = []
        for name in sorted(dirs):
            if name in SKIPPED_NAMES:
                continue
            if (base / name).is_symlink():
                links.append((base / name).relative_to(product).as_posix())
            else:
                kept.append(name)
        dirs[:] = kept
        for name in sorted(files):
            if name in SKIPPED_NAMES:
                continue
            path = base / name
            info = path.lstat()
            rel = path.relative_to(product).as_posix()
            if stat.S_ISLNK(info.st_mode):
                links.append(rel)
            elif stat.S_ISREG(info.st_mode):
                regular.append(rel)
                total += info.st_size
            if len(regular) > MAX_PRODUCT_FILES or total > MAX_PRODUCT_BYTES:
                raise ValueError(
                    f"the product is over {MAX_PRODUCT_FILES} files or {MAX_PRODUCT_BYTES} bytes"
                )
    return sorted(regular), sorted(links)


def _select(
    product: Path, regular: list[str], links: list[str], budget: int
) -> tuple[list[tuple[str, str]], list[str]]:
    """The Python files that fit the character budget, whole (a cut file would mislead), and one
    line per file left out with the reason."""
    shown: list[tuple[str, str]] = []
    left: list[str] = []
    remaining = budget
    for rel in regular:
        if not rel.endswith(".py"):
            left.append(f"{safe_text(rel)} (not Python)")
        elif (product / rel).stat().st_size > remaining * 4:  # at most 4 bytes a character
            left.append(f"{safe_text(rel)} (over the size budget)")
        else:
            try:
                text = (product / rel).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                left.append(f"{safe_text(rel)} (not UTF-8 text)")
                continue
            if len(text) > remaining:
                left.append(f"{safe_text(rel)} (over the size budget)")
            else:
                shown.append((rel, text))
                remaining -= len(text)
    left += [f"{safe_text(rel)} (symlink, never followed)" for rel in links]
    if len(left) > _MAX_LEFT_OUT_LISTED:
        more = len(left) - _MAX_LEFT_OUT_LISTED
        left = [*left[:_MAX_LEFT_OUT_LISTED], f"and {more} more"]
    return shown, left


def _own_modules(regular: list[str]) -> set[str]:
    """Top-level names the product provides: `a.py` gives `a`, `pkg/b.py` gives `pkg`."""
    return {rel.split("/")[0].removesuffix(".py") for rel in regular if rel.endswith(".py")}


def _prompt(idea: str, shown: list[tuple[str, str]], left_out: list[str]) -> str:
    """The idea and the files as quoted material inside a fence no text inside can close."""
    fence = _fence(idea, *(text for _, text in shown))
    parts = [f"Idea:\n{fence}\n{idea.strip()}\n{fence}", "Product source files:"]
    parts += [f"{safe_text(path)}\n{fence}python\n{text.rstrip()}\n{fence}" for path, text in shown]
    if left_out:
        listing = "\n".join(f"- {line}" for line in left_out)
        parts.append(f"Files left out, which you have not seen:\n{listing}")
    else:
        parts.append("No files were left out.")
    return "\n\n".join(parts)


def _fence(*texts: str) -> str:
    longest = max((len(m) for t in texts for m in re.findall(r"`+", t)), default=0)
    return "`" * max(3, longest + 1)


def _block(language: str, body: str) -> str:
    fence = _fence(body)
    return f"{fence}{language}\n{body if body.endswith(chr(10)) else body + chr(10)}{fence}"


def _text(item: object, key: str) -> str:
    value = item[key]  # type: ignore[index]
    if not isinstance(value, str):
        raise TypeError(f"{key} is not text")
    return value
