"""The paired comparison, on hand-built results whose answers are known."""

import dataclasses

import pytest
from docs_support import ROOT, captured_parser

from antstreet.bench.paired import (
    KPIS,
    MIN_TASKS,
    Paired,
    bootstrap_interval,
    compare,
    main,
    render,
    task_values,
)
from antstreet.bench.results import CellResult, cell_dir


def cell(task, arm="firm", rep=1, *, ok=True, cost=0, secs=1.0, visible=None, infra=False, h="h"):
    """A result; `visible` is (passed, total) of the boss's own checks."""
    return CellResult(
        task=task,
        arm=arm,
        rep=rep,
        set_hash=h,
        model="haiku",
        budget_micros=400_000,
        hidden={"c": "passed" if ok else "failed"},
        visible_passed=visible[0] if visible else None,
        visible_total=visible[1] if visible else None,
        cost_micros=cost,
        boss_micros=0,
        unknown_cost_events=0,
        outcome="completed",
        failure_class=None if ok else ("infrastructure" if infra else "model"),
        duration_s=secs,
    )


def sides(oks_a, oks_b, **kw):
    """Cells for tasks t0, t1, ... : arm firm passes by `oks_a`, arm single by `oks_b`."""
    a = [cell(f"t{i}", "firm", ok=ok, **kw) for i, ok in enumerate(oks_a)]
    b = [cell(f"t{i}", "single", ok=ok, **kw) for i, ok in enumerate(oks_b)]
    return a, b


def run(a, b, kpi="delivery", arm_a="firm", arm_b="single", **kw):
    return compare(a, b, arm_a, arm_b, kpi, resamples=2000, **kw)


def test_an_obvious_win_is_shown():
    a, b = sides([True] * 10, [False] * 10)
    p = run(a, b)
    assert (p.tasks, p.mean, p.low, p.high) == (10, 1.0, 1.0, 1.0)
    assert p.shown and "verdict: shown" in render(p)


def test_a_tie_is_not_shown():
    a, b = sides([True, False] * 5, [True, False] * 5)
    p = run(a, b)
    assert (p.mean, p.low, p.high) == (0.0, 0.0, 0.0) and not p.shown
    assert render(p).endswith("verdict: not shown")


def test_a_loss_is_not_shown():
    a, b = sides([False] * 10, [True] * 10)
    p = run(a, b)
    assert p.mean == -1.0 and p.high < 0 and not p.shown


def test_a_win_whose_interval_reaches_zero_is_not_shown():
    # 3 tasks gained, 2 lost: mean +0.2, but resampling often draws more losses than gains.
    a, b = sides([True] * 3 + [False] * 2 + [True] * 5, [False] * 3 + [True] * 2 + [True] * 5)
    p = run(a, b)
    assert p.mean == pytest.approx(0.1) and p.low < 0 < p.high and not p.shown


def test_one_task_cannot_show_anything():
    a, b = sides([True], [False])
    p = run(a, b)
    assert (p.tasks, p.mean) == (1, 1.0) and MIN_TASKS == 2
    assert not p.shown


def test_delivery_is_the_share_of_a_tasks_runs_and_tasks_are_weighted_equally():
    a = [cell("t0", ok=r != 4, rep=r) for r in (1, 2, 3, 4)] + [cell("t1", ok=False)]
    b = [cell("t0", "single", ok=False), cell("t1", "single", ok=True)]
    assert task_values(a, "firm", "delivery") == {"t0": 0.75, "t1": 0.0}
    p = run(a, b)
    assert (p.tasks, p.mean) == (2, -0.125)  # +0.75 on t0, -1 on t1, however many runs each had


def test_cost_is_the_mean_per_task_and_lower_is_a_win():
    a = [cell(t, cost=c) for t, c in [("t0", 1_000_000), ("t0", 3_000_000), ("t1", 2_000_000)]]
    b = [cell("t0", "single", cost=4_000_000), cell("t1", "single", cost=4_000_000)]
    assert task_values(a, "firm", "cost_per_delivery") == {"t0": 2.0, "t1": 2.0}
    p = run(a, b, "cost_per_delivery")
    assert (p.mean, p.low, p.high) == (-2.0, -2.0, -2.0) and p.tasks == 2 and not p.shown
    assert (p.wins, p.losses, p.sign_p) == (2, 0, 0.25)  # two tasks can never reach p < 0.025
    swapped = run(b, a, "cost_per_delivery", arm_a="single", arm_b="firm")
    assert swapped.mean == 2.0 and not swapped.shown


def test_equal_costs_are_a_tie():
    a, b = sides([True] * 6, [True] * 6, cost=123_457)
    p = run(a, b, "cost_per_delivery")
    assert (p.mean, p.low, p.high, p.shown) == (0.0, 0.0, 0.0, False)


def test_time_is_the_median_of_a_tasks_runs_and_lower_is_a_win():
    a = [cell("t0", secs=s, rep=i) for i, s in enumerate([10.0, 20.0, 600.0])]
    a += [cell("t1", secs=30.0), cell("t1", secs=50.0, rep=2)]
    b = [cell("t0", "single", secs=50.0), cell("t1", "single", secs=50.0)]
    assert task_values(a, "firm", "time") == {"t0": 20.0, "t1": 40.0}
    p = run(a, b, "time")
    # lower is a win: both tasks are wins for A, but 2 of 2 gives sign p = 0.25: not shown
    assert (p.mean, p.wins, p.losses, p.shown) == (-20.0, 2, 0, False)


def test_false_pass_counts_runs_that_pass_every_visible_check_and_fail_a_hidden_one():
    gamed = cell("t0", ok=False, visible=(3, 3))
    honest = cell("t0", rep=2, ok=False, visible=(2, 3))
    right = cell("t0", rep=3, ok=True, visible=(3, 3))
    unmeasured = cell("t0", rep=4, ok=False)  # no visible checks recorded: not counted as gamed
    assert task_values([gamed, honest, right, unmeasured], "firm", "false_pass") == {"t0": 0.25}
    a = [cell(f"t{i}", ok=True, visible=(1, 1)) for i in range(8)]
    b = [cell(f"t{i}", "firm", ok=False, visible=(1, 1)) for i in range(8)]
    p = compare(a, b, "firm", "firm", "false_pass", resamples=500)
    assert (p.mean, p.shown) == (-1.0, True)  # A never gamed, B always did: lower is a win


def test_false_pass_is_refused_for_an_arm_without_visible_checks():
    a, b = sides([True] * 3, [True] * 3)
    with pytest.raises(ValueError, match="only the firm arm"):
        run(a, b, "false_pass")


def test_pass_all_is_one_only_when_every_run_delivered_and_higher_is_a_win():
    a = [cell(t, rep=r) for t in ("t0", "t1") for r in range(1, 6)]
    b = [cell("t0", "single", ok=r != 3, rep=r) for r in range(1, 6)]
    b += [cell("t1", "single", rep=r) for r in range(1, 6)]
    assert task_values(b, "single", "pass_all") == {"t0": 0.0, "t1": 1.0}
    assert task_values(b, "single", "delivery")["t0"] == 0.8  # 4 of 5 is not reliable
    p = run(a, b, "pass_all")
    assert (p.tasks, p.mean) == (2, 0.5) and "pass_all (share)" in render(p)
    a10, b10 = sides([True] * 10, [False] * 10)
    assert run(a10, b10, "pass_all").shown and not run(b10, a10, "pass_all", "single", "firm").shown


def test_pass_all_refuses_tasks_with_different_numbers_of_counted_runs():
    a = [cell("t0", rep=r) for r in (1, 2, 3)] + [cell("t1", rep=r) for r in (1, 2, 3)]
    b = [cell("t0", "single", rep=r) for r in (1, 2, 3)]
    b += [cell("t1", "single", rep=r, ok=r != 3, infra=True) for r in (1, 2, 3)]
    with pytest.raises(ValueError, match=r"same number of counted runs.*\[2, 3\]"):
        run(a, b, "pass_all")
    assert run(a, b).tasks == 2  # delivery is a share, so it still compares


def test_infrastructure_cells_are_excluded_and_counted():
    a = [cell("t0"), cell("t1", ok=False, infra=True), cell("t2")]
    b = [cell("t0", "single", ok=False), cell("t1", "single"), cell("t2", "single", ok=False)]
    p = run(a, b)
    assert (p.tasks, p.unpaired, p.infrastructure, p.mean) == (2, 1, 1, 1.0)
    assert "not on both sides: 1" in render(p) and "infrastructure cells excluded: 1" in render(p)


def test_a_task_on_one_side_only_is_not_paired():
    a = [cell("t0"), cell("t1")]
    b = [cell("t0", "single", ok=False)]
    p = run(a, b)
    assert (p.tasks, p.unpaired) == (1, 1)


def test_different_task_set_hashes_are_refused():
    a = [cell("t0", h="one")]
    b = [cell("t0", "single", h="two")]
    with pytest.raises(ValueError, match="different task sets"):
        run(a, b)
    mixed_on_one_side = [cell("t0", h="one"), cell("t1", h="two")]
    with pytest.raises(ValueError, match="different task sets"):
        run(mixed_on_one_side, [cell("t0", "single", h="one")])


def test_a_side_without_the_arm_or_without_a_shared_task_is_refused():
    a, b = sides([True], [True])
    with pytest.raises(ValueError, match="no results for arm 'single-review'"):
        run(a, b, arm_b="single-review")
    with pytest.raises(ValueError, match="no task has a counted run on both sides"):
        run([cell("t0")], [cell("t9", "single")])
    with pytest.raises(ValueError, match="kpi must be one of"):
        run(a, b, "speed")


def test_the_same_seed_gives_the_same_interval_and_the_interval_brackets_the_mean():
    diffs = [1.0, 0.0, -1.0, 1.0, 0.0, 0.0, 1.0, -1.0, 0.0, 1.0, 0.0, 0.0]
    first = bootstrap_interval(diffs, 10_000, seed=7)
    assert bootstrap_interval(diffs, 10_000, seed=7) == first
    low, high = first
    assert low < sum(diffs) / len(diffs) < high
    assert bootstrap_interval(diffs, 200, seed=1) != bootstrap_interval(diffs, 200, seed=2)
    a, b = sides([True, False, True, False] * 3, [False, False, True, True] * 3)
    assert run(a, b, seed=3) == run(a, b, seed=3)


def test_the_interval_is_the_percentile_of_the_resampled_means():
    # Two tasks, differences 0 and 1: a resampled mean is 0, 0.5 or 1 with chance 1/4, 1/2, 1/4,
    # so the 2.5% point is 0 and the 97.5% point is 1.
    assert bootstrap_interval([0.0, 1.0], 10_000, seed=0) == (0.0, 1.0)
    with pytest.raises(ValueError):
        bootstrap_interval([], 10, 0)


def test_the_interval_matches_the_exact_distribution_of_a_resampled_mean():
    # 20 tasks, 10 gained: a resampled mean is Binomial(20, 1/2) / 20, whose 2.5% and 97.5% points
    # are 6/20 and 14/20 (P(X<=5) = 0.021, P(X<=6) = 0.058).
    assert bootstrap_interval([1.0] * 10 + [0.0] * 10, 10_000, seed=0) == (0.3, 0.7)


def test_a_strong_consistent_gain_excludes_zero_and_a_balanced_one_does_not():
    assert bootstrap_interval([1.0] * 18 + [0.0] * 2, 5000, 0)[0] > 0
    low, high = bootstrap_interval([1.0, -1.0] * 10, 5000, 0)
    assert low < 0 < high


def test_command_line_reads_two_folders_and_prints_the_verdict(tmp_path, capsys):
    a, b = sides([True] * 8, [False] * 8)
    for c in a + b:
        c.save(cell_dir(tmp_path / "run", c.task, c.arm, c.rep))
    assert main([str(tmp_path / "run"), str(tmp_path / "run"), "--resamples", "500"]) == 0
    out = capsys.readouterr().out
    assert "paired firm vs single, delivery" in out and "tasks: 8" in out
    assert "mean difference (firm - single): +1.0000" in out and out.endswith("verdict: shown\n")
    for kpi in KPIS:
        if kpi != "false_pass":
            assert main([str(tmp_path / "run"), str(tmp_path / "run"), "--kpi", kpi]) == 0


def test_command_line_refuses_mismatched_sets_and_empty_folders(tmp_path, capsys):
    cell("t0", h="one").save(cell_dir(tmp_path / "x", "t0", "firm", 1))
    cell("t0", "single", h="two").save(cell_dir(tmp_path / "y", "t0", "single", 1))
    assert main([str(tmp_path / "x"), str(tmp_path / "y")]) == 1
    assert "different task sets" in capsys.readouterr().err
    assert main([str(tmp_path / "x"), str(tmp_path / "nowhere")]) == 1
    assert "no results for arm" in capsys.readouterr().err


def test_a_confounded_comparison_is_warned_about(tmp_path, capsys):
    a = cell("t0")
    b = dataclasses.replace(cell("t0", "single"), model="sonnet", budget_micros=1)
    a.save(cell_dir(tmp_path / "x", "t0", "firm", 1))
    b.save(cell_dir(tmp_path / "y", "t0", "single", 1))
    assert main([str(tmp_path / "x"), str(tmp_path / "y")]) == 0
    out = capsys.readouterr().out
    assert "WARNING: model differs" in out and "WARNING: budget_micros differs" in out


def test_every_option_and_kpi_is_documented_where_the_docs_say_it():
    cli = (
        (ROOT / "docs" / "CLI.md")
        .read_text(encoding="utf-8")
        .split("`python -m antstreet.bench.paired`")[1]
    )
    cli = cli.split("\n## ")[0]
    options = {s for a in captured_parser(main)._actions for s in a.option_strings} - {
        "-h",
        "--help",
    }
    assert options == {"--arm-a", "--arm-b", "--kpi", "--resamples", "--seed"}
    for text in (cli, (ROOT / "bench" / "METHOD.md").read_text(encoding="utf-8")):
        assert all(kpi in text for kpi in KPIS)
    assert all(f"`{o}`" in cli for o in options)
    assert "`shown`" in cli and "`not shown`" in cli


def test_the_interval_ends_are_the_25th_and_the_974th_of_a_thousand_sorted_means():
    import random
    import statistics

    diffs = [0.1 * i for i in range(7)]
    rng = random.Random(4)
    means = sorted(statistics.fmean(rng.choices(diffs, k=7)) for _ in range(1000))
    assert bootstrap_interval(diffs, 1000, seed=4) == (means[25], means[974])


def test_an_empty_difference_list_says_there_is_nothing_to_resample():
    with pytest.raises(ValueError, match="no differences to resample"):
        bootstrap_interval([], 10, 0)


def test_the_defaults_are_ten_thousand_resamples_and_seed_zero():
    a, b = sides([True] * 8, [False] * 8)
    p = compare(a, b, "firm", "single", "delivery")
    assert (p.resamples, p.seed) == (10_000, 0)


def test_the_seed_given_is_the_seed_used_and_recorded():
    a, b = sides([True, False, True, False] * 3, [False, False, True, True] * 3)
    p = run(a, b, seed=5)
    assert p.seed == 5
    va, vb = task_values(a, "firm", "delivery"), task_values(b, "single", "delivery")
    diffs = [va[t] - vb[t] for t in sorted(va)]
    assert (p.low, p.high) == bootstrap_interval(diffs, 2000, 5)


def test_one_resample_is_allowed_and_zero_is_refused_with_its_reason():
    a, b = sides([True] * 8, [False] * 8)
    assert compare(a, b, "firm", "single", "delivery", resamples=1).resamples == 1
    with pytest.raises(ValueError, match="resamples must be at least 1, got 0"):
        compare(a, b, "firm", "single", "delivery", resamples=0)


def test_the_refusals_say_why():
    a, b = sides([True], [False])
    with pytest.raises(ValueError, match="only the firm arm has"):
        compare(a, b, "firm", "single", "false_pass")
    other = [cell("zz", "single")]
    with pytest.raises(ValueError, match="no task has a counted run on both sides"):
        compare(a, other, "firm", "single", "delivery")


def test_a_comparison_of_like_with_like_is_not_warned_about(tmp_path, capsys):
    cell("t0").save(cell_dir(tmp_path / "x", "t0", "firm", 1))
    cell("t0", "single").save(cell_dir(tmp_path / "y", "t0", "single", 1))
    assert main([str(tmp_path / "x"), str(tmp_path / "y")]) == 0
    assert "WARNING" not in capsys.readouterr().out


def _paired(kpi):
    from antstreet.bench.paired import Paired

    return Paired("firm", "single", kpi, "h", 8, 1.5, 0.25, 2.0, 10, 3, 1, 2)


@pytest.mark.parametrize(
    ("kpi", "unit", "mean", "interval"),
    [
        ("delivery", "share", "+1.5000", "[+0.2500, +2.0000]"),
        ("false_pass", "share", "+1.5000", "[+0.2500, +2.0000]"),
        ("cost_per_delivery", "$", "+1.5000", "[+0.2500, +2.0000]"),
        ("time", "s", "+1.5", "[+0.2, +2.0]"),
    ],
)
def test_each_kpi_is_shown_with_its_unit_and_places(kpi, unit, mean, interval):
    lines = render(_paired(kpi)).split("\n")
    assert len(lines) == 7
    assert lines[0] == f"paired firm vs single, {kpi} ({unit}), task set h"
    assert lines[2] == f"mean difference (firm - single): {mean}"
    assert lines[3] == f"95% interval: {interval} (10 task resamples, seed 3)"


def test_the_command_line_defaults_and_options_are_the_documented_ones(tmp_path, capsys):
    a, b = sides([True] * 8, [False] * 8)
    for c in a + b:
        c.save(cell_dir(tmp_path / "run", c.task, c.arm, c.rep))
    run_dir = str(tmp_path / "run")
    assert main([run_dir, run_dir]) == 0
    assert "(10000 task resamples, seed 0)" in capsys.readouterr().out
    assert main([run_dir, run_dir, "--seed", "3", "--resamples", "50"]) == 0
    assert "(50 task resamples, seed 3)" in capsys.readouterr().out
    for bad in (["--arm-a", "x"], ["--arm-b", "x"], ["--kpi", "x"], ["--seed", "x"]):
        with pytest.raises(SystemExit):
            main([run_dir, run_dir, *bad])


def test_the_parser_names_its_command_and_describes_itself():
    parser = captured_parser(main)
    assert parser.prog == "python -m antstreet.bench.paired" and parser.description


def test_cost_per_delivery_says_so_when_unknown_costs_were_counted_as_zero():
    a, b = sides([True, True], [True, True], cost=100_000)
    a[0] = dataclasses.replace(a[0], unknown_cost_events=1)
    p = run(a, b, "cost_per_delivery")
    assert p.unknown_cost_cells == 1
    assert "1 counted cell(s) have events of unknown cost" in render(p)
    assert "unknown cost" not in render(
        run(*sides([True, True], [True, True]), "cost_per_delivery")
    )
    assert "unknown cost" not in render(run(a, b, "delivery"))


# --- pass_fraction: the secondary KPI, per-task share of hidden cases passed ---


def cases(task, arm, passed, total, rep=1):
    """A result with `total` hidden cases of which the first `passed` passed."""
    hidden = {f"k{i}": "passed" if i < passed else "failed" for i in range(total)}
    return dataclasses.replace(cell(task, arm, rep, ok=passed == total), hidden=hidden)


def fraction_sides():
    a = [
        cases("t0", "firm", 4, 4),  # 1.0
        cases("t1", "firm", 2, 4),  # 0.5
        cases("t2", "firm", 1, 2, rep=1),  # runs 0.5 and 1.0 -> task value 0.75
        cases("t2", "firm", 2, 2, rep=2),
        cases("t3", "firm", 1, 2),  # only on A: unpaired
        dataclasses.replace(cases("t2", "firm", 0, 2, rep=3), failure_class="infrastructure"),
    ]
    b = [
        cases("t0", "single", 2, 4),  # 0.5
        cases("t1", "single", 2, 4),  # 0.5
        cases("t2", "single", 0, 2),  # 0.0
        cases("t4", "single", 2, 2),  # only on B: unpaired
    ]
    return a, b


def test_pass_fraction_pairs_per_task_and_matches_the_hand_computed_example():
    a, b = fraction_sides()
    assert task_values(a, "firm", "pass_fraction") == {"t0": 1.0, "t1": 0.5, "t2": 0.75, "t3": 0.5}
    p = compare(a, b, "firm", "single", "pass_fraction", resamples=10_000, seed=0)
    # diffs t0 +0.5, t1 0, t2 +0.75; t3 and t4 unpaired; the infrastructure cell is excluded
    assert p.tasks == 3 and p.unpaired == 2 and p.infrastructure == 1
    assert p.mean == pytest.approx((0.5 + 0.0 + 0.75) / 3)
    assert (p.low, p.high) == bootstrap_interval([0.5, 0.0, 0.75], 10_000, 0)
    assert (p.resamples, p.seed) == (10_000, 0)


def test_pass_fraction_is_deterministic_for_seed_0_and_rendered_as_a_share():
    a, b = fraction_sides()
    first = compare(a, b, "firm", "single", "pass_fraction", resamples=2000, seed=0)
    assert first == compare(a, b, "firm", "single", "pass_fraction", resamples=2000, seed=0)
    assert "pass_fraction (share)" in render(first)


def test_pass_fraction_gives_partial_credit_where_delivery_sees_a_tie():
    a = [cases(f"t{i}", "firm", 3, 4) for i in range(8)]
    b = [cases(f"t{i}", "single", 1, 4) for i in range(8)]
    assert compare(a, b, "firm", "single", "delivery", resamples=500).mean == 0.0
    p = compare(a, b, "firm", "single", "pass_fraction", resamples=500)
    assert p.mean == pytest.approx(0.5) and p.shown


def test_pass_fraction_cell_with_no_hidden_result_scores_zero_not_a_crash():
    empty = dataclasses.replace(cell("t0", "firm", ok=False), hidden={})
    assert task_values([empty], "firm", "pass_fraction") == {"t0": 0.0}


def test_pass_fraction_no_shared_task_is_refused_like_delivery():
    a = [cases("t0", "firm", 1, 2)]
    b = [cases("t1", "single", 1, 2)]
    with pytest.raises(ValueError, match="no task has a counted run on both sides"):
        compare(a, b, "firm", "single", "pass_fraction")


def test_pass_fraction_reads_the_command_line_flag_and_delivery_stays_the_default(tmp_path, capsys):
    a, b = fraction_sides()
    for side, side_cells in (("a", a), ("b", b)):
        for r in side_cells:
            r.save(cell_dir(tmp_path / side, r.task, r.arm, r.rep))
    assert main([str(tmp_path / "a"), str(tmp_path / "b"), "--kpi", "pass_fraction"]) == 0
    assert "pass_fraction (share)" in capsys.readouterr().out
    assert main([str(tmp_path / "a"), str(tmp_path / "b")]) == 0
    assert "delivery (share)" in capsys.readouterr().out


# --- the exact one-sided sign test beside the interval; the verdict needs both ------------------


def delivery_tasks(k, wins, losses=0):
    """k tasks x 3 runs: the first `wins` go firm 1/3 vs single 0/3, the next `losses` the other
    way, the rest 0-0."""
    a, b = [], []
    for i in range(k):
        for rep in range(1, 4):
            a_ok = i < wins and rep == 1
            b_ok = wins <= i < wins + losses and rep == 1
            a.append(cell(f"t{i:02d}", "firm", rep, ok=a_ok))
            b.append(cell(f"t{i:02d}", "single", rep, ok=b_ok))
    return a, b


def test_the_worked_example_has_an_interval_above_zero_but_sign_p_0_0625_so_it_is_not_shown():
    a, b = delivery_tasks(30, wins=4)
    p = compare(a, b, "firm", "single", "delivery", resamples=10_000, seed=0)
    assert (round(p.low, 3), round(p.high, 3)) == (0.011, 0.089)
    assert p.low > 0
    assert (p.wins, p.losses, p.n_nonzero, p.sign_p) == (4, 0, 4, 0.0625)
    assert not p.shown
    out = render(p)
    assert "sign test (one-sided, ties dropped): 4 non-tied tasks, 4 wins for firm, 0 losses" in out
    assert "p = 0.0625" in out and "AND sign-test p < 0.025" in out
    assert out.endswith("verdict: not shown")


def test_eight_wins_no_losses_is_p_0_0039_and_shown_when_the_interval_excludes_zero():
    a, b = delivery_tasks(8, wins=8)
    p = compare(a, b, "firm", "single", "delivery", resamples=2000)
    assert (p.wins, p.losses, p.sign_p) == (8, 0, 1 / 256) and p.low > 0
    assert p.shown and "p = 0.0039" in render(p)


def test_losses_are_counted_and_make_the_p_larger():
    a, b = delivery_tasks(12, wins=8, losses=2)
    p = compare(a, b, "firm", "single", "delivery", resamples=500)
    assert (p.wins, p.losses, p.n_nonzero) == (8, 2, 10)
    assert p.sign_p == pytest.approx(56 / 1024)  # C(10,8)+C(10,9)+C(10,10) = 56
    assert not p.shown


def test_all_ties_is_p_1_and_not_shown():
    a, b = sides([True] * 6, [True] * 6)
    p = run(a, b)
    assert (p.wins, p.losses, p.n_nonzero, p.sign_p) == (0, 0, 0, 1.0) and not p.shown
    assert "0 non-tied tasks" in render(p) and "p = 1.0000" in render(p)


def test_lower_is_better_kpis_count_a_cheaper_task_as_a_win():
    a = [cell(f"t{i}", cost=1_000_000) for i in range(8)]
    b = [cell(f"t{i}", "single", cost=3_000_000) for i in range(8)]
    p = run(a, b, "cost_per_delivery")
    assert (p.wins, p.losses) == (8, 0) and p.shown
    q = run(b, a, "cost_per_delivery", arm_a="single", arm_b="firm")
    assert (q.wins, q.losses) == (0, 8) and not q.shown


def test_the_verdict_is_an_and_of_interval_and_sign_test():
    from antstreet.bench.paired import sign_test

    assert sign_test([0.1] * 8)[2] < 0.025
    assert Paired(
        "firm", "single", "delivery", "h", 8, 1, 0.5, 1, 10, 0, 0, 0, 0, 8, 0, 0.0039
    ).shown
    # interval excludes 0 but p is large -> not shown; p small but interval reaches 0 -> not shown
    assert not Paired(
        "firm", "single", "delivery", "h", 8, 1, 0.5, 1, 10, 0, 0, 0, 0, 4, 0, 0.0625
    ).shown
    assert not Paired(
        "firm", "single", "delivery", "h", 8, 1, -0.5, 1, 10, 0, 0, 0, 0, 8, 0, 0.0039
    ).shown
