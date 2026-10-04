"""boss.bench.spec_p1: the P1 criteria in code against the criteria written first, the scoring of
drafts on failing products, and the mapper pass under a spend cap. No model calls: a fake CLI."""

import json
import re
import sys
from pathlib import Path

import pytest
from boss_init import BOSS_INIT_LINE

from boss import spec
from boss.bench import spec_p1 as p1
from boss.bench.drafts import DraftCell, save_claims
from boss.bench.score import DraftScore

ROOT = Path(__file__).parent.parent
TASKS = ROOT / "bench" / "tasks"
CRITERIA = ROOT / "bench" / "spec_truth" / "P1_CRITERIA.md"

PLAIN = (
    "from slugify import slugify\n\ndef test_a():\n"
    "    assert slugify('Hello World') == 'hello-world'\n"
)
RAISES = (
    "import pytest\nfrom slugify import slugify\n\ndef test_b():\n"
    "    with pytest.raises(ValueError):\n        slugify('a', 0)\n"
)
IDEA_TEXT = (TASKS / "slugify" / "idea.md").read_text(encoding="utf-8").strip()


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_the_criteria_in_the_code_are_the_criteria_that_were_written_down_first():
    text = CRITERIA.read_text(encoding="utf-8")
    assert f"at least {p1.KILL_RATE:.0%}" in text and "31%" in text
    assert f"at least {p1.SUBSET_RATE:.0%}" in text and "8%" in text
    assert f"at most {p1.WRONG_SHARE:.0%}" in text
    assert f"At most {p1.MAX_BAD_DRAFTS} of the 17" in text
    assert f"at most {p1.MEAN_CHECKS}" in text
    assert "$4.00" in text and "P2 is not run here" in text
    assert (p1.EXPECTED_PRODUCTS, p1.EXPECTED_SUBSET) == (35, 16)
    assert re.search(r"28 of 89 pairs killed \(31%\).*3 of 38 \(8%\)", " ".join(text.split()))


def cell(status="scored", checks=8, wrong=(), cost=100_000):
    score = None
    if status == "scored":
        score = DraftScore(checks, tuple(wrong), 4, ("m1", "m2"), (), ("m3", "m4"))
    return DraftCell("slugify", 1, "h", "term_sheet_v3.md", "s", "haiku", None, status,
                     "completed", "" if score else "refused", cost, 1, 1, 0, score)  # fmt: skip


def draft(tmp_path, name, **kw):
    return p1.Draft(name, cell(**kw), tmp_path / name, "idea")


def product(task, key_rep, non_ascii):
    return p1.Failing(p1.Product("final3", task, "single", key_rep, Path("."), "x"), non_ascii)


def result(kills, subset_flags, drafts=None, tmp_path=Path(".")):
    """A P1 with one draft per task `t0..` and the given kill outcomes of its one product each."""
    drafts = drafts or [draft(tmp_path, f"t{n}") for n in range(len(kills))]
    prods = tuple(product(f"t{n}", 1, flag) for n, flag in enumerate(subset_flags))
    pairs = {f"t{n}": {prods[n].product.key: bool(k)} for n, k in enumerate(kills)}
    return p1.P1(tuple(drafts), pairs, prods)


def test_each_criterion_is_decided_at_its_boundary_and_all_five_must_hold(tmp_path):
    kills = [1] * 9 + [0] * 11  # 9 of 20 = 45%
    flags = [True] * 10 + [False] * 10  # the first ten tasks are the subset: 9 + 0 kills
    base = result(kills, flags, tmp_path=tmp_path)
    assert base.killed() == (9, 20) and base.killed(True) == (9, 10)
    assert p1.verdicts(base) == {"a": True, "b": True, "c": True, "d": True, "e": True}
    below = result([1] * 8 + [0] * 12, flags, tmp_path=tmp_path)
    assert p1.verdicts(below)["a"] is False
    thin = result([0] * 20, flags, tmp_path=tmp_path)
    assert p1.verdicts(thin)["b"] is False
    forty = result([1] * 4 + [0] * 6, [True] * 10, tmp_path=tmp_path)
    assert p1.verdicts(forty)["b"] is True, "exactly 40% of the subset"


def test_wrong_checks_bad_drafts_and_mean_checks_have_their_own_boundaries(tmp_path):
    five = [draft(tmp_path, f"t{n}", checks=20, wrong=("c01",) if n == 0 else ()) for n in range(1)]
    assert p1.verdicts(result([1], [True], drafts=five, tmp_path=tmp_path))["c"] is True  # 1/20
    over = [draft(tmp_path, "t0", checks=19, wrong=("c01",))]
    assert p1.verdicts(result([1], [True], drafts=over, tmp_path=tmp_path))["c"] is False  # 1/19
    bad = [draft(tmp_path, f"t{n}", status="invalid") for n in range(3)]
    full = result([1] * 3, [True] * 3, drafts=bad, tmp_path=tmp_path)
    assert full.bad == 3 and p1.verdicts(full)["d"] is False
    two = result([1] * 3, [True] * 3, drafts=[*bad[:2], draft(tmp_path, "t2")], tmp_path=tmp_path)
    assert two.bad == 2 and p1.verdicts(two)["d"] is True
    twelve = result([1], [True], drafts=[draft(tmp_path, "t0", checks=12)], tmp_path=tmp_path)
    assert p1.verdicts(twelve)["e"] is True
    many = result([1], [True], drafts=[draft(tmp_path, "t0", checks=13)], tmp_path=tmp_path)
    assert p1.verdicts(many)["e"] is False


def test_a_task_with_no_usable_draft_adds_no_pairs_and_counts_as_bad(tmp_path):
    drafts = [draft(tmp_path, "t0", status="invalid"), draft(tmp_path, "t1")]
    result_ = p1.P1(
        tuple(drafts), {"t1": {"final3/t1/single/rep1": True}},
        (product("t0", 1, True), product("t1", 1, True)),
    )  # fmt: skip
    assert result_.killed() == (1, 1) and result_.bad == 1
    assert p1.render(result_).count("not usable") >= 1


def make_raw(raw, single_calc, single_other, firm_calc, firm_other):
    """Failing final3 products: `calc` ones fail a non-ASCII check, `slugify` ones do not."""
    plan = [("calc", "single", single_calc), ("slugify", "single", single_other),
            ("calc", "firm", firm_calc), ("slugify", "firm", firm_other)]  # fmt: skip
    for task, arm, count in plan:
        failing = "malformed_tokens" if task == "calc" else "basic"
        for rep in range(1, count + 1):
            cell_ = raw / "final3" / task / arm / f"rep{rep}"
            write(cell_ / "result.json", json.dumps({"hidden": {failing: "failed"}}))
            where = cell_ / "workspace" if arm == "single" else cell_ / ".boss/runs/r1/product"
            write(where / "m.py", "x = 1\n")
    passing = raw / "final3" / "slugify" / "single" / "rep99" / "result.json"
    write(passing, json.dumps({"hidden": {"basic": "passed"}}))


def test_the_failing_products_are_counted_and_checked_against_the_numbers_the_criteria_name(
    tmp_path,
):
    make_raw(tmp_path, 6, 13, 10, 6)  # 19 single and 16 firm, 16 of them with a non-ASCII failure
    found = p1.failing_products(tmp_path)
    assert len(found) == 35 and sum(f.non_ascii for f in found) == 16
    assert sum(1 for f in found if f.product.arm == "single") == 19


def test_other_counts_of_failing_products_are_an_error_not_a_quiet_change(tmp_path):
    make_raw(tmp_path, 3, 2, 1, 1)
    with pytest.raises(p1.P1Error, match="expected 35 failing products"):
        p1.failing_products(tmp_path)


def test_a_failing_product_without_its_files_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(p1, "EXPECTED_PRODUCTS", 1)
    monkeypatch.setattr(p1, "EXPECTED_SUBSET", 0)
    write(
        tmp_path / "final3/slugify/firm/rep1/result.json",
        json.dumps({"hidden": {"basic": "failed"}}),
    )
    with pytest.raises(p1.P1Error, match="without its files"):
        p1.failing_products(tmp_path)


def made_draft(out, checks, claims, untested=None, task="slugify"):
    folder = out / task / "rep1"
    for check_id, code in checks.items():
        write(folder / "checks" / f"test_{check_id}.py", code)
    rules = spec.split((TASKS / task / "idea.md").read_text(encoding="utf-8").strip())
    sheet_checks = [type("C", (), {"id": c, "criteria": tuple(r)})() for c, r in claims.items()]
    save_claims(folder, rules, type("D", (), {"sheet": type("S", (), {"checks": sheet_checks})(),
                                              "untested": untested or {}})())  # fmt: skip
    score = DraftScore(
        len(checks), (), 2, ("accents_dropped_not_folded",), (), ("max_length_zero_accepted",)
    )
    DraftCell(
        task,
        1,
        "h",
        "term_sheet_v3.md",
        "s",
        "haiku",
        None,
        "scored",
        "completed",
        "",
        90_000,
        1,
        1,
        0,
        score,
    ).save(folder)
    return folder


def test_a_draft_is_scored_on_the_failing_products_of_its_task_and_its_coverage_is_read(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(p1, "EXPECTED_PRODUCTS", 2)
    monkeypatch.setattr(p1, "EXPECTED_SUBSET", 0)
    out, raw = tmp_path / "out", tmp_path / "raw"
    made_draft(out, {"c01": PLAIN, "c02": RAISES}, {"c01": ["R04"], "c02": ["R13"]})
    for rep in (1, 2):
        write(
            raw / "final3/slugify/single" / f"rep{rep}" / "result.json",
            json.dumps({"hidden": {"basic": "failed"}}),
        )
    write(
        raw / "final3/slugify/single/rep1/workspace/slugify.py",
        "def slugify(t, max_length=None):\n    return t\n",
    )
    write(
        raw / "final3/slugify/single/rep2/workspace/slugify.py",
        "def slugify(t, max_length=None):\n    return t.lower().replace(' ', '-')\n",
    )  # passes PLAIN, accepts 0
    got = p1.run_score(out, raw, TASKS, workers=1, expected_tasks=1)
    assert got.pairs == {
        "slugify": {"final3/slugify/single/rep1": True, "final3/slugify/single/rep2": True}
    }
    assert got.killed() == (2, 2)
    coverage = p1.coverage_of(got.drafts[0])
    assert coverage is not None and coverage.rules == 10 and coverage.uncovered == 8
    text = p1.render(got)
    assert "(a)" in text and "slugify | scored | 2 |" in text


def test_a_missing_draft_for_a_task_is_an_error(tmp_path):
    (tmp_path / "out").mkdir()
    with pytest.raises(p1.P1Error, match="expected the 17"):
        p1.run_score(tmp_path / "out", tmp_path, TASKS)


# --- the mapper pass ----------------------------------------------------------------------------

FAKE = f"""#!{sys.executable}
import os
home = os.environ["HOME"]
open(os.path.join(home, "calls"), "a").write("x")
print({BOSS_INIT_LINE!r})
print(open(os.path.join(home, "out.json")).read())
"""
RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "terminal_reason": "completed",
    "total_cost_usd": 0.05,
    "modelUsage": {"m": {"inputTokens": 1, "outputTokens": 1}},
}


@pytest.fixture
def fake(tmp_path):
    """A fake `claude`; HOME survives the stripped environment, so it answers from there."""
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE)
    cli.chmod(0o755)
    (tmp_path / "calls").write_text("")

    def env(output):
        (tmp_path / "out.json").write_text(json.dumps(RESULT | {"structured_output": output}))
        return {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}

    return str(cli), env, lambda: len((tmp_path / "calls").read_text())


def test_the_mapper_pass_saves_each_map_counts_the_spend_and_stops_at_the_cap(tmp_path, fake):
    cli, env, calls = fake
    out = tmp_path / "out"
    made_draft(out, {"c01": PLAIN}, {"c01": ["R04"]})
    good = {"maps": [{"check": "c01", "exercises": [{"rule": "R04", "line": 4}]}]}
    n, spent = p1.run_mapper(out, TASKS, 200_000, environ=env(good), executable=cli)
    assert (n, spent) == (1, 50_000) and calls() == 1
    saved = json.loads((out / "slugify/rep1" / p1.MAPPER_FILE).read_text())
    assert saved["status"] == "ok" and saved["exercises"] == {"c01": [["R04", 4]]}
    assert p1.run_mapper(out, TASKS, 200_000, environ=env(good), executable=cli) == (0, 0), "done"
    text = p1.render_mapper(out, TASKS)
    assert "1 drafts mapped; 0 citations the mapper could not confirm" in text


def test_the_mapper_pass_makes_no_call_that_could_pass_the_cap(tmp_path, fake):
    cli, env, calls = fake
    for name in ("one", "two"):
        made_draft(tmp_path / name, {"c01": PLAIN}, {"c01": ["R04"]})
    good = {"maps": [{"check": "c01", "exercises": [{"rule": "R04", "line": 4}]}]}
    below = p1.SPEC_MAPPER.cap_micros - 1  # the call may cost up to its cap
    assert p1.run_mapper(tmp_path / "one", TASKS, below, environ=env(good), executable=cli) == (
        0,
        0,
    )
    assert calls() == 0
    cap = p1.SPEC_MAPPER.cap_micros
    assert p1.run_mapper(tmp_path / "two", TASKS, cap, environ=env(good), executable=cli) == (
        1,
        50_000,
    )


def test_a_map_the_gate_refuses_is_saved_as_failed_with_its_spend(tmp_path, fake):
    cli, env, _ = fake
    out = tmp_path / "out"
    made_draft(out, {"c01": PLAIN}, {"c01": ["R04"]})
    bad = {"maps": [{"check": "c01", "exercises": [{"rule": "R04", "line": 1}]}]}
    assert p1.run_mapper(out, TASKS, 1_000_000, environ=env(bad), executable=cli) == (1, 50_000)
    saved = json.loads((out / "slugify/rep1" / p1.MAPPER_FILE).read_text())
    assert saved["status"] == "failed" and "line 1 is not an assertion" in saved["detail"]
    assert "| slugify | failed |" in p1.render_mapper(out, TASKS)


def test_the_cli_refuses_a_missing_folder_and_prints_a_report(tmp_path, capsys):
    assert (
        p1.main(["score", "--drafts", str(tmp_path), "--raw", str(tmp_path), "--tasks", str(TASKS)])
        == 1
    )
    assert "spec_p1:" in capsys.readouterr().err


def test_a_mapper_call_with_no_reported_cost_counts_at_its_cap_never_as_zero(tmp_path, fake):
    cli, env, calls = fake
    made_draft(tmp_path / "out", {"c01": PLAIN}, {"c01": ["R04"]})
    made_draft(tmp_path / "out", {"c01": PLAIN}, {"c01": ["R04"]}, task="calc")
    good = {"maps": [{"check": "c01", "exercises": [{"rule": "R04", "line": 4}]}]}
    environ = env(good)
    out_json = Path(environ["HOME"]) / "out.json"
    no_cost = json.loads(out_json.read_text())
    no_cost.pop("total_cost_usd")
    out_json.write_text(json.dumps(no_cost))
    cap = 2 * p1.SPEC_MAPPER.cap_micros - 1
    n, spent = p1.run_mapper(tmp_path / "out", TASKS, cap, environ=environ, executable=cli)
    assert (n, spent) == (1, p1.SPEC_MAPPER.cap_micros), "the second call might not fit"
