# 2026-10-03-new18

Firm against single agent on 18 of the 42 new tasks. Written from saved cells only: no model call, no
spend. The raw folder is `bench/results/raw/new18` (git-ignored). Numbers below are pasted from
`python -m boss.bench.kpi`, `python -m boss.bench.table` and `python -m boss.bench.paired`; the counts
in sections 3 to 5 were counted by hand from the cells, the ledgers and the hidden checks.
Model: Haiku for the boss and every worker, $0.40 a cell, firm `--slice 0.20`.

## Read this first: this is not a blind comparison

The run used a frozen copy of commit `6e66f6c`. The copy has no `.git` folder, so it was compared with
that commit's `src/` and `bench/` by file: no file differs. Its prompts:

| arm | worker prompt | what it says that the other arm's does not |
|---|---|---|
| single | `solo_v1.md` | "Your work will be judged by checks you cannot see. Handle the edge cases the request states." |
| firm | `builder_v3.md` | the gate runs "the checks shown in your task"; no edge-case sentence |

- The single arm was told it is measured by hidden checks and was given an edge-case instruction the
  firm's workers did not get. `bench/PREREG.md` says no model is told it is measured. So the single
  arm had an advantage that the firm arm did not, and the size of it was not measured.
- Commit `6b6111a` (after this run's code) replaced them with `solo_v2.md` and `builder_v4.md`: both
  say to handle every stated behaviour and edge case, and neither mentions unseen checks. This run
  does not use them.
- `final3` (the original 17 tasks) also ran on `solo_v1` and `builder_v3`, so the two sets share
  the flaw and can be compared with each other. Neither is a fair test of the firm.
- Using it as a verdict on the firm needs a rerun on `solo_v2` and `builder_v4`. The recorded cost of
  this run is $0.1950 x 54 + $0.0872 x 54 = $15.2.

## Answer

1. **The gap between the arms in `final3` is not reproduced, and neither run shows a difference.**
   Paired by task, delivery, firm minus single: `final3` +0.059 [-0.078, +0.196]; `new18` -0.037
   [-0.130, +0.074]. Both verdicts: not shown. The sign flipped. Firm 29/54 (54%), single 31/54 (57%).
   By task the firm did better on 3 (fracmath, ringbuffer, shortestpath), worse on 5 (exprtokens,
   luhn, minheap, prefixtrie, unionfind), the same on 10; in `final3` it was 4, 3 and 10.
2. **The cost gap is reproduced.** The firm costs $0.195 a cell against $0.087 (2.2 times) and $0.363
   against $0.152 a delivered task (2.4 times). Paired, firm minus single: cost +$0.108
   [+0.089, +0.130], time +132 s [+116, +151]. `final3` was +$0.127 and +178 s. The tool prints "not
   shown" for these because its rule asks for the interval to be below 0; here it is above 0, so the
   firm cost more and took longer on this set, and zero is outside the interval.
3. **The firm's failures are the same kind as in 2026-10-02.** 25 of 54 firm cells failed a hidden
   check. 20 are a behaviour the idea states that the boss checks omit (or test only with inputs the
   product already passes), and 14 of the 25 fail a non-ASCII-digit or sign input check that none of
   the 15 drafts for those five tasks has. 5 are a wrong boss check that the worker followed. 0 are
   workers special-casing a check.
4. **Check quality is better than in `final3`**: 6 of 426 boss checks are wrong (1%, in 6 of 54
   drafts), against 20 of 397 (5%, in 16 of 51 drafts). Those 6 cells cost the firm $2.24 of $10.53
   (21%), and 5 of the 6 products failed a hidden check.
5. **Where the boss wrote the check the single agent lacked, the firm won.** fracmath and
   ringbuffer: the single agent failed one cell each (a mixed fraction with two spaces; appending after
   `popleft`), behaviour that all 3 boss drafts test; the firm passed 6 of 6.
   shortestpath is not that: no draft has a scale check.

## 1. Method

- 18 tasks (bytesize cronnext dedentblock exprtokens fracmath iniparse isoweek luhn mdheadings
  minheap moneysplit prefixtrie rangesum ringbuffer shortestpath unionfind urlquery wordwrap) x 2
  arms (single, firm) x 3 reps = 108 cells; 108 are counted, 0 infrastructure exclusions.
- The cells record task set `767892a59e311ab5`, the 35-task set at commit `6e66f6c`. The files of these
  18 tasks (without `mutants/`, which no arm sees) are identical in the current 59-task set.
- The firm arm is `boss fund` with the term sheet approved automatically, as in `bench/METHOD.md`.
  No held-out checks. The boss prompt, `term_sheet_v1.md`, is the same as at the current commit.
- **Reruns.** The usage limit and a killed process cut cells off. 56 attempts at 54 distinct cells
  were set aside in `raw/superseded-*/new18` and the cells rerun; the counted cells are those in
  `raw/new18`. The other 54 of the 108 ran once.
  - 54 first attempts have a `result.json`: 53 are marked infrastructure (26 firm `boss:usage_limit`,
    3 firm `usage_limit`, 24 single `usage_limit`), and 1 is a single minheap cell marked
    `usage_limit` with no failure class (60.9 s, $0.041, all 8 hidden checks passed); its rerun also
    passed 8 of 8.
  - 2 reruns (rangesum firm, reps 1 and 2) were killed and have no `result.json`; those two cells
    were run a third time.
  - The counted cells have the same task set hash as each other.

## 2. Numbers pasted from the repo's commands

`python -m boss.bench.table raw/new18`:

```
Task set: 767892a59e311ab5 | Model: haiku | Budget per cell: $0.4000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | 54 | 18 | 31 | 57% [44-70%] | 89% | $0.0872 | $0.1519 | 0% | 0 | 0 | 1m27s | 5/18 |
| firm | 54 | 18 | 29 | 54% [41-66%] | 89% | $0.1950 | $0.3631 | 46% | 0 | 0 | 3m24s | 6/18 |

Visible vs hidden: 52 of 54 firm cells passed every visible check; 24 of those failed a hidden check.
Wrong boss checks: 6 of 426 checks failed on the reference solution, in 6 drafts.

| task | single | firm |
| --- | --- | --- |
| bytesize | 0/3 | 0/3 |
| cronnext | 0/3 | 0/3 |
| dedentblock | 3/3 | 3/3 |
| exprtokens | 2/3 | 1/3 |
| fracmath | 2/3 | 3/3 |
| iniparse | 3/3 | 3/3 |
| isoweek | 0/3 | 0/3 |
| luhn | 1/3 | 0/3 |
| mdheadings | 0/3 | 0/3 |
| minheap | 3/3 | 2/3 |
| moneysplit | 3/3 | 3/3 |
| prefixtrie | 2/3 | 1/3 |
| rangesum | 3/3 | 3/3 |
| ringbuffer | 2/3 | 3/3 |
| shortestpath | 1/3 | 2/3 |
| unionfind | 2/3 | 1/3 |
| urlquery | 2/3 | 2/3 |
| wordwrap | 2/3 | 2/3 |

Pass rates from fewer than ~60 paired tasks cannot show a 20-point difference; treat them as descriptive.
```

`python -m boss.bench.kpi raw/new18`:

```
| KPI | new18/firm (haiku, $0.4000, --slice 0.20) | new18/single (haiku, $0.4000) |
| --- | --- | --- |
| 1 Delivery rate | 54% [41-66%] (29/54) | 57% [44-70%] (31/54) |
| 2 False-pass rate | 46% [33-59%] (24/52) | 43% [30-56%] (23/54) |
| 3 Cost per delivered task | $0.3631 | $0.1519 |
|   events of unknown cost | 0 | 0 |
| 4 Time to delivery (median) | delivered 3m00s; all counted 3m24s | delivered 0m58s; all counted 1m27s |
| 5 Reliability (pass^k) | 6/18 (k=3) | 5/18 (k=3) |
| 6 Investor questions | 1.00 per run (54 in 54 runs) | 0 (the single arm asks none) |
| 7 Check quality | 6/426 wrong (1%) | n/a (no boss checks) |

Sample sizes (counted cells over tasks; infrastructure failures excluded):
  new18/firm (haiku, $0.4000, --slice 0.20): 54 cells over 18 tasks (0 excluded)
  new18/single (haiku, $0.4000): 54 cells over 18 tasks (0 excluded)

Intervals are Wilson 95%. Overlapping intervals mean no demonstrated difference.
```

`python -m boss.bench.paired raw/new18 raw/new18 --arm-a firm --arm-b single --kpi K`:

```
paired firm vs single, delivery (share), task set 767892a59e311ab5
tasks: 18 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): -0.0370
95% interval: [-0.1296, +0.0741] (10000 task resamples, seed 0)
verdict: not shown

paired firm vs single, cost_per_delivery ($), task set 767892a59e311ab5
tasks: 18 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): +0.1078
95% interval: [+0.0887, +0.1299] (10000 task resamples, seed 0)
verdict: not shown

paired firm vs single, time (s), task set 767892a59e311ab5
tasks: 18 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): +132.2
95% interval: [+116.2, +151.4] (10000 task resamples, seed 0)
verdict: not shown
```

`--kpi false_pass` prints "cannot compare: false_pass needs visible checks, which only the firm arm has".

The same commands on `raw/final3` (17 tasks, task set `c130282a6eec5fe8`), for comparison:

```
| 1 Delivery rate | 69% [55-80%] (35/51) | 63% [49-75%] (32/51) |
| 2 False-pass rate | 33% [20-50%] (12/36) | 38% [26-52%] (19/50) |
| 3 Cost per delivered task | $0.3202 | $0.1474 |
| 4 Time to delivery (median) | delivered 4m00s; all counted 4m04s | delivered 1m25s; all counted 1m28s |
| 5 Reliability (pass^k) | 9/17 (k=3) | 8/17 (k=3) |
| 6 Investor questions | 1.18 per run (60 in 51 runs) | 0 (the single arm asks none) |
| 7 Check quality | 20/397 wrong (5%) | n/a (no boss checks) |

delivery:          mean difference (firm - single): +0.0588, 95% interval: [-0.0784, +0.1961], verdict: not shown
cost_per_delivery: mean difference (firm - single): +0.1272, 95% interval: [+0.1017, +0.1561], verdict: not shown
time (s):          mean difference (firm - single): +178.1,  95% interval: [+137.5, +229.2],  verdict: not shown
```

Side by side:

| | `final3`, 17 tasks | `new18`, 18 tasks |
|---|---|---|
| delivery, firm / single | 35/51 / 32/51 | 29/54 / 31/54 |
| paired delivery, firm - single | +0.059 [-0.078, +0.196] | -0.037 [-0.130, +0.074] |
| cost per delivered task, firm / single | $0.320 / $0.147 | $0.363 / $0.152 |
| median time per cell, firm / single | 4m04s / 1m28s | 3m24s / 1m27s |
| firm visible-pass cells that failed hidden | 12 of 36 | 24 of 52 |
| wrong boss checks | 20 of 397 | 6 of 426 |

## 3. Where the cost goes

Counted from the firm ledgers: the firm spent $10.53 over 54 cells.

- The boss's call is $4.83 (46%), and 83% of the firm's extra $0.108 a cell over the single arm.
- Slice 1 costs $0.0867 a cell on average, the single agent $0.0872.
- 12 later slices cost $1.01 (9.6%). 9 of them ($0.93) are in the 6 cells that have a wrong boss
  check; the other 3 are bytesize rep 1, exprtokens rep 3 and urlquery rep 1.
- 45 cells ended after one slice, 6 after two, 3 after three. 50 of the 54 last worker statuses are
  `done`. No ledger records a dispute or an investor ruling.

## 4. Why the firm's 25 failed cells failed

Each cell is classed as in 2026-10-02: the failing hidden check was re-run on the saved product, and
the cell's `.boss/runs/*/checks` were read for the behaviour it tests. The table has every failed
firm cell. The "single" column is how many of that task's 3 single cells passed.

| class | cells | what it is |
|---|---|---|
| (a) The boss's checks omit the behaviour (or test it only with inputs the product already gets right) | 20 | 13 non-ASCII or sign input, 7 other |
| (b) A wrong boss check, followed by the worker, made it build the wrong thing | 5 | luhn 1, mdheadings 2, unionfind 1, wordwrap 1 |
| (c) Budget or slice cap | 0 alone | luhn rep 1 and unionfind rep 3 hit the cap, both with a wrong check (rangesum rep 2 did too and passed) |
| (d) Merge or assembly | 0 | one task, one file |
| (e) Infrastructure | 0 | none in the counted cells |

| task (single) | firm cell | hidden check that failed, and how | boss check for it | class |
|---|---|---|---|---|
| bytesize (0) | reps 1, 2, 3 | `parse_errors`: `"١ KB"` and 4 more non-ASCII inputs return a number. `format_binary`: `format_size(10**40)` raises `decimal.InvalidOperation` | none, 0 of 3 drafts, for either | a |
| cronnext (0) | reps 1, 2, 3 | `invalid_expressions`: `+5 * * * *` accepted (3 inputs) and a non-ASCII digit accepted (5). Reps 1 and 2 also `bad_arguments_and_never`: 60 s gate time-out, see section 6. Rep 2 also `next_fires`: `next_fires(None, after, 0)` does not raise `TypeError` | none for a sign or a non-ASCII digit; none for `None` with count 0 | a |
| exprtokens (2) | reps 2, 3 | `identifiers`: a non-ASCII letter and a non-ASCII digit are accepted | none | a |
| isoweek (0) | rep 1 | `weeks_in_year` wrong for 22 years (1993 gives 53); `parse_iso_week("2021-W53-1")` accepted; `9999-W52-7` not rejected; non-ASCII digits | drafts 1 and 2 assert only `weeks_in_year(y) in (52, 53)`; none checks week 53 of a 52-week year or non-ASCII | a |
| isoweek | reps 2, 3 | `parse_errors`: non-ASCII digits in `parse_iso_week` (6 inputs) | none | a |
| luhn (1) | rep 1 | `check_digit("7992739871")` returns 4, not 3, so 4 hidden checks fail; also non-ASCII digits | `c08` is wrong: it expects `with_check_digit("  4111111111111111  ")` to end in 4, the reference gives 3. The worker did not dispute it. `c06` passed in slice 1 and failed in slices 2 and 3, which hit the cap (visible 6/8) | b (also a) |
| luhn | reps 2, 3 | `malformed` and `payload_errors`: `"٠٠"`, a full-width `３` and Arabic-Indic digits accepted | none | a |
| mdheadings (0) | rep 1 | `titles`: `"## A \t##"` gives `"A "` (closing sequence after a tab or two spaces) | drafts test `"## A ##"` only | a |
| mdheadings | rep 2 | `anchors`: `naïve – ideas` gives one hyphen, not two. `headings`: `"##\t\tTwo tabs"` keeps a tab. `titles`: `"# #"` gives a heading | `c05` is wrong (expects `a-b` for `A # B`; the idea says spaces are not merged). Slice 3 collapses spaces to satisfy it | b (also a) |
| mdheadings | rep 3 | `code_fences`: a shorter fence closes a longer one. `titles`: `"## A \t##"` | `c04` is wrong (a `~~` closes `~~~~`). Slice 2 says it changed the fence rule "to match test expectations" | b (also a) |
| minheap (3) | rep 3 | `ties`: a priority type that defines only `<` | no draft uses such a type | a |
| prefixtrie (2) | reps 1, 3 | `longest_common_prefix` after `delete` and `insert` returns `"fl"`, not `"flow"` | all 3 drafts test it on a fixed trie; none combines it with `delete` | a |
| shortestpath (1) | rep 1 | `scale`: a 50,000-node chain does not finish in 60 s (178 s measured on a busy machine) | none, 0 of 3 drafts | a |
| unionfind (2) | rep 1 | `groups`: sets must be ordered by their earliest element; the product orders by the root's position | `c06` tests set order, with an input the product gets right | a (partly) |
| unionfind | rep 3 | `groups` and `random_ops`: element order inside a set | `c06` is wrong (`[2, 4, 3]`; the reference gives `[2, 3, 4]`). Slice 2 builds an order to satisfy it | b |
| urlquery (2) | rep 1 | `parse_errors`: `a=% 1` is accepted | drafts test `%4` and `%zz`, not a space after `%` | a (partly) |
| wordwrap (2) | rep 3 | `indent`: continuation lines get the first line's width in spaces | `c07` is wrong (expects `"  def"`; the reference gives `"def"`). Slice 1 says it chose a "rest_indent defaulting for alignment" | b |

- 14 of the 25 cells fail a non-ASCII-digit or sign input check (bytesize 3, cronnext 3, exprtokens 2,
  isoweek 3, luhn 3: 14 of the 15 cells of those five tasks). The single arm fails one in 12 of the
  same 15 cells (bytesize 3, cronnext 3, exprtokens 1, isoweek 3, luhn 2). The 2026-10-02 note had 10 of
  15 firm and 6 of 15 single, on other tasks. Each of the five ideas states the rule in a sentence
  (for example "digits that are not ASCII 0-9").
- Failed firm cells where the single arm passed the same task at least once: 13. They are exprtokens 2
  (single passed 2 of 3), luhn 3 (1 of 3), minheap 1 (3), prefixtrie 2 (2), shortestpath 1 (1),
  unionfind 2 (2), urlquery 1 (2) and wordwrap 1 (2). Class (b) is 3 of them (luhn rep 1, unionfind
  rep 3, wordwrap rep 3), class (a) the other 10. In luhn rep 1 the non-ASCII failure was there as
  well, so a correct check would not have saved the cell.
- 4 tasks (bytesize, cronnext, isoweek, mdheadings) failed 6 of 6 cells in both arms. In each,
  the hidden check tests a rule the idea states, and the reference passes it (see section 6).

## 5. The 6 wrong boss checks

`wrong_checks` is 1 in each of 6 cells and 0 in the other 48. Each was found by running the cell's
boss checks on the task's reference solution.

| cell | wrong check | what is wrong | outcome |
|---|---|---|---|
| luhn firm rep 1 | `c08` | expects check digit 4 for `4111111111111111`; the Luhn digit is 3 | capped, visible 6/8, hidden 3/7 |
| mdheadings firm rep 2 | `c05` | expects anchor `a-b` for `A # B` | hidden 4/7; the worker bent anchors |
| mdheadings firm rep 3 | `c04` | a `~~` closes a `~~~~` fence | hidden 5/7 |
| rangesum firm rep 2 | `c04` | `prefix(5)` is 21 after `set(2, 10)`; the reference gives 22 | capped at $0.44, visible 7/8, hidden 7/7 |
| unionfind firm rep 3 | `c06` | expects `[2, 4, 3]` for a set | capped, hidden 5/7 |
| wordwrap firm rep 3 | `c07` | expects `"  def"` for a hanging indent | hidden 5/6 |

- No worker disputed any of them: the ledgers hold no dispute in any of the 54 cells. In `final3`
  workers disputed 10 checks.
- In 5 of the 6 cells a later worker status or the visible results show the code being changed to
  satisfy the wrong check (luhn rep 1, mdheadings reps 2 and 3, unionfind rep 3, wordwrap rep 3), and
  those 5 products failed a hidden check. rangesum rep 2 was capped trying to satisfy `c04` and still
  passed every hidden check.

## 6. Things that look wrong, and limits

- **The prompts are not blind** (top of this note).
- **cronnext `bad_arguments_and_never` is near the 60 s gate limit.** Re-run in isolation on 3 products
  while the machine was busy, it took 48 to 50 s each. The recorded result is a failure for firm reps
  1 and 2 and a pass for single rep 1. Time-outs depend on load. No cell outcome changes: all 6
  cronnext cells also fail `invalid_expressions`.
- **shortestpath `scale`** passes or fails on time too: firm rep 1 took 178 s on a busy machine, and
  single reps 2 and 3 also time out. A faster or slower machine could move a cell.
- 4 of 18 tasks have 0 passes in 6 cells. Each failing check tests a rule the idea states and the
  reference passes it; I found no grading fault. Task validation (`tests/test_bench_tasks.py`)
  covers every task in the set.
- The 6 reps of a task are one model and one prompt: cells of one task are not independent.
- Classification is by reading. "No boss check" means a search of the check source for the
  behaviour (non-ASCII characters and escapes, signs, `chr(`) found nothing; "partly" means a
  check covers the area, with inputs that do not separate the failing product.
- 18 tasks x 3 reps, one model. Differences of 2 cells are noise; the paired interval for delivery
  includes zero in both runs.
- The 24 tasks not run here are not covered.
