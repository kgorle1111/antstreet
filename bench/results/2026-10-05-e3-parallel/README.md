# 2026-10-05-e3-parallel

E3 from `bench/PREREG.md`: on multi-file tasks, does building in parallel cut the time to a delivered
product without lowering delivery? Written from saved cells only: no model call, no spend. The raw
folders are `bench/results/raw/e3-base` (arms single and firm) and `bench/results/raw/e3-par` (firm
with `--max-tasks 3 --parallel 3`), git-ignored. Numbers in section 2 are pasted from
`python -m boss.bench.kpi`, `python -m boss.bench.table` and `python -m boss.bench.paired`; the counts
in sections 3 and 4 were counted by hand from the cells, the ledgers and the hidden checks.
Model: Haiku for the boss and every worker, $0.80 a cell, firm `--slice 0.20`.

## Answer

1. **E3 is not shown.** The rule needs a median time to delivery at least 1.3x faster. It was slower:
   delivered cells took 5m22s with `--max-tasks 3 --parallel 3` against 4m19s for the default firm,
   a speedup of 0.80x (259 s / 322 s). Counting every cell the medians are 5m35s and 5m58s, 1.07x.
   Neither reaches 1.3x.
2. **Delivery did not drop by the paired test, and did not rise.** Firm-par 7/24, firm 8/24, single
   6/24. Paired by task, firm-par minus firm: -0.042 [-0.167, +0.083]. Zero is inside the interval.
3. **For firm-par against firm no interval lies wholly on the unfavourable side.** Time +26 s
   [-68, +111], cost per assigned cell +$0.020 [-0.025, +0.058]. The data cannot tell "no change" from a
   modest gain or loss.
4. **Against the single agent, both firms are wholly on the unfavourable side for time and cost.**
   Firm-par minus single: time +280 s [+198, +375], cost per assigned cell +$0.208 [+0.145, +0.301].
   Firm minus single: time +254 s [+155, +406], cost per assigned cell +$0.188 [+0.110, +0.318]. The
   delivery interval for both starts at 0.000, and the tool says "not shown".
5. **The feature ran in 4 of 24 cells.** `--max-tasks 3` is a ceiling. The boss asked for one task in
   17 cells, two tasks at once in 4, one task twice (a fired worker replaced) in 2, and in 1 cell the
   boss call timed out before any task. So this tests "parallel when the boss chooses to split", and
   the boss rarely chose to.
6. **0 interface failures in 33 failed firm cells.** In the 4 split cells no hidden failure crosses a
   module boundary, and 2 of the 4 delivered.

## What this shows, and what it does not

Shows, on 8 tasks and Haiku:
- With the boss planning as it does now, `--parallel 3` did not make delivery faster: 0.80x on
  delivered cells and 1.07x on all cells, against a bar of 1.3x.
- The boss split an independent-module idea into more than one task in 4 of 24 cells (17%). Where it
  does not split, the flag has nothing to run at once and the cell is a default firm cell.
- No sign of integration breaks from splitting (0 in 4 split cells). Four cells say little.

Does not show:
- That parallel building is slow when the work is split. Only 4 cells split. Their durations (713,
  376, 267 and 292 s) sit among those of the unsplit cells of the same tasks (section 3), and 4 cells
  are not a test.
- That it would help with a planner that always splits. Forcing a split (or a prompt that asks for
  one) is a different experiment, not run here.
- Anything about Sonnet or another budget. One model, one budget, 24 cells per arm, 8 tasks. A
  delivery difference of one cell is noise.
- Where the firm's time goes. I have not traced it. The boss's call is 32% of the firm-par spend and
  38% of the firm's, and a split does not shorten that part.

## 1. Method

- 8 multi-file tasks (`bench/tasks-multi`: csv-stats graph-report inventory-orders invoice-render
  kvstore-wal markdown-toc ratelimit-registry todo-cli) x 3 reps. Arms: single and firm in
  `raw/e3-base` (48 cells); firm `--slice 0.20 --max-tasks 3 --parallel 3` in `raw/e3-par` (24 cells).
  72 cells counted, 0 infrastructure exclusions. All cells record task set `ed1824911b464045`.
- The firm arm is `boss fund` with the term sheet approved automatically, as in `bench/METHOD.md`.
  No held-out checks.
- A frozen copy of `main` at `a94e17c`, with the blinded prompts `solo_v2` (single) and `builder_v4`
  (firm workers): neither says it is measured, and neither names another arm.
- **Reruns.** The plan's usage limit cut 24 first attempts, all firm cells (13 for `e3-base`, 11 for
  `e3-par`), each recorded as `infrastructure` with outcome `usage_limit`. They were moved to
  `raw/superseded-2026-10-04-e3-usage-limit/` (excluded under B71) and rerun with the same snapshot
  and the same options. The counted cells are those in `raw/e3-base` and `raw/e3-par`.
- The paired `time` KPI is, per task, the median wall-clock of its cells (`duration_s` in
  `result.json`), then the mean over tasks. The KPI table's "delivered" median is over delivered cells
  only (8 firm, 7 firm-par, 6 single). The 1.3x rule is read on the KPI table.

## 2. Numbers pasted from the repo's commands

`python -m boss.bench.kpi raw/e3-base raw/e3-par`:

```
| KPI | e3-base/firm (haiku, $0.8000, --slice 0.20) | e3-base/single (haiku, $0.8000) | e3-par/firm (haiku, $0.8000, --slice 0.20 --max-tasks 3 --parallel 3) |
| --- | --- | --- | --- |
| 1 Delivery rate | 33% [18-53%] (8/24) | 25% [12-45%] (6/24) | 29% [15-49%] (7/24) |
| 2 False-pass rate | 65% [43-82%] (13/20) | 75% [55-88%] (18/24) | 73% [48-89%] (11/15) |
| 3 Cost per delivered task (pooled: total spend / delivered cells) | $0.9886 | $0.5646 | $1.1973 |
|   events of unknown cost | 0 | 0 | 1 |
| 4 Time to delivery (median) | delivered 4m19s; all counted 5m58s | delivered 2m08s; all counted 2m08s | delivered 5m22s; all counted 5m35s |
| 5 Reliability (pass^k) | 2/8 (k=3) | 1/8 (k=3) | 1/8 (k=3) |
| 6 Investor questions | 1.04 per run (25 in 24 runs) | 0 (the single arm asks none) | 1.21 per run (29 in 24 runs) |
| 7 Check quality | 12/179 wrong (7%) | n/a (no boss checks) | 15/180 wrong (8%) |

Sample sizes (counted cells over tasks; infrastructure failures excluded):
  e3-base/firm (haiku, $0.8000, --slice 0.20): 24 cells over 8 tasks (0 excluded)
  e3-base/single (haiku, $0.8000): 24 cells over 8 tasks (0 excluded)
  e3-par/firm (haiku, $0.8000, --slice 0.20 --max-tasks 3 --parallel 3): 24 cells over 8 tasks (0 excluded)

Intervals are Wilson 95%. Overlapping intervals mean no demonstrated difference.
```

`python -m boss.bench.table raw/e3-base`:

```
Task set: ed1824911b464045 | Model: haiku | Budget per cell: $0.8000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | 24 | 8 | 6 | 25% [12-45%] | 82% | $0.1412 | $0.5646 | 0% | 0 | 0 | 2m08s | 1/8 |
| firm | 24 | 8 | 8 | 33% [18-53%] | 73% | $0.3295 | $0.9886 | 38% | 0 | 0 | 5m58s | 2/8 |

Visible vs hidden: 20 of 24 firm cells passed every visible check; 13 of those failed a hidden check.
Wrong boss checks: 12 of 179 checks failed on the reference solution, in 7 drafts.

| task | single | firm |
| --- | --- | --- |
| csv-stats | 0/3 | 0/3 |
| graph-report | 3/3 | 3/3 |
| inventory-orders | 2/3 | 3/3 |
| invoice-render | 0/3 | 0/3 |
| kvstore-wal | 0/3 | 0/3 |
| markdown-toc | 1/3 | 1/3 |
| ratelimit-registry | 0/3 | 1/3 |
| todo-cli | 0/3 | 0/3 |

Pass rates from fewer than ~60 paired tasks cannot show a 20-point difference; treat them as descriptive.
```

`python -m boss.bench.table raw/e3-par`:

```
Task set: ed1824911b464045 | Model: haiku | Budget per cell: $0.8000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| firm | 24 | 8 | 7 | 29% [15-49%] | 77% | $0.3492 | $1.1973 | 32% | 1 | 0 | 5m35s | 1/8 |

Visible vs hidden: 15 of 24 firm cells passed every visible check; 11 of those failed a hidden check.
Wrong boss checks: 15 of 180 checks failed on the reference solution, in 11 drafts.

| task | firm |
| --- | --- |
| csv-stats | 0/3 |
| graph-report | 3/3 |
| inventory-orders | 2/3 |
| invoice-render | 0/3 |
| kvstore-wal | 0/3 |
| markdown-toc | 2/3 |
| ratelimit-registry | 0/3 |
| todo-cli | 0/3 |

Pass rates from fewer than ~60 paired tasks cannot show a 20-point difference; treat them as descriptive.
```

`python -m boss.bench.paired DIR_A DIR_B --arm-a A --arm-b B --kpi K` (the difference is A minus B).

Firm-par against firm (`raw/e3-par raw/e3-base`, both arms `firm`):

```
paired firm vs firm, time (s), task set ed1824911b464045
tasks: 8 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - firm): +26.1
95% interval: [-67.7, +110.7] (10000 task resamples, seed 0)
verdict: not shown

paired firm vs firm, delivery (share), task set ed1824911b464045
tasks: 8 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - firm): -0.0417
95% interval: [-0.1667, +0.0833] (10000 task resamples, seed 0)
verdict: not shown

paired firm vs firm, cost_per_delivery ($), task set ed1824911b464045
tasks: 8 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - firm): +0.0197
95% interval: [-0.0250, +0.0577] (10000 task resamples, seed 0)
verdict: not shown
```

Firm-par against single (`raw/e3-par raw/e3-base`, arms `firm` and `single`):

```
paired firm vs single, time (s), task set ed1824911b464045
tasks: 8 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): +280.1
95% interval: [+197.5, +375.3] (10000 task resamples, seed 0)
verdict: not shown

paired firm vs single, delivery (share), task set ed1824911b464045
tasks: 8 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): +0.0417
95% interval: [+0.0000, +0.1250] (10000 task resamples, seed 0)
verdict: not shown

paired firm vs single, cost_per_delivery ($), task set ed1824911b464045
tasks: 8 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): +0.2080
95% interval: [+0.1446, +0.3010] (10000 task resamples, seed 0)
verdict: not shown
```

Firm against single (`raw/e3-base raw/e3-base`):

```
paired firm vs single, time (s), task set ed1824911b464045
tasks: 8 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): +254.0
95% interval: [+154.8, +406.1] (10000 task resamples, seed 0)
verdict: not shown

paired firm vs single, delivery (share), task set ed1824911b464045
tasks: 8 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): +0.0833
95% interval: [+0.0000, +0.2083] (10000 task resamples, seed 0)
verdict: not shown

paired firm vs single, cost_per_delivery ($), task set ed1824911b464045
tasks: 8 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): +0.1884
95% interval: [+0.1098, +0.3175] (10000 task resamples, seed 0)
verdict: not shown
```

The `cost_per_delivery` KPI name is the tool's; what it computes is the cost per assigned cell: each
task's mean cost over all its runs, delivered or not (`src/boss/bench/paired.py`; PREREG E6). It is
not the pooled cost per delivered task in the KPI table above.

The tool prints "not shown" for time and cost when the interval is above 0, because its rule asks for
the interval to be below 0 (a benefit). For firm against single those intervals lie wholly above 0:
the firm was slower and dearer, and zero is outside the interval.

## 3. How often the plan split

Counted from the `hired` events in each cell's ledger. A split is two different tasks hired in the
same second.

| firm-par cells (24) | count | cells |
|---|---|---|
| one task, one worker | 17 | all the others |
| two tasks at once | 4 | csv-stats rep 3, graph-report reps 1 and 2, kvstore-wal rep 3 |
| one task, a second worker after the first was fired | 2 | ratelimit-registry rep 2, todo-cli rep 3 |
| boss call timed out, no task | 1 | todo-cli rep 2 (300 s, $0.00) |

- The 4 split cells: graph-report reps 1 and 2 delivered; csv-stats rep 3 and kvstore-wal rep 3 did
  not. Their durations are 713 s (csv-stats), 376 and 267 s (graph-report) and 292 s (kvstore-wal).
  The same tasks in the default firm took 540, 316 and 451 s (csv-stats), 258, 359 and 240 s
  (graph-report), and 242 and 273 s (kvstore-wal; rep 1 stopped on an invalid draft after 121 s).
- In `e3-base` (no `--max-tasks`) the boss asked for one task in all 23 firm cells where it planned. One cell
  (kvstore-wal rep 1) wrote an invalid draft and hired nobody; one (ratelimit-registry rep 3) hired a
  second worker for the same task after a firing.

## 4. Why the firm cells failed

A cell failed when a hidden check failed: 16 of 24 firm cells and 17 of 24 firm-par cells. Each was
classed by re-running the hidden checks on the saved product (`bench/tasks-multi/<id>/hidden_checks`),
reading the cell's `.boss/runs/*/checks`, and running those checks on the task's reference solution to
find the wrong ones. One class per cell, in this order:

- **other**: no product was built.
- **wrong boss check**: the boss's draft held a check the reference fails, and either the cell failed
  its visible checks only on wrong checks, or the product satisfied a wrong check and a hidden failure
  is that same behaviour.
- **cross-module (interface) break**: a hidden failure that comes from one module calling another with
  the wrong shape (import, argument, return type).
- **cap**: the budget ended the cell with boss checks unmet and no wrong check to explain it.
- **boss checks omit a stated behaviour**: every boss check passed, a hidden check failed, and no
  wrong check is involved.

| class | firm (16) | firm-par (17) |
|---|---|---|
| boss checks omit a stated behaviour | 11 | 9 |
| wrong boss check | 5 | 7 |
| cross-module (interface) break | 0 | 0 |
| cap | 0 | 0 |
| other | 0 | 1 |

| class | firm | firm-par |
|---|---|---|
| omit | csv-stats reps 2, 3; invoice-render reps 1, 2, 3; kvstore-wal reps 2, 3; markdown-toc rep 3; todo-cli reps 1, 2, 3 | csv-stats rep 2; inventory-orders rep 2; invoice-render reps 1, 2, 3; kvstore-wal reps 1, 2, 3; ratelimit-registry rep 3 |
| wrong check | csv-stats rep 1; kvstore-wal rep 1; markdown-toc rep 2; ratelimit-registry reps 1, 2 | csv-stats reps 1, 3; markdown-toc rep 2; ratelimit-registry reps 1, 2; todo-cli reps 1, 3 |
| other | none | todo-cli rep 2 (boss call exceeded 300 s) |

What the omissions are (the idea states each behaviour; no boss check in the cell tests it):
- invoice-render, all 6 cells of both runs: an empty invoice must raise `ValueError` (2 cells did not
  raise, 4 died with `'int' object has no attribute 'quantize'`), and `compute_totals` must not modify
  its arguments. In 3 cells non-finite unit prices (`NaN`, `Infinity`) raise `decimal.InvalidOperation`
  instead of `ValueError`.
- kvstore-wal, 5 cells (both runs): a torn multi-byte character at the tail of the log must be ignored
  (all 5 raise `UnicodeDecodeError`). In 4 of them a log rewrite also rejects a delete record it must
  normalise.
- todo-cli, 3 cells of `e3-base`: non-`str` input to `TodoList` raises `AttributeError` or `TypeError`,
  not `ValueError`; invalid inputs do not raise `ParseError`.
- csv-stats, 3 cells (reps 2 and 3 of `e3-base`, rep 2 of `e3-par`): `1_000` accepted by `numbers()`,
  blank-line rules, `describe` fields.
- One missing rule each: ratelimit-registry rep 3 of `e3-par` (`available()` and `remaining()` must be
  floats), inventory-orders rep 2 of `e3-par` (line order of `place_order`), markdown-toc rep 3 of
  `e3-base` (marker layouts that must raise `ValueError`).

The wrong boss checks, found by running every cell's checks on the reference:
- 12 of 179 checks in `e3-base` (7 drafts) and 15 of 180 in `e3-par` (11 drafts).
- 12 failed cells are classed wrong check. In 4 of them the product was bent to satisfy the wrong
  check and a hidden check failed on that same behaviour: markdown-toc rep 2 in both runs
  (`slugify("   ")` expected to be `"section"`; the idea says each space becomes `-`), csv-stats rep 1
  of `e3-base` (a blank line inside a column expected to count as a missing value; the idea says
  blank lines are skipped) and todo-cli rep 1 of `e3-par` (a tag filter that ignores the status).
  In the other 8 the cell failed visible checks that were themselves wrong (or, for kvstore-wal rep 1
  of `e3-base`, the draft had a syntax error and no worker was hired).
- Workers disputed a check in 6 cells of `e3-par` (csv-stats rep 1, graph-report reps 1 and 3,
  inventory-orders rep 1, ratelimit-registry rep 1, todo-cli rep 3) and 2 of `e3-base`
  (ratelimit-registry reps 2 and 3). Graph-report reps 1 and 3 and inventory-orders rep 1 of `e3-par`
  delivered every hidden check all the same.

Cap: 4 cells ended `capped` (`e3-base` csv-stats rep 2 and ratelimit-registry rep 1; `e3-par`
csv-stats reps 2 and 3). In both csv-stats rep 2 cells every boss check had passed, so the cap did not
decide the cell. In the other two the unmet checks were wrong checks, so they are classed wrong check,
with the cap as a cost.

Interface check: the hidden failures of the 4 split cells are csv-stats rep 3 (`read_table` blank
lines, `1_000` in `numbers()`, `describe` fields: each inside one module) and kvstore-wal rep 3
(`log.py`: torn tail and delete normalisation). `render_summary` and `render_table`, which use both
other csv-stats modules, passed in csv-stats rep 3, and both split graph-report cells passed every
hidden check. None of the 33 failed cells shows an import, argument or return-type mismatch between
modules.

## 5. Things that look wrong, and limits

- **The flag did not take effect in 20 of 24 cells** (section 3). The comparison is mostly default firm
  against default firm with different luck, which is why every interval for firm-par against firm
  includes zero.
- **Boss checks pass, the product is still wrong.** 20 of 24 firm cells and 15 of 24 firm-par cells
  passed every visible check; 13 and 11 of those failed a hidden check (false-pass rates 65% and 73%).
- **One boss timeout** (todo-cli rep 2 of `e3-par`, 300 s, $0.00) counts as a failed cell and its time
  is in the time median. It is not an infrastructure stop, so the rule does not exclude it.
- **One unknown-cost event** in `e3-par`: its cost is a floor.
- **8 tasks, 3 reps, one model.** One cell is 4 points of delivery. The 8 tasks are the whole set, and
  4 of them (csv-stats, invoice-render, kvstore-wal, todo-cli) failed in all 6 firm cells.
- The time KPI includes the boss's draft and any wait for the investor. Faster module building alone
  would show only in part, and I did not separate the two.
- Classification is by reading. "No boss check" means the cell's checks were read for the behaviour
  and none tests it.
