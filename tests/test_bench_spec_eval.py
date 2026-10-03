"""boss.bench.spec_eval: the offline evaluation's arithmetic, on small hand-made fixtures, and its
guards against stale labels and a moved goalpost."""

import json
import re
import shutil
from pathlib import Path

import pytest

from boss import spec
from boss.bench import spec_eval as ev
from boss.bench.tasks import load_task, load_tasks

ROOT = Path(__file__).parent.parent
TASKS = ROOT / "bench" / "tasks"
TRUTH = ROOT / "bench" / "spec_truth"
ORIGINAL_17 = sorted(p.stem for p in TRUTH.glob("*.json"))

NON_ASCII_CHECK = (
    "from slugify import slugify\n\ndef test_a():\n    assert slugify('Crème') == 'creme'\n"
)
PLAIN_CHECK = (
    "from slugify import slugify\n\ndef test_a():\n"
    "    assert slugify('Hello World') == 'hello-world'\n"
)
RAISES_CHECK = (
    "import pytest\nfrom slugify import slugify\n\ndef test_a():\n"
    "    with pytest.raises(ValueError):\n        slugify('a', 0)\n"
)


def slugify_labels() -> ev.Labels:
    return ev.load_labels(TRUTH, load_task(TASKS / "slugify"))


# --- the goalpost -----------------------------------------------------------------------------


def test_the_criteria_in_the_code_are_the_criteria_that_were_written_down_first():
    text = (TRUTH / ev.CRITERIA_FILE).read_text(encoding="utf-8")
    for pattern in (
        r"at most \d+ in at least \d+% of the ideas|at most \d+ sentences",
        r"At least \d+% of the 15 known-omission cells",
        r"Median flagged rules per draft is at most \d+",
        r"is at least \d+ points, with at least \d+ triples",
        r"If under \d+%, every file was hand-labelled",
    ):
        assert re.search(pattern, text, re.I), pattern
    assert f"at most {ev.MAX_SENTENCES}" in text and f"{ev.SENTENCE_SHARE:.0%}" in text
    assert f"At least {ev.RECALL:.0%} of the {ev.KNOWN_OMISSIONS} known-omission" in text
    assert f"is at most {ev.BURDEN_MEDIAN}" in text
    assert f"at least {ev.GAP_POINTS} points, with at least {ev.MIN_TRIPLES} triples" in text
    assert f"under {ev.AGREEMENT:.0%}" in text
    assert "(9 of 15)" in text and round(ev.RECALL * ev.KNOWN_OMISSIONS) == 9


def test_every_report_header_names_the_hash_of_the_criteria_file():
    header = ev.criteria_header(TRUTH)
    assert "sha256" in header and "missing" not in header
    assert "missing" in ev.criteria_header(TRUTH / "nowhere")


# --- labels -----------------------------------------------------------------------------------


def test_there_are_hand_labels_for_the_17_original_tasks_and_every_one_loads():
    assert len(ORIGINAL_17) == 17
    for task in load_tasks(TASKS):
        if task.id in ORIGINAL_17:
            labels = ev.load_labels(TRUTH, task)
            assert set(labels.hidden) == {c.id for c in task.hidden_checks()}


def test_labels_made_for_another_idea_are_refused(tmp_path):
    shutil.copytree(TASKS / "slugify", tmp_path / "slugify")
    (tmp_path / "slugify" / "idea.md").write_text("1. Something else entirely.\n", encoding="utf-8")
    with pytest.raises(ev.EvalError, match="another idea or splitter"):
        ev.load_labels(TRUTH, load_task(tmp_path / "slugify"))


def test_a_label_for_a_rule_that_is_not_the_labelled_one_is_refused(tmp_path):
    truth = tmp_path / "truth"
    shutil.copytree(TRUTH, truth)
    data = json.loads((truth / "slugify.json").read_text(encoding="utf-8"))
    data["rules"]["R04"] = "Not the text of rule four at all"
    (truth / "slugify.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ev.EvalError, match="not the rule that was labelled"):
        ev.load_labels(truth, load_task(TASKS / "slugify"))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["hidden"].pop("basic"), "labels cover"),
        (lambda d: d["hidden"].update(basic=[]), "names no rule"),
        (lambda d: d["hidden"].update(basic=["R99"]), "names no rule or an unknown one"),
    ],
)
def test_labels_must_cover_every_hidden_check_with_known_rules(tmp_path, mutate, message):
    truth = tmp_path / "truth"
    shutil.copytree(TRUTH, truth)
    data = json.loads((truth / "slugify.json").read_text(encoding="utf-8"))
    mutate(data)
    (truth / "slugify.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ev.EvalError, match=message):
        ev.load_labels(truth, load_task(TASKS / "slugify"))


def test_missing_labels_are_an_eval_error(tmp_path):
    with pytest.raises(ev.EvalError, match="cannot read"):
        ev.load_labels(tmp_path, load_task(TASKS / "slugify"))


def test_rules_of_and_checks_of_are_inverse_views_of_the_labels():
    labels = slugify_labels()
    assert labels.rules_of(["accents"]) == {"R04", "R05"}
    assert labels.checks_of("R13") == ("max_length_invalid",)
    assert labels.rules_of(["nonexistent"]) == set()


# --- O1 ---------------------------------------------------------------------------------------


def test_o1_passes_nothing_it_should_not_and_reports_every_property_it_checks(monkeypatch):
    assert ev.split_problems("1. It adds. It subtracts.\n2. It divides.") == []
    real = spec.split("1. It adds. It subtracts.")
    r = real.rules[0]
    bad = spec.Split(
        real.idea_sha256,
        (spec.Rule("R01", "G1", r.start + 1, r.end, r.text, r.kind, ()), *real.rules[1:]),
        False,
        0,
    )
    monkeypatch.setattr(spec, "split", lambda idea: bad)
    problems = ev.split_problems("1. It adds. It subtracts.")
    assert any("offsets do not reproduce" in p for p in problems)


def test_a_refused_idea_is_a_problem_not_a_crash():
    long = "\n\n".join(f"Rule number {n} holds." for n in range(60))
    assert ev.split_problems(long)[0].startswith("refused")


def test_stripping_removes_list_markers_and_rewraps_lines():
    out = ev.strip_numbering("Intro.\n\n1. One\n   continues.\n2. Two.")
    assert out == "Intro.\nOne continues. Two."


def test_sentence_count_is_taken_before_the_cap():
    idea = "\n".join(f"{n}. First {n}. Second {n}. Third {n}." for n in range(1, 21))
    assert ev.sentence_count(idea) == 60
    assert spec.split(idea).coarse


def test_o1_on_the_real_ideas_has_no_property_failure_and_names_the_coarse_ones():
    o1 = ev.run_o1(load_tasks(TASKS))
    assert o1.failures == {}
    assert {"jsonpointer", "semver", "wildcard"} <= set(o1.coarse)
    assert "O1 the splitter" in ev.render_o1(o1)


# --- O2 ---------------------------------------------------------------------------------------


def test_the_proposer_names_one_scored_rule_per_hidden_check_and_agreement_counts_hits():
    task = load_task(TASKS / "slugify")
    labels = slugify_labels()
    proposed = ev.propose(task, labels.split)
    assert set(proposed) == set(labels.hidden)
    assert set(proposed.values()) <= {r.id for r in labels.split.scorable} | {""}, (
        "a blank means no proposal"
    )
    hits, total = ev.agreement(labels, proposed)
    assert total == len(labels.hidden) and 0 <= hits <= total
    assert ev.agreement(labels, {"accents": "R04", "basic": "R99"}) == (1, 2)
    assert "hand labels only" in ev.render_o2([("t", 1, 4)])
    assert "usable as a starting point" in ev.render_o2([("t", 3, 4)])


# --- drafts and cells -------------------------------------------------------------------------


def write(path: Path, text: str = "def test_a():\n    assert True\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_find_drafts_takes_checks_folders_of_known_tasks_in_the_chosen_groups_only(tmp_path):
    write(tmp_path / "final3/slugify/firm/rep2/.boss/runs/r1/checks/test_c01.py")
    write(tmp_path / "drafts-single/slugify/rep1/checks/test_c01.py")
    write(tmp_path / "final3/calc/firm/rep1/.boss/runs/r1/checks/test_c01.py")  # no labels
    write(tmp_path / "superseded-x/slugify/rep1/checks/test_c01.py")  # not a draft group
    write(tmp_path / "heldout3/slugify/firm/rep1/.boss/runs/r1/held_out/test_h01.py")  # not visible
    (tmp_path / "pilot/slugify/rep1/checks").mkdir(parents=True)  # empty
    found = ev.find_drafts(tmp_path, {"slugify"})
    assert sorted((d.group, d.rep) for d in found) == [("drafts-single", 1), ("final3", 2)]
    assert found[0].key == "final3/slugify/rep2/r1"


def test_read_sources_names_checks_the_way_the_boss_does(tmp_path):
    write(tmp_path / "test_c01.py", "x = 1\n")
    write(tmp_path / "test_c02.py", "y = 2\n")
    write(tmp_path / "notes.txt", "no")
    assert ev.read_sources(tmp_path) == {"c01": "x = 1\n", "c02": "y = 2\n"}


def final3_cell(raw: Path, task: str, rep: int, hidden: dict[str, str]) -> None:
    cell = raw / "final3" / task / "firm" / f"rep{rep}"
    write(cell / "result.json", json.dumps({"hidden": hidden}))
    write(cell / ".boss/runs/r1/checks/test_c01.py", PLAIN_CHECK)


def fifteen_cells(raw: Path) -> None:
    names = ["bigdecimal", "calc", "duration", "jsonpointer", "semver", "tokenbucket", "toposort"]
    for n in range(15):
        final3_cell(raw, names[n % 7], n // 7 + 1, {"basic": "failed", "other": "passed"})
    final3_cell(raw, "slugify", 1, {"basic": "passed"})  # passes everything: not an omission


def test_the_known_omissions_are_the_failed_firm_cells_without_the_class_b_cell(tmp_path):
    fifteen_cells(tmp_path)
    final3_cell(tmp_path, "wildcard", 1, {"basic": "failed"})
    cells = ev.known_omissions(tmp_path)
    assert len(cells) == 15 and all(c.failed == ("basic",) for c in cells)
    assert ("wildcard", 1) not in {(c.task, c.rep) for c in cells}


def test_a_different_number_of_known_omissions_is_an_error_not_a_quiet_change(tmp_path):
    fifteen_cells(tmp_path)
    final3_cell(tmp_path, "slugify", 2, {"basic": "failed"})
    with pytest.raises(ev.EvalError, match="expected 15"):
        ev.known_omissions(tmp_path)


def test_product_failures_lists_the_hidden_checks_each_saved_product_failed(tmp_path):
    write(
        tmp_path / "final3/slugify/single/rep1/result.json",
        json.dumps({"hidden": {"a": "failed", "b": "passed"}}),
    )
    write(tmp_path / "pilot/slugify/firm/rep1/result.json", json.dumps({"hidden": {"a": "passed"}}))
    write(tmp_path / "pilot/slugify/firm/rep2/result.json", json.dumps({"hidden": "not a map"}))
    assert sorted(map(sorted, ev.product_failures(tmp_path, "slugify"))) == [[], ["a"]]


# --- O3 ---------------------------------------------------------------------------------------


def two_drafts(tmp_path: Path) -> tuple[list[ev.DraftRef], ev.Cell, ev.Cell]:
    with_ascii = write(tmp_path / "d1/checks/test_c01.py", NON_ASCII_CHECK).parent
    without = write(tmp_path / "d2/checks/test_c01.py", PLAIN_CHECK).parent
    refs = [
        ev.DraftRef("final3", "slugify", 1, with_ascii),
        ev.DraftRef("pilot", "slugify", 1, without),
    ]
    return (
        refs,
        ev.Cell("slugify", 1, ("accents",), with_ascii),
        ev.Cell("slugify", 2, ("accents",), without),
    )


def test_o3_counts_a_cell_as_found_when_a_flagged_rule_is_one_of_its_failing_checks_rules(tmp_path):
    refs, covered, uncovered = two_drafts(tmp_path)
    o3 = ev.run_o3(refs, {"slugify": slugify_labels()}, [covered, uncovered])
    by_rep = {c.cell.rep: c for c in o3.cells}
    assert by_rep[1].hit == () and by_rep[1].flagged == ("R13",)  # no ValueError
    assert by_rep[2].hit == ("R04", "R05")
    assert by_rep[2].types == ("non_ascii",)
    assert o3.recall == 0.5 and not o3.recall_passed
    first, second = o3.cells
    assert (second.scorable, second.failing) == (len(slugify_labels().split.scorable), 2)
    assert 0 < second.chance < 1 and first.chance < second.chance, "more flags, more chance"
    assert sorted(o3.flags_per_draft) == [1, 3] and o3.median_burden == 2
    assert o3.burden_passed
    assert set(o3.by_group) == {"final3", "pilot"}
    # d1 flags R13 (not a rule of `accents`); d2 flags R04, R05 (non_ascii, both right) and R13.
    assert o3.by_type == {"exception": (0, 2), "non_ascii": (2, 2)}
    assert o3.base == (4, 2 * len(slugify_labels().split.scorable))


def test_a_flag_on_a_rule_the_failing_checks_do_not_test_is_not_a_hit(tmp_path):
    refs, _, uncovered = two_drafts(tmp_path)
    off_target = ev.Cell("slugify", 3, ("basic",), uncovered.checks_dir)
    o3 = ev.run_o3(refs, {"slugify": slugify_labels()}, [off_target])
    assert o3.cells[0].flagged == ("R04", "R05", "R13") and o3.cells[0].hit == ()


def test_the_o3_report_has_a_row_per_cell_and_both_verdicts(tmp_path):
    refs, covered, uncovered = two_drafts(tmp_path)
    text = ev.render_o3(ev.run_o3(refs, {"slugify": slugify_labels()}, [covered, uncovered]))
    assert "| slugify rep2 | accents | R04, R05, R13 | R04, R05 | non_ascii |" in text
    assert "recall 1/2 = 50%" in text and "FAIL" in text and "PASS" in text


# --- O4 ---------------------------------------------------------------------------------------


def test_o4_compares_kill_rates_by_whether_an_anchor_of_the_rule_is_in_the_draft(tmp_path):
    refs, _, _ = two_drafts(tmp_path)  # d1 has non-ASCII (anchors present), d2 does not
    labels = {"slugify": slugify_labels()}
    violations = {"slugify": {"m_accents": {"R04", "R05"}, "m_other": {"R13"}}}
    kill_map = {
        refs[0].key: {"m_accents": True, "m_other": False},
        refs[1].key: {"m_accents": False, "m_other": False},
    }
    o4 = ev.run_o4(refs, {}, labels, kill_map, violations)
    # R04 and R05 carry a non_ascii anchor; R13 carries ValueError, which neither draft has.
    assert (o4.present.killed, o4.present.total) == (2, 2)
    assert (o4.missing.killed, o4.missing.total) == (0, 4)
    assert o4.gap == 100 and not o4.enough and not o4.passed
    assert o4.by_missing_type["non_ascii"].total == 2
    assert o4.drafts == 2
    assert "INCONCLUSIVE" in ev.render_o4(o4)


def test_o4_passes_only_with_enough_triples_on_both_sides_and_a_big_enough_gap():
    big = ev.O4(ev.Side(40, 40), ev.Side(10, 40), {}, 1, 1)
    assert big.gap == 75 and big.passed
    assert not ev.O4(ev.Side(40, 40), ev.Side(10, 39), {}, 1, 1).passed
    assert not ev.O4(ev.Side(24, 40), ev.Side(15, 40), {}, 1, 1).passed
    assert ev.O4(ev.Side(25, 40), ev.Side(15, 40), {}, 1, 1).passed
    assert ev.Side(0, 0).rate == 0.0


def test_o4_skips_drafts_with_no_kill_result_and_rules_with_no_anchor(tmp_path):
    refs, _, _ = two_drafts(tmp_path)
    labels = {"slugify": slugify_labels()}
    violations = {"slugify": {"m": {"R06", "R04"}}}  # R06 (lowercase) has no anchor
    o4 = ev.run_o4(refs, {}, labels, {refs[0].key: {"m": True}}, violations)
    assert (o4.present.total, o4.missing.total, o4.drafts) == (1, 0, 1)


def test_a_hand_mutant_is_one_not_harvested_from_an_earlier_run():
    names = {m.name for m in ev.hand_mutants(load_task(TASKS / "slugify"))}
    assert names == {"accents_dropped_not_folded", "max_length_zero_accepted"}


def test_kills_and_violations_on_a_real_task_agree_with_the_mutants_names(tmp_path):
    task = load_task(TASKS / "slugify")
    draft = write(tmp_path / "checks/test_c01.py", RAISES_CHECK).parent
    assert ev.kills(task, draft) == {
        "accents_dropped_not_folded": False,
        "max_length_zero_accepted": True,
    }
    violated = ev.mutant_violations(task, slugify_labels())
    assert violated["max_length_zero_accepted"] == {"R13"}
    assert violated["accents_dropped_not_folded"] == {"R04", "R05"}


# --- O5 and the whole run ---------------------------------------------------------------------


def test_o5_counts_flags_on_rules_no_saved_product_ever_failed(tmp_path):
    refs, covered, uncovered = two_drafts(tmp_path)
    labels = {"slugify": slugify_labels()}
    o3 = ev.run_o3(refs, labels, [covered, uncovered])
    # d1 flags R13 (tested by max_length_invalid); d2 flags R04, R05 (accents) and R13.
    assert ev.run_o5(o3, labels, {"slugify": [{"basic"}, set()]}) == ev.O5(4, 4, 0)
    assert ev.run_o5(o3, labels, {"slugify": [{"accents"}]}) == ev.O5(4, 2, 0)
    assert ev.run_o5(o3, labels, {"slugify": [{"max_length_invalid"}]}) == ev.O5(4, 2, 0)
    assert "100%" in ev.render_o5(ev.O5(2, 2, 0)) and "0%" in ev.render_o5(ev.O5(0, 0, 0))


def test_a_run_of_o1_and_o2_needs_no_saved_cells_and_o3_to_o5_refuse_without_them(tmp_path, capsys):
    out = tmp_path / "report.md"
    assert (
        ev.main(["o1", "o2", "--tasks", str(TASKS), "--truth", str(TRUTH), "--out", str(out)]) == 0
    )
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Offline evaluation of the spec layer")
    assert "## O1" in text and "## O2" in text and "## O3" not in text
    assert ev.main(["o3", "--tasks", str(TASKS), "--truth", str(TRUTH)]) == 1
    assert "need --raw" in capsys.readouterr().err


def test_a_check_that_times_out_is_run_once_more_under_a_longer_limit(monkeypatch):
    calls = []

    def fake(workspace, checks_dir, checks, timeout_s=0.0, sandbox=None):
        calls.append(([c.id for c in checks], timeout_s))
        slow = len(calls) == 1
        return [
            ev.CheckResult(
                c.id,
                ev.CheckStatus.TIMEOUT if slow and c.id == "c02" else ev.CheckStatus.PASSED,
                None,
                "",
                "",
                0.0,
            )
            for c in checks
        ]

    monkeypatch.setattr(ev, "run_gate", fake)
    checks = [ev.Check("c01", "test_c01.py"), ev.Check("c02", "test_c02.py")]
    results = ev.gate(Path("w"), Path("c"), checks, 10.0)
    assert [r.status.value for r in results] == ["passed", "passed"]
    assert calls == [(["c01", "c02"], 10.0), (["c02"], ev.RETRY_TIMEOUT_S)]


def test_a_check_that_still_hangs_under_the_longer_limit_stays_a_timeout(monkeypatch):
    def hang(workspace, checks_dir, checks, timeout_s=0.0, sandbox=None):
        return [ev.CheckResult(c.id, ev.CheckStatus.TIMEOUT, None, "", "", 0.0) for c in checks]

    monkeypatch.setattr(ev, "run_gate", hang)
    results = ev.gate(Path("w"), Path("c"), [ev.Check("c01", "test_c01.py")], 10.0)
    assert [r.status for r in results] == [ev.CheckStatus.TIMEOUT]


def test_the_chance_baseline_is_a_hypergeometric_tail():
    cell = ev.Cell("t", 1, ("a",), Path("c"))
    assert ev.O3Cell(cell, (), (), (), 10, 2).chance == 0
    assert ev.O3Cell(cell, ("R01",), (), (), 10, 2).chance == pytest.approx(0.2)
    assert ev.O3Cell(cell, tuple(f"R{n:02d}" for n in range(9)), (), (), 10, 2).chance == 1
    assert ev.O3Cell(cell, ("R01",), (), ()).chance == 1.0, "no counts, no claim of rarity"


# --- O4b --------------------------------------------------------------------------------------


def saved_product(raw: Path, group: str, arm: str, rep: int, hidden: dict[str, str]) -> None:
    cell = raw / group / "slugify" / arm / f"rep{rep}"
    write(cell / "result.json", json.dumps({"hidden": hidden}))
    where = cell / "workspace" if arm == "single" else cell / ".boss/runs/r1/product"
    write(where / "slugify.py", "def slugify(t, max_length=None):\n    return t\n")


def test_failing_products_are_those_that_failed_exactly_one_hidden_check(tmp_path):
    saved_product(tmp_path, "final3", "single", 1, {"accents": "failed", "basic": "passed"})
    saved_product(tmp_path, "final3", "firm", 2, {"accents": "failed", "basic": "failed"})  # two
    saved_product(tmp_path, "heldout3", "firm", 1, {"accents": "passed", "basic": "failed"})
    saved_product(tmp_path, "final3", "single", 3, {"accents": "passed"})  # passes everything
    (tmp_path / "pilot/slugify/single/rep1").mkdir(parents=True)  # no result at all
    found = ev.failing_products(tmp_path, {"slugify"})
    assert sorted((p.key, p.failed) for p in found) == [
        ("final3/slugify/single/rep1", "accents"),
        ("heldout3/slugify/firm/rep1", "basic"),
    ]
    assert ev.failing_products(tmp_path, {"calc"}) == []


def test_a_firm_product_is_not_run_against_the_draft_it_was_built_against(tmp_path):
    saved_product(tmp_path, "final3", "firm", 1, {"accents": "failed"})
    saved_product(tmp_path, "final3", "single", 1, {"accents": "failed"})
    firm, single = sorted(ev.failing_products(tmp_path, {"slugify"}), key=lambda p: p.arm)
    own = ev.DraftRef("final3", "slugify", 1, tmp_path)
    other = ev.DraftRef("final3", "slugify", 2, tmp_path)
    assert firm.built_from(own) and not firm.built_from(other)
    assert not single.built_from(own), "a single agent never saw a draft"


def test_a_draft_kills_a_product_when_a_sound_check_fails_on_it(tmp_path):
    task = load_task(TASKS / "slugify")
    saved_product(tmp_path, "final3", "single", 1, {"accents": "failed"})
    product = ev.failing_products(tmp_path, {"slugify"})[0]  # returns its input unchanged
    sound = write(tmp_path / "d1/checks/test_c01.py", PLAIN_CHECK).parent
    wrong = write(
        tmp_path / "d2/checks/test_c01.py", PLAIN_CHECK.replace("hello-world", "nope")
    ).parent
    assert ev.kills_products(task, sound, [product]) == {product.key: True}
    assert ev.kills_products(task, wrong, [product]) == {product.key: False}, (
        "a wrong check kills all"
    )


def test_o4b_counts_triples_by_anchor_presence_and_skips_the_draft_a_product_came_from(tmp_path):
    saved_product(tmp_path, "final3", "single", 1, {"accents": "failed"})
    product = ev.failing_products(tmp_path, {"slugify"})[0]
    refs, _, _ = two_drafts(tmp_path)  # d1 has non-ASCII; d2 has none
    labels = {"slugify": slugify_labels()}
    kill_map = {refs[0].key: {product.key: True}, refs[1].key: {product.key: False}}
    o4 = ev.run_o4b(refs, labels, [product], kill_map)
    # `accents` tests R04 and R05, both with a non_ascii anchor: present in d1, missing in d2.
    assert (o4.present.killed, o4.present.total) == (2, 2)
    assert (o4.missing.killed, o4.missing.total) == (0, 2)
    assert o4.gap == 100 and o4.by_missing_type["non_ascii"].total == 2
    assert "no criterion" in ev.render_o4b(o4, 1)
