"""Fault injection for the crash and resume harness (U1). Not a test module.

Every `antstreet` command of a trial runs in its own process (`drive`), so a fault can kill it
for real (SIGKILL) and threads can run trials side by side. The fake `claude` plays the boss and
the worker, keeps a session store like the real CLI (`tests/test_session_lost.py`), and writes
what a provider would bill to `$HOME/bill.jsonl` the moment a model call is made, before any
fault: the ground truth the ledger is reconciled against.

Faults, each injected at worker call `n` (`$HOME/fault` holds `<n>:<kind>`):

    kill_worker     the worker process is SIGKILLed mid-slice, after its call was billed
    hang            a tool call hangs past the slice timeout; the runner stops it
    gibberish       the worker prints bytes that are not the stream format and exits 0
    garbled_result  a well-formed result whose status is not the schema's (cost known)
    kill_antstreet  the `antstreet` process is SIGKILLed mid-slice, after the call was billed
    block           the worker waits for `$HOME/release` (two resumes racing for one run)

`crash_at_line=K` kills `antstreet` after ledger line K is written and before its anchor is.

Run as a script, it runs every trial and prints the table docs/RECOVERY.md holds:
`uv run python tests/fault_support.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from boss_init import BOSS_INIT

from antstreet.cli import EXIT_FAILED, EXIT_INTERRUPTED, EXIT_OK
from antstreet.errors import INFRASTRUCTURE
from antstreet.ledger import Event, EventType, read_events, total

CHECK = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
DRAFT = {
    "tasks": [{"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]}],
    "checks": [{"description": "reverses a word", "task": "t1", "code": CHECK}],
}
INIT = {
    "type": "system", "subtype": "init", "tools": ["Read", "Write", "Edit", "StructuredOutput"],
    "mcp_servers": [], "permissionMode": "dontAsk", "claude_code_version": "2.1.285",
}  # fmt: skip
BOSS_USD = 0.004
TURN_USD = 0.01  # each worker call; the CLI reports a session's cumulative total, as the real one
GOOD_FROM = 2  # the worker's product passes from its second call on: a clean run is two slices
SLICE_TIMEOUT_S = 2.0
WORKER_FAULTS = ("kill_worker", "hang", "gibberish", "garbled_result", "ctrl_c", "kill_antstreet")
POINTS = (1, 2)  # the first slice (a new session) and the second (a resumed one)

FAKE_CLAUDE = f"""#!{sys.executable}
import json, os, signal, sys, time
argv = sys.argv[1:]
home = os.environ["HOME"]
say = lambda e: print(json.dumps(e), flush=True)
usage = {{"m": {{"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 0}}}}
result = {{"type": "result", "subtype": "success", "is_error": False,
          "terminal_reason": "completed", "modelUsage": usage}}
def bill(kind, sid, usd):
    with open(os.path.join(home, "bill.jsonl"), "a") as fh:
        fh.write(json.dumps({{"kind": kind, "session": sid, "usd": usd}}) + chr(10))
        fh.flush()
        os.fsync(fh.fileno())
if argv[argv.index("--tools") + 1] == "":   # the boss drafting a term sheet
    say({BOSS_INIT!r})
    bill("boss", None, {BOSS_USD!r})
    say(result | {{"total_cost_usd": {BOSS_USD!r}, "structured_output": {DRAFT!r}}})
    sys.exit(0)
store = os.path.join(home, "store")
os.makedirs(store, exist_ok=True)
resume = "--resume" in argv
sid = argv[argv.index("--resume" if resume else "--session-id") + 1]
path = os.path.join(store, sid)
if resume and not os.path.exists(path):
    print("No conversation found with session ID: " + sid, file=sys.stderr, flush=True)
    sys.exit(1)
if not resume and os.path.exists(path):
    print("Error: Session ID " + sid + " is already in use.", file=sys.stderr, flush=True)
    sys.exit(1)
calls = os.path.join(home, "calls")
n = int(open(calls).read()) + 1 if os.path.exists(calls) else 1
open(calls, "w").write(str(n))
turns = int(open(path).read()) + 1 if resume else 1
open(path, "w").write(str(turns))
init = {INIT!r} | {{"session_id": sid}}
init["model"] = "claude-" + argv[argv.index("--model") + 1] + "-4-5-20251001"
say(init)
bill("worker", sid, {TURN_USD!r})   # the model was called: this turn is paid whatever follows
planned = os.path.join(home, "fault")   # the worker's environment is stripped: a file
at, _, kind = (open(planned).read() if os.path.exists(planned) else "").partition(":")
fault = kind if at == str(n) else ""
if fault == "kill_worker":
    os.kill(os.getpid(), signal.SIGKILL)
if fault == "kill_antstreet":
    os.kill(os.getppid(), signal.SIGKILL)
    sys.exit(1)
if fault == "hang":
    time.sleep(120)
if fault == "ctrl_c":   # the investor presses Ctrl-C; the CLI reports what it spent, then stops
    def stopped(signum, frame):
        say(result | {{"session_id": sid, "total_cost_usd": round({TURN_USD!r} * turns, 6),
                      "structured_output": {{"status": "continuing", "reason": "stopped"}}}})
        sys.exit(0)
    signal.signal(signal.SIGINT, stopped)
    os.kill(os.getppid(), signal.SIGINT)
    time.sleep(120)
if fault == "gibberish":
    print("\\x1b[2J{{{{ not json", flush=True)
    print("}}{{ ]] \\u00ff\\u00fe", flush=True)
    sys.exit(0)
if fault == "block":
    open(os.path.join(home, "blocked"), "w").write("")
    while not os.path.exists(os.path.join(home, "release")):
        time.sleep(0.05)
good = n >= {GOOD_FROM!r}   # a faulted call above wrote nothing
open("rev.py", "w").write("def reverse(s):\\n    return " + ("s[::-1]" if good else "s") + "\\n")
status = {{"status": "done" if good else "continuing", "reason": "wrote rev.py"}}
if fault == "garbled_result":
    status = "}}{{ status: ??"
say(result | {{"session_id": sid, "total_cost_usd": round({TURN_USD!r} * turns, 6),
              "structured_output": status}})
"""

# Runs in the child: the CLI's `main`, with the trial's patches. Answers "a" to the term sheet and
# "y" to anything after it; prints what the CLI says; exits with its code.
DRIVER = """
import functools, json, os, signal, sys
spec = json.loads(sys.argv[1])
from antstreet import cli, runner, signing
if spec.get("timeout_s"):
    cli.run_slice = functools.partial(
        runner.run_slice, timeout_s=spec["timeout_s"], grace_s=0.5
    )
if spec.get("crash_at_line"):
    real = signing.write_anchor
    def write_anchor(key_file, run, lines, last):
        if lines == spec["crash_at_line"]:  # the line is written and synced; its anchor is not
            os.kill(os.getpid(), signal.SIGKILL)
        return real(key_file, run, lines, last)
    signing.write_anchor = write_anchor
answers = iter(["a"])
code = cli.main(
    spec["argv"],
    ask=lambda prompt: next(answers, "y"),
    say=lambda text: print(text, flush=True),
    environ=spec["environ"],
)
sys.exit(code)
"""


@dataclass(frozen=True)
class Step:
    command: str
    code: int
    output: str


@dataclass(frozen=True)
class Trial:
    fault: str
    point: int
    steps: tuple[Step, ...]
    events: tuple[Event, ...]
    billed_micros: int
    verified: bool
    rerun_changed: bool  # a resume after the end wrote a line or spent money
    problems: tuple[str, ...] = ()  # anything else the trial saw go wrong

    @property
    def final(self) -> Step:
        return next(s for s in reversed(self.steps) if s.command in ("fund", "resume"))

    @property
    def recovered(self) -> bool:
        return self.final.code == EXIT_OK and "1/1 checks passed" in self.final.output

    @property
    def escalated(self) -> bool:
        """Stopped with a reason that says what to do, nothing lost unseen."""
        told = "antstreet fund" in self.final.output or "antstreet resume" in self.final.output
        return not self.recovered and self.final.code > 0 and told and not self.silent_loss_micros

    @property
    def booked_micros(self) -> int:
        return total(self.events).cost_micros

    @property
    def unknown_events(self) -> int:
        return total(self.events).unknown_cost_events

    @property
    def silent_loss_micros(self) -> int:
        """Billed money on no ledger line, with no event of unknown cost to say a figure is low."""
        unbooked = self.billed_micros - self.booked_micros
        return unbooked if unbooked > 0 and not self.unknown_events else 0

    @property
    def double_spends(self) -> int:
        return double_spends(self.events, self.billed_micros)

    def wasted_micros(self, clean: Trial) -> int:
        """What the fault cost: the spend past a clean run's, or all of it when the run must be
        started again (nothing it bought can be resumed)."""
        return self.billed_micros - clean.billed_micros if self.recovered else self.billed_micros


def double_spends(events: Sequence[Event], billed_micros: int) -> int:
    """Each way a slice can be paid twice: booked twice, run again after it was booked, another
    bought before the gate judged the one just paid for (its work is paid for again), or more
    booked than was billed (a session's cumulative total counted twice)."""
    ends = Counter((e.actor, e.data.get("slice")) for e in events if e.event is EventType.SLICE_END)
    count = sum(n - 1 for n in ends.values() if n > 1)
    ended: set[tuple[str, object]] = set()
    ungraded: dict[str, object] = {}  # worker -> its last paid slice the gate has not judged
    for e in events:
        key = (e.actor, e.data.get("slice"))
        if e.event is EventType.SLICE_END:
            ended.add(key)
            if e.data.get("outcome") not in INFRASTRUCTURE:  # never gated: it did no work
                ungraded[e.actor] = e.data.get("slice")
        elif e.event is EventType.CHECK_RESULT and "worker" in e.data:
            actor = f"worker:{e.data['worker']}"
            if ungraded.get(actor) == e.data.get("slice"):
                del ungraded[actor]
        elif e.event is EventType.SLICE_START:
            count += key in ended
            count += ungraded.pop(e.actor, None) is not None
    return count + (total(events).cost_micros > billed_micros)


def _usd(micros: float) -> str:
    return f"${micros / 1_000_000:.4f}"


def _micros(usd: float) -> int:
    return round(usd * 1_000_000)


class Lab:
    """One trial's folder: a project, a fake `claude` and its bill."""

    def __init__(self, root: Path, fault: str = "") -> None:
        self.root = root
        self.project = root / "project"
        self.project.mkdir(parents=True, exist_ok=True)
        fake = root / "fake-claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        self.environ = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(root),
            "BOSS_CLAUDE_BIN": str(fake),
        }
        self.plan(fault)
        self.steps: list[Step] = []

    def plan(self, fault: str) -> None:
        """`<call>:<kind>`, read by the fake at every worker call; "" for none."""
        (self.root / "fault").write_text(fault)

    def spec(self, *argv: str, **patches: object) -> str:
        return json.dumps(
            {"argv": [*argv, "--dir", str(self.project)], "environ": self.environ, **patches}
        )

    def drive(self, *argv: str, **patches: object) -> Step:
        """Run one `antstreet` command in a process of its own and record how it ended."""
        done = subprocess.run(
            [sys.executable, "-c", DRIVER, self.spec(*argv, **patches)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        step = Step(argv[0], done.returncode, done.stdout + done.stderr)
        self.steps.append(step)
        return step

    def start(self, *argv: str, **patches: object) -> subprocess.Popen[str]:
        return subprocess.Popen(
            [sys.executable, "-c", DRIVER, self.spec(*argv, **patches)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def run_dir(self) -> Path | None:
        runs = self.project / ".boss" / "runs"
        found = sorted(runs.iterdir()) if runs.is_dir() else []
        return found[-1] if found else None

    def billed(self) -> int:
        bill = self.root / "bill.jsonl"
        lines = bill.read_text().splitlines() if bill.exists() else []
        return sum(_micros(json.loads(line)["usd"]) for line in lines)

    def events(self) -> list[Event]:
        run = self.run_dir()
        return read_events(run / "ledger.jsonl") if run else []

    def finish(self, fault: str, point: int, problems: Sequence[str] = ()) -> Trial:
        """Resume once more (it must change nothing), verify, and read the books."""
        before, billed = self.events(), self.billed()
        self.drive("resume")
        rerun_changed = self.events() != before or self.billed() != billed
        verified = self.run_dir() is None or self.drive("verify").code == EXIT_OK
        return Trial(
            fault,
            point,
            tuple(self.steps),
            tuple(before),
            billed,
            verified,
            rerun_changed,
            tuple(problems),
        )


FUND = ("fund", "Reverse a string.", "--budget", "0.50")


def worker_fault(root: Path, kind: str, point: int) -> Trial:
    """A fault in worker call `point`; `antstreet` resumes until the run ends (at most twice)."""
    lab = Lab(root, f"{point}:{kind}")
    step = lab.drive(*FUND, timeout_s=SLICE_TIMEOUT_S)
    for _ in range(2):
        if step.code >= 0 and step.code != EXIT_INTERRUPTED:  # killed by a signal, or Ctrl-C
            break
        step = lab.drive("resume", timeout_s=SLICE_TIMEOUT_S)
    return lab.finish(kind, point)


def anchor_crash(root: Path, line: int) -> Trial:
    """`antstreet` killed after ledger line `line` is written, before its anchor is."""
    lab = Lab(root)
    step = lab.drive(*FUND, crash_at_line=line)
    if step.code < 0:
        lab.drive("resume")
    return lab.finish("anchor_crash", line)


def concurrent_resume(root: Path) -> Trial:
    """A second `resume` while the first is mid-slice: it must be refused and change nothing."""
    lab = Lab(root, "1:kill_antstreet")
    lab.drive(*FUND)
    lab.plan("2:block")
    first = lab.start("resume")
    blocked = root / "blocked"
    deadline = time.monotonic() + 120
    while not blocked.exists() and first.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    ledger = lab.run_dir() / "ledger.jsonl"  # type: ignore[operator]
    before = ledger.read_bytes()
    second = lab.drive("resume")
    problems = []
    if ledger.read_bytes() != before:
        problems.append("the second resume changed the ledger")
    if second.code != EXIT_FAILED or "still being written by another" not in second.output:
        problems.append(f"the second resume was not refused: {second.code} {second.output!r}")
    (root / "release").write_text("")
    output, _ = first.communicate(timeout=300)
    lab.steps.insert(-1, Step("resume", first.returncode, output))
    return lab.finish("concurrent_resume", 2, problems)


def baseline(root: Path) -> Trial:
    lab = Lab(root)
    lab.drive(*FUND)
    return lab.finish("none", 0)


BASELINE_LINES = 12  # ledger lines of a clean run; the anchor crash is injected after each


def all_trials(root: Path) -> list[Trial]:
    jobs = [("baseline", baseline, ())]
    jobs += [(f"{k}-{p}", worker_fault, (k, p)) for k in WORKER_FAULTS for p in POINTS]
    jobs += [(f"anchor-{n}", anchor_crash, (n,)) for n in range(1, BASELINE_LINES + 1)]
    jobs += [("concurrent", concurrent_resume, ())]
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
        futures = [pool.submit(fn, root / name, *args) for name, fn, args in jobs]
        return [f.result() for f in futures]


ROWS = (
    ("kill_worker", "worker SIGKILLed mid-slice"),
    ("hang", "tool call hangs past the slice timeout"),
    ("gibberish", "worker prints gibberish, no result"),
    ("garbled_result", "result with an unparseable status"),
    ("ctrl_c", "Ctrl-C mid-slice (the CLI reports its cost)"),
    ("kill_antstreet", "`antstreet` SIGKILLed mid-slice"),
    ("anchor_crash", "`antstreet` killed between a ledger write and its anchor"),
    ("concurrent_resume", "a second `resume` while the first runs"),
)


def table(trials: Sequence[Trial]) -> str:
    """The measured table: per fault, how the trials ended and what the fault cost."""
    clean = next(t for t in trials if t.fault == "none")
    lines = [
        "| Fault | Trials | Recovered | Escalated cleanly | Double-spends | Silent losses "
        "| Unknown-cost events | Billed, not booked, per fault | Wasted per fault |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for fault, label in ROWS:
        mine = [t for t in trials if t.fault == fault]
        n = len(mine)
        wasted = sum(t.wasted_micros(clean) for t in mine) / n
        unbooked = sum(t.billed_micros - t.booked_micros for t in mine) / n
        lines.append(
            f"| {label} | {n} | {sum(t.recovered for t in mine)}/{n} "
            f"| {sum(t.escalated for t in mine)}/{n} | {sum(t.double_spends for t in mine)} "
            f"| {sum(bool(t.silent_loss_micros) for t in mine)} "
            f"| {sum(t.unknown_events for t in mine)} | {_usd(unbooked)} | {_usd(wasted)} |"
        )
    return "\n".join(lines)


def summary(trials: Sequence[Trial]) -> str:
    """The sentence under the table, from the same trials."""
    faulted = [t for t in trials if t.fault != "none"]
    verified = all(t.verified for t in faulted)
    still = not any(t.rerun_changed for t in faulted)
    return (
        f"Across {len(faulted)} faulted trials: {sum(t.recovered for t in faulted)} recovered, "
        f"{sum(t.escalated for t in faulted)} escalated cleanly, "
        f"{sum(t.double_spends for t in faulted)} double-spends, "
        f"{sum(bool(t.silent_loss_micros) for t in faulted)} silent losses, "
        f"{'every' if verified else 'NOT every'} ledger verified, and a further `resume` "
        f"{'changed nothing in any of them' if still else 'CHANGED a ledger or spent money'}."
    )


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        found = all_trials(Path(tmp))
        print(table(found), summary(found), sep="\n\n")
