"""docs/LEDGER.md stays true: every event type documented, every `data` key the code writes named.

The code is run for real (scripted workers, the real gate, the real CLI against a fake `claude`)
and every event it writes is checked against the document: type, actor, key, value type, and the
example line under each heading.
"""

import dataclasses
import inspect
import json
import re
from collections import defaultdict
from dataclasses import fields

import pytest
from docs_support import DOCS, ROOT, code_spans, fake_claude, read, run_cli, section, table

from antstreet import budget, held_out, pipeline, state
from antstreet.approval import content_hashes
from antstreet.dispatch import DispatchPolicy, plan_cascade, plan_dispatch
from antstreet.errors import Outcome
from antstreet.firm import FirmConfig, run_firm
from antstreet.gate import run_gate
from antstreet.ledger import LEDGER_VERSION, Billing, Event, EventType, LedgerWriter, read_events
from antstreet.limits import RunLimits
from antstreet.roles import examiner, registry
from antstreet.roles.base import RoleSpec, ledger_fields
from antstreet.roles.examiner import run_examiner
from antstreet.rundir import RunPaths
from antstreet.runner import SliceRun
from antstreet.stream import Usage
from antstreet.termsheet import CheckSpec, Round, Task, TermSheet
from antstreet.worker import IsolationError, ModelMismatchError

# The module-scoped `produced` fixture runs ~20 whole runs (over two minutes). Under xdist each
# worker that received one of these tests would build its own copy, so the module is pinned to one
# worker (needs `--dist loadgroup`, which CI and CONTRIBUTING.md pass).
pytestmark = pytest.mark.xdist_group("docs-ledger")

DOC = DOCS / "LEDGER.md"
SRC = ROOT / "src" / "antstreet"

# --- scripted firm: the pattern of tests/test_firm.py, copied on purpose ---------------------

C01 = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
C02 = "from rev import reverse\n\ndef test_empty():\n    assert reverse('') == ''\n"
GOOD = "def reverse(s):\n    return s[::-1]\n"
HALF = "def reverse(s):\n    return s\n"  # passes c02 only
BAD = "def reverse(s):\n    raise RuntimeError\n"


def sheet(rounds=None) -> TermSheet:
    rounds = rounds or (Round(1, 500_000, 2),)
    checks = (
        CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),
        CheckSpec("c02", "empty string", "test_c02.py", "t1"),
    )
    tasks = (Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),)
    return TermSheet("Reverse a string.", sum(r.budget_micros for r in rounds), rounds, checks,
                     tasks, True)  # fmt: skip


class Script:
    """A scripted worker: each step is (source, status, outcome, cost, disputes, denials)."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.totals = {}

    def __call__(self, spec, workspace, log_path, *, env):
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        code, status, outcome, cost, disputes, denials = step
        if code is not None:
            (workspace / "rev.py").write_text(code)
        session = str(spec.session_id)
        if cost is not None:
            self.totals[session] = self.totals.get(session, 0) + cost
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("{}\n")
        report = {"status": status, "reason": f"scripted {status}"}
        if disputes:
            report["disputed_checks"] = [
                {"check": c, "reason": "the idea says otherwise"} for c in disputes
            ]
        return SliceRun(
            outcome=outcome,
            usage=Usage(self.totals.get(session) if cost is not None else None, 10, 5, 0),
            status=report,
            session_id=session,
            exit_code=0,
            duration_s=0.1,
            log_path=log_path,
            denials=[{"tool": tool, "reason": "rule"} for tool in denials],
        )


class ModelScript(Script):
    """A scripted worker whose init names the model it ran: the launched one unless `ran` says
    otherwise."""

    def __init__(self, *steps, ran=None):
        super().__init__(*steps)
        self.ran = ran

    def __call__(self, spec, workspace, log_path, *, env):
        run = super().__call__(spec, workspace, log_path, env=env)
        return dataclasses.replace(run, model_id=self.ran or f"claude-{spec.model}-4-5-20251001")


def dispatched(rounds=None) -> TermSheet:
    policy = DispatchPolicy("sonnet", 100_000)
    return plan_dispatch(sheet(rounds), tier="haiku", profile=None, policy=policy, reads={})


def step(
    code, status="continuing", outcome=Outcome.COMPLETED, cost=10_000, disputes=(), denials=()
):
    return (code, status, outcome, cost, disputes, denials)


H01 = "from rev import reverse\n\ndef test_held():\n    assert reverse('xy') == 'yx'\n"


def firm_events(tmp_path, worker, s=None, *, answers=(), config=None, expect=None, held=False):
    """Run the loop on a fresh run folder and return every event it wrote. `held` gives the run one
    approved held-out check."""
    paths = RunPaths(tmp_path)
    paths.checks.mkdir(parents=True)
    (paths.checks / "test_c01.py").write_text(C01)
    (paths.checks / "test_c02.py").write_text(C02)
    s = s or sheet()
    replies = iter(answers)
    with LedgerWriter(paths.ledger) as ledger:
        data = {"hashes": content_hashes(s, paths.checks)}
        if held:
            entry = held_out.HeldOutCheck("h01", held_out.file_name("h01"), "Reverse a string.")
            held_out.write(paths.held_out, [(entry, H01)])
            data["held_out_hashes"] = held_out.hashes(paths.held_out)
        ledger.append(
            Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data=data)
        )
        try:
            run_firm(
                s, paths, ledger, "r1", env={"HOME": "/h"}, config=config or FirmConfig(),
                ask=lambda q: next(replies), say=lambda _: None, slice_runner=worker, gate=run_gate,
                sleep=lambda _: None,
            )  # fmt: skip
        except (IsolationError, ModelMismatchError) as exc:
            assert expect is type(exc)
    return read_events(paths.ledger)


# --- the real CLI against a fake `claude`, for boss_call and the investor's own events -------


def cli_events(tmp_path, *, binary=None, answers=("a",), extra=()):
    _, run_dir, _ = run_cli(
        tmp_path,
        ["fund", "Reverse a string.", "--budget", "0.50", *extra],
        answers=answers,
        binary=binary,
    )
    return read_events(run_dir / "ledger.jsonl")


def cli_spec_events(tmp_path):
    """`antstreet fund --spec`: a boss that cites the idea's rules, so `boss_call` carries `prompt`
    and
    `rules` and `approved` carries the coverage summary."""
    from test_cli import DRAFT as PLAIN
    from test_cli import FAKE_CLAUDE
    from test_cli_spec import CITING, IDEA

    tmp_path.mkdir(parents=True, exist_ok=True)
    fake = tmp_path / "fake-claude-spec"
    fake.write_text(FAKE_CLAUDE.replace(repr(PLAIN), repr(CITING)))
    fake.chmod(0o755)
    _, run_dir, _ = run_cli(
        tmp_path, ["fund", IDEA, "--budget", "0.50", "--spec"], binary=str(fake)
    )
    return read_events(run_dir / "ledger.jsonl")


def cli_spec_mapper_events(tmp_path):
    """`antstreet fund --spec --roles spec_mapper`: a fake boss that cites rules and a fake mapper
    that
    agrees with it, so the mapper's `role_call` is booked."""
    from test_cli import DRAFT as PLAIN
    from test_cli import FAKE_CLAUDE
    from test_cli_spec import CITING, IDEA

    maps = {"maps": [{"check": "c01", "exercises": [{"rule": "R02", "line": 4}]}]}
    pick = f"({CITING!r} if '\"maps\"' not in argv[argv.index('--json-schema') + 1] else {maps!r})"
    tmp_path.mkdir(parents=True, exist_ok=True)
    fake = tmp_path / "fake-claude-mapper"
    fake.write_text(FAKE_CLAUDE.replace(repr(PLAIN), pick))
    fake.chmod(0o755)
    _, run_dir, _ = run_cli(
        tmp_path,
        ["fund", IDEA, "--budget", "0.50", "--spec", "--roles", "spec_mapper"],
        binary=str(fake),
    )
    return read_events(run_dir / "ledger.jsonl")


def cli_resumed_events(tmp_path):
    """A run stopped by a wall-clock limit that is already over, then `antstreet resume` on it."""
    fund = ["fund", "Reverse a string.", "--budget", "0.50", "--max-minutes", "1e-9"]
    run_cli(tmp_path, fund)
    _, run_dir, _ = run_cli(tmp_path, ["resume"])
    return read_events(run_dir / "ledger.jsonl")


def cli_awaiting_events(tmp_path):
    """`antstreet fund` with no terminal to ask on (the real `input`, a stdin that is not a TTY),
    then
    `antstreet approve --sheet` with the value it printed: the waiting `stopped` and the
    approval."""
    import io
    import re
    import sys
    from unittest import mock

    from antstreet.cli import main

    project = tmp_path / "project"
    project.mkdir(parents=True, exist_ok=True)
    environ = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    environ["BOSS_CLAUDE_BIN"] = str(fake_claude(tmp_path))
    said: list[str] = []
    with mock.patch.object(sys, "stdin", io.StringIO()):
        argv = ["fund", "Reverse a string.", "--budget", "0.50", "--dir", str(project)]
        main(argv, say=said.append, environ=environ)
    [run_dir] = sorted((project / ".boss" / "runs").iterdir())
    [value] = set(re.findall(r"--sheet ([0-9a-f]{16})", "\n".join(said)))
    approve = ["approve", run_dir.name, "--sheet", value, "--dir", str(project)]
    main(approve, say=said.append, environ=environ)
    return read_events(run_dir / "ledger.jsonl")


def cli_topped_up_events(tmp_path):
    """A round that closed below its unlock threshold because its budget ran out ($0.108 funds one
    slice and leaves less than the $0.105 another needs), then `antstreet topup` on it."""
    run_cli(tmp_path, ["fund", "Reverse a string.", "--budget", "0.108"], broken=True)
    _, run_dir, _ = run_cli(tmp_path, ["topup", "--round", "1", "--amount", "0.25"])
    return read_events(run_dir / "ledger.jsonl")


def roles_events(folder, fix="y"):
    """A run with every role: the real CLI against the fake `claude` of tests/test_pipeline.py,
    which also plays each role. It reaches a disputed check, an approved amendment and both
    judgements."""
    import test_pipeline as staged

    folder.mkdir(parents=True)
    fx = staged.Fx(folder)
    staged.every_role(fx)
    assert fx.fund("--roles", "all", answers={"Task": "d", "Add these": fix}).code == 0
    return fx.events()


def examiner_events(tmp_path):
    """The examiner's call booked by `run_examiner`, with the model call itself stubbed."""
    paths = RunPaths(tmp_path)
    paths.checks.mkdir(parents=True)
    (paths.checks / "test_c01.py").write_text(C01)
    (paths.checks / "test_c02.py").write_text(C02)
    entry = held_out.HeldOutCheck("h01", held_out.file_name("h01"), "Reverse a string.")

    def stub(idea, names, n, visible_ids, **_):
        return [(entry, H01)], Usage(12_000, 900, 400, 0)

    with pytest.MonkeyPatch.context() as patch, LedgerWriter(paths.ledger) as ledger:
        patch.setattr(examiner, "examine", stub)
        run_examiner(
            sheet(), paths, ledger, "r1", n=1, env={"HOME": "/h"}, model="haiku", say=lambda _: None
        )
    return read_events(paths.ledger)


def audit_events(tmp_path):
    """`antstreet audit plan` and `antstreet audit check` against a fake boss and a small git
    repository:
    the boss's audit draft, the investor's approval and the gate's signed verdict."""
    from audit_support import RIGHT_SLUG, Audit, branch, later

    audit = Audit(tmp_path)
    assert audit.plan()[0] == 0
    branch(audit.repo, "good", {"slug.py": RIGHT_SLUG}, later())
    assert audit.check(audit.run_id(), "good", "--claim", "done")[0] == 0
    return read_events(audit.store / ".boss" / "runs" / audit.run_id() / "ledger.jsonl")


def audit_questions_events(tmp_path):
    """`antstreet audit plan --questions` with no terminal, then `antstreet audit approve` twice:
    the stop awaiting the answers, the investor's `answered` rulings, the stop awaiting the
    approval."""
    from audit_support import Audit
    from test_questions import QUESTIONS

    from antstreet import cli

    audit = Audit(tmp_path)
    audit.set_draft(QUESTIONS, "audit_questions.json")
    said: list[str] = []

    def run(*argv):
        return cli.main(["audit", *argv], ask=None, say=said.append, environ=audit.environ())

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli, "_unattended", lambda ask: True)
        repo = ("--repo", str(audit.repo))
        assert run("plan", *repo, "--request", str(audit.request), "--questions") == 4
        assert run("approve", audit.run_id(), "--answers", "y,n,s", *repo) == 4
        digest = re.findall(r"--sheet ([0-9a-f]{16})", "\n".join(said))[-1]
        assert run("approve", audit.run_id(), "--sheet", digest) == 0
    return read_events(audit.store / ".boss" / "runs" / audit.run_id() / "ledger.jsonl")


@pytest.fixture(scope="module")
def produced(tmp_path_factory) -> dict[str, list[Event]]:
    """Every event the code writes across a set of runs that reaches every writer, by type."""
    root = tmp_path_factory.mktemp("ledger")
    runs = []

    def where(name):
        return root / name

    two_rounds = sheet((Round(1, 204_000, 1), Round(2, 300_000, 2)))
    # w1 is refused a tool, disputes c01 and stalls; w2 inherits the unruled dispute and passes
    # the other check, so the investor is asked about c01 (kept); round 2 is funded.
    runs.append(firm_events(where("full"), Script(
        step(BAD, disputes=("c01",), denials=("Write",)), step(BAD),
        step(HALF, cost=100_000), step(GOOD, "done"),
    ), two_rounds, answers=["k", "y"]))  # fmt: skip
    # The investor answers each escalation: set aside (`s`), drop or keep a disputed check,
    # unblock with a note. Each answer writes its own `ruled` or `abandoned` event.
    runs.append(firm_events(where("blocked"), Script(step(None, "blocked")), answers=["s"]))
    runs.append(firm_events(where("unblocked"), Script(step(None, "blocked"), step(GOOD, "done")),
                            answers=["u", "use the standard library"]))  # fmt: skip
    runs.append(
        firm_events(where("disputed"), Script(step(HALF, disputes=("c01",))), answers=["s"])
    )
    runs.append(firm_events(where("dropped"), Script(step(HALF, disputes=("c01",))), answers=["d"]))
    kept = Script(step(HALF, disputes=("c01",)), step(GOOD, "done"))
    runs.append(firm_events(where("kept"), kept, answers=["k"]))
    runs.append(firm_events(where("abandoned"), Script(step(BAD), step(BAD), step(BAD), step(BAD))))
    runs.append(
        firm_events(where("paused"), Script(step(None, outcome=Outcome.USAGE_LIMIT, cost=None)))
    )
    runs.append(firm_events(where("login"), Script(step(None, outcome=Outcome.LOGIN, cost=0))))
    runs.append(firm_events(where("limit"), Script(step(HALF)), config=FirmConfig(
        limits=RunLimits(max_slices=1))))  # fmt: skip
    runs.append(firm_events(where("isolation"), Script(IsolationError("tools differ")),
                            expect=IsolationError))  # fmt: skip
    runs.append(firm_events(where("declined"), Script(step(HALF, cost=100_000)), two_rounds,
                            answers=["n"]))  # fmt: skip
    runs.append(firm_events(where("held-out"), Script(step(GOOD, "done")), held=True))
    runs.append(examiner_events(where("examiner")))
    # dispatch: w1 stalls and w2 is hired one tier up; a thinner round steps the effort instead
    on = FirmConfig(dispatch=True)
    runs.append(firm_events(where("dispatch"), ModelScript(
        step(BAD), step(BAD), step(GOOD, "done")), dispatched(), config=on))  # fmt: skip
    thin = dispatched((Round(1, 400_000, 2),))
    runs.append(
        firm_events(
            where("dispatch-refused"),
            ModelScript(step(BAD, cost=120_000), step(BAD, cost=120_000), step(GOOD, "done")),
            thin,
            config=on,
        )
    )
    ladder = FirmConfig(dispatch=True, cascade=True, max_tier="opus")
    cascaded = plan_cascade(
        sheet((Round(1, 5_000_000, 2),)),
        starts={"t1": "haiku"},
        profile=None,
        policy=DispatchPolicy("opus", 100_000, cascade=True),
        reads={},
    )
    runs.append(firm_events(where("cascade"), ModelScript(
        step(BAD), step(BAD), step(GOOD, "done")), cascaded, config=ladder))  # fmt: skip
    runs.append(firm_events(where("wrong-model"), ModelScript(
        step(HALF), ran="claude-sonnet-4-5-20250929"), dispatched(), config=on,
        expect=ModelMismatchError))  # fmt: skip
    runs.append(cli_events(where("cli-dispatch"), extra=("--dispatch", "rules")))
    runs.append(cli_events(where("cli-approved")))
    runs.append(cli_events(where("cli-rejected"), answers=("r",)))
    runs.append(cli_events(where("cli-no-boss"), binary="/nonexistent/claude"))
    runs.append(cli_events(where("cli-thinking"), extra=("--boss-thinking", "0")))
    runs.append(cli_spec_events(where("cli-spec")))
    runs.append(cli_spec_mapper_events(where("cli-spec-mapper")))
    runs.append(cli_resumed_events(where("cli-resumed")))
    runs.append(cli_topped_up_events(where("cli-topped-up")))
    runs.append(cli_awaiting_events(where("cli-awaiting")))
    runs.append(audit_events(where("audit")))
    runs.append(audit_questions_events(where("audit-questions")))
    runs.append(roles_events(where("cli-roles")))
    runs.append(roles_events(where("cli-declined"), fix="n"))
    runs.append(roles_events(where("cli-skipped"), fix=EOFError))  # the boss's skip: ruled.reason
    found: dict[str, list[Event]] = defaultdict(list)
    for events in runs:
        for e in events:
            found[e.event.value].append(e)
    return found


@pytest.fixture(scope="module")
def text() -> str:
    return read(DOC)


def sections(text: str) -> dict[str, str]:
    """`### `name`` sections of the 'Events' part, by event type name."""
    body = section(text, "Events")
    parts = re.split(r"^### `([a-z_]+)`\s*$", body, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def keys_table(body: str) -> dict[str, str]:
    """key -> type cell, from the section's table (rows whose first cell is a code span)."""
    rows = [r for r in table(body) if r[0].startswith("`")]
    return {r[0].strip("`"): r[1] for r in rows}


def actors_of(body: str) -> set[str]:
    line = next(ln for ln in body.splitlines() if ln.startswith("- Actor"))
    return set(code_spans(line))


def json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    return {int: "int", float: "float", str: "str", dict: "object", list: "list"}[type(value)]


def declared(cell: str) -> set[str]:
    return set(re.findall(r"[a-z]+", cell))


def examples_of(body: str) -> list[Event]:
    blocks = re.findall(r"```json\n(.+?)\n```", body, flags=re.S)
    assert blocks, "a section has no example line"
    return [Event.from_json(block) for block in blocks]


NO_WRITER = {"denied"}


def test_every_event_type_has_a_section_and_no_section_names_another_type(text):
    documented = set(sections(text))
    assert documented == {e.value for e in EventType}, (
        f"missing: {sorted({e.value for e in EventType} - documented)}; "
        f"unknown: {sorted(documented - {e.value for e in EventType})}"
    )


def test_top_level_fields_are_the_event_fields_plus_the_version(text):
    rows = {r[0].strip("`"): r for r in table(section(text, "Top-level fields"))}
    assert set(rows) == {"v", *(f.name for f in fields(Event))}
    assert LEDGER_VERSION == 1 and "`v` | int | Always 1" in text
    for billing in Billing:
        assert f"`{billing.value}`" in rows["billing"][2]
    plain = json.loads(Event(run="r", round=0, actor="boss", event=EventType.STOPPED).to_json())
    assert set(plain) | {"prev"} == set(rows)  # `prev` is written by the writer, not by the event
    chained = json.loads(
        dataclasses.replace(Event(run="r", round=0, actor="boss", event=EventType.STOPPED),
                            prev="0" * 64).to_json()
    )  # fmt: skip
    assert set(chained) == set(rows)


def test_actor_forms_and_the_writer_rules_are_documented(text):
    body = section(text, "Top-level fields")
    for actor in ("boss", "gate", "rule", "investor", "worker:<name>", "role:<name>"):
        assert f"`{actor}`" in body


def test_only_the_reserved_types_have_no_writer_and_the_document_says_so(produced, text):
    # role_call has two: `pipeline.py` (`antstreet fund --roles`) and `roles/examiner.py`.
    unwritten = {e.value for e in EventType} - set(produced)
    assert unwritten == NO_WRITER, f"types with no writer changed: {sorted(unwritten)}"
    for name in NO_WRITER:
        assert "No code writes this event" in sections(text)[name]


def test_every_actor_the_code_used_is_documented_for_its_type(produced, text):
    docs = sections(text)
    for name, events in produced.items():
        seen = {"worker:<name>" if e.actor.startswith("worker:") else e.actor for e in events}
        assert seen <= actors_of(docs[name]), (
            f"{name}: written by {seen}, documented {actors_of(docs[name])}"
        )


def test_every_data_key_the_code_writes_is_documented_with_the_right_type(produced, text):
    docs = sections(text)
    problems = []
    for name, events in produced.items():
        keys = keys_table(docs[name])
        for e in events:
            for key, value in e.data.items():
                if key not in keys:
                    problems.append(f"{name}: key {key!r} is written but not documented")
                elif json_type(value) not in declared(keys[key]):
                    problems.append(f"{name}.{key}: {json_type(value)} is not in {keys[key]!r}")
    assert not problems, "\n".join(sorted(set(problems)))


def test_every_documented_key_is_written_by_some_run(produced, text):
    docs = sections(text)
    stale = []
    for name, events in produced.items():
        written = {k for e in events for k in e.data}
        stale += [f"{name}.{k}" for k in keys_table(docs[name]) if k not in written]
    assert not stale, f"documented but never written by the runs: {stale}"


def test_nested_evidence_keys_are_documented(produced, text):
    [evidence_rows] = [table(sections(text)["fired"].split("Evidence keys")[1])]
    documented = {r[0].strip("`") for r in evidence_rows}
    written = {k for e in produced["fired"] for k in e.data["evidence"]}
    assert written == documented


def test_the_dispatch_keys_of_a_hire_are_documented(produced, text):
    documented = {r[0].strip("`") for r in table(sections(text)["hired"].split("Dispatch keys")[1])}
    written = {k for e in produced["hired"] if "dispatch" in e.data for k in e.data["dispatch"]}
    assert written == documented


def test_the_strength_keys_of_a_verdict_are_documented(produced, text):
    rows = table(sections(text)["audited"].split("Strength keys")[1])
    documented = {r[0].strip("`"): r[1] for r in rows}
    measured = [e.data["strength"] for e in produced["audited"] if e.data.get("strength")]
    assert measured, "no audit run measured strength"
    for strength in measured:
        assert set(strength) == set(documented)
        for key, value in strength.items():
            assert json_type(value) in declared(documented[key]), key


def test_the_started_config_keys_are_documented_with_their_types(produced, text):
    rows = table(sections(text)["started"].split("Config keys")[1])
    documented = {r[0].strip("`"): r[1] for r in rows}

    def flat(prefix, data):
        for key, value in data.items():
            if isinstance(value, dict):
                yield from flat(f"{prefix}{key}.", value)
            else:
                yield f"{prefix}{key}", json_type(value)

    written = {}
    for e in produced["started"]:
        for key, kind in flat("", e.data["config"]):
            written.setdefault(key, set()).add(kind)
    assert set(written) == set(documented)
    for key, kinds in written.items():
        assert kinds <= declared(documented[key]), f"{key}: {kinds} is not in {documented[key]!r}"


def test_every_ruling_and_when_its_optional_keys_appear_is_documented(produced, text):
    body = sections(text)["ruled"]
    rulings = {e.data["ruling"] for e in produced["ruled"]}
    assert rulings == {"dropped", "kept", "unblocked", "declined", "answered"}, (
        "a run no longer reaches all"
    )
    for ruling in rulings:
        assert f"`{ruling}`" in body
    for e in produced["ruled"]:
        # the investor rules; the boss only records a declined fix round nobody was asked about
        assert e.actor == "investor" or (e.actor == "boss" and e.data["ruling"] == "declined")
        assert ("reason" in e.data) == (e.actor == "boss")
        assert ("check" in e.data) == (e.data["ruling"] in ("dropped", "kept"))
        assert ("note" in e.data) == (e.data["ruling"] == "unblocked")
        assert ("task" in e.data) == (e.data["ruling"] not in ("declined", "answered"))
        answered = e.data["ruling"] == "answered"
        assert ("question" in e.data) == ("answer" in e.data) == answered
        assert ("added" in e.data) == (answered and e.data["answer"] != "skip")


def test_each_example_is_a_valid_line_of_the_right_type_with_the_shape_the_code_writes(
    produced, text
):
    docs = sections(text)
    for name, body in docs.items():
        for example in examples_of(body):
            assert example.event.value == name
            if name in NO_WRITER:
                continue
            shape = {k: json_type(v) for k, v in example.data.items()}
            shapes = [{k: json_type(v) for k, v in e.data.items()} for e in produced[name]]
            assert shape in shapes, f"{name}: no run writes an event shaped like {shape}"


def test_the_topped_up_example_is_what_the_budget_reads(text):
    [example] = examples_of(sections(text)["topped_up"])
    base = sheet().rounds[0].budget_micros
    grown = budget.round_budget(sheet(), [example], example.round)
    assert example.round == 1 and grown == base + example.data["micros"]
    assert example.actor == "investor"


def test_the_role_call_section_matches_the_helper_and_names_its_two_writers(produced, text):
    [example] = examples_of(sections(text)["role_call"])
    spec = RoleSpec("critic", "quality", "boss", "review", "a gate", "critic_v1.md", ("s/one",))
    fields = ledger_fields(spec, Usage(7, 3, 2, 1), "completed", model="haiku", env={"HOME": "/h"})
    built = Event(run="r", round=0, actor=spec.actor, event=EventType.ROLE_CALL, **fields)
    documented = keys_table(sections(text)["role_call"])
    # the helper's own keys are documented, and the pipeline adds the rest on top of them
    assert set(built.data) <= set(documented) and {"result", "detail"} <= set(documented)
    assert {"requested", "kept", "problems"} <= set(documented)  # the examiner's own keys
    for key, value in built.data.items():
        assert json_type(value) in declared(documented[key]), key
    assert example.actor == "role:critic" and example.cost_micros is not None
    # Who writes it: `Pipeline._book`, through `ledger_fields`, always in round 0, and the
    # examiner's `run_examiner`. `report.py` reads the events; nothing else names the type or the
    # helper.
    book = inspect.getsource(pipeline.Pipeline._book)
    assert "ledger_fields(" in book and "EventType.ROLE_CALL" in book
    assert "Recorder(self.ledger, self.run_id, 0)(spec.actor," in book
    own = {SRC / "ledger.py", SRC / "roles" / "base.py", SRC / "roles" / "examiner.py"}
    callers = sorted(
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if p not in own and ("ledger_fields" in read(p) or "ROLE_CALL" in read(p))
    )
    assert callers == ["budget.py", "pipeline.py", "report.py"], (
        f"a new module touches role_call: {callers}"
    )
    assert "ledger_fields" not in read(SRC / "report.py")
    # Every event the pipeline wrote is under a role actor, in round 0, with the two keys it adds.
    written = [e for e in produced["role_call"] if e.actor != "role:examiner"]
    chosen = set(registry()) - set(pipeline.BY_OPTION)  # what `--roles all` names
    assert {e.actor for e in written} == {f"role:{name}" for name in chosen}
    for e in written:
        assert e.round == 0 and e.data["result"] in {"ok", "failed", "unused"}
        assert isinstance(e.data["detail"], str) and e.data["role"] == e.actor.removeprefix("role:")


def test_the_started_roles_field_is_what_the_pipeline_records_and_resume_reads(produced, text):
    with_roles = [
        e
        for e in produced["started"]
        if "roles" in e.data and e.data["roles"]["names"] not in (["spec_mapper"], [])
    ]
    # a run awaiting `antstreet approve` records roles with no names; every other run with roles
    # is a run with every role --roles all names; the `--spec` run
    # names the mapper alone, because `all` includes the staged roles --spec refuses
    assert with_roles
    assert any(e.data.get("roles", {}).get("names") == ["spec_mapper"] for e in produced["started"])
    chosen = sorted(set(registry()) - set(pipeline.BY_OPTION))
    for event in with_roles:
        assert sorted(event.data["roles"]) == ["model", "names", "thinking_tokens"]
        assert event.data["roles"]["names"] == chosen
        assert pipeline.recorded_setup([event]) == pipeline.Setup(
            tuple(chosen), event.data["roles"]["model"], None
        )
    # run_firm found this event and wrote none, so there is one per run, and the same config
    assert [e for e in produced["started"] if "roles" not in e.data]  # runs without roles exist
    assert "record_start" in read(SRC / "cli.py") and "Nothing is written without roles" in (
        inspect.getdoc(pipeline.Pipeline.record_start) or ""
    )
    assert "`roles`" in sections(text)["started"] and "`record_start`" in sections(text)["started"]


def test_the_examiners_role_call_is_in_round_1_with_its_own_keys(produced, text):
    documented = keys_table(sections(text)["role_call"])
    [written] = [e for e in produced["role_call"] if e.actor == "role:examiner"]
    assert written.round == 1  # counts against round 1's budget, unlike the pipeline's round 0
    assert {"requested", "kept", "problems"} <= set(written.data) <= set(documented)
    assert "result" not in written.data and "detail" not in written.data
    assert "EventType.ROLE_CALL" in read(SRC / "roles" / "examiner.py")


def test_the_state_contract_is_a_subset_of_this_document(text):
    docs = sections(text)
    contract = re.findall(r"^\s{4}(\w+)\s+\S+\s+\{([^}]*)\}", inspect.getdoc(state) or "", re.M)
    assert contract, "state.py's contract docstring changed shape; update this test"
    for name, keys in contract:
        # the docstring marks a key that only some events carry with a trailing `?`
        named = {k.strip().rstrip("?") for k in keys.split(",") if k.strip() and k.strip() != "..."}
        assert named <= set(keys_table(docs[name])), f"{name}: contract keys not documented"
    assert "state.py" in text
