"""Scoring the auditor's flags against the reference solution, and the runner that gets them.
A fake `claude` plays the auditor: no model calls, no spend."""

import json
import sys
from pathlib import Path

import pytest
from boss_init import BOSS_INIT_LINE

from boss.bench import audit as audit_module
from boss.bench.audit import (
    AUDITED,
    FAILED,
    REJECTED,
    AuditCell,
    AuditScore,
    advice_correct,
    find_drafts,
    main,
    render_report,
    run_audit,
    score_audit,
    settings_for,
    summarize,
    support,
)
from boss.bench.drafts import DraftCell
from boss.bench.results import CellResult, cell_dir
from boss.bench.score import DraftScore
from boss.bench.table import wilson_interval
from boss.bench.tasks import load_task, load_tasks
from boss.roles.advisory import Advice, Audit, Verdict
from boss.termsheet import CheckSpec, Round, Task, TermSheet

REFERENCE = "# REFERENCE-MARKER\ndef f(x):\n    return x + 1\n"
MUTANT = "# MUTANT-MARKER\ndef f(x):\n    return x\n"
SOUND = "from demo import f\n\ndef test_one():\n    assert f(1) == 2\n"
WRONG = "from demo import f\n\ndef test_two():\n    assert f(2) == 100\n"
QUOTE = "Create demo.py"


def v(check: str, kind: str) -> Verdict:
    return Verdict(check, kind, "" if kind == "unsupported" else QUOTE, "because")


# --- the scorer, by hand ------------------------------------------------------------------------


def test_a_mixed_audit_is_counted_into_the_four_cells_of_the_confusion_matrix():
    # truth: c02 and c04 are wrong (the reference fails them); c01 and c03 are right.
    #
    #   verdicts:  c01 consistent   c02 contradicts   c03 unsupported   c04 consistent
    #
    #                       truth wrong      truth right
    #   flagged             c02  -> TP = 1   c03 -> FP = 1
    #   judged consistent   c04  -> FN = 1   c01 -> TN = 1
    #
    #   precision = 1 / (1 + 1) = 0.5      recall = 1 / (1 + 1) = 0.5
    #   by kind: consistent 2 (1 wrong: c04), contradicts 1 (1 wrong: c02), unsupported 1 (0)
    audit = Audit((v("c01", "consistent"), v("c02", "contradicts"), v("c03", "unsupported"),
                   v("c04", "consistent")))  # fmt: skip
    assert score_audit({"c02", "c04"}, audit) == AuditScore(
        checks=4,
        wrong=2,
        flagged=2,
        true_positives=1,
        false_positives=1,
        false_negatives=1,
        true_negatives=1,
        judged={"consistent": 2, "contradicts": 1, "unsupported": 1},
        judged_wrong={"consistent": 1, "contradicts": 1, "unsupported": 0},
    )


def test_an_auditor_that_flags_nothing_misses_every_wrong_check():
    # truth: c02 wrong. verdicts: all consistent.
    #   flagged 0 -> TP = 0, FP = 0;  c02 -> FN = 1;  c01, c03 -> TN = 2
    audit = Audit(tuple(v(c, "consistent") for c in ("c01", "c02", "c03")))
    got = score_audit(["c02"], audit)
    assert (got.flagged, got.true_positives, got.false_positives) == (0, 0, 0)
    assert (got.false_negatives, got.true_negatives, got.wrong) == (1, 2, 1)


def test_an_auditor_that_flags_everything_has_no_false_negatives_and_all_the_false_alarms():
    # truth: nothing wrong. verdicts: c01 contradicts, c02 unsupported, c03 unsupported.
    #   flagged 3 -> TP = 0, FP = 3;  FN = 0;  TN = 0
    audit = Audit((v("c01", "contradicts"), v("c02", "unsupported"), v("c03", "unsupported")))
    got = score_audit([], audit)
    assert (got.flagged, got.true_positives, got.false_positives) == (3, 0, 3)
    assert (got.false_negatives, got.true_negatives, got.wrong) == (0, 0, 0)
    assert got.judged == {"consistent": 0, "contradicts": 1, "unsupported": 2}
    assert got.judged_wrong == {"consistent": 0, "contradicts": 0, "unsupported": 0}


def test_every_wrong_check_flagged_is_all_true_positives():
    # truth: c01, c02 wrong; verdicts: contradicts, unsupported -> TP = 2, nothing else.
    got = score_audit({"c01", "c02"}, Audit((v("c01", "contradicts"), v("c02", "unsupported"))))
    assert (got.true_positives, got.false_positives, got.false_negatives) == (2, 0, 0)
    assert got.judged_wrong == {"consistent": 0, "contradicts": 1, "unsupported": 1}


@pytest.mark.parametrize(
    ("wrong", "verdicts"),
    [
        (["c09"], [v("c01", "consistent")]),  # truth names a check the audit does not cover
        ([], [v("c01", "consistent"), v("c01", "contradicts")]),  # two verdicts for one check
        ([], []),
        ([], [Verdict("c01", "maybe", QUOTE, "x")]),
    ],
)
def test_an_audit_that_does_not_match_the_draft_cannot_be_scored(wrong, verdicts):
    with pytest.raises(ValueError):
        score_audit(wrong, Audit(tuple(verdicts)))


def test_a_score_that_does_not_add_up_is_refused():
    ok = dict(
        checks=4,
        wrong=2,
        flagged=2,
        true_positives=1,
        false_positives=1,
        false_negatives=1,
        true_negatives=1,
        judged={},
        judged_wrong={},
    )
    AuditScore(**ok)
    for change in ({"flagged": 3}, {"wrong": 3}, {"checks": 5}):
        with pytest.raises(ValueError):
            AuditScore(**ok | change)


@pytest.mark.parametrize(
    ("is_wrong", "recommendation", "correct"),
    [
        (True, "drop", True),  # a wrong check should be dropped
        (True, "keep", False),  # ... and keeping it gets a correct worker fired
        (False, "keep", True),  # a right check should stay
        (False, "drop", False),  # ... and dropping it weakens the gate
    ],
)
def test_advice_is_correct_when_it_drops_a_wrong_check_and_keeps_a_right_one(
    is_wrong, recommendation, correct
):
    for confidence in ("low", "high"):  # confidence does not change whether it was right
        advice = Advice(recommendation, confidence, QUOTE, "why")
        assert advice_correct(is_wrong, advice) is correct


# --- fixtures: tiny tasks, a results folder of each layout, a fake auditor -----------------------

FAKE = f"""#!{sys.executable}
import json, os, re, sys
home = os.environ["HOME"]
with open(os.path.join(home, "calls.log"), "a") as log:
    log.write(json.dumps({{"argv": sys.argv[1:], "env": sorted(os.environ)}}) + "\\n")
mode = open(home + "/mode").read().strip() if os.path.exists(home + "/mode") else "ok"
base = {{"type": "result", "subtype": "success", "is_error": False,
        "terminal_reason": "completed", "session_id": "s", "total_cost_usd": 0.03,
        "modelUsage": {{"m": {{"inputTokens": 100, "outputTokens": 50}}}}}}
print({BOSS_INIT_LINE!r})
prompt = sys.argv[-1]
ids = re.findall(r"^Check (c\\d+)$", prompt, re.M)
kinds = json.load(open(home + "/kinds.json"))
task = next(name for name in kinds if "marker-" + name in prompt)
if mode == "login":
    print(json.dumps(base | {{"is_error": True, "api_error_status": 401,
                             "terminal_reason": "api_error", "total_cost_usd": 0,
                             "modelUsage": {{}}}}))
elif mode == "capped":
    print(json.dumps(base | {{"subtype": "error_max_budget_usd", "is_error": True,
                             "terminal_reason": "budget_exhausted", "total_cost_usd": 0.15}}))
elif mode == "empty":
    print(json.dumps(base))
elif mode == "partial":
    verdicts = [{{"check": ids[0], "verdict": "consistent", "quote": "Create demo.py",
                 "why": "w"}}]
    print(json.dumps(base | {{"structured_output": {{"verdicts": verdicts}}}}))
else:
    verdicts = [
        {{"check": i, "verdict": kinds[task][i],
         "quote": "" if kinds[task][i] == "unsupported" else "Create demo.py", "why": "w"}}
        for i in ids
    ]
    print(json.dumps(base | {{"structured_output": {{"verdicts": verdicts}}}}))
"""


def make_task(root: Path, name: str) -> None:
    folder = root / name
    (folder / "reference").mkdir(parents=True)
    (folder / "reference" / "demo.py").write_text(REFERENCE)
    for mutant in ("m1", "m2", "m3"):
        (folder / "mutants" / mutant).mkdir(parents=True)
        (folder / "mutants" / mutant / "demo.py").write_text(MUTANT)
    (folder / "hidden_checks").mkdir()
    (folder / "hidden_checks" / "test_secret.py").write_text("# HIDDEN-MARKER\n")
    (folder / "meta.json").write_text(json.dumps({"id": name, "title": name, "difficulty": "easy"}))
    (folder / "idea.md").write_text(f"Create demo.py, marker-{name}, with f(x) returning x + 1.")


def write_checks(folder: Path, codes: list[str]) -> None:
    folder.mkdir(parents=True)
    for n, code in enumerate(codes, start=1):
        (folder / f"test_c{n:02d}.py").write_text(code)


def make_firm_results(root: Path, cells: dict[tuple[str, int], list[str] | None]) -> Path:
    """A `boss.bench.run` folder: each firm cell has a run with checks and a term sheet, or (None)
    a run that never drafted."""
    for (task, rep), codes in cells.items():
        folder = cell_dir(root, task, "firm", rep)
        CellResult(
            task=task, arm="firm", rep=rep, set_hash="h", model="haiku", budget_micros=400_000,
            hidden={"x": "passed"}, visible_passed=1, visible_total=1, cost_micros=1,
            boss_micros=1, unknown_cost_events=0, outcome="completed", failure_class=None,
            duration_s=1.0,
        ).save(folder)  # fmt: skip
        run = folder / ".boss" / "runs" / "r1"
        run.mkdir(parents=True)
        if codes is None:
            continue
        write_checks(run / "checks", codes)
        specs = tuple(
            CheckSpec(f"c{n:02d}", f"describes c{n:02d}", f"test_c{n:02d}.py", "t1")
            for n in range(1, len(codes) + 1)
        )
        sheet = TermSheet("idea", 1, (Round(1, 1, len(specs)),), specs, (Task("t1", "b", ("d",)),))
        (run / "term_sheet.json").write_text(sheet.to_json())
    return root


def make_drafts_results(root: Path, cells: dict[tuple[str, int], tuple[str, list[str]]]) -> Path:
    """A `boss.bench.drafts` folder: (status, check codes) per cell; no term sheet is saved."""
    for (task, rep), (status, codes) in cells.items():
        folder = root / task / f"rep{rep}"
        write_checks(folder / "checks", codes)
        score = DraftScore(len(codes), (), 1, ("m1",), (), ()) if status == "scored" else None
        DraftCell(
            task=task, rep=rep, set_hash="h", prompt="p", prompt_sha="s", boss_model="haiku",
            boss_thinking=None, status=status, outcome="completed", detail="", cost_micros=1,
            tokens_in=0, tokens_out=0, tokens_cached=0, score=score,
        ).save(folder)  # fmt: skip
    return root


class Env:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.home = tmp_path
        self.tasks = tmp_path / "tasks"
        for name in ("alpha", "beta"):
            make_task(self.tasks, name)
        fake = tmp_path / "fake-claude"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        self.out = tmp_path / "out"
        self.environ = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "BOSS_CLAUDE_BIN": str(fake),
        }
        self.validated: list[str] = []
        monkeypatch.setattr(audit_module, "validate_task", lambda t: self.validated.append(t.id))
        # what the fake auditor says: check id -> verdict kind, per task
        self.kinds({"alpha": {"c01": "consistent", "c02": "contradicts"},
                    "beta": {"c01": "consistent", "c02": "unsupported"}})  # fmt: skip

    def kinds(self, kinds: dict) -> None:
        (self.home / "kinds.json").write_text(json.dumps(kinds))

    def mode(self, mode: str) -> None:
        (self.home / "mode").write_text(mode)

    def calls(self) -> list[dict]:
        log = self.home / "calls.log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def task(self, name: str):
        return load_task(self.tasks / name)

    def run(self, *argv: str) -> int:
        return main(
            ["--tasks", str(self.tasks), "--out", str(self.out), *argv], environ=self.environ
        )


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


@pytest.fixture
def pilot(tmp_path):
    """Two firm cells. alpha: c01 sound, c02 wrong. beta: c01 sound, c02 sound."""
    root = make_firm_results(
        tmp_path / "pilot", {("alpha", 1): [SOUND, WRONG], ("beta", 1): [SOUND, SOUND]}
    )
    CellResult(  # a single-arm cell has no boss draft and is not counted as missing one
        task="alpha", arm="single", rep=1, set_hash="h", model="haiku", budget_micros=1,
        hidden={"x": "passed"}, visible_passed=None, visible_total=None, cost_micros=1,
        boss_micros=0, unknown_cost_events=0, outcome="completed", failure_class=None,
        duration_s=1.0,
    ).save(cell_dir(root, "alpha", "single", 1))  # fmt: skip
    return root


# --- finding the drafts -------------------------------------------------------------------------


def test_a_run_folder_gives_each_firm_cell_its_checks_and_the_term_sheets_descriptions(env, pilot):
    tasks = load_tasks(env.tasks)
    found, without = find_drafts(pilot, tasks)
    assert without == 0 and [(t.source, t.task.id, t.rep) for t in found] == [
        ("pilot", "alpha", 1),
        ("pilot", "beta", 1),
    ]
    alpha = found[0]
    assert alpha.described and alpha.checks_dir.name == "checks"
    assert [(c.id, c.description, c.file) for c in alpha.specs] == [
        ("c01", "describes c01", "test_c01.py"),
        ("c02", "describes c02", "test_c02.py"),
    ]


def test_a_drafts_folder_gives_its_scored_drafts_without_descriptions(env, tmp_path):
    root = make_drafts_results(
        tmp_path / "d1",
        {("alpha", 1): ("scored", [SOUND, WRONG]), ("beta", 1): ("invalid", [SOUND])},
    )
    found, without = find_drafts(root, load_tasks(env.tasks))
    assert without == 1  # the invalid draft is not audited
    [target] = found
    assert (target.source, target.task.id, target.rep, target.described) == (
        "d1",
        "alpha",
        1,
        False,
    )
    assert [c.description for c in target.specs] == ["", ""]


def test_cells_without_a_draft_are_counted_and_tasks_outside_the_selection_are_skipped(
    env, tmp_path
):
    root = make_firm_results(
        tmp_path / "r", {("alpha", 1): [SOUND], ("alpha", 2): None, ("beta", 1): [SOUND]}
    )
    found, without = find_drafts(root, [env.task("alpha")])
    assert [(t.task.id, t.rep) for t in found] == [("alpha", 1)] and without == 1
    drafts = make_drafts_results(
        tmp_path / "d", {("alpha", 1): ("scored", [SOUND]), ("beta", 1): ("scored", [SOUND])}
    )
    found, without = find_drafts(drafts, [env.task("alpha")])
    assert [(t.task.id, t.rep) for t in found] == [("alpha", 1)] and without == 0


def test_a_term_sheet_that_cannot_be_read_leaves_the_audit_to_the_code_alone(env, pilot):
    for sheet in pilot.glob("*/firm/rep1/.boss/runs/r1/term_sheet.json"):
        sheet.write_text("not json")
    found, _ = find_drafts(pilot, load_tasks(env.tasks))
    assert [t.described for t in found] == [False, False]
    assert all(c.description == "" for t in found for c in t.specs)


def test_a_folder_holding_both_layouts_yields_both(env, pilot):
    make_drafts_results(pilot, {("alpha", 2): ("scored", [SOUND])})
    found, _ = find_drafts(pilot, load_tasks(env.tasks))
    assert sorted((t.task.id, t.rep, t.described) for t in found) == [
        ("alpha", 1, True),
        ("alpha", 2, False),
        ("beta", 1, True),
    ]


# --- one audit ----------------------------------------------------------------------------------


def audit_one(env, pilot, name="alpha", **kw):
    [target] = [t for t in find_drafts(pilot, load_tasks(env.tasks))[0] if t.task.id == name]
    return run_audit(
        target, env.out, environ=env.environ, settings=settings_for("haiku", None, "h"), **kw
    )


def test_an_audit_is_saved_with_verdicts_the_truth_cost_and_a_score_that_matches(env, pilot):
    cell = audit_one(env, pilot)
    assert (cell.status, cell.outcome, cell.detail) == (AUDITED, "completed", "")
    assert (cell.cost_micros, cell.tokens_in, cell.tokens_out) == (30_000, 100, 50)
    assert cell.checks == ("c01", "c02") and cell.wrong == ("c02",)  # the reference fails WRONG
    assert [(x.check, x.verdict) for x in cell.verdicts] == [
        ("c01", "consistent"),
        ("c02", "contradicts"),
    ]
    # truth c02 wrong; the auditor flagged c02: TP = 1, nothing else
    assert cell.score == score_audit(["c02"], Audit(cell.verdicts))
    assert (cell.score.true_positives, cell.score.false_positives) == (1, 0)
    saved = env.out / "pilot" / "alpha" / "rep1" / "audit.json"
    assert AuditCell.load(saved) == cell


def test_the_auditor_sees_the_idea_the_checks_and_their_descriptions_and_nothing_else(env, pilot):
    env.environ["SECRET_TOKEN"] = "hunter2"
    audit_one(env, pilot)
    [call] = env.calls()
    argv = call["argv"]
    assert argv[argv.index("--model") + 1] == "haiku" and argv[argv.index("--tools") + 1] == ""
    prompt = argv[-1]
    assert env.task("alpha").idea in prompt
    assert SOUND in prompt and WRONG in prompt and "describes c02" in prompt
    assert "SECRET_TOKEN" not in call["env"]
    for word in ("HIDDEN-MARKER", "MUTANT-MARKER", "REFERENCE-MARKER"):
        assert word not in json.dumps(argv)


def test_a_draft_saved_without_descriptions_is_audited_on_its_code_and_marked_so(env, tmp_path):
    root = make_drafts_results(tmp_path / "d1", {("alpha", 1): ("scored", [SOUND, WRONG])})
    [target] = find_drafts(root, load_tasks(env.tasks))[0]
    cell = run_audit(
        target, env.out, environ=env.environ, settings=settings_for("haiku", None, "h")
    )
    assert cell.described is False and cell.status == AUDITED
    assert "(none saved)" in env.calls()[0]["argv"][-1]


def test_a_broken_gate_stops_the_audit_before_any_call_is_paid_for(env, pilot, monkeypatch):
    def broken(*args):
        raise RuntimeError("the gate broke")

    monkeypatch.setattr(audit_module, "_wrong_ids", broken)
    with pytest.raises(RuntimeError, match="gate broke"):
        audit_one(env, pilot)
    assert env.calls() == [] and not env.out.exists()


def test_a_finished_audit_is_not_made_again(env, pilot):
    first = audit_one(env, pilot)
    env.mode("login")
    assert audit_one(env, pilot) == first
    assert len(env.calls()) == 1


@pytest.mark.parametrize(
    ("mode", "status"),
    [("login", FAILED), ("capped", FAILED), ("empty", REJECTED), ("partial", REJECTED)],
)
def test_an_audit_that_fails_or_is_rejected_is_recorded_with_no_verdicts_and_no_score(
    env, pilot, mode, status
):
    env.mode(mode)
    cell = audit_one(env, pilot)
    assert cell.status == status and cell.verdicts is None and cell.wrong is None
    assert cell.score is None and cell.detail
    assert AuditCell.load(env.out / "pilot" / "alpha" / "rep1" / "audit.json") == cell
    kept = env.out / "pilot" / "alpha" / "rep1" / "rejected_output.json"
    if mode == "partial":
        assert cell.detail == "c02: no verdict" and cell.cost_micros == 30_000  # paid for
        refused = json.loads(kept.read_text())
        assert refused["role"] == "check_auditor" and refused["problems"] == ["c02: no verdict"]
        assert [v["check"] for v in refused["output"]["verdicts"]] == ["c01"]
    else:
        assert not kept.exists()  # nothing was refused: there was no output to keep
    if mode == "capped":
        assert cell.outcome == "capped" and cell.cost_micros == 150_000
    if mode == "login":
        assert cell.outcome == "login"


def test_a_failed_audit_is_made_again_only_when_asked(env, pilot):
    env.mode("login")
    assert audit_one(env, pilot).status == FAILED
    assert audit_one(env, pilot).status == FAILED and len(env.calls()) == 1
    env.mode("ok")
    assert audit_one(env, pilot, retry_failed=True).status == AUDITED
    assert len(env.calls()) == 2
    env.mode("empty")  # a rejected audit is a result, not a failure to run
    assert audit_one(env, pilot, retry_failed=True).status == AUDITED and len(env.calls()) == 2


# --- the saved cell -----------------------------------------------------------------------------


def test_a_malformed_saved_audit_is_refused_with_its_path(env, pilot, tmp_path):
    cell = audit_one(env, pilot)
    path = env.out / "pilot" / "alpha" / "rep1" / "audit.json"
    raw = json.loads(path.read_text())
    bad = tmp_path / "bad.json"
    for change in (
        {"status": "done"},
        {"rep": True},
        {"rep": "1"},
        {"described": 1},
        {"verdicts": None},  # audited with no verdicts
        {"verdicts": [{"check": "c01"}]},
        {"verdicts": [{"check": "c01", "verdict": "x", "quote": 1, "why": ""}]},
        {"wrong": [1]},
        {"checks": "c01"},
        {"extra": 1},
    ):
        bad.write_text(json.dumps(raw | change))
        with pytest.raises(ValueError, match="bad.json"):
            AuditCell.load(bad)
    bad.write_text("{")
    with pytest.raises(ValueError, match="not valid JSON"):
        AuditCell.load(bad)
    assert AuditCell.load(path) == cell


# --- the report ---------------------------------------------------------------------------------


def cell_of(**over) -> AuditCell:
    base = dict(
        source="s", task="t", rep=1, set_hash="h", prompt_sha="p", model="haiku", thinking=None,
        described=True, status=AUDITED, outcome="completed", detail="", cost_micros=30_000,
        tokens_in=1, tokens_out=1, tokens_cached=0, checks=("c01", "c02", "c03", "c04"),
        verdicts=(v("c01", "consistent"), v("c02", "contradicts"), v("c03", "unsupported"),
                  v("c04", "consistent")),
        wrong=("c02", "c04"),
    )  # fmt: skip
    return AuditCell(**base | over)


def excluded(status, cost=None):
    return cell_of(status=status, verdicts=None, wrong=None, cost_micros=cost, detail="why")


def test_a_summary_adds_up_the_audited_cells_only_and_counts_the_rest_apart():
    # two audited drafts, each the matrix worked out above: TP 1, FP 1, FN 1, TN 1 each.
    cells = [cell_of(), cell_of(rep=2, cost_micros=50_000), excluded(REJECTED, 20_000),
             excluded(FAILED)]  # fmt: skip
    s = summarize(cells)
    assert (s.calls, s.audits, s.rejected, s.failed) == (4, 2, 1, 1)
    assert (s.checks, s.wrong, s.flagged) == (8, 4, 4)
    assert (s.true_positives, s.false_positives, s.false_negatives) == (2, 2, 2)
    assert s.judged == {"consistent": 4, "contradicts": 2, "unsupported": 2}
    assert s.judged_wrong == {"consistent": 2, "contradicts": 2, "unsupported": 0}
    assert s.mean_cost_micros == pytest.approx((30_000 + 50_000 + 20_000) / 3)  # unknown is not 0
    assert s.unknown_cost_calls == 1


def test_the_report_gives_precision_and_recall_with_wilson_intervals_and_the_split_by_kind():
    text = render_report([cell_of(), cell_of(rep=2)])
    low, high = wilson_interval(2, 4)
    interval = f"[{low * 100:.0f}-{high * 100:.0f}%]"
    assert f"precision (flag is a wrong check): 2/4 = 50% {interval}" in text
    assert f"recall (wrong check is flagged): 2/4 = 50% {interval}" in text
    assert "- checks: 8, wrong (truth): 4 (50%)" in text
    assert "true positives 2, false positives 2, false negatives 2" in text
    assert "- flagged: 4 (2.0 per audit)" in text
    assert "| consistent | 4 | 2 | 50% | 50% |" in text
    assert "| contradicts | 2 | 2 | 100% | 50% |" in text
    assert "| unsupported | 2 | 0 | 0% | 0% |" in text
    assert "| s | 2 | 8 | 4 | 4 | 2 | 2 | 2 | 0 |" in text
    assert "$0.0300" in text


def test_rejected_and_failed_audits_are_excluded_from_every_rate_and_said_so():
    with_extras = render_report([cell_of(), excluded(REJECTED, 1), excluded(FAILED)])
    alone = render_report([cell_of()])
    rates = [ln for ln in with_extras.splitlines() if ln.startswith(("- checks", "- flagged"))]
    assert rates == [ln for ln in alone.splitlines() if ln.startswith(("- checks", "- flagged"))]
    assert "1 rejected (paid for, failed the gate) and 1 failed audits are excluded" in with_extras
    assert "| s | 1 | 4 | 2 | 2 | 1 | 1 | 1 | 2 |" in with_extras  # 2 excluded


def test_a_report_of_only_failures_has_no_rates_and_does_not_divide_by_zero():
    text = render_report([excluded(FAILED), excluded(REJECTED)])
    assert "precision (flag" not in text and "| 2 | 0 | 1 | 1 | n/a | n/a | 2 |" in text
    assert "No audit produced an opinion (1 rejected, 1 failed)" in text
    with pytest.raises(ValueError):
        render_report([])


def test_precision_and_recall_over_nothing_are_not_a_number_not_zero():
    clean = cell_of(
        wrong=(), verdicts=tuple(v(c, "consistent") for c in ("c01", "c02", "c03", "c04"))
    )
    text = render_report([clean])
    assert "precision (flag is a wrong check): n/a (no cases)" in text
    assert "recall (wrong check is flagged): n/a (no cases)" in text
    assert "recall cannot be measured at all" in text


def test_the_report_says_recall_rests_on_few_wrong_checks_until_it_does_not():
    small = summarize([cell_of()])
    lines = " ".join(support(small))
    assert "Recall rests on 2 wrong checks and precision on 2 flags" in lines
    assert (
        "rough figure" in lines
        and "one more or fewer wrong check found moves it by 50 points" in lines
    )
    assert "lower bound" in lines and "Base rate: 50%" in lines
    assert "stays advisory" in lines
    # the warning holds up to 29 wrong checks and stops at 30 (2 wrong per draft)
    assert "rough figure" in " ".join(support(summarize([cell_of(rep=n) for n in range(14)])))
    thirty = summarize([cell_of(rep=n) for n in range(15)])
    assert thirty.wrong == 30 and "rough figure" not in " ".join(support(thirty))


def test_the_report_names_audits_that_ran_on_code_alone():
    text = render_report([cell_of(), cell_of(rep=2, described=False)])
    assert "1 of 2 audits ran on drafts saved without check descriptions" in text
    assert "ran on drafts saved without" not in render_report([cell_of()])


def test_results_made_with_different_settings_are_flagged_as_mixed():
    assert "WARNING" not in render_report([cell_of(), cell_of(rep=2)])
    assert "WARNING" in render_report([cell_of(), cell_of(rep=2, model="sonnet")])


# --- the command line ---------------------------------------------------------------------------


def test_dry_run_prints_the_calls_and_the_ceiling_and_spends_and_writes_nothing(env, pilot, capsys):
    assert env.run("--results", str(pilot), "--dry-run") == 0
    out = capsys.readouterr().out
    assert (
        "2 drafts, 2 to audit" in out and "2 calls, up to $0.3 at the per-call cap of $0.15" in out
    )
    assert "pilot/alpha rep1 (to do)" in out and "pilot/beta rep1 (to do)" in out
    assert env.calls() == [] and not env.out.exists() and env.validated == []


def test_dry_run_says_which_drafts_are_done_and_counts_only_the_rest(env, pilot, capsys):
    assert env.run("--results", str(pilot), "--only", "alpha") == 0
    capsys.readouterr()
    assert env.run("--results", str(pilot), "--dry-run") == 0
    out = capsys.readouterr().out
    assert "2 drafts, 1 to audit" in out and "up to $0.15 at" in out
    assert "pilot/alpha rep1\n" in out and "pilot/beta rep1 (to do)" in out


def test_a_real_run_prints_the_ceiling_first_then_each_audit_then_the_report(env, pilot, capsys):
    assert env.run("--results", str(pilot), "--jobs", "1") == 0
    out = capsys.readouterr().out
    assert out.index("up to $0.3") < out.index("pilot/alpha") < out.index("precision (flag")
    assert sorted(env.validated) == ["alpha", "beta"]
    # alpha: c02 wrong and flagged (TP). beta: nothing wrong, c02 flagged unsupported (FP).
    assert "- checks: 4, wrong (truth): 1 (25%)" in out
    assert "true positives 1, false positives 1, false negatives 0" in out
    assert "precision (flag is a wrong check): 1/2 = 50%" in out
    assert "recall (wrong check is flagged): 1/1 = 100%" in out
    assert len(env.calls()) == 2


def test_running_again_makes_no_call_and_prints_the_same_report(env, pilot, capsys):
    env.run("--results", str(pilot))
    first = capsys.readouterr().out.split("\n\n", 1)[1]
    env.mode("login")
    assert env.run("--results", str(pilot)) == 0
    again = capsys.readouterr().out
    assert len(env.calls()) == 2 and "0 to audit" in again
    assert again.split("\n\n", 1)[1] == first


def test_an_interrupted_run_only_makes_the_missing_audits(env, pilot):
    env.run("--results", str(pilot), "--only", "alpha")
    assert len(env.calls()) == 1
    env.run("--results", str(pilot))
    assert len(env.calls()) == 2 and env.validated == ["alpha", "beta"]


def test_both_run_folders_and_both_layouts_are_audited_side_by_side(env, pilot, tmp_path, capsys):
    rerun = make_firm_results(tmp_path / "rerun1", {("alpha", 1): [SOUND, SOUND]})
    drafts = make_drafts_results(tmp_path / "d1", {("beta", 1): ("scored", [SOUND, WRONG])})
    assert env.run("--results", str(pilot), str(rerun), str(drafts)) == 0
    out = capsys.readouterr().out
    assert len(env.calls()) == 4
    for source in ("pilot", "rerun1", "d1"):
        assert f"| {source} |" in out
    assert "1 of 4 audits ran on drafts saved without check descriptions" in out
    assert (env.out / "rerun1" / "alpha" / "rep1" / "audit.json").is_file()
    assert (env.out / "d1" / "beta" / "rep1" / "audit.json").is_file()


def test_results_folders_with_one_name_are_refused_before_anything_runs(env, pilot, tmp_path):
    other = make_firm_results(tmp_path / "elsewhere" / "pilot", {("alpha", 1): [SOUND]})
    with pytest.raises(SystemExit) as info:
        env.run("--results", str(pilot), str(other))
    assert info.value.code == 2 and env.calls() == []


def test_changed_settings_are_refused_before_any_spend(env, pilot, capsys):
    env.run("--results", str(pilot), "--only", "alpha")
    capsys.readouterr()
    assert env.run("--results", str(pilot), "--model", "sonnet") == 1
    assert "use a fresh --out" in capsys.readouterr().err and len(env.calls()) == 1
    assert env.run("--results", str(pilot), "--thinking", "0") == 1


def test_failed_audits_are_listed_and_counted_never_as_nothing_flagged(env, pilot, capsys):
    env.mode("login")
    assert env.run("--results", str(pilot)) == 0
    out = capsys.readouterr().out
    assert "failed (login)" in out and "| 2 | 0 | 0 | 2 | n/a | $0.0000 | 0 |" in out
    assert "precision" not in out
    env.mode("ok")
    assert env.run("--results", str(pilot), "--retry-failed") == 0
    assert "| 2 | 2 | 0 | 0 | 2.0 |" in capsys.readouterr().out


def test_nothing_to_audit_is_an_error(env, tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert env.run("--results", str(empty)) == 1
    assert "no drafts found" in capsys.readouterr().err
    assert env.run("--results", str(empty), "--only", "nope") == 1
    assert "no matching tasks" in capsys.readouterr().err


def test_a_results_folder_that_cannot_be_read_is_reported_not_a_traceback(env, pilot, capsys):
    (pilot / "alpha" / "firm" / "rep1" / "result.json").write_text("{")
    assert env.run("--results", str(pilot)) == 1
    assert "cannot read drafts under" in capsys.readouterr().err


def test_the_command_is_the_documented_module(env):
    assert audit_module.AUDITOR.cap_micros == 150_000
    assert audit_module.settings_for("haiku", None, "h").prompt_sha != ""
