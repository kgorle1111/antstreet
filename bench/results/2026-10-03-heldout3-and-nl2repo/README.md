# 2026-10-03-heldout3-and-nl2repo

Two finished runs, written up from their saved results. No model call was made and nothing was
spent writing this note. The raw folders stay under `bench/results/raw/` (git-ignored); this note
holds only numbers and the commands that printed them.

- `heldout3`: the firm arm with `--held-out 3`, on the 17 original tasks, 3 runs each (51 cells).
  Question: do the boss's held-out checks (experiment E1 in `bench/PREREG.md`) lower the false-pass
  rate? Baseline: `final3` (firm and single, the same 17 tasks).
- `nl2repo-decouple`: one imported NL2Repo task, one run per arm.

Haiku for the boss and every worker. Budget $0.40 a cell on the 17 tasks, $0.80 on the NL2Repo task.
Costs are the CLI's client-side estimates.

## Result

- **E1 is not shown.** Held-out firm against `final3` firm on the false-pass share, paired by task:
  mean difference +0.098 (the held-out arm is higher), 95% interval [-0.039, +0.255], verdict
  `not shown`. The interval includes 0.
- The held-out checks caught none of the 17 false passes. 150 held-out checks were written in 50
  cells; 149 passed. The one that failed is wrong (the reference solution fails it), and that
  cell passed every hidden check.
- Delivery was lower with `--held-out 3` than in `final3`: 28/51 against 35/51 for the firm. Paired by
  task, the difference is -0.137 [-0.255, -0.020]. The `shown` rule only looks for a gain, so it
  prints `not shown`; the interval is below 0. This is not an effect of held-out checks alone:
  the code changed between the two runs (see Limits).
- Against the single agent in `final3`: delivery -0.078 [-0.216, +0.039], not shown. The firm costs
  $0.1852 more per run, averaged by task [+0.161, +0.209], and takes 262 s longer [+220, +304].
- One cell, `heldout3/linediff/firm/rep2`, hit the plan's usage limit and is counted as delivered
  (backlog B71). Without it, or counted as not delivered, delivery is 27/50 or 27/51. Nothing in the
  conclusions moves.
- NL2Repo: one task, one run per arm. The single agent delivered, the firm did not. That is all
  one task supports.

## Method

1. `heldout3` and `final3` ran the same 17 tasks: both carry task-set hash `c130282a6eec5fe8`.
   `heldout3` firm options: `--slice 0.20 --held-out 3`; `final3` firm: `--slice 0.20`.
2. Every number below is printed by `python -m boss.bench.kpi`, `python -m boss.bench.table` or
   `python -m boss.bench.paired`. The paired runs use the defaults (10,000 task resamples, seed 0).
3. Held-out counts (section 3) are not in any of those commands' output. They are summed from the
   `held_out_*` fields of each `result.json`, and `held_out_wrong` is recomputed with
   `boss.bench.score.count_wrong_checks` on each cell's saved `held_out/` folder. That is the same
   function the runner calls. The script is not committed.
4. While this note was written, the `linediff` rep 2 cell of `heldout3` was being run again in the
   raw folder. The figures here are the 51 cells as first saved; the original cell is kept in
   `bench/results/raw/superseded-2026-10-03-usage-limit/`. The commands were run on a scratch copy of
   `heldout3` that holds the original cell. The two B71 variants (section 2) are scratch copies too:
   one without the cell, one with a single hidden check of it set to `failed`.

## 1. The 17 tasks: `heldout3` against `final3`

`python -m boss.bench.kpi heldout3 final3` (columns: `heldout3` firm, `final3` firm, `final3`
single):

```
| KPI | heldout3/firm (haiku, $0.4000, --slice 0.20 --held-out 3) | final3/firm (haiku, $0.4000, --slice 0.20) | final3/single (haiku, $0.4000) |
| --- | --- | --- | --- |
| 1 Delivery rate | 55% [41-68%] (28/51) | 69% [55-80%] (35/51) | 63% [49-75%] (32/51) |
| 2 False-pass rate | 42% [29-58%] (17/40) | 33% [20-50%] (12/36) | 38% [26-52%] (19/50) |
| 3 Cost per delivered task | $0.5058 | $0.3202 | $0.1474 |
|   events of unknown cost | 0 | 0 | 0 |
| 4 Time to delivery (median) | delivered 5m22s; all counted 5m32s | delivered 4m00s; all counted 4m04s | delivered 1m25s; all counted 1m28s |
| 5 Reliability (pass^k) | 5/17 (k=3) | 9/17 (k=3) | 8/17 (k=3) |
| 6 Investor questions | 1.04 per run (53 in 51 runs) | 1.18 per run (60 in 51 runs) | 0 (the single arm asks none) |
| 7 Check quality | 19/391 wrong (5%) | 20/397 wrong (5%) | n/a (no boss checks) |
```

`python -m boss.bench.table heldout3` (the table of `final3` is in
`2026-10-02-why-the-firm-loses`):

```
| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| firm | 51 | 17 | 28 | 55% [41-68%] | 91% | $0.2777 | $0.5058 | 34% | 0 | 0 | 5m32s | 5/17 |

Visible vs hidden: 41 of 51 firm cells passed every visible check; 17 of those failed a hidden check.
Wrong boss checks: 19 of 391 checks failed on the reference solution, in 14 drafts.
```

Passed cells out of 3 runs, by task (`final3` firm / `heldout3` firm):

| task | final3 | heldout3 | task | final3 | heldout3 |
|---|---|---|---|---|---|
| bigdecimal | 1 | 1 | roman | 3 | 3 |
| calc | 0 | 0 | semver | 1 | 0 |
| csvline | 3 | 2 | slugify | 3 | 2 |
| duration | 0 | 1 | tokenbucket | 1 | 0 |
| intervals | 3 | 3 | toposort | 2 | 0 |
| jsonpointer | 1 | 2 | wildcard | 2 | 1 |
| justify | 3 | 2 | workdays | 3 | 2 |
| linediff | 3 | 3 | **total** | **35** | **28** |
| lrucache | 3 | 3 | | | |
| matrixops | 3 | 3 | | | |

`heldout3` did better on 2 tasks (duration, jsonpointer), worse on 8, the same on 7.

Paired by task, 17 tasks, `heldout3` firm minus the baseline (`--arm-a firm --arm-b firm|single`):

| KPI | against `final3` firm | verdict | against `final3` single | verdict |
|---|---|---|---|---|
| delivery (share of runs) | -0.1373 [-0.2549, -0.0196] | not shown | -0.0784 [-0.2157, +0.0392] | not shown |
| false pass (share of runs) | +0.0980 [-0.0392, +0.2549] | not shown | n/a, firm arms only | |
| cost per delivery ($) | +0.0580 [+0.0340, +0.0794] | not shown | +0.1852 [+0.1613, +0.2092] | not shown |
| time (s) | +83.6 [+17.6, +143.0] | not shown | +261.8 [+220.0, +304.4] | not shown |

How to read the verdicts: `shown` means the interval excludes 0 in the first directory's favour
(higher delivery, lower false pass, lower cost, lower time). For delivery, cost and time against
`final3` firm, the intervals exclude 0 on the unfavourable side: the held-out run delivered less,
cost more and took longer. The tool prints `not shown` for those; it has no word for "shown worse".
The paired `cost_per_delivery` is the mean cost of a task's runs, delivered or not; it differs from
the KPI row, which divides all spend by delivered cells.

## 2. The cell that hit the usage limit (B71)

`heldout3/linediff/firm/rep2`: outcome `usage_limit`, all 8 hidden checks passed, 3 of 3 held-out
checks passed, cost $0.297, 404 s, 1 wrong boss check. `visible_passed` is not recorded, so the cell
is in neither false-pass count. The runner scored the product it found and called it delivered. It
touches delivery, cost per delivered task, time and pass^k only.

`python -m boss.bench.kpi` on the two variants (without the cell; with the cell counted as not
delivered):

```
| KPI | heldout3-without-B71/firm | heldout3-B71-not-delivered/firm |
| --- | --- | --- |
| 1 Delivery rate | 54% [40-67%] (27/50) | 53% [40-66%] (27/51) |
| 2 False-pass rate | 42% [29-58%] (17/40) | 42% [29-58%] (17/40) |
| 3 Cost per delivered task | $0.5135 | $0.5245 |
| 4 Time to delivery (median) | delivered 5m21s; all counted 5m31s | delivered 5m21s; all counted 5m32s |
| 5 Reliability (pass^k) | 5/17 (k varies: k=2: 1 task, k=3: 16 tasks) | 4/17 (k=3) |
```

| | as saved (51 cells) | without the cell (50) | counted as not delivered (51) |
|---|---|---|---|
| Delivery | 28/51, 55% [41-68%] | 27/50, 54% [40-67%] | 27/51, 53% [40-66%] |
| False pass | 17/40, 42% | 17/40, 42% | 17/40, 42% |
| Cost per delivered task | $0.5058 | $0.5135 | $0.5245 |
| Median time, delivered | 5m22s | 5m21s | 5m21s |
| pass^k | 5/17 | 5/17 | 4/17 |
| Paired delivery, against `final3` firm | -0.1373 [-0.2549, -0.0196] | -0.1373 [-0.2549, -0.0196] | -0.1569 [-0.2745, -0.0392] |
| Paired delivery, against `final3` single | -0.0784 [-0.2157, +0.0392] | -0.0784 [-0.2157, +0.0392] | -0.0980 [-0.2353, +0.0392] |

The false-pass rate and the E1 verdict do not depend on the cell. The "not delivered" column is a
sensitivity check, not a correction: the product did pass every hidden check.

## 3. Held-out checks

The 51 cells wrote 150 held-out checks in 50 cells (3 each). `intervals` rep 3 has none.

| | count |
|---|---|
| Held-out checks written | 150 |
| Held-out checks passed | 149 |
| Cells with all held-out checks passed | 49 of 50 |
| `held_out_wrong` recorded in the 51 results | none (the field is empty in every cell) |
| `held_out_wrong` recomputed against the reference | 1 of 150 checks, in 1 cell |

The one failing held-out check (`lrucache` rep 3, `h02`) is the wrong one: the reference solution
fails it. The product passed every hidden check.

Visible-pass cells that had held-out checks (40 of the 41 visible-pass cells):

| | hidden failed | hidden passed |
|---|---|---|
| held-out failed | 0 | 1 |
| held-out passed | 17 | 22 |

- Sensitivity of the held-out checks to a hidden failure: 0 of 17.
- The KPI false-pass rate counts a cell as "said done" when every visible check passed and, if it
  had held-out checks, every held-out check passed. That is 40 cells, 17 of them false passes.
  The audit in `2026-10-03-false-pass-audit` counts 17 of the 41 visible-pass cells; it is the same 17
  cells. The 41 includes `lrucache` rep 3 (failed a held-out check, passed every hidden check),
  which the 40 leaves out.
- That audit read all 17 against the task text: each is a real departure from the idea, and the
  held-out checks passed in all of them.
- `PREREG.md` says a run is marked not delivered when a held-out check fails. The delivery figures
  here do not apply that: they count hidden checks only. `lrucache` rep 3 is the one cell it would
  change, and it passed every hidden check.

## 4. E1 verdict

Pre-registered rule (`bench/PREREG.md`): E1 is "not shown" if the firm with held-out checks does
not have a lower false-pass rate than the firm without them, by the paired test.

- Paired false-pass share, `heldout3` firm minus `final3` firm: +0.0980, 95% interval
  [-0.0392, +0.2549], 17 tasks. The interval includes 0. **Verdict: not shown.**
- The point estimate is higher with held-out checks, not lower. Raw: 17 of 51 runs with a visible-pass
  and a hidden failure, against 12 of 51 in `final3`. By the KPI definition: 17 of 40 (42%
  [29-58%]) against 12 of 36 (33% [20-50%]); the intervals overlap.
- The E1 arm "single at the firm's mean dollar spend" was not run here.
- The result is a failure to show a benefit. It does not show that held-out checks do harm: the
  interval reaches +0.255 and -0.039.

## 5. NL2Repo, one task

`python -m boss.bench.table nl2repo-decouple`:

```
Task set: 653f557f2c2c652b | Model: haiku | Budget per cell: $0.8000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| single | 1 | 1 | 1 | 100% [21-100%] | 100% | $0.2290 | $0.2290 | 0% | 0 | 0 | 3m07s | 1/1 |
| firm | 1 | 1 | 0 | 0% [0-79%] | 93% | $0.2821 | n/a | 43% | 0 | 0 | 4m24s | 0/1 |

Visible vs hidden: 1 of 1 firm cells passed every visible check; 1 of those failed a hidden check.
```

`python -m boss.bench.kpi nl2repo-decouple`:

```
| KPI | nl2repo-decouple/firm (haiku, $0.8000) | nl2repo-decouple/single (haiku, $0.8000) |
| --- | --- | --- |
| 1 Delivery rate | 0% [0-79%] (0/1) | 100% [21-100%] (1/1) |
| 2 False-pass rate | 100% [21-100%] (1/1) | 0% [0-79%] (0/1) |
| 3 Cost per delivered task | n/a (0 delivered) | $0.2290 |
| 4 Time to delivery (median) | delivered n/a; all counted 4m24s | delivered 3m07s; all counted 3m07s |
| 5 Reliability (pass^k) | 0/1 (k=1) | 1/1 (k=1) |
| 6 Investor questions | 1.00 per run (1 in 1 runs) | 0 (the single arm asks none) |
| 7 Check quality | not measured | n/a (no boss checks) |
```

- The task has 67 tests. The single agent passed 67; the firm passed 62 and failed 5. Its 8
  visible checks all passed.
- Different task set from section 1 (hash `653f557f2c2c652b`, and a budget of $0.80 against $0.40).
  Do not pool or compare these figures with the 17 tasks.
- One task and one run per arm: every interval is wide, and there is no paired test. It says nothing
  about arms in general.
- The cell's failure class is `unlabelled`: nobody has read why the firm's product failed 5 tests.
  Boss-check quality is not measured on imported tasks (`bench/METHOD.md`).
- The task text, its tests and any product are NL2Repo content with no licence. None of it is copied
  into this repository; this note holds counts only.
- Not comparable with the external leaderboard (see `bench/METHOD.md`, imported tasks).

## Limits

- `heldout3` and `final3` are not the same code with one flag changed. `briefs.py` and `rule.py`
  changed between them and `--held-out 3` adds the examiner's call (see `2026-10-02-why-the-firm-loses`,
  section 1). No firm run without `--held-out` was made on the later code, so the difference in
  delivery cannot be put on held-out checks, on the code, or on run-to-run noise.
- 17 tasks, 3 runs each. Runs of one task are not independent; the cell-level Wilson intervals
  are narrower than the evidence supports. The paired interval over tasks is the better one, and
  a percentile bootstrap over 17 tasks is itself narrow (`bench/METHOD.md`).
- The false-pass rate is conditional on all visible checks passing. The paired false-pass figure is
  per run over all runs and ignores held-out results; the KPI figure counts held-out results.
- Haiku writes both the checks and the code, and no worker can run code.
- Held-out counts come from a one-off script over the saved results, not from a repo command.
- The raw `heldout3` folder is being changed (one cell re-run). Re-running the commands above on it
  will not reproduce these numbers until that run finishes and the cell is accounted for.

## What may be published

> On 17 small Python tasks (3 runs each, Haiku), giving the boss's drafting step 3 held-out checks
> per run did not lower the share of runs that passed every visible check and still failed a hidden
> one: 17 of 40 against 12 of 36 without them. Paired by task the difference is +0.098 [-0.039,
> +0.255]: not shown. The held-out checks passed in all 17 of those runs.

What this does not support: any statement about held-out checks that holds the code fixed, any
other model, any claim from the NL2Repo task beyond "one task, one run per arm".
