"""The staged flow around the loop, end to end. One fake `claude` plays the boss, the worker and
every role: it tells them apart by the system prompt it is given, and reads what each should
return from files under HOME, so a test sets what every role answers, including a failed call.
Nothing here makes a model call."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import pytest

from boss.boss import load_prompt
from boss.cli import EXIT_FAILED, EXIT_INCOMPLETE, EXIT_INTERRUPTED, EXIT_OK, EXIT_USAGE, main
from boss.firm import FirmConfig
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.pipeline import Pipeline, RolesError, Setup, parse_roles, recorded_setup
from boss.roles import registry
from boss.roles.base import system_prompt
from boss.roles.judge import Calibration, CaseResult, judge_identity, load_rubric
from boss.rundir import RunPaths
from boss.termsheet import CheckSpec, Round, Task, TermSheet, TermSheetError

IDEA = (
    "Write rev.py with a function reverse(s) that returns the string s reversed. "
    "An empty string gives an empty string."
)
Q1 = "returns the string s reversed"
Q2 = "An empty string gives an empty string"
CHECK1 = "from rev import reverse\n\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
CHECK2 = "from rev import reverse\n\n\ndef test_empty():\n    assert reverse('') == ''\n"
GOOD = "def reverse(s):\n    return s[::-1]\n"
BOSS_DRAFT = {
    "tasks": [{"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]}],
    "checks": [{"description": "reverses a word", "task": "t1", "code": CHECK1}],
}
INIT = {
    "type": "system",
    "subtype": "init",
    "tools": ["Read", "Write", "Edit", "StructuredOutput"],
    "mcp_servers": [],
    "permissionMode": "dontAsk",
    "claude_code_version": "2.1.285",
    "session_id": "s-1",
}
USAGE = {"m": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 0}}

# Every call is answered from HOME/fake/<who>.json: one answer, or a list (the n-th call gets the
# n-th, the last one repeats). An answer is {"out": ..., "cost": ...} or {"fail": true, "cost": ...}
# (an API error that still cost something). "@artifact" in an output stands for a fragment of the
# text the model was asked to judge, so evidence can be scripted without knowing the text.
FAKE = f"""#!{sys.executable}
import hashlib, json, os, sys
home = os.environ["HOME"]
folder = os.path.join(home, "fake")
argv = sys.argv[1:]
say = lambda e: print(json.dumps(e), flush=True)
result = {{"type": "result", "subtype": "success", "is_error": False,
          "terminal_reason": "completed", "modelUsage": {USAGE!r}, "session_id": "s-1"}}


def nth(who):
    path = os.path.join(folder, "n_" + who)
    n = int(open(path).read()) if os.path.exists(path) else 0
    open(path, "w").write(str(n + 1))
    return n


def answer(who):
    path = os.path.join(folder, who + ".json")
    if not os.path.exists(path):
        return None
    scripted = json.load(open(path))
    n = nth(who)
    return scripted[min(n, len(scripted) - 1)] if isinstance(scripted, list) else scripted


def calls_so_far(who):
    path = os.path.join(folder, "n_" + who)
    return int(open(path).read()) if os.path.exists(path) else 0


def log(who, **extra):
    with open(os.path.join(folder, "calls.jsonl"), "a") as fh:
        fh.write(json.dumps({{"who": who, **extra}}) + "\\n")


def fill(value, fragment):
    if value == "@artifact":
        return fragment
    if isinstance(value, list):
        return [fill(v, fragment) for v in value]
    if isinstance(value, dict):
        return {{k: fill(v, fragment) for k, v in value.items()}}
    return value


if argv[argv.index("--output-format") + 1] == "json":   # the boss or a role
    system = argv[argv.index("--system-prompt") + 1]
    table = json.load(open(os.path.join(folder, "prompts.json")))
    who = table.get(hashlib.sha256(system.encode()).hexdigest(), "unknown")
    prompt = argv[-1]
    scripted = answer(who)
    log(who, unscripted=scripted is None, model=argv[argv.index("--model") + 1],
        thinking=os.environ.get("MAX_THINKING_TOKENS", "unset"))
    open(os.path.join(folder, "last_" + who + ".txt"), "w").write(prompt)
    if scripted is None or scripted.get("fail"):
        cost = (scripted or {{}}).get("cost", 0.002)
        say(result | {{"subtype": "error_during_execution", "is_error": True,
                      "api_error_status": 500, "terminal_reason": "api_error",
                      "total_cost_usd": cost}})
    else:
        body = prompt.split("<artifact>\\n")[-1].split("\\n</artifact>")[0]
        line = max((" ".join(l.split()) for l in body.splitlines()), key=len, default="")[:60]
        say(result | {{"total_cost_usd": scripted.get("cost", 0.004),
                      "structured_output": fill(scripted["out"], line)}})
else:                                                    # a worker slice
    say({INIT!r})
    flag = os.path.join(folder, "interrupt")   # empty: every slice; a number: that slice only
    if os.path.exists(flag) and open(flag).read() in ("", str(calls_so_far("worker"))):
        os.kill(os.getppid(), 2)  # Ctrl-C in the investor's terminal, mid-slice
        import time; time.sleep(30)
    step = answer("worker") or {{"files": {{"rev.py": {GOOD!r}}}}}
    log("worker")
    open(os.path.join(folder, "last_worker.txt"), "w").write(argv[-1])
    for name, text in step["files"].items():
        open(name, "w").write(text)
    cum = os.path.join(folder, "cum")   # the CLI reports a session's cumulative cost
    before = float(open(cum).read()) if "--resume" in argv and os.path.exists(cum) else 0.0
    total = before + step.get("cost", 0.006)
    open(cum, "w").write(repr(total))
    status = {{"status": step.get("status", "done"), "reason": step.get("reason", "wrote rev.py")}}
    if step.get("disputes"):
        status["disputed_checks"] = step["disputes"]
    say(result | {{"total_cost_usd": total, "structured_output": status}})
"""


def ok(out, cost=0.004):
    return {"out": out, "cost": cost}


def bad(cost=0.002):
    return {"fail": True, "cost": cost}


def story(n, priority, criteria):
    return {
        "id": f"S{n}",
        "as_a": "caller",
        "i_want": "reverse(s) to reverse a string",
        "so_that": "I get it backwards",
        "priority": priority,
        "criteria": [
            {
                "id": f"S{n}.{m}",
                "given": "a string",
                "when": "reverse is called",
                "then": f"it gives the result {m}",
                "source": source,
            }
            for m, source in enumerate(criteria, start=1)
        ],
    }


STORIES = {"stories": [story(1, "must", [Q1, Q2])]}
TWO_STORIES = {"stories": [story(1, "must", [Q1]), story(2, "should", [Q2])]}
ONE_QUOTED = {"stories": [story(1, "must", [Q1])]}


def design(stories=("S1",)):
    task = {
        "id": "t1",
        "brief": "Create rev.py with reverse(s).",
        "paths": ["rev.py"],
        "stories": list(stories),
        "interfaces": ["reverse(s: str) -> str"],
    }
    return {"tasks": [task]}


def checks_out(*criteria, codes=(CHECK1, CHECK2)):
    checks = [
        {"criteria": [c], "task": "t1", "description": f"checks {c}", "code": code}
        for c, code in zip(criteria, codes, strict=False)
    ]
    return {"checks": checks, "untestable": []}


def audit_out(*ids, verdict="consistent"):
    return {
        "verdicts": [
            {"check": i, "verdict": verdict, "quote": Q1, "why": f"{i} follows the idea"}
            for i in ids
        ]
    }


REVIEW_OK = {"missing": [], "misread": [], "verdict": "accept"}
REVIEW_MISSING = {
    "missing": [{"quote": Q2, "why": "no criterion tests the empty string"}],
    "misread": [],
    "verdict": "revise",
}
ADVICE = {
    "recommendation": "drop",
    "confidence": "medium",
    "quote": Q2,
    "why": "the idea is silent",
}


def judge_out(rubric_id, score=4):
    scores = [
        {"criterion": c.id, "score": score, "evidence": "@artifact"}
        for c in load_rubric(rubric_id).criteria
    ]
    return {"scores": scores, "summary": "reads fine"}


def prompt_table():
    table = {}
    for name, spec in registry().items():
        table[hashlib.sha256(system_prompt(spec).encode()).hexdigest()] = name
    for prompt in ("term_sheet_v1.md", "term_sheet_v2.md"):
        table[hashlib.sha256(load_prompt(prompt).encode()).hexdigest()] = "boss"
    return table


@dataclasses.dataclass
class Out:
    code: int
    transcript: list[tuple[str, str]]

    @property
    def said(self) -> list[str]:
        return [t for kind, t in self.transcript if kind == "say"]

    @property
    def text(self) -> str:
        return "\n".join(self.said)

    def index(self, kind: str, start: str) -> int:
        """Where in the conversation something was said or asked, or an assertion error."""
        for n, (k, t) in enumerate(self.transcript):
            if k == kind and start in t:
                return n
        raise AssertionError(f"no {kind} containing {start!r} in:\n{self.text}")


DEFAULT_ANSWERS = {"[a]pprove": "a", "Round": "y", "Add these": "y"}


class Fx:
    def __init__(self, tmp_path: Path) -> None:
        self.home = tmp_path
        self.folder = tmp_path / "fake"
        self.folder.mkdir()
        self.fake = tmp_path / "fake-claude"
        self.fake.write_text(FAKE)
        self.fake.chmod(0o755)
        self.project = tmp_path / "project"
        self.project.mkdir()
        (self.folder / "prompts.json").write_text(json.dumps(prompt_table()))
        self.set("boss", ok(BOSS_DRAFT))

    def set(self, who: str, answer) -> None:
        (self.folder / f"{who}.json").write_text(json.dumps(answer))

    def unset(self, who: str) -> None:
        (self.folder / f"{who}.json").unlink()

    def run(self, *argv: str, answers=None, **env) -> Out:
        replies = {k: v if isinstance(v, list) else [v] for k, v in DEFAULT_ANSWERS.items()}
        replies |= {k: v if isinstance(v, list) else [v] for k, v in (answers or {}).items()}
        transcript: list[tuple[str, str]] = []

        def ask(prompt: str) -> str:
            transcript.append(("ask", prompt))
            for prefix, queue in replies.items():
                if prompt.startswith(prefix):
                    reply = queue.pop(0) if len(queue) > 1 else queue[0]
                    if reply in (EOFError, KeyboardInterrupt):
                        raise reply
                    return reply
            raise AssertionError(f"unexpected question {prompt!r}")

        environ = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(self.home),
            "BOSS_CLAUDE_BIN": str(self.fake),
            **env,
        }
        code = main(
            [*argv, "--dir", str(self.project)],
            ask=ask,
            say=lambda t: transcript.append(("say", t)),
            environ=environ,
        )
        unscripted = [c["who"] for c in self.calls(full=True) if c.get("unscripted")]
        assert not unscripted, f"a model was called with no scripted answer: {unscripted}"
        return Out(code, transcript)

    def fund(self, *extra: str, budget="0.50", **kw) -> Out:
        return self.run("fund", IDEA, "--budget", budget, *extra, **kw)

    def calls(self, full=False):
        path = self.folder / "calls.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return rows if full else [r["who"] for r in rows]

    def last_prompt(self, who: str) -> str:
        return (self.folder / f"last_{who}.txt").read_text()

    @property
    def run_dir(self) -> Path:
        [run] = sorted((self.project / ".boss" / "runs").iterdir())
        return run

    def events(self, kind=None, actor=None):
        found = read_events(self.run_dir / "ledger.jsonl")
        return [
            e
            for e in found
            if (kind is None or e.event is kind) and (actor is None or e.actor == actor)
        ]

    def role_calls(self, name=None):
        found = self.events(EventType.ROLE_CALL)
        return [e for e in found if name is None or e.actor == f"role:{name}"]


@pytest.fixture
def fx(tmp_path):
    return Fx(tmp_path)


def call_facts(event):
    d = event.data
    return d["outcome"], d["result"], event.cost_micros


STAGE_1 = ("product_manager", "user_agent", "system_designer", "tester", "check_auditor", "judge")


def script_stage_1(fx, *, stories=STORIES, design_out=None, tests=None, audit=("c01", "c02")):
    fx.set("product_manager", ok(stories))
    fx.set("user_agent", ok(REVIEW_OK))
    fx.set("system_designer", ok(design_out or design()))
    fx.set("tester", ok(tests or checks_out("S1.1", "S1.2")))
    fx.set("check_auditor", ok(audit_out(*audit)))
    fx.set("judge", ok(judge_out("stories")))


# --- no roles: today's run, exactly -------------------------------------------------------------

# What `boss fund` printed before roles existed, captured from that code with the same fake, the run
# id and the project folder replaced by placeholders.
TODAYS_OUTPUT = f"""Run RUN: drafting the term sheet...
TERM SHEET
Idea: {IDEA}
Budget: $0.5 (estimated cost, not a bill)
Round 1: $0.5, next unlocks at 1 passing checks

Task t1 (owns rev.py):
  Create rev.py with reverse(s).

Check c01 [t1] reverses a word
--- PROJECT/.boss/runs/RUN/checks/test_c01.py
{CHECK1.rstrip()}
Approved. Hiring a worker...
w1 slice 1 on t1: 1/1 checks pass; round 1 has spent $0.006 of $0.5
BOARD REPORT  run RUN

Approved by investor: yes
Round 1: 1/1 checks passed, next round unlocked

Checks
  c01  passed   1 passed

Spend (estimated by the CLI, not a bill)
  boss         $0.0040   tokens in 10 / out 5 / cached 0
  worker:w1    $0.0060   tokens in 10 / out 5 / cached 0
  total        $0.0100   tokens in 20 / out 10 / cached 0

Workers
  w1 on t1 (haiku): completed, status done: "wrote rev.py", 1 slice(s)

Run folder: PROJECT/.boss/runs/RUN  (built files: PROJECT/.boss/runs/RUN/product)"""


def test_with_no_roles_the_ledger_and_the_output_are_what_they_always_were(fx):
    out = fx.fund()
    assert out.code == EXIT_OK
    shown = out.text.replace(fx.run_dir.name, "RUN").replace(str(fx.project.resolve()), "PROJECT")
    assert shown == TODAYS_OUTPUT
    assert [(e.actor, str(e.event)) for e in fx.events()] == [
        ("boss", "boss_call"),
        ("investor", "approved"),
        ("boss", "started"),
        ("boss", "hired"),
        ("worker:w1", "slice_start"),
        ("worker:w1", "slice_end"),
        ("gate", "check_result"),
        ("boss", "round_closed"),
        ("gate", "check_result"),
    ]
    started = fx.events(EventType.STARTED)[0]
    assert set(started.data) == {"config"}  # no roles field appears on a run without roles
    assert [t for k, t in out.transcript if k == "ask"] == [
        "[a]pprove, [r]eject, or [e]dit files and re-check? "
    ]
    assert fx.calls() == ["boss", "worker"]


def test_no_roles_asks_the_boss_once_and_shows_no_notes(fx):
    out = fx.fund()
    sheet = out.index("say", "TERM SHEET")
    assert (
        out.transcript[sheet + 1][0] == "ask"
    )  # nothing is shown between the sheet and the question


# --- choosing roles: refused before anything is spent -------------------------------------------


@pytest.mark.parametrize(
    ("roles", "message"),
    [
        ("wizard", "Unknown role(s) 'wizard'. Known roles: check_auditor, consultant, critic"),
        ("product_manager,wizard,elf", "'elf', 'wizard'"),
        ("user_agent", "user_agent needs product_manager"),
        ("tester", "tester needs product_manager and system_designer"),
        ("tester,product_manager", "tester needs product_manager and system_designer"),
        ("system_designer,product_manager", "system_designer needs tester"),
        ("system_designer", "system_designer needs tester"),
    ],
)
def test_roles_that_cannot_run_together_are_a_usage_error_before_any_spend(fx, roles, message):
    out = fx.fund("--roles", roles)
    assert out.code == EXIT_USAGE and message in out.text
    assert not (fx.project / ".boss").exists() and fx.calls() == []


def test_the_role_list_is_sorted_deduplicated_and_all_means_every_role():
    known = registry()
    assert parse_roles("tester, product_manager,system_designer,tester", known) == (
        "product_manager",
        "system_designer",
        "tester",
    )
    assert parse_roles("all", known) == tuple(sorted(known))
    assert parse_roles("  ", known) == ()
    with pytest.raises(RolesError):
        parse_roles("all,nobody", known)


def test_the_chosen_roles_are_on_the_started_event_the_config_stays_as_it_was(fx):
    fx.set("check_auditor", ok(audit_out("c01")))
    fx.fund("--roles", "check_auditor", "--boss-model", "sonnet", "--boss-thinking", "0")
    [started] = fx.events(EventType.STARTED)
    roles = {"names": ["check_auditor"], "model": "sonnet", "thinking_tokens": 0}
    assert started.data["roles"] == roles
    assert recorded_setup(fx.events()) == Setup(("check_auditor",), "sonnet", 0)
    assert recorded_setup([]) is None
    assert set(started.data["config"]) == {f.name for f in dataclasses.fields(FirmConfig)}


# --- each stage-1 role alone --------------------------------------------------------------------


def test_the_product_manager_alone_saves_stories_and_shows_what_no_criterion_quotes(fx):
    fx.set("product_manager", ok(ONE_QUOTED))
    out = fx.fund("--roles", "product_manager")
    assert out.code == EXIT_OK
    saved = json.loads((fx.run_dir / "stories.json").read_text())
    assert saved["stories"][0]["criteria"][0]["source"] == Q1
    assert out.index("say", "Stories the product manager wrote") > out.index("say", "TERM SHEET")
    assert "S1.1 given a string; when reverse is called" in out.text
    assert (
        "Parts of your idea no acceptance criterion quotes:\n  - An empty string gives" in out.text
    )
    [call] = fx.role_calls("product_manager")
    assert call.actor == "role:product_manager" and call.cost_micros == 4_000
    assert call_facts(call) == ("completed", "ok", 4_000)
    assert call.data["role"] == "product_manager" and call.round == 0
    assert (call.tokens_in, call.tokens_out) == (10, 5)
    assert [e.event for e in fx.events()][:2] == [EventType.ROLE_CALL, EventType.BOSS_CALL]
    assert fx.calls()[:2] == ["product_manager", "boss"]  # the boss still drafts alone


def test_when_every_sentence_is_quoted_the_investor_is_told_so(fx):
    fx.set("product_manager", ok(STORIES))
    out = fx.fund("--roles", "product_manager")
    assert "Every part of your idea is quoted by an acceptance criterion." in out.text
    assert "Parts of your idea no acceptance criterion quotes" not in out.text


def test_the_user_agent_reads_the_stories_and_its_opinion_is_marked_as_one(fx):
    fx.set("product_manager", ok(ONE_QUOTED))
    fx.set("user_agent", ok(REVIEW_MISSING))
    out = fx.fund("--roles", "product_manager,user_agent")
    assert "User agent's opinion of the stories, unverified: revise" in out.text
    assert f'  missing: "{Q2}" | why: no criterion tests the empty string' in out.text
    [call] = fx.role_calls("user_agent")
    assert call_facts(call) == ("completed", "ok", 4_000) and call.actor == "role:user_agent"
    assert "S1.1" in fx.last_prompt("user_agent")  # it was shown the stories, not only the idea


def test_a_user_agent_that_finds_nothing_says_so_and_only_a_success_may(fx):
    fx.set("product_manager", ok(STORIES))
    fx.set("user_agent", ok(REVIEW_OK))
    out = fx.fund("--roles", "product_manager,user_agent")
    assert "unverified: accept; it found nothing missing or misread." in out.text


def test_the_check_auditor_alone_puts_one_opinion_per_check_under_the_sheet(fx):
    fx.set("check_auditor", ok(audit_out("c01", verdict="unsupported")))
    out = fx.fund("--roles", "check_auditor")
    assert out.index("say", "Check auditor's opinion of each check") > out.index(
        "say", "TERM SHEET"
    )
    assert "c01: auditor's opinion, unverified: not stated in the idea" in out.text
    [call] = fx.role_calls("check_auditor")
    assert call_facts(call) == ("completed", "ok", 4_000)
    assert call.data["detail"] == "1 of 1 checks flagged"
    assert fx.calls() == ["boss", "check_auditor", "worker"]  # it audits the sheet the boss drafted


def test_the_judge_scores_the_stories_and_says_it_is_uncalibrated(fx):
    fx.set("product_manager", ok(STORIES))
    fx.set("judge", ok(judge_out("stories")))
    out = fx.fund("--roles", "product_manager,judge")
    assert "Judge's score of the stories (advisory, gates nothing):" in out.text
    assert (
        "stories v1 by haiku: mean 4.0 of 5 (uncalibrated: advisory only, do not act on it)"
        in out.text
    )
    [call] = fx.role_calls("judge")
    assert call.data["rubric"] == "stories" and call.data["calibrated"] is False
    prompt = fx.last_prompt("judge")
    assert f"<context>\n{IDEA}\n</context>" in prompt and "S1.1" in prompt


def test_a_judge_with_no_stories_has_nothing_to_score_and_is_not_called(fx):
    out = fx.fund("--roles", "judge")
    assert out.code == EXIT_OK and fx.role_calls() == [] and "judge" not in fx.calls()


# --- calibration: used only when it covers this judge -------------------------------------------


def write_calibration(fx, *, model="haiku", agree=True, rubric_version=None):
    rubric = load_rubric("stories")
    prompt, skills = judge_identity()
    human_scores = [1, 2, 3, 4, 5]
    results = []
    for n in range(20):
        human = {c.id: human_scores[(n + k) % 5] for k, c in enumerate(rubric.criteria)}
        judged = human if agree else {c: 6 - s for c, s in human.items()}
        results.append(CaseResult(f"case{n}", human, judged))
    calibration = Calibration(
        "stories", rubric_version or rubric.version, model, prompt, skills, "0" * 64, tuple(results)
    )
    path = fx.project / ".boss" / "calibration" / "stories.json"
    path.parent.mkdir(parents=True)
    calibration.save(path)
    return path


def judged_line(fx):
    fx.set("product_manager", ok(STORIES))
    fx.set("judge", ok(judge_out("stories")))
    out = fx.fund("--roles", "product_manager,judge")
    return out, fx.role_calls("judge")[0]


def test_a_calibration_that_covers_this_judge_and_meets_the_bar_makes_the_score_calibrated(fx):
    write_calibration(fx)
    out, call = judged_line(fx)
    assert "mean 4.0 of 5 (calibrated)" in out.text and call.data["calibrated"] is True


@pytest.mark.parametrize(
    "variant", [{"model": "opus"}, {"rubric_version": 9}, {"agree": False}], ids=str
)
def test_a_calibration_for_another_judge_or_below_the_bar_leaves_it_uncalibrated(fx, variant):
    write_calibration(fx, **variant)
    out, call = judged_line(fx)
    assert "(uncalibrated: advisory only, do not act on it)" in out.text
    assert call.data["calibrated"] is False


def test_an_unreadable_calibration_file_is_said_and_not_used(fx):
    path = fx.project / ".boss" / "calibration" / "stories.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    out, call = judged_line(fx)
    assert "is unusable" in out.text and "(uncalibrated: advisory only" in out.text
    assert call.data["calibrated"] is False


# --- the staged draft replaces the boss's ------------------------------------------------------


def test_the_staged_draft_replaces_the_boss_draft_and_shows_the_coverage_matrix(fx):
    script_stage_1(fx)
    fx.unset("boss")  # a boss call now would be an unscripted model call, and fail the test
    out = fx.fund("--roles", "product_manager,system_designer,tester")
    assert out.code == EXIT_OK
    assert fx.events(EventType.BOSS_CALL) == [] and "boss" not in fx.calls()
    assert fx.calls()[:3] == ["product_manager", "system_designer", "tester"]
    matrix = "Which check covers which acceptance criterion:"
    assert out.index("say", matrix) > out.index("say", "TERM SHEET")
    assert "2 criteria: 2 covered, 0 untestable, 0 with no check" in out.text
    sheet = json.loads((fx.run_dir / "term_sheet.json").read_text())
    assert [c["criteria"] for c in sheet["checks"]] == [["S1.1"], ["S1.2"]]
    assert sheet["approved_by_investor"] is True
    assert "Public interface, exactly:\n- reverse(s: str) -> str" in sheet["tasks"][0]["brief"]
    facts = {e.actor: call_facts(e) for e in fx.role_calls()}
    assert facts == {
        "role:product_manager": ("completed", "ok", 4_000),
        "role:system_designer": ("completed", "ok", 4_000),
        "role:tester": ("completed", "ok", 4_000),
    }


def test_the_approval_covers_the_staged_sheet_and_its_check_files(fx):
    script_stage_1(fx)
    fx.fund("--roles", "product_manager,system_designer,tester")
    [approved] = fx.events(EventType.APPROVED)
    assert set(approved.data["hashes"]) == {"term_sheet", "test_c01.py", "test_c02.py"}
    assert approved.actor == "investor"


def test_more_rounds_are_planned_by_story_priority_when_the_sheet_is_staged(fx):
    script_stage_1(fx, stories=TWO_STORIES, design_out=design(("S1", "S2")))
    fx.set("tester", ok(checks_out("S1.1", "S2.1")))
    fx.fund("--roles", "product_manager,system_designer,tester", "--rounds", "2")
    sheet = json.loads((fx.run_dir / "term_sheet.json").read_text())
    assert [(r["n"], r["unlock_checks"]) for r in sheet["rounds"]] == [(1, 1), (2, 2)]
    assert sum(r["budget_micros"] for r in sheet["rounds"]) == 500_000 == sheet["budget_micros"]
    assert fx.events(EventType.BOSS_CALL) == []


def test_the_boss_still_splits_a_rounds_budget_when_it_drafts_alone(fx):
    two = {"description": "empty gives empty", "task": "t1", "code": CHECK2}
    fx.set("boss", ok(BOSS_DRAFT | {"checks": [*BOSS_DRAFT["checks"], two]}))
    fx.set("check_auditor", ok(audit_out("c01", "c02")))
    fx.fund("--roles", "check_auditor", "--rounds", "2")
    sheet = json.loads((fx.run_dir / "term_sheet.json").read_text())
    assert [(r["n"], r["unlock_checks"]) for r in sheet["rounds"]] == [(1, 1), (2, 2)]


# --- notes bind nothing --------------------------------------------------------------------------


def test_notes_are_shown_under_the_sheet_and_do_not_change_what_is_approved(fx):
    fx.fund()
    plain = fx.events(EventType.APPROVED)[0].data["hashes"]
    (fx.home / "with-notes").mkdir()
    other = Fx(fx.home / "with-notes")
    other.set("product_manager", ok(STORIES))
    other.set("user_agent", ok(REVIEW_MISSING))
    other.set("check_auditor", ok(audit_out("c01", verdict="contradicts")))
    out = other.fund("--roles", "product_manager,user_agent,check_auditor")
    asked = out.index("ask", "[a]pprove")
    for note in (
        "Stories the product manager wrote",
        "User agent's opinion",
        "Check auditor's opinion",
    ):
        assert out.index("say", "TERM SHEET") < out.index("say", note) < asked
    assert other.events(EventType.APPROVED)[0].data["hashes"] == plain


# --- a role that fails: spend booked, the investor told, never an empty opinion ----------------

DESIGN_ROLES = "product_manager,user_agent,system_designer,tester"


def told(out, start):
    """The first line said that starts with `start` (a failure is said at once, and again under
    the sheet)."""
    return next(t for t in out.said if t.startswith(start))


def test_when_the_product_manager_fails_the_boss_drafts_alone_and_the_investor_is_told(fx):
    script_stage_1(fx)
    fx.set("product_manager", bad(0.003))
    out = fx.fund("--roles", DESIGN_ROLES)
    assert out.code == EXIT_OK
    assert fx.calls()[:2] == ["product_manager", "boss"]  # no user agent, designer or tester
    assert set(fx.calls()) == {"product_manager", "boss", "worker"}
    [call] = fx.role_calls()
    assert call.actor == "role:product_manager" and call_facts(call) == (
        "api_error",
        "failed",
        3_000,
    )
    assert "api_error" in call.data["detail"]
    assert "The product_manager failed (" in told(out, "The product_manager failed")
    assert "the run goes on without its output." in out.text
    assert (
        "There are no stories, so the staged draft cannot run: the boss drafts alone." in out.text
    )
    assert "product_manager: FAILED (" in out.text and "not a clean result" in out.text
    assert out.index("say", "product_manager: FAILED") > out.index("say", "TERM SHEET")
    assert len(fx.events(EventType.BOSS_CALL)) == 1 and not (fx.run_dir / "stories.json").exists()


def test_stories_that_fail_their_gate_are_paid_for_and_are_not_used(fx):
    bad_stories = {"stories": [story(1, "must", ["a sentence the idea never says"])]}
    fx.set("product_manager", ok(bad_stories, cost=0.005))
    out = fx.fund("--roles", "product_manager")
    [call] = fx.role_calls()
    assert call_facts(call) == ("completed", "failed", 5_000)
    assert "is not a fragment of the idea" in call.data["detail"]
    assert "Stories the product manager wrote" not in out.text
    assert "product_manager: FAILED" in out.text


def test_when_the_designer_fails_the_tester_is_not_asked_and_the_boss_drafts(fx):
    script_stage_1(fx)
    fx.set("system_designer", bad(0.003))
    out = fx.fund("--roles", "product_manager,system_designer,tester")
    assert fx.calls() == ["product_manager", "system_designer", "boss", "worker"]
    facts = {e.actor: call_facts(e) for e in fx.role_calls()}
    assert facts == {
        "role:product_manager": ("completed", "ok", 4_000),
        "role:system_designer": ("api_error", "failed", 3_000),
    }
    assert "The staged draft failed at system_designer (" in out.text
    assert "the boss drafts alone instead." in told(out, "The staged draft failed")
    assert len(fx.events(EventType.BOSS_CALL)) == 1
    assert "Which check covers which acceptance criterion" not in out.text


def test_when_the_tester_fails_the_designers_paid_call_is_booked_as_unused(fx):
    script_stage_1(fx)
    fx.set("tester", bad(0.002))
    out = fx.fund("--roles", "product_manager,system_designer,tester")
    assert fx.calls() == ["product_manager", "system_designer", "tester", "boss", "worker"]
    facts = {e.actor: call_facts(e) for e in fx.role_calls()}
    assert facts == {
        "role:product_manager": ("completed", "ok", 4_000),
        "role:system_designer": ("completed", "unused", 4_000),
        "role:tester": ("api_error", "failed", 2_000),
    }
    assert "The staged draft failed at tester (" in out.text
    assert sorted(p.name for p in (fx.run_dir / "checks").iterdir()) == ["test_c01.py"]
    assert out.code == EXIT_OK


def test_a_tester_whose_check_passes_on_nothing_fails_assembly_and_leaves_no_files_behind(fx):
    script_stage_1(fx)
    always = "def test_x():\n    assert True\n"
    fx.set("tester", ok(checks_out("S1.1", "S1.2", codes=(CHECK1, always))))
    out = fx.fund("--roles", "product_manager,system_designer,tester")
    facts = {e.actor: call_facts(e) for e in fx.role_calls()}
    assert facts["role:system_designer"] == ("completed", "unused", 4_000)
    assert facts["role:tester"] == ("completed", "unused", 4_000)
    assert "The staged draft failed at assembly (check c02 passes on an empty workspace" in out.text
    assert sorted(p.name for p in (fx.run_dir / "checks").iterdir()) == ["test_c01.py"]
    assert "boss" in fx.calls() and out.code == EXIT_OK


@pytest.mark.parametrize(
    ("role", "roles"),
    [
        ("user_agent", "product_manager,user_agent"),
        ("check_auditor", "check_auditor"),
        ("judge", "product_manager,judge"),
    ],
)
def test_a_failed_advisory_role_is_a_note_that_says_it_failed_never_no_problems_found(
    fx, role, roles
):
    script_stage_1(fx)
    fx.set("boss", ok(BOSS_DRAFT))
    fx.set(role, bad(0.002))
    out = fx.fund("--roles", roles)
    assert out.code == EXIT_OK
    [call] = fx.role_calls(role)
    assert call_facts(call) == ("api_error", "failed", 2_000)
    assert out.index("say", f"{role}: FAILED") > out.index("say", "TERM SHEET")
    assert f"The {role} failed (" in out.text
    assert not any(
        w in out.text for w in ("found nothing", "opinion of each check", "score of the")
    )


def test_a_judge_whose_evidence_is_not_in_the_artifact_is_a_failed_judge(fx):
    script_stage_1(fx)
    rubric = load_rubric("stories")
    scores = [
        {"criterion": c.id, "score": 5, "evidence": "made up words here"} for c in rubric.criteria
    ]
    fx.set("judge", ok({"scores": scores, "summary": "great"}))
    out = fx.fund("--roles", "product_manager,judge")
    [call] = fx.role_calls("judge")
    assert call_facts(call) == ("completed", "failed", 4_000)
    assert "judge: FAILED" in out.text and "mean 5" not in out.text


def test_rejecting_the_sheet_keeps_every_role_call_on_the_ledger_and_hires_nobody(fx):
    script_stage_1(fx)
    out = fx.fund("--roles", ",".join(STAGE_1), answers={"[a]pprove": "r"})
    assert out.code == EXIT_FAILED and "Rejected. Nothing was funded." in out.text
    kinds = [str(e.event) for e in fx.events()]
    assert kinds == ["role_call"] * 6 + ["stopped"]
    assert not (fx.run_dir / "workspaces").exists()


def test_the_report_total_is_the_boss_plus_every_role_plus_every_worker(fx):
    script_stage_1(fx)
    out = fx.fund("--roles", ",".join(STAGE_1))
    assert out.code == EXIT_OK
    events = fx.events()
    boss = sum(e.cost_micros for e in events if e.actor == "boss")
    roles = sum(e.cost_micros for e in fx.role_calls())
    workers = sum(e.cost_micros for e in events if e.actor.startswith("worker:"))
    assert (boss, roles, workers) == (0, 6 * 4_000, 6_000)  # staged: the boss was never asked
    assert sum(e.cost_micros for e in events) == boss + roles + workers
    assert "  total        $0.0300" in out.text
    for role in STAGE_1:
        assert f"  role:{role}" in out.text and "$0.0040" in out.text


# --- stage 2: a consultant's line before the investor rules on a dispute -----------------------

WRONG = "from rev import reverse\n\n\ndef test_same():\n    assert reverse('ab') == 'ab'\n"
DISPUTE = {"check": "c02", "reason": "the idea says reverse, and this check wants the same string"}


def with_a_wrong_check(fx):
    """The boss drafts one right check and one that contradicts the idea; the worker passes the
    first and disputes the second, so the investor is asked to rule."""
    wrong = {"description": "leaves ab as it is", "task": "t1", "code": WRONG}
    fx.set("boss", ok(BOSS_DRAFT | {"checks": [*BOSS_DRAFT["checks"], wrong]}))
    fx.set("worker", {"files": {"rev.py": GOOD}, "disputes": [DISPUTE]})


def test_the_consultants_line_is_shown_before_the_dispute_question(fx):
    with_a_wrong_check(fx)
    fx.set("consultant", ok(ADVICE))
    out = fx.fund("--roles", "consultant", answers={"Task": "d"})
    assert out.code == EXIT_OK
    line = "consultant's opinion, unverified: drop this check (confidence medium)"
    assert out.index("say", line) < out.index("ask", "Task t1: w1 disputes check c02")
    assert f'idea: "{Q2}" | why: the idea is silent' in out.text
    [call] = fx.role_calls("consultant")
    assert call.actor == "role:consultant" and call_facts(call) == ("completed", "ok", 4_000)
    assert call.data["check"] == "c02" and call.data["detail"] == "drop c02" and call.round == 0
    prompt = fx.last_prompt("consultant")
    assert "assert reverse('ab') == 'ab'" in prompt and DISPUTE["reason"] in prompt
    assert IDEA in prompt and "leaves ab as it is" in prompt
    kinds = [e.event for e in fx.events()]
    assert kinds.index(EventType.ROLE_CALL) < kinds.index(EventType.RULED)
    [ruled] = fx.events(EventType.RULED)
    assert ruled.actor == "investor" and ruled.data["ruling"] == "dropped"  # the investor decided


def test_a_consultant_that_fails_does_not_block_the_ruling_and_the_investor_is_told(fx):
    with_a_wrong_check(fx)
    fx.set("consultant", bad(0.003))
    out = fx.fund("--roles", "consultant", answers={"Task": "d"})
    assert out.code == EXIT_OK
    [call] = fx.role_calls("consultant")
    assert call_facts(call) == ("api_error", "failed", 3_000) and call.data["check"] == "c02"
    told_at = out.index("say", "The consultant failed (")
    assert told_at < out.index("ask", "Task t1: w1 disputes check c02")
    assert "consultant's opinion" not in out.text
    assert fx.events(EventType.RULED)[0].data["ruling"] == "dropped"


def test_a_consultant_whose_quote_is_not_in_the_idea_is_a_failed_consultant(fx):
    with_a_wrong_check(fx)
    fx.set("consultant", ok(ADVICE | {"quote": "the idea says nothing of the kind"}, cost=0.005))
    out = fx.fund("--roles", "consultant", answers={"Task": "d"})
    [call] = fx.role_calls("consultant")
    assert call_facts(call) == ("completed", "failed", 5_000)
    assert "consultant's opinion" not in out.text and "The consultant failed (" in out.text
    assert out.code == EXIT_OK


def test_without_the_consultant_a_dispute_goes_straight_to_the_investor(fx):
    with_a_wrong_check(fx)
    out = fx.fund(answers={"Task": "d"})
    assert out.code == EXIT_OK and "consultant" not in fx.calls() and "Asking the" not in out.text
    assert fx.role_calls() == [] and "opinion" not in out.text


def test_the_consultant_is_not_called_when_nothing_is_disputed(fx):
    fx.set("consultant", ok(ADVICE))
    out = fx.fund("--roles", "consultant")
    assert out.code == EXIT_OK and fx.role_calls() == [] and "consultant" not in fx.calls()


def test_resume_takes_its_roles_from_the_ledger_and_does_not_run_stage_one_again(fx):
    script_stage_1(fx)
    fx.set("tester", ok(checks_out("S1.1", "S1.2", codes=(CHECK1, WRONG))))
    fx.set("consultant", ok(ADVICE))
    (fx.folder / "interrupt").write_text("")
    roles = "product_manager,system_designer,tester,consultant"
    out = fx.fund("--roles", roles)
    assert out.code == EXIT_INTERRUPTED
    before = fx.calls()
    assert before == ["product_manager", "system_designer", "tester"]
    (fx.folder / "interrupt").unlink()
    fx.set("worker", {"files": {"rev.py": GOOD}, "disputes": [DISPUTE]})
    out = fx.run("resume", answers={"Task": "d"})
    assert out.code == EXIT_OK
    assert fx.calls()[:3] == before  # no product manager, designer or tester again
    assert fx.calls().count("consultant") == 1
    assert out.index("say", "consultant's opinion, unverified") < out.index("ask", "Task t1:")
    [started] = fx.events(EventType.STARTED)
    assert started.data["roles"]["names"] == sorted(roles.split(","))


# --- stage 3: a critic's verified findings can become an investor-approved fix round -----------

BUGGY = "def reverse(s):\n    return s[::-1] if len(s) < 5 else s\n"
LONG = "from rev import reverse\n\n\ndef test_long():\n    assert reverse('abcdef') == 'fedcba'\n"
LENIENT = (
    "def test_long():\n    try:\n        from rev import reverse\n    except ImportError:\n"
    "        return\n    assert reverse('abcdef') == 'fedcba'\n"
)  # fails on the product, but passes when there is no product at all
PASSES = "from rev import reverse\n\n\ndef test_short():\n    assert reverse('ab') == 'ba'\n"
CLAIM = "reverse leaves strings of five or more characters as they are"
QUESTION = "Add these 1 checks and fund a fix round of $0.3? [y]es / [n]o "


def finding(code=LONG, *, severity="high", claim=CLAIM, quote=Q1):
    return {"severity": severity, "claim": claim, "quote": quote, "test_code": code}


def critic_finds(fx, *findings, cost=0.004):
    """The worker delivers a product the approved check misses; the critic's tests are `findings`;
    a second slice, if one is funded, fixes the product."""
    fx.set("worker", [{"files": {"rev.py": BUGGY}}, {"files": {"rev.py": GOOD}}])
    fx.set("critic", ok({"findings": list(findings)}, cost=cost))


def approvals(fx):
    return fx.events(EventType.APPROVED)


def asked(out, start):
    return [t for k, t in out.transcript if k == "ask" and t.startswith(start)]


def product_verdicts(fx):
    results = fx.events(EventType.CHECK_RESULT)
    return {e.data["check"]: e.data["status"] for e in results if e.data.get("scope") == "product"}


def test_a_verified_finding_the_investor_approves_is_fixed_by_a_worker_and_recorded(fx):
    critic_finds(fx, finding())
    out = fx.fund("--roles", "critic")
    assert out.code == EXIT_OK
    assert f"Critic verified a finding (high): {CLAIM}" in out.text
    assert (
        "Critic: 1 finding(s) verified by running their tests on the product, 0 rejected."
        in out.text
    )
    [call] = fx.role_calls("critic")
    assert call.actor == "role:critic" and call_facts(call) == ("completed", "ok", 4_000)
    assert (call.data["verified"], call.data["rejected"], call.round) == (1, 0, 0)
    # the investor reads the check they are asked to approve, then is asked once
    shown = out.index("say", "Check c02 [t1]")
    assert shown < out.index("ask", QUESTION) < out.index("say", "Approved. Funding a worker")
    assert "assert reverse('abcdef') == 'fedcba'" in out.text
    assert asked(out, "Add these") == [QUESTION]
    # the amendment: the investor's approval of exactly the amended sheet, adding c02, in round 2
    first, amendment = approvals(fx)
    assert amendment.actor == "investor" and amendment.round == 2
    assert set(amendment.data) == {"hashes", "round", "added_checks"}
    assert amendment.data["round"] == 2 and amendment.data["added_checks"] == ["c02"]
    assert set(amendment.data["hashes"]) == {"term_sheet", "test_c01.py", "test_c02.py"}
    assert amendment.data["hashes"]["test_c01.py"] == first.data["hashes"]["test_c01.py"]
    sheet = json.loads((fx.run_dir / "term_sheet.json").read_text())
    assert sheet["approved_by_investor"] is True and sheet["budget_micros"] == 500_000 + 300_000
    assert [c["id"] for c in sheet["checks"]] == ["c01", "c02"]
    assert sheet["checks"][1]["description"] == CLAIM and sheet["checks"][1]["task"] == "t1"
    rounds = [(r["n"], r["budget_micros"], r["unlock_checks"]) for r in sheet["rounds"]]
    assert rounds == [(1, 500_000, 1), (2, 300_000, 2)]
    assert (fx.run_dir / "checks" / "test_c02.py").read_text() == LONG
    assert (fx.run_dir / "critic-1" / "critic_checks").is_dir()  # its scratch is in the run folder
    # a worker was funded, told of the new check, and fixed the product
    assert fx.calls() == ["boss", "worker", "critic", "worker"]
    assert (fx.run_dir / "product" / "rev.py").read_text() == GOOD
    assert "--- check c02" in (fx.folder / "last_worker.txt").read_text()
    assert product_verdicts(fx) == {"c01": "passed", "c02": "passed"}
    assert fx.events(EventType.SLICE_END)[-1].round == 2
    assert "w1 slice 2 on t1: 2/2 checks pass; round 2 has spent" in out.text
    assert "  c02  passed" in out.text and asked(out, "Round") == []  # the amendment funded it


@pytest.mark.parametrize("answer", ["y", "yes", "a", "approve", " YES "])
def test_every_way_the_firm_accepts_a_yes_is_a_yes_here(fx, answer):
    critic_finds(fx, finding())
    out = fx.fund("--roles", "critic", answers={"Add these": answer})
    assert out.code == EXIT_OK and len(approvals(fx)) == 2


@pytest.mark.parametrize("answer", ["n", "no", "", "maybe", EOFError])
def test_anything_but_a_yes_is_a_no_and_the_findings_stay_in_the_report(fx, answer):
    critic_finds(fx, finding())
    out = fx.fund("--roles", "critic", answers={"Add these": answer})
    assert out.code == EXIT_OK  # the product already passes every approved check
    assert "No fix round. The findings are in the report only." in out.text
    assert len(approvals(fx)) == 1 and fx.calls() == ["boss", "worker", "critic"]
    assert sorted(p.name for p in (fx.run_dir / "checks").iterdir()) == ["test_c01.py"]
    sheet = json.loads((fx.run_dir / "term_sheet.json").read_text())
    assert len(sheet["checks"]) == 1 and len(sheet["rounds"]) == 1
    assert sheet["budget_micros"] == 500_000
    assert fx.role_calls("critic")[0].data["verified"] == 1  # on the ledger, so in the report


def test_ctrl_c_at_the_question_is_an_interruption_and_a_resume_does_not_ask_again(fx):
    critic_finds(fx, finding())
    out = fx.fund("--roles", "critic", answers={"Add these": KeyboardInterrupt})
    assert out.code == EXIT_INTERRUPTED and "continue with `boss resume" in out.text
    assert len(approvals(fx)) == 1 and len(fx.role_calls("critic")) == 1
    assert sorted(p.name for p in (fx.run_dir / "checks").iterdir()) == ["test_c01.py"]
    before = fx.events()
    out = fx.run("resume")  # the findings are not offered again: they wait in the critic-1 folder
    assert out.code == EXIT_OK and asked(out, "Add these") == [] and fx.events() == before


def test_review_cycles_zero_reports_the_findings_and_asks_nothing(fx):
    critic_finds(fx, finding())
    out = fx.fund("--roles", "critic", "--review-cycles", "0")
    assert out.code == EXIT_OK and f"Critic verified a finding (high): {CLAIM}" in out.text
    assert "--review-cycles is 0" in out.text and asked(out, "Add these") == []
    assert len(approvals(fx)) == 1 and fx.calls() == ["boss", "worker", "critic"]


def test_one_review_cycle_means_the_critic_is_not_asked_again_after_the_fix_round(fx):
    critic_finds(fx, finding())
    fx.fund("--roles", "critic")
    assert fx.calls().count("critic") == 1 and len(fx.role_calls("critic")) == 1


def test_two_review_cycles_let_the_critic_look_again_after_the_first_fix(fx):
    critic_finds(fx, finding())
    fx.set("critic", [ok({"findings": [finding()]}), ok({"findings": []})])
    out = fx.fund("--roles", "critic", "--review-cycles", "2")
    assert out.code == EXIT_OK and fx.calls().count("critic") == 2
    assert [e.data["cycle"] for e in fx.role_calls("critic")] == [1, 2]
    assert (fx.run_dir / "critic-1").is_dir() and (fx.run_dir / "critic-2").is_dir()
    assert "Critic: 0 finding(s) verified" in out.text
    assert len(approvals(fx)) == 2 and len(asked(out, "Add these")) == 1  # nothing new to add


def test_a_finding_whose_check_would_pass_on_an_empty_workspace_is_dropped_with_a_line(fx):
    critic_finds(fx, finding(LENIENT, claim="a lenient test"), finding())
    out = fx.fund("--roles", "critic")
    assert out.code == EXIT_OK
    dropped = "Finding not proposed as a check (a lenient test): it does not fail on an empty"
    assert dropped in out.text
    assert asked(out, "Add these") == [QUESTION]  # one check, not two
    assert approvals(fx)[1].data["added_checks"] == ["c03"]  # c02 was the dropped one
    assert sorted(p.name for p in (fx.run_dir / "checks").iterdir()) == [
        "test_c01.py",
        "test_c03.py",
    ]
    assert (
        json.loads((fx.run_dir / "term_sheet.json").read_text())["rounds"][1]["unlock_checks"] == 2
    )


def test_when_every_finding_is_dropped_there_is_no_question_and_no_new_round(fx):
    critic_finds(fx, finding(LENIENT))
    out = fx.fund("--roles", "critic")
    assert out.code == EXIT_OK and asked(out, "Add these") == []
    assert len(approvals(fx)) == 1 and fx.calls() == ["boss", "worker", "critic"]
    assert sorted(p.name for p in (fx.run_dir / "checks").iterdir()) == ["test_c01.py"]


@pytest.mark.parametrize(
    "findings", [[], [finding(PASSES)]], ids=["no findings", "the test passes on the product"]
)
def test_no_verified_finding_means_no_question(fx, findings):
    critic_finds(fx, *findings)
    out = fx.fund("--roles", "critic")
    assert out.code == EXIT_OK
    said = f"Critic: 0 finding(s) verified by running their tests on the product, {len(findings)}"
    said += " rejected."
    assert said in out.text
    [call] = fx.role_calls("critic")
    assert call_facts(call) == ("completed", "ok", 4_000) and call.data["verified"] == 0
    assert call.data["rejected"] == len(findings) and asked(out, "Add these") == []
    assert len(approvals(fx)) == 1 and fx.calls() == ["boss", "worker", "critic"]


def test_the_critic_is_told_which_checks_pass_and_reads_the_product(fx):
    critic_finds(fx)
    fx.fund("--roles", "critic")
    prompt = fx.last_prompt("critic")
    assert "- reverses a word" in prompt and "File: rev.py" in prompt and BUGGY.strip() in prompt


def test_a_critic_that_fails_is_booked_said_and_the_run_is_unchanged(fx):
    fx.set("critic", bad(0.003))
    out = fx.fund("--roles", "critic")
    assert out.code == EXIT_OK
    [call] = fx.role_calls("critic")
    assert call_facts(call) == ("api_error", "failed", 3_000)
    assert "The critic failed (" in out.text and "Critic: " not in out.text
    assert asked(out, "Add these") == []


def test_the_critic_is_not_run_when_nothing_was_built(fx):
    fx.set("critic", ok({"findings": []}))
    out = fx.fund("--roles", "critic", "--max-minutes", "1e-9")
    assert out.code == EXIT_INCOMPLETE and fx.role_calls() == [] and "critic" not in fx.calls()


def test_a_run_that_ended_early_reports_the_findings_and_offers_no_fix_round(fx):
    fx.set("worker", {"files": {"rev.py": "def reverse(s):\n    return s\n"}})
    fx.set("critic", ok({"findings": [finding()]}))
    out = fx.fund("--roles", "critic", "--budget", "0.12", "--slice", "0.005")
    reason = "round 1 closed below its unlock threshold"
    assert out.code == EXIT_INCOMPLETE and f"Ended early: {reason}" in out.text
    assert "Critic verified a finding (high)" in out.text
    assert f"The run ended early ({reason}): no fix round is offered." in out.text
    assert asked(out, "Add these") == [] and len(approvals(fx)) == 1


def test_the_fix_budget_is_what_the_new_round_is_funded_with(fx):
    critic_finds(fx, finding())
    out = fx.fund("--roles", "critic", "--fix-budget", "0.2")
    assert out.code == EXIT_OK
    assert asked(out, "Add these") == [
        "Add these 1 checks and fund a fix round of $0.2? [y]es / [n]o "
    ]
    sheet = json.loads((fx.run_dir / "term_sheet.json").read_text())
    assert sheet["rounds"][1]["budget_micros"] == 200_000 and sheet["budget_micros"] == 700_000


def test_the_default_fix_budget_is_two_slices_and_a_reserve_from_the_runs_options(fx):
    critic_finds(fx, finding())
    fx.fund("--roles", "critic", "--slice", "0.06", "--reserve", "0.02")
    sheet = json.loads((fx.run_dir / "term_sheet.json").read_text())
    assert sheet["rounds"][1]["budget_micros"] == 2 * 60_000 + 20_000


@pytest.mark.parametrize("small", ["0.104999", "0.01"])
def test_a_fix_budget_below_one_slice_and_a_reserve_is_refused_before_anything_is_spent(fx, small):
    out = fx.fund("--roles", "critic", "--fix-budget", small)
    assert out.code == EXIT_USAGE and "--fix-budget must be at least $0.105" in out.text
    assert not (fx.project / ".boss").exists() and fx.calls() == []


def test_the_smallest_fix_budget_is_one_reserve_and_one_minimum_slice(fx):
    out = fx.fund("--roles", "critic", "--reserve", "0.01", "--fix-budget", "0.014")
    assert out.code == EXIT_USAGE and "at least $0.015" in out.text and fx.calls() == []
    fx.set("critic", ok({"findings": []}))
    out = fx.fund("--roles", "critic", "--reserve", "0.01", "--fix-budget", "0.015")
    assert out.code == EXIT_OK


@pytest.mark.parametrize("bad_cycles", ["-1", "1.5", "many"])
def test_review_cycles_is_a_whole_number(fx, bad_cycles, capsys):
    with pytest.raises(SystemExit) as info:
        fx.fund("--review-cycles", bad_cycles)
    assert info.value.code == 2 and "whole number of 0 or more" in capsys.readouterr().err


def two_tasks(fx, finding_code):
    """Two tasks: t1 owns rev.py, t2 owns util.py; a helper no task owns comes with the first."""
    util_check = "from util import shout\n\n\ndef test_shout():\n    assert shout('a') == 'A'\n"
    draft = {
        "tasks": [
            {"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]},
            {"id": "t2", "brief": "Create util.py with shout(s).", "paths": ["util.py"]},
        ],
        "checks": [
            {"description": "reverses a word", "task": "t1", "code": CHECK1},
            {"description": "shouts a letter", "task": "t2", "code": util_check},
        ],
    }
    helper = "def h():\n    return 1\n"
    fx.set("boss", ok(draft))
    fx.set(
        "worker",
        [
            {"files": {"rev.py": GOOD, "helpers.py": helper}},
            {"files": {"util.py": "def shout(s):\n    return s[:1].upper() + s[1:]\n"}},
            {"files": {"util.py": "def shout(s):\n    return s.upper()\n"}},
        ],
    )
    fx.set("critic", ok({"findings": [finding(finding_code, claim="a claim about the code")]}))


def test_the_new_check_belongs_to_the_task_that_owns_the_module_its_test_imports(fx):
    two_tasks(fx, "from util import shout\n\n\ndef test_all():\n    assert shout('ab') == 'AB'\n")
    out = fx.fund("--roles", "critic", "--max-tasks", "2")
    assert out.code == EXIT_OK
    sheet = json.loads((fx.run_dir / "term_sheet.json").read_text())
    tasks = [(c["id"], c["task"]) for c in sheet["checks"]]
    assert tasks == [("c01", "t1"), ("c02", "t2"), ("c03", "t2")]
    assert fx.events(EventType.SLICE_END)[-1].actor == "worker:w2"  # t2's worker fixed it
    assert any("Check c03 [t2]" in line for line in out.said)


def test_a_finding_no_task_owns_is_not_proposed(fx):
    two_tasks(fx, "from helpers import h\n\n\ndef test_h():\n    assert h() == 2\n")
    out = fx.fund("--roles", "critic", "--max-tasks", "2")
    assert out.code == EXIT_OK and asked(out, "Add these") == []
    assert (
        "Finding not proposed (a claim about the code): no task owns the module its test"
        in out.text
    )
    assert len(approvals(fx)) == 1 and not (fx.run_dir / "checks" / "test_c03.py").exists()


# --- resume: stage 3 is not repeated ------------------------------------------------------------


def test_resuming_a_finished_run_that_used_the_critic_adds_no_events_and_no_calls(fx):
    critic_finds(fx, finding())
    fx.fund("--roles", "critic")
    before, calls = fx.events(), fx.calls()
    for _ in range(2):
        out = fx.run("resume")
        assert out.code == EXIT_OK and "c02  passed" in out.text
        assert fx.events() == before and fx.calls() == calls
    assert asked(out, "Add these") == []


def test_resuming_after_the_investor_said_no_does_not_ask_again(fx):
    critic_finds(fx, finding())
    fx.fund("--roles", "critic", answers={"Add these": "n"})
    before = fx.events()
    out = fx.run("resume")
    assert out.code == EXIT_OK and fx.events() == before and asked(out, "Add these") == []


def test_a_run_interrupted_before_stage_three_gets_its_critic_on_resume_exactly_once(fx):
    critic_finds(fx, finding())
    (fx.folder / "interrupt").write_text("")
    out = fx.fund("--roles", "critic")
    assert out.code == EXIT_INTERRUPTED and fx.role_calls() == []
    (fx.folder / "interrupt").unlink()
    out = fx.run("resume")
    assert out.code == EXIT_OK and len(fx.role_calls("critic")) == 1 and len(approvals(fx)) == 2
    before = fx.events()
    fx.run("resume")
    assert fx.events() == before


def test_resume_can_offer_the_fix_round_with_its_own_budget(fx):
    critic_finds(fx, finding())
    (fx.folder / "interrupt").write_text("")
    fx.fund("--roles", "critic")
    (fx.folder / "interrupt").unlink()
    fx.run("resume", "--fix-budget", "0.25")
    sheet = json.loads((fx.run_dir / "term_sheet.json").read_text())
    assert sheet["rounds"][1]["budget_micros"] == 250_000
    out = fx.run("resume", "--fix-budget", "0.01")
    assert out.code == EXIT_USAGE and "--fix-budget must be at least $0.105" in out.text


# --- stage 3: a demo that ran, installed with the product --------------------------------------

DEMO = {
    "demo_code": "from rev import reverse\n\nprint(reverse('abc'))\n",
    "steps": [{"says": "reverses the letters of abc", "quote": Q1}],
    "usage": "Call reverse(s) with a string; it returns the string reversed.",
}
BAD_PRODUCT = "def reverse(s):\n    return s\n"


def usage_file(fx):
    return fx.run_dir / "product" / "USAGE.md"


def test_the_demo_is_installed_beside_the_product_and_usage_md_holds_the_real_output(fx):
    fx.set("demo_writer", ok(DEMO))
    out = fx.fund("--roles", "demo_writer")
    assert out.code == EXIT_OK
    product = fx.run_dir / "product"
    assert (product / "demo.py").read_text() == DEMO["demo_code"]
    text = usage_file(fx).read_text()
    assert DEMO["usage"] in text and "```text\ncba\n```" in text  # what the demo printed
    assert "reverses the letters" not in text  # the model's claims about output are never shown
    [call] = fx.role_calls("demo_writer")
    assert call.actor == "role:demo_writer" and call_facts(call) == ("completed", "ok", 4_000)
    assert f"Demo installed in {product}: USAGE.md says how to use the product." in out.text
    assert fx.calls() == ["boss", "worker", "demo_writer"]
    assert "rev.py" in fx.last_prompt("demo_writer")  # it was shown the product's source


def test_the_demo_is_not_attempted_when_a_check_fails(fx):
    fx.set("worker", {"files": {"rev.py": BAD_PRODUCT}})
    fx.set("demo_writer", ok(DEMO))
    out = fx.fund("--roles", "demo_writer")
    assert out.code == EXIT_INCOMPLETE
    assert fx.role_calls() == [] and "demo_writer" not in fx.calls() and not usage_file(fx).exists()
    assert not (fx.run_dir / "product" / "demo.py").exists()


def test_the_demo_is_not_attempted_when_the_fix_round_did_not_fix_it(fx):
    critic_finds(fx, finding())
    fx.set("worker", {"files": {"rev.py": BUGGY}})  # never fixes it
    fx.set("demo_writer", ok(DEMO))
    out = fx.fund("--roles", "critic,demo_writer")
    assert out.code == EXIT_INCOMPLETE
    assert len(approvals(fx)) == 2 and "demo_writer" not in fx.calls()
    assert not usage_file(fx).exists()


def test_the_demo_is_made_after_the_fix_round_and_shows_the_fixed_product(fx):
    critic_finds(fx, finding())
    demo = DEMO | {"demo_code": "from rev import reverse\n\nprint(reverse('abcdefg'))\n"}
    fx.set("demo_writer", ok(demo))
    out = fx.fund("--roles", "critic,demo_writer")
    assert out.code == EXIT_OK
    assert fx.calls() == ["boss", "worker", "critic", "worker", "demo_writer"]
    assert "```text\ngfedcba\n```" in usage_file(fx).read_text()


@pytest.mark.parametrize(
    ("code", "why"),
    [
        ("from rev import reverse\n\nraise SystemExit(3)\n", "the demo exited 3"),
        ("import subprocess\nprint(1)\n", "imports 'subprocess'"),
        ("print('x'\n", "syntax error"),
    ],
    ids=["exits 3", "imports subprocess", "does not parse"],
)
def test_a_rejected_demo_is_one_line_saying_why_and_nothing_is_installed(fx, code, why):
    fx.set("demo_writer", ok(DEMO | {"demo_code": code}))
    out = fx.fund("--roles", "demo_writer")
    assert out.code == EXIT_OK  # the product is fine; only the demo was refused
    [call] = fx.role_calls("demo_writer")
    assert call_facts(call) == ("completed", "failed", 4_000) and why in call.data["detail"]
    line = told(out, "The demo_writer failed (")
    assert why in line and "\n" not in line
    assert not usage_file(fx).exists() and not (fx.run_dir / "product" / "demo.py").exists()


def test_a_demo_call_that_fails_is_booked_and_said(fx):
    fx.set("demo_writer", bad(0.003))
    out = fx.fund("--roles", "demo_writer")
    [call] = fx.role_calls("demo_writer")
    assert call_facts(call) == ("api_error", "failed", 3_000)
    assert "The demo_writer failed (" in out.text and not usage_file(fx).exists()


def test_a_demo_never_replaces_a_file_the_product_already_has(fx):
    fx.set("worker", {"files": {"rev.py": GOOD, "USAGE.md": "mine\n"}})
    fx.set("demo_writer", ok(DEMO))
    out = fx.fund("--roles", "demo_writer")
    [call] = fx.role_calls("demo_writer")
    assert call_facts(call) == ("not_called", "failed", 0) and "exists" in call.data["detail"]
    assert usage_file(fx).read_text() == "mine\n" and "demo_writer" not in fx.calls()
    assert out.code == EXIT_OK


def test_the_judge_scores_usage_md_against_the_usage_rubric_and_says_it_is_uncalibrated(fx):
    fx.set("demo_writer", ok(DEMO))
    fx.set("judge", ok(judge_out("usage", 5)))
    out = fx.fund("--roles", "demo_writer,judge")
    assert "Judge's score of USAGE.md (advisory, gates nothing):" in out.text
    uncalibrated = "(uncalibrated: advisory only, do not act on it)"
    assert f"usage v1 by haiku: mean 5.0 of 5 {uncalibrated}" in out.text
    [call] = fx.role_calls("judge")
    assert call.data["rubric"] == "usage" and call.data["calibrated"] is False
    assert f"<context>\n{IDEA}\n</context>" in fx.last_prompt("judge")
    assert "cba" in fx.last_prompt("judge")  # it was shown the file, with the real output in it


def test_no_judgement_of_usage_when_nothing_was_installed(fx):
    fx.set("demo_writer", bad())
    fx.set("judge", ok(judge_out("usage")))
    fx.fund("--roles", "demo_writer,judge")
    assert "judge" not in fx.calls()


def test_a_demo_without_the_judge_role_is_not_judged(fx):
    fx.set("demo_writer", ok(DEMO))
    fx.set("judge", ok(judge_out("usage")))
    fx.fund("--roles", "demo_writer")
    assert fx.role_calls("judge") == [] and "judge" not in fx.calls()


def test_a_failed_usage_judge_is_said_and_the_demo_stays(fx):
    fx.set("demo_writer", ok(DEMO))
    fx.set("judge", bad(0.002))
    out = fx.fund("--roles", "demo_writer,judge")
    assert "The judge failed (" in out.text and "mean" not in out.text
    assert call_facts(fx.role_calls("judge")[0]) == ("api_error", "failed", 2_000)
    assert usage_file(fx).exists()


# --- resume: the demo is neither repeated nor lost ----------------------------------------------


def test_resuming_a_finished_run_that_made_a_demo_adds_no_events_and_keeps_the_demo(fx):
    fx.set("demo_writer", ok(DEMO))
    fx.set("judge", ok(judge_out("usage")))
    fx.fund("--roles", "demo_writer,judge")
    before, calls, text = fx.events(), fx.calls(), usage_file(fx).read_text()
    for _ in range(2):
        out = fx.run("resume")
        assert out.code == EXIT_OK
        assert fx.events() == before and fx.calls() == calls
        assert usage_file(fx).read_text() == text  # product/ was rebuilt; the demo came back
        assert (fx.run_dir / "product" / "demo.py").read_text() == DEMO["demo_code"]
    assert "Judge's score" not in out.text


def test_a_refused_demo_is_not_asked_for_again_on_resume(fx):
    fx.set("demo_writer", bad())
    fx.fund("--roles", "demo_writer")
    before = fx.events()
    fx.set("demo_writer", ok(DEMO))
    fx.run("resume")
    assert fx.events() == before and not usage_file(fx).exists()


def test_a_run_interrupted_before_the_demo_gets_it_on_resume(fx):
    fx.set("demo_writer", ok(DEMO))
    (fx.folder / "interrupt").write_text("")
    assert fx.fund("--roles", "demo_writer").code == EXIT_INTERRUPTED
    (fx.folder / "interrupt").unlink()
    assert fx.run("resume").code == EXIT_OK and usage_file(fx).exists()
    assert len(fx.role_calls("demo_writer")) == 1


def test_an_interrupted_fix_round_continues_on_resume_without_a_second_critic(fx):
    critic_finds(fx, finding())
    fx.set("demo_writer", ok(DEMO))
    (fx.folder / "interrupt").write_text("1")  # the second slice: the fix
    out = fx.fund("--roles", "critic,demo_writer")
    assert out.code == EXIT_INTERRUPTED and len(approvals(fx)) == 2
    assert fx.calls() == ["boss", "worker", "critic"]
    (fx.folder / "interrupt").unlink()
    out = fx.run("resume")
    assert out.code == EXIT_OK and asked(out, "Add these") == []
    assert fx.calls() == ["boss", "worker", "critic", "worker", "demo_writer"]
    assert product_verdicts(fx) == {"c01": "passed", "c02": "passed"} and usage_file(fx).exists()


def test_a_second_review_cycle_on_resume_makes_a_new_demo_for_the_new_build(fx):
    blank = "from rev import reverse\n\n\ndef test_blank():\n    assert reverse(' ') == ''\n"
    stripped = "def reverse(s):\n    return s.strip()[::-1]\n"
    fx.set("worker", [{"files": {"rev.py": v}} for v in (BUGGY, GOOD, stripped)])
    fx.set("critic", [ok({"findings": [finding()]}), ok({"findings": [finding(blank, quote=Q2)]})])
    later = DEMO | {"demo_code": "from rev import reverse\n\nprint(reverse(' xyz'))\n"}
    fx.set("demo_writer", [ok(DEMO), ok(later)])
    fx.fund("--roles", "critic,demo_writer")
    assert fx.calls().count("demo_writer") == 1 and "cba" in usage_file(fx).read_text()
    out = fx.run("resume", "--review-cycles", "2")
    assert out.code == EXIT_OK
    assert fx.calls() == [
        "boss",
        "worker",
        "critic",
        "worker",
        "demo_writer",
        "critic",
        "worker",
        "demo_writer",
    ]
    assert "```text\nzyx\n```" in usage_file(fx).read_text()  # the new build's demo, not the old


# --- every role at once ------------------------------------------------------------------------


def test_every_role_end_to_end_and_the_ledger_adds_up(fx):
    script_stage_1(fx, stories=STORIES)
    fx.set("tester", ok(checks_out("S1.1", "S1.2", codes=(CHECK1, WRONG))))
    fx.set("judge", [ok(judge_out("stories")), ok(judge_out("usage", 5))])
    fx.set("consultant", ok(ADVICE))
    disputing = {"files": {"rev.py": BUGGY}, "disputes": [DISPUTE]}
    fx.set("worker", [disputing, {"files": {"rev.py": GOOD}}])
    fx.set("critic", ok({"findings": [finding()]}))
    fx.set("demo_writer", ok(DEMO))
    out = fx.fund("--roles", "all", answers={"Task": "d"})
    assert out.code == EXIT_OK
    assert fx.calls() == [
        "product_manager", "user_agent", "system_designer", "tester", "check_auditor", "judge",
        "worker", "consultant", "critic", "worker", "demo_writer", "judge",
    ]  # fmt: skip
    assert {e.actor for e in fx.role_calls()} == {f"role:{n}" for n in registry()}
    assert all(e.round == 0 and e.data["result"] == "ok" for e in fx.role_calls())
    events = fx.events()
    spent = {}
    for e in events:
        kind = e.actor.split(":")[0]
        spent[kind] = spent.get(kind, 0) + (e.cost_micros or 0)
    assert (spent["role"], spent["worker"], spent["boss"]) == (10 * 4_000, 12_000, 0)
    assert sum(spent.values()) == 10 * 4_000 + 12_000
    assert "  total        $0.0520" in out.text
    kinds = [str(e.event) for e in events]
    assert kinds.count("started") == 1 and kinds.count("approved") == 2
    assert usage_file(fx).exists() and (fx.run_dir / "stories.json").exists()


# --- the board report lists every role call -----------------------------------------------------


def test_the_board_report_lists_every_role_call_and_its_outcome_one_line_each(fx):
    script_stage_1(fx)
    fx.set("tester", bad(0.003))
    fx.set("critic", ok({"findings": []}))
    out = fx.fund("--roles", f"{DESIGN_ROLES},critic")
    assert out.code == EXIT_OK
    report = (fx.run_dir / "report.md").read_text()
    assert report.rstrip("\n") in out.text
    section = report.split("Roles (each call, in order; their spend is in the lines above)\n")[1]
    lines = section.rstrip("\n").split("\n\n")[0].split("\n")
    unused = "not used: the staged draft failed at tester"
    assert lines == [
        "  product_manager  ok (completed), $0.0040: stories 1, criteria 2",
        "  user_agent  ok (completed), $0.0040: 0 missing, 0 misread",
        f"  system_designer  unused (completed), $0.0040: {unused}",
        "  tester  failed (api_error), $0.0030: boss call ended as api_error",
        "  critic  ok (completed), $0.0040: 0 verified, 0 rejected",
    ]
    assert lines == [line for line in lines if line.startswith("  ")]
    # the numbers above are the ledger's: one line per ROLE_CALL event, in its order
    assert len(lines) == len(fx.role_calls())


def test_a_report_of_a_run_without_roles_is_the_one_it_always_was(fx):
    fx.fund()
    assert "Roles" not in (fx.run_dir / "report.md").read_text()


# --- what the roles are called with --------------------------------------------------------------


def model_and_thinking(fx, who):
    rows = [r for r in fx.calls(full=True) if r["who"] == who]
    return [(r["model"], r["thinking"]) for r in rows]


def test_every_role_call_uses_the_bosss_model_and_thinking_setting_and_the_ledger_says_which(fx):
    script_stage_1(fx)
    fx.fund("--roles", ",".join(STAGE_1), "--boss-model", "sonnet", "--boss-thinking", "0")
    for who in STAGE_1:
        assert model_and_thinking(fx, who) == [("sonnet", "0")], who
    assert {e.data["model"] for e in fx.role_calls()} == {"sonnet"}
    assert {e.data["prompt"] for e in fx.role_calls()} == {registry()[n].prompt for n in STAGE_1}


def test_the_default_model_is_the_bosss_and_the_cli_chooses_the_thinking(fx):
    fx.set("check_auditor", ok(audit_out("c01")))
    fx.fund("--roles", "check_auditor")
    assert model_and_thinking(fx, "check_auditor") == [("haiku", "unset")]


def test_a_resumed_run_calls_its_roles_with_the_model_and_thinking_it_was_started_with(fx):
    with_a_wrong_check(fx)
    fx.set("consultant", ok(ADVICE))
    (fx.folder / "interrupt").write_text("")
    fx.fund("--roles", "consultant", "--boss-model", "sonnet", "--boss-thinking", "0")
    (fx.folder / "interrupt").unlink()
    fx.run("resume", answers={"Task": "d"})
    assert model_and_thinking(fx, "consultant") == [("sonnet", "0")]


def test_a_run_started_without_roles_resumes_without_roles(fx):
    (fx.folder / "interrupt").write_text("")
    fx.fund()
    (fx.folder / "interrupt").unlink()
    out = fx.run("resume")
    assert out.code == EXIT_OK and fx.role_calls() == []
    assert "Asking the" not in out.text


def test_a_started_event_with_a_damaged_roles_field_is_read_as_no_roles():
    def started(roles):
        return Event(run="r", round=0, actor="boss", event=EventType.STARTED, data={"roles": roles})

    assert recorded_setup([started("critic")]) is None
    assert recorded_setup([started({"names": "critic"})]) is None
    damaged = {"names": ["critic", 7], "model": "m", "thinking_tokens": True}
    assert recorded_setup([started(damaged)]) == Setup(("critic", "7"), "m", None)
    assert recorded_setup([started({"names": [], "model": "m", "thinking_tokens": 5})]) == Setup(
        (), "m", 5
    )


def test_a_blank_role_list_is_no_roles(fx):
    out = fx.fund("--roles", " , ")
    assert out.code == EXIT_OK and fx.role_calls() == [] and "Asking the" not in out.text


def test_the_critic_is_not_told_that_a_failing_check_passes(fx):
    fx.set("worker", {"files": {"rev.py": "def reverse(s):\n    return s\n"}})
    fx.set("critic", ok({"findings": []}))
    fx.fund("--roles", "critic", "--budget", "0.12", "--slice", "0.005")
    prompt = fx.last_prompt("critic")
    assert "- reverses a word" not in prompt and "- none" in prompt


# --- found by mutation testing -----------------------------------------------------------------


def test_the_advisor_gives_no_opinion_on_a_check_that_is_not_on_the_sheet(fx, tmp_path):
    sheet = TermSheet(
        IDEA,
        500_000,
        (Round(1, 500_000, 1),),
        (CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),),
        (Task("t1", "Create rev.py.", ("rev.py",)),),
    )
    with LedgerWriter(tmp_path / "ledger.jsonl") as ledger:
        pipe = Pipeline(
            Setup(("consultant",), "haiku", None),
            tmp_path,
            RunPaths(tmp_path / "run"),
            ledger,
            "r1",
            {"HOME": str(fx.home)},
            str(fx.fake),
            lambda question: "",
            lambda text: None,
        )
        advise = pipe.advisor(sheet)
        assert advise is not None and advise("c99", "a reason") is None
    assert fx.calls() == [] and not (tmp_path / "ledger.jsonl").read_text()


def test_what_a_model_wrote_in_a_note_is_made_safe_before_the_investor_reads_it(fx):
    hostile = story(1, "must", [Q1, Q2])
    hostile["as_a"] = "caller\x1b[2J"
    fx.set("product_manager", ok({"stories": [hostile]}))
    forged = {"quote": Q2, "why": "one\nFORGED: verdict accept\x1b[0m"}
    fx.set("user_agent", ok(REVIEW_MISSING | {"missing": [forged]}))
    out = fx.fund("--roles", "product_manager,user_agent")
    assert out.code == EXIT_OK and "\x1b" not in out.text
    assert "caller\\x1b[2J" in out.text and "\\x1b[0m" in out.text
    assert not any(line.startswith("FORGED") for line in out.text.splitlines())
    assert "why: one FORGED: verdict accept" in out.text


def test_the_user_agents_misreadings_are_shown_with_the_criterion_they_concern(fx):
    misread = {"criterion": "S1.1", "quote": Q1, "why": "the criterion tests a different thing"}
    fx.set("product_manager", ok(STORIES))
    fx.set("user_agent", ok({"missing": [], "misread": [misread], "verdict": "revise"}))
    out = fx.fund("--roles", "product_manager,user_agent")
    assert f'  misread S1.1: "{Q1}" | why: the criterion tests a different thing' in out.text
    [call] = fx.role_calls("user_agent")
    assert call_facts(call) == ("completed", "ok", 4_000)
    assert call.data["detail"] == "0 missing, 1 misread"


def two_task_staging(fx):
    util_check = "from util import shout\n\n\ndef test_shout():\n    assert shout('a') == 'A'\n"
    fx.set("product_manager", ok({"stories": [story(1, "must", [Q1]), story(2, "must", [Q2])]}))
    tasks = [
        {"id": "t1", "brief": "Create rev.py.", "paths": ["rev.py"], "stories": ["S1"]},
        {"id": "t2", "brief": "Create util.py.", "paths": ["util.py"], "stories": ["S2"]},
    ]
    fx.set("system_designer", ok({"tasks": [t | {"interfaces": []} for t in tasks]}))
    checks = [
        {"criteria": ["S1.1"], "task": "t1", "description": "reverses", "code": CHECK1},
        {"criteria": ["S2.1"], "task": "t2", "description": "shouts", "code": util_check},
    ]
    fx.set("tester", ok({"checks": checks, "untestable": []}))
    shout = "def shout(s):\n    return s.upper()\n"
    fx.set("worker", [{"files": {"rev.py": GOOD}}, {"files": {"util.py": shout}}])


def test_the_staged_draft_may_use_as_many_tasks_as_the_investor_allowed(fx):
    two_task_staging(fx)
    out = fx.fund("--roles", "product_manager,system_designer,tester", "--max-tasks", "2")
    assert out.code == EXIT_OK and "boss" not in fx.calls()
    sheet = json.loads((fx.run_dir / "term_sheet.json").read_text())
    assert [t["id"] for t in sheet["tasks"]] == ["t1", "t2"]
    assert fx.role_calls("system_designer")[0].data["detail"] == "2 task(s)"
    assert "Use at most 2 tasks." in fx.last_prompt("system_designer")


def test_with_the_default_of_one_task_a_two_task_design_is_refused_and_the_boss_drafts(fx):
    two_task_staging(fx)
    out = fx.fund("--roles", "product_manager,system_designer,tester")
    assert "The staged draft failed at system_designer" in out.text
    assert [e.data["result"] for e in fx.role_calls("system_designer")] == ["failed"]
    assert fx.calls()[-2:] == ["boss", "worker"]


def test_an_amended_sheet_that_does_not_validate_is_not_offered(fx, monkeypatch):
    def refuse(sheet, checks_dir):
        raise TermSheetError(["the rounds do not add up"])

    monkeypatch.setattr("boss.pipeline.validate", refuse)
    critic_finds(fx, finding())
    out = fx.fund("--roles", "critic")
    assert out.code == EXIT_OK and asked(out, "Add these") == []
    assert "The amended term sheet does not validate: the rounds do not add up" in out.text
    assert len(approvals(fx)) == 1 and fx.calls() == ["boss", "worker", "critic"]
    assert sorted(p.name for p in (fx.run_dir / "checks").iterdir()) == ["test_c01.py"]


def test_a_fix_round_after_an_early_finish_still_asks_to_fund_the_rounds_that_never_opened(fx):
    script_stage_1(fx, stories=TWO_STORIES, design_out=design(("S1", "S2")))
    fx.set("tester", ok(checks_out("S1.1", "S2.1")))
    critic_finds(fx, finding())
    out = fx.fund("--roles", "product_manager,system_designer,tester,critic", "--rounds", "2")
    assert out.code == EXIT_OK
    [question] = asked(out, "Round 2")  # the firm's own rule, which the amendment does not bypass
    assert question.startswith("Round 2: 2/3 checks pass. Fund $")
    sheet = json.loads((fx.run_dir / "term_sheet.json").read_text())
    assert [r["n"] for r in sheet["rounds"]] == [1, 2, 3]
    assert sorted(e.data.get("round", 1) for e in approvals(fx)) == [1, 2, 3]
