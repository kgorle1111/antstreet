# 2026-10-03-blind35

Firm against single agent on 35 tasks (the original 17 and 18 of the 42 added since), with both arms
given the same blinded instruction. Written from saved cells only: no model call, no spend. The raw
folders are `bench/results/raw/blind-orig17` and `bench/results/raw/blind-new18` (git-ignored).
Numbers in sections 2 and 3 are pasted from `python -m boss.bench.kpi`, `python -m boss.bench.table`
and `python -m boss.bench.paired`. Counts in sections 4 and 5 were counted from the cells, the
ledgers and the hidden checks by one-off scripts that are not committed.
Model: Haiku for the boss and every worker, $0.40 a cell, firm `--slice 0.20`.

## Why this run exists

The 17-task run (`final3`) and the 18-task run (`new18`) gave the two arms different worker prompts:
the single arm's `solo_v1.md` said "Your work will be judged by checks you cannot see. Handle the edge
cases the request states.", and the firm's `builder_v3.md` had no such sentence (see
`2026-10-03-new18`). `bench/PREREG.md` says no model is told it is measured. This run uses the
prompts from commit `6b6111a`:

| arm | worker prompt | the instruction about edge cases |
|---|---|---|
| single | `solo_v2.md` | "Handle every behaviour and edge case the request states, including those it mentions only once." |
| firm | `builder_v4.md` | "Handle every behaviour and edge case the request states, including those it mentions only once, whether or not a check touches it." |

- Neither prompt mentions hidden checks, grading or the other arm (`tests/test_blinding.py`).
- The two sentences are not word for word the same. The firm's worker is still told that a gate runs
  "the checks shown in your task", and its brief carries the boss's checks; the single agent has
  neither. That is the arm, not a flaw in the blinding: it is what the firm adds.
- Between `6e66f6c` and `e203f65` a builder skill file (`request-first.md`) also lost a sentence that
  told the worker "in benchmark runs about half the cells that passed every visible check still
  broke a rule no visible check touched".

## Answer

1. **With equal, blinded instructions the firm shows no delivery benefit.** 35 tasks, 3 runs each:
   firm 64/105 (61%), single 62/105 (59%). Paired by task, delivery, firm minus single: +0.019
   [-0.076, +0.124], verdict not shown. By task the firm did better on 6 (bigdecimal, matrixops,
   mdheadings, slugify, toposort, wildcard), worse on 5 (lrucache, luhn, minheap, urlquery,
   workdays), the same on 24. Per run: the 17 original tasks +0.098 [-0.039, +0.255]; the 18 new tasks
   -0.056 [-0.185, +0.074]. All three are not shown.
2. **The firm's cost and time are shown, on the costly side.** Per delivered task $0.3525 against
   $0.1496 (2.4 times); median time per cell 3m34s against 1m25s (2.5 times), and 3m10s against 1m12s
   for delivered cells (2.6 times). Paired, firm minus single: cost +$0.127 [+0.109, +0.145], time
   +142 s [+122, +165]. The tool prints "not shown" for both because its rule asks for the interval to
   lie below 0 (the firm cheaper, the firm faster). Both intervals lie above 0: the firm cost more and
   took longer, and zero is outside each interval.
3. **The earlier headline (firm 69%, single 63%) does not stand.** It came from one run on 17 tasks
   with unequal prompts, and its two arms ran on different commits. Section 3 compares the runs.
   The two sets of runs differ in both the prompt and the code, so the change cannot be put on the
   prompt alone. What the data do show: on the same 17 tasks both arms delivered fewer cells (firm
   35 to 30, single 32 to 25), on the 18 new tasks both delivered more (firm 29 to 34, single 31 to
   37), and over all 35 tasks the old runs summed to firm 64, single 63 and these runs give firm 64,
   single 62.
4. **The firm's failures are the same kind as in 2026-10-02 and 2026-10-03-new18.** 41 of 105 firm
   cells failed a hidden check. 40 are a behaviour the idea states that the boss's checks omit (or
   test only with inputs the product already gets right); 24 of the 41 fail a non-ASCII-digit or sign
   input check, and none of the 27 drafts for those nine tasks has such an input. 1 is a wrong boss
   check that the worker followed (workdays rep 3). 0 are budget caps alone, 0 other.

## 1. Method

- 35 tasks x 2 arms (single, firm) x 3 reps = 210 cells; 210 are counted, 0 infrastructure
  exclusions. `blind-orig17`: the 17 original tasks (bigdecimal calc csvline duration intervals
  jsonpointer justify linediff lrucache matrixops roman semver slugify tokenbucket toposort wildcard
  workdays). `blind-new18`: bytesize cronnext dedentblock exprtokens fracmath iniparse isoweek luhn
  mdheadings minheap moneysplit prefixtrie rangesum ringbuffer shortestpath unionfind urlquery
  wordwrap. The other 24 added tasks were not run.
- Code: a frozen copy of commit `e203f65` (no `.git` folder). Its `src/` and `bench/` were compared
  with this repository's by file: no file differs. In it `SOLO_PROMPT = "solo_v2.md"` and
  `BUILDER_PROMPT = "builder_v4.md"`. The boss prompt, `term_sheet_v1.md`, is the same as in
  `new18`.
- Both runs record task set `0a83fc97a753b08c`, the 59-task set at that commit. The files of the
  17 original tasks are those pinned by `tests/test_bench_tasks.py` (hash `c130282a6eec5fe8`); the files
  of the 18 new tasks are identical to those `new18` ran (see its note).
- The firm arm is `boss fund` with the term sheet approved automatically, as in `bench/METHOD.md`.
  No held-out checks.
- **Reruns (B71).** The plan's usage limit cut 168 first attempts off (81 single, 87 firm: 81
  `boss:usage_limit`, 6 `usage_limit`), spending $0.93. All 168 are marked infrastructure. By the rule
  decided for backlog B71, a cell that ends on an infrastructure stop is excluded whatever its
  product scored, and the gap is rerun. They were moved to
  `raw/superseded-2026-10-03-blind-usage-limit/` and rerun with the same frozen copy and options; the
  counted cells are those in `raw/blind-orig17` and `raw/blind-new18`. The other 42 cells ran once.
  The counted cells' recorded cost is $31.83 (single $9.27, firm $22.56).
- The pooled figures use a folder of symbolic links to the 35 task folders of the two runs (outside
  the repository, label `blind35`): the three commands read one folder per column, and they refuse
  a comparison across different task sets. Both runs carry one task-set hash, so the pooled paired
  test is allowed. The per-run figures use the two raw folders.
- Outcomes of the counted cells: single 105 completed. Firm 96 completed, 8 capped, 1 crashed
  (unionfind rep 3, delivered). Capped firm cells: 5 failed, 3 delivered (wildcard rep 3, workdays
  rep 2, ringbuffer rep 2).

## 2. Numbers pasted from the repo's commands

`python -m boss.bench.table blind35` (the whole output is `table.md` in this folder):

```
Task set: 0a83fc97a753b08c | Model: haiku | Budget per cell: $0.4000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | 105 | 35 | 62 | 59% [49-68%] | 92% | $0.0883 | $0.1496 | 0% | 0 | 0 | 1m25s | 18/35 |
| firm | 105 | 35 | 64 | 61% [51-70%] | 92% | $0.2149 | $0.3525 | 43% | 0 | 0 | 3m34s | 16/35 |

Visible vs hidden: 87 of 105 firm cells passed every visible check; 33 of those failed a hidden check.
Wrong boss checks: 28 of 813 checks failed on the reference solution, in 20 drafts.
```

`python -m boss.bench.kpi blind35`:

```
| KPI | blind35/firm (haiku, $0.4000, --slice 0.20) | blind35/single (haiku, $0.4000) |
| --- | --- | --- |
| 1 Delivery rate | 61% [51-70%] (64/105) | 59% [49-68%] (62/105) |
| 2 False-pass rate | 38% [28-48%] (33/87) | 41% [32-51%] (43/105) |
| 3 Cost per delivered task | $0.3525 | $0.1496 |
|   events of unknown cost | 0 | 0 |
| 4 Time to delivery (median) | delivered 3m10s; all counted 3m34s | delivered 1m12s; all counted 1m25s |
| 5 Reliability (pass^k) | 16/35 (k=3) | 18/35 (k=3) |
| 6 Investor questions | 1.11 per run (117 in 105 runs) | 0 (the single arm asks none) |
| 7 Check quality | 28/813 wrong (3%) | n/a (no boss checks) |

Sample sizes (counted cells over tasks; infrastructure failures excluded):
  blind35/firm (haiku, $0.4000, --slice 0.20): 105 cells over 35 tasks (0 excluded)
  blind35/single (haiku, $0.4000): 105 cells over 35 tasks (0 excluded)

Intervals are Wilson 95%. Overlapping intervals mean no demonstrated difference.
```

`python -m boss.bench.paired blind35 blind35 --arm-a firm --arm-b single --kpi K`:

```
paired firm vs single, delivery (share), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): +0.0190
95% interval: [-0.0762, +0.1238] (10000 task resamples, seed 0)
verdict: not shown

paired firm vs single, cost_per_delivery ($), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): +0.1265
95% interval: [+0.1089, +0.1448] (10000 task resamples, seed 0)
verdict: not shown

paired firm vs single, time (s), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): +142.1
95% interval: [+122.2, +164.6] (10000 task resamples, seed 0)
verdict: not shown
```

`--kpi false_pass` prints "cannot compare: false_pass needs visible checks, which only the firm arm has".
The paired `cost_per_delivery` is the mean cost of a task's runs, delivered or not; it differs from the
KPI row, which divides all spend by delivered cells.

The same commands on each run alone (`blind-orig17`, `blind-new18`), rows of the KPI table:

```
| KPI | blind-orig17/firm | blind-orig17/single | blind-new18/firm | blind-new18/single |
| 1 Delivery rate | 59% [45-71%] (30/51) | 49% [36-62%] (25/51) | 63% [50-75%] (34/54) | 69% [55-79%] (37/54) |
| 2 False-pass rate | 39% [26-54%] (16/41) | 51% [38-64%] (26/51) | 37% [25-51%] (17/46) | 31% [21-45%] (17/54) |
| 3 Cost per delivered task | $0.3862 | $0.1885 | $0.3228 | $0.1233 |
| 4 Time to delivery (median) | delivered 3m13s; all counted 3m56s | delivered 1m10s; all counted 1m25s | delivered 3m09s; all counted 3m29s | delivered 1m14s; all counted 1m20s |
| 5 Reliability (pass^k) | 7/17 (k=3) | 7/17 (k=3) | 9/18 (k=3) | 11/18 (k=3) |
| 6 Investor questions | 1.16 per run (59 in 51 runs) | 0 | 1.07 per run (58 in 54 runs) | 0 |
| 7 Check quality | 18/392 wrong (5%) | n/a | 10/421 wrong (2%) | n/a |
```

Paired, firm minus single, per run:

| | `blind-orig17` (17 tasks) | `blind-new18` (18 tasks) |
|---|---|---|
| delivery | +0.0980 [-0.0392, +0.2549], not shown | -0.0556 [-0.1852, +0.0741], not shown |
| cost per delivery ($) | +0.1347 [+0.1097, +0.1620] | +0.1188 [+0.0949, +0.1450] |
| time (s) | +162.0 [+127.9, +201.3] | +123.3 [+105.8, +143.4] |

## 3. Against the unblinded runs

Delivered cells, firm / single, with the paired delivery difference where the tool allows one (it
refuses two different task-set hashes, so the unblinded runs cannot be pooled by the tool; the
"35 tasks, unblinded" column is the sum of the two printed counts):

| | `final3` (17 tasks, unblinded) | `blind-orig17` (same 17 tasks) | `new18` (18 tasks, unblinded) | `blind-new18` (same 18 tasks) | 35 tasks, unblinded | 35 tasks, blinded |
|---|---|---|---|---|---|---|
| delivery, firm / single | 35/51 / 32/51 | 30/51 / 25/51 | 29/54 / 31/54 | 34/54 / 37/54 | 64/105 / 63/105 | 64/105 / 62/105 |
| paired delivery, firm - single | +0.059 [-0.078, +0.196] | +0.098 [-0.039, +0.255] | -0.037 [-0.130, +0.074] | -0.056 [-0.185, +0.074] | | +0.019 [-0.076, +0.124] |
| cost per delivered task, firm / single | $0.320 / $0.147 | $0.386 / $0.189 | $0.363 / $0.152 | $0.323 / $0.123 | | $0.353 / $0.150 |
| paired cost per delivery | +$0.127 | +$0.135 | +$0.108 | +$0.119 | | +$0.127 |
| paired time | +178 s | +162 s | +132 s | +123 s | | +142 s |
| median time per cell, firm / single | 4m04s / 1m28s | 3m56s / 1m25s | 3m24s / 1m27s | 3m29s / 1m20s | | 3m34s / 1m25s |
| firm visible-pass cells that failed hidden | 12 of 36 | 16 of 41 | 24 of 52 | 17 of 46 | 36 of 88 | 33 of 87 |
| wrong boss checks | 20 of 397 | 18 of 392 | 6 of 426 | 10 of 421 | 26 of 823 | 28 of 813 |

- The unblinded runs differ from these in more than the prompt. `final3` ran the single arm at one
  commit and the firm arm at another (`dca56c1`, `a886934`). `new18` ran at `6e66f6c`. Between
  `6e66f6c` and `e203f65`, 27 files under `src/` changed (the KPI and paired tools, ledger signing,
  budget planning, run exclusion, role code, the two worker prompts and a builder skill). So a
  difference between an unblinded and a blinded cell is the prompt, the code and the run-to-run
  spread together, and this note does not separate them.
- The run-to-run spread is large. On the 17 original tasks the firm delivered 35 in `final3` and 28
  in `heldout3` (a later commit and `--held-out 3`; see `2026-10-03-heldout3-and-nl2repo`), and 30
  here. The single arm delivered 32 there and 25 here, on the same 17 tasks. Moves of 5 to 7 cells in
  one arm are inside that spread.
- What does not move: no run, blinded or not, shows a delivery difference between the arms (every
  paired interval includes 0), and the firm's cost per delivered task is 2.0 to 2.6 times the single
  agent's in all of them (here 2.4).
- The firm's lead on the 17 original tasks did not shrink with the blinded prompts (3 cells before, 5
  now); it is the 18 new tasks that carry it below zero (-2 before, -3 now). Both are within noise.

## 4. Where the cost goes

Summed from the 105 firm ledgers (costs are the CLI's estimates): the firm spent $22.56, an average
$0.2149 a cell against $0.0883 for the single agent, +$0.1266.

| | per firm cell | share of firm spend | share of the extra $0.1266 |
|---|---|---|---|
| Boss call | $0.0934 | 43% | 74% |
| Slice 1 | $0.0951 | 44% | 5% (the single agent's whole cell is $0.0883) |
| Slices 2 and later | $0.0263 | 12% | 21% |

- Slices per firm cell: 1 in 85 cells, 2 in 16, 3 in 2, 4 in 1, 6 in 1.
- 20 firm cells had a wrong boss check. They cost $0.321 a cell against $0.190 for the other 85 and
  delivered 11 of 20 (55%) against 53 of 85 (62%).
- Boss share 43%; `new18` had 46%, `final3` 40%.

## 5. Why the firm's 41 failed cells failed

Each cell is classed as in 2026-10-02: the failing hidden check was re-run on the saved product
(`run_gate` on the product folder, which gave the failing test ids below), the cell's
`.boss/runs/*/checks` were searched and read for the behaviour, and the ledger was read for disputes,
caps and what the worker's last status said. 41 of the 105 firm cells failed a hidden check: 87 passed
every visible check and 33 of those failed a hidden check; the other 8 had a visible check failing at the end.

| class | cells | what it is |
|---|---|---|
| (a) The boss's checks omit the behaviour (or test it only with inputs the product already gets right) | 40 | 24 non-ASCII digit or sign input; 16 other |
| (b) A wrong boss check, followed by the worker, made it build the wrong thing | 1 | workdays rep 3 |
| (c) Budget or slice cap alone | 0 | 5 failed cells ended capped; in 4 the failure is a class (a) omission, in 1 it is class (b) |
| (d) Merge or assembly | 0 | one task, one file |
| (e) Infrastructure | 0 | none in the counted cells |
| Other | 0 | |

In the 9 failed cells that had a wrong boss check (duration reps 2 and 3, jsonpointer rep 1,
tokenbucket rep 3, wildcard rep 1, workdays rep 3, cronnext rep 1, exprtokens rep 1, luhn rep 2), the
product still failed the wrong check in 8: the worker did not bend its code to it, as `builder_v4.md`
asks. The wrong checks still cost slices, a firing (duration rep 2, exprtokens rep 1) and two cells set
aside after a dispute (jsonpointer rep 1, wildcard rep 1).

| task (single passes of 3) | firm cells that failed | failing hidden check, and how | boss check for it | class |
|---|---|---|---|---|
| bytesize (0) | reps 1, 2, 3 | `parse_errors`: `"١ KB"` and 4 more non-ASCII inputs accepted (rep 2 also `.5 KB`). `format_binary`: `format_size(10**40)` | none, 0 of 3 drafts, for either | a |
| calc (0) | reps 1, 2, 3 | `malformed_tokens`: 5 non-ASCII digit inputs accepted. Rep 3 also `associativity`: a long chain raises `RecursionError` | none for non-ASCII; no long chain | a |
| cronnext (0) | reps 1, 2, 3 | `invalid_expressions`: `+5 * * * *`, `1_0 * * * *`, `*/+1 * * * *` and non-ASCII digits accepted | none for a sign, an underscore or a non-ASCII digit. Rep 1 ended capped with wrong checks `c02` and `c05` still failing | a |
| duration (0) | reps 1, 2, 3 | `parse_decimals`: 5 non-ASCII inputs accepted. Reps 2, 3 also `parse_negative`: `"- 1s"` and `"-\t1s"` accepted | none for non-ASCII; drafts test `"--1s"` only. Rep 2 capped; reps 2, 3 had wrong checks (`c02`; `c01`, `c03`) that the worker did not follow | a |
| exprtokens (1) | reps 1, 2 | `identifiers`: a non-ASCII letter and non-ASCII digits are not errors | none. Rep 1 spent 6 slices, 2 workers and $0.348 on a wrong check (`c07`, a position) that it never followed | a |
| isoweek (0) | reps 1, 2, 3 | `parse_errors`: 6 non-ASCII inputs accepted; reps 1 and 3 also `9999-W52-7` not rejected | none. Rep 3 ended capped in slice 1 with every visible check passing | a |
| jsonpointer (1) | reps 1, 2 | `list_indexes`, `set_value_errors`: non-ASCII index tokens. Rep 1 also `set_value_isolation`: untouched branches shared, not copied | none for non-ASCII; none for copies. Rep 1 set aside after 2 slices on wrong checks `c02`, `c06` | a |
| luhn (2) | reps 1, 2, 3 | `malformed` (7 inputs), `payload_errors` (3): non-ASCII digits accepted | none. Rep 2 ended capped with wrong check `c06` still failing | a |
| semver (0) | reps 2, 3 | `parse_invalid_input`: non-ASCII digits accepted | none | a |
| bigdecimal (0) | rep 1 | `compare`: `compare("-1", "1")` returns 0 | `c06` tests same-sign negatives only | a (partly) |
| bigdecimal | rep 3 | `large_operands`: 150-digit operands give a wrong result | the largest operand any check uses is 20 digits | a (partly) |
| lrucache (3) | rep 3 | `expiry`, `rewrite_resets_expiry`: putting an expired key again leaves two entries | `c04`, `c07` expire keys, none puts one again | a (partly) |
| semver | reps 1, 3 | `sort_versions`: an invalid element in a one-item list does not raise | tests `sort_versions([])` and valid lists | a (partly) |
| tokenbucket (0) | reps 1, 2, 3 | `basic`: `available()` is not a `float` | none, 0 of 3 drafts (`== 5.0` also passes for an `int`) | a |
| tokenbucket | rep 3 | also `clock_backwards`. Wrong checks `c03`, `c04`, `c06`; the worker disputed all three; slice 2 changed the clock initialisation to try to satisfy `c03` and `c04`, which still failed | `c08` tests one backward step | a; `clock_backwards` may be (b), not traced |
| toposort (0) | rep 1 | `cycle_error`, `random_graphs`: `NameError: name 'color' is not defined` when a cycle sits among other nodes | checks use graphs that are only the cycle | a (partly) |
| toposort | rep 3 | `dependency_only_nodes`: a generator as a dict value gives one layer | none | a |
| wildcard (1) | rep 1 | `char_sets` reversed range, `escapes` (`\*`, `\?` literal), `filter_names` | none for `\*`, `\?` or a reversed range. Set aside after 2 slices (the worker blocked) on wrong check `c03` | a |
| mdheadings (0) | rep 2 | `titles`: `"## A \t##"` and `"## A  ##   "` keep a trailing space | drafts test `"## A ##"` only | a (partly) |
| minheap (3) | rep 1 | `ties`: a priority type that defines only `<` | none uses a custom type | a |
| prefixtrie (1) | reps 2, 3 | `longest_common_prefix` after `delete` and `insert` returns `"fl"`, not `"flow"` | tested on fixed tries, never after a delete | a (partly) |
| urlquery (3) | reps 1, 2 | `parse_errors`: `a=% 1` accepted | tests `%`, `%4`, `%zz`, not a space after `%` | a (partly) |
| workdays (3) | rep 3 | `add_business_days`, `..._holidays`: the result is wrong when the start is on a weekend (the start day is not counted) | `c07` is wrong: it expects Tuesday for Saturday + 2 business days with Monday a holiday; the reference gives Wednesday. The product passes `c07`. Slices 2 and 3 capped | b (also c) |

- 24 of the 41 cells fail a non-ASCII-digit or sign input check (bytesize 3, calc 3, cronnext 3,
  duration 3, exprtokens 2, isoweek 3, jsonpointer 2, luhn 3, semver 2). None of the 27 firm drafts
  for those nine tasks has a non-ASCII input in any check (searched for non-ASCII characters, `\u`
  and `\x` escapes, `chr(`, `isascii`). The firm fails 24 of those 27 cells. The single arm fails 21
  of the same 27 on the same named hidden checks (not all of which test only non-ASCII input). Each
  idea states the rule in a sentence.
- Of the 16 other class (a) cells, 6 have no boss check for the behaviour at all (tokenbucket 3,
  toposort rep 3, wildcard rep 1, minheap rep 1); in 10 a check covers the area with inputs that do
  not separate the failing product (marked "partly" above).
- Wrong boss checks that were followed: 1 (workdays rep 3). The `new18` note counted 5 of its 6
  wrong-check cells as followed.
- 7 tasks passed none of their 6 cells across both arms (bytesize, calc, cronnext, duration, isoweek,
  semver, tokenbucket). Each task's hidden checks pass on its reference solution
  (`tests/test_bench_tasks.py`) and the idea states each behaviour they test.

## 6. Things that look wrong, and limits

- **Not a verdict on all prompts.** One equal instruction was tried, with one model.
- **The arms are not identical.** The firm's worker sees the boss's checks and is told a gate runs
  them; the single agent is not. The two edge-case sentences differ by a clause (section "Why this run
  exists").
- **Task selection.** 35 of 59 tasks. 18 of the 42 added tasks were run, the other 24 were not.
- **Pooling.** The two runs were pooled for the headline and for the pooled paired test. Both have
  one task-set hash and the same code; they ran on different days with the plan's usage limit in
  between. Section 2 gives each run alone.
- **Rerun cells.** 168 of 210 cells are second attempts (B71). A cut-off first attempt ran on the same
  code and prompts, but the machine's load was not the same. Timeouts depend on load (see
  `new18`, section 6).
- 35 tasks x 3 reps, one model. Cells of one task are not independent: the cell-level Wilson intervals
  are narrower than the evidence supports, and a percentile bootstrap over 35 tasks is itself
  narrow (`bench/METHOD.md`). A difference of 2 cells (64 against 62) is noise. The paired interval
  for delivery reaches +0.124 and -0.076: a gain or loss of about 8 to 12 points is not excluded.
- Classification is by reading. "No boss check" means a search of the check source for the behaviour
  found nothing; "partly" means a check covers the area with inputs that do not separate the failing
  product. The tokenbucket rep 3 `clock_backwards` cause was not traced (the product after slice 2 is
  not saved).
- Why the firm beat the single agent on its 6 tasks was not analysed.
- Haiku writes both the checks and the code, and no worker can run code.

## What may be published

> On 35 small Python tasks (3 runs each, Haiku, both arms given the same instruction and neither told
> about hidden checks) the firm delivered 64 of 105 against 62 of 105 for a single agent. Paired by
> task the difference is +0.019 [-0.076, +0.124]: not shown. The firm cost 2.4 times as much per
> delivered task ($0.3525 against $0.1496) and took 2.5 times as long per run (median 3m34s against
> 1m25s); both paired intervals lie above 0 (+$0.127 [+0.109, +0.145]; +142 s [+122, +165]).

What this does not support: any claim that the firm delivers more than a single agent; any claim
about the effect of the prompts alone; any other model or task type.
