# 2026-10-13-e9-coverage

E9 from `bench/PREREG.md`: does `antstreet fund --coverage` (every scored rule of the idea cited by
a check, no check passing on a stub product, before any worker is paid) raise the firm's delivery?
Written from saved cells only: no model call, no spend. The raw folders are
`bench/results/raw/e9-coverage`, `e9-firm` and `e9-single` (git-ignored). Numbers in section 3 are
pasted from `python -m antstreet.bench.paired`, `.kpi` and `.table`; section 4 comes from
`e9_cells.py` in this folder. Code: `main` at `90138e1`, the merge of PR #82, for all three arms.
Budget $0.40 a cell, `--slice 0.20` for both firm arms, the `haiku` alias for the boss and every
worker.

## Read this first: the arms did not run on the same model

The plan says "Haiku boss and workers" and the runner passed the alias `haiku`. Between the coverage
arm's first stretch and the rest of the run, the Claude CLI's `haiku` alias moved from
`claude-haiku-4-5-20251001` to `claude-haiku-5-5`. The worker logs (the CLI's own stream, which names
the model) show:

| arm | cells on Haiku 4.5 | cells on Haiku 5.5 | ran |
|---|---|---|---|
| coverage | 80 (`bigdecimal` to `shortestpath` rep 2) | 25 (`shortestpath` rep 3 to `workdays`) | 2026-10-10 to 10-11, then 10-13 |
| firm | 0 | 105 | 2026-10-13 |
| single | 0 | 105 | 2026-10-13 |

Four coverage cells and one firm cell have no worker log, because the boss stopped the run before
any worker; their stretch is taken from their start time. Boss calls do not log the model, but their
cost per call drops about elevenfold at the same boundary for the same output size (section 4), so
the boss moved with the workers.

So **the pre-registered comparisons pair 80 Haiku 4.5 coverage cells with Haiku 5.5 firm and single
cells**. All three arms share the commit, not the model. The arms also ran one after another
(coverage, then firm, then single), not interleaved, which is how a change outside the repo reached
one arm and not the others.

**No absolute number here compares with earlier results.** blind35, E4 and E4b ran on Haiku 4.5
(blind35's worker logs say `claude-haiku-4-5-20251001`; it delivered firm 64/105, single 62/105). E9's firm and single ran on Haiku 5.5 and deliver 98/105 and
103/105. Cost does not compare either: the CLI prices Haiku 5.5 about a tenth of Haiku 4.5 per
token, so the $0.40 cap is a different constraint on each model.

## Answer

1. **Primary decision, E9: not shown.** Coverage minus firm, paired delivery: -0.2000 [-0.3238,
   -0.0762]. The rule needs the interval above 0.
2. **Second decision: not shown.** Coverage minus single: -0.2476 [-0.3619, -0.1429]. A separate
   claim; neither result is reported as the other.
3. **The run does not show that `--coverage` hurts.** Both intervals lie below zero, but the gap is
   mostly the model change, not the flag (section 5, confidence about 90%). On the 25 cells where
   both arms ran on Haiku 5.5, coverage delivered 22 and the firm 24; on the 8 tasks wholly in that
   stretch, paired: -0.0833 [-0.2917, +0.0833], zero inside. On Haiku 4.5, against blind35's firm
   (an older commit) on the 26 tasks wholly in that stretch: +0.1026 [-0.0128, +0.2308], zero
   inside. Neither is a decision; they say where the -0.20 comes from.
4. **Reported, not decided on.** Firm minus single (both Haiku 5.5): -0.0476 [-0.1143, +0.0095],
   not shown either way; not comparable with blind35's +0.019. Delivery: coverage 77/105 (73%),
   firm 98/105 (93%), single 103/105 (98%). False passes (passed every visible check, failed a
   hidden one): 16 of 80 (20%), 6 of 100 (6%), 2 of 105 (2%). Cost per assigned cell: $0.2948,
   $0.0109, $0.0029; paired, coverage minus firm, +$0.2839 [+0.2230, +0.3444], and on the 8 Haiku
   5.5 tasks +$0.0110 [+0.0070, +0.0153] (about 2.1x the firm's). Median time per cell: 5m47s,
   1m23s, 0m20s (delivered cells: 5m20s, 1m21s, 0m20s).
5. **What the gate did.** In 101 coverage cells the boss's draft reached approval. Its first draft
   had no gap in 35; the boss was asked to redraft once in 54 and twice in 12. Of 78 redrafts, 44
   were kept (fewer gaps), 27 had no fewer gaps, and 7 failed (4 boss calls not completed, 3 invalid
   drafts), leaving the earlier draft. Left at approval: 18 rules no check cites in 12 cells (the
   approval waives them), 41 rules whose checks lack what the rule names in 22 cells, 6 weak checks
   in 6 cells; the stub products ran in every cell.
6. **Capped and stopped cells.** Capped (worker budget spent): coverage 9, firm 0, single 0, all 9
   on Haiku 4.5. The boss stopped the run before any worker: coverage 4 (3 boss calls crashed, 1
   invalid draft), firm 1 (crashed), single 0. Hidden checks that timed out: 1, 0, 0.

## What this shows, and what it does not

Shows:
- `--coverage` did not meet E9's bar. The decision rule is "the interval lies above 0", and it does
  not; that verdict stands whatever caused the gap.
- On Haiku 5.5 these 35 tasks are close to solved without the firm: one agent delivers 103 of 105
  for about $0.003 a cell in the CLI's estimate.
- A clean gate does not make a passing product. In 12 of the 24 approved coverage cells that failed
  a hidden check, the gate showed no gap at all: every rule cited, every anchor present, no weak
  check (section 5).

Does not show:
- That `--coverage` lowers delivery. 25 of the coverage arm's 28 failures are in its Haiku 4.5
  stretch, compared with firm cells on Haiku 5.5; the firm itself delivers 33 points more on Haiku
  5.5 at this commit than on Haiku 4.5 at blind35's commit, on the same 26 tasks (section 5).
- That it helps on Haiku 4.5. Against blind35's firm it is +0.1026 [-0.0128, +0.2308]: zero inside,
  different commits (builder prompt v5 against v4), different weeks.
- Anything about the cost of `--coverage` at a fixed model beyond the 8 Haiku 5.5 tasks: the
  arm-level cost gap is mostly the price of Haiku 4.5.

## 1. Method

- Arms, as pre-registered, all from `90138e1` with `--reps 3 --budget 0.40 --model haiku
  --boss-model haiku --jobs 2`, over blind35's 35 tasks (task set `0a83fc97a753b08c`):
  coverage (`--arms firm --coverage --firm-args "--slice 0.20"`), firm (`--arms firm --firm-args
  "--slice 0.20"`), single (`--arms single`). Each arm in its own `--out`, fresh; blind35's cells
  were not reused. The runner checked `git rev-parse --short HEAD` was `90138e1` before starting.
- `--coverage` turns on `--spec`, so the coverage arm's boss also uses the rule-citing draft prompt
  (`term_sheet_v3.md`); the firm arm's boss does not. That is the feature as the plan defines it.
- 105 cells per arm, all counted, 0 infrastructure exclusions. Set aside and rerun under the plan's
  infrastructure rule: 3 coverage cells that ended `api_error` after the machine slept
  (`raw/superseded-2026-10-10-e9-sleep`) and 2 half-run cells when the process was killed
  (`raw/superseded-2026-10-11-e9-killed`). One redraft call inside a counted cell (`semver` rep 3)
  ended `api_error`; the cell went on with its earlier draft and is counted, as the plan counts any
  outcome of a cell that ran.
- Delivered means every hidden check passed. No held-out checks. Costs are the CLI's client-side
  estimates; boss calls are outside the cell budget (`bench.run` prints "up to $42 of budget plus
  boss calls").
- The `cost_per_delivery` KPI of `paired` is each task's mean cost over all its cells, delivered or
  not: the cost per assigned cell.

## 2. Reproduction

From a checkout with the raw folders (the `e9-runner` worktree):

```
python -m antstreet.bench.paired --arm-a firm --arm-b firm --kpi delivery --resamples 10000 --seed 0 \
  bench/results/raw/e9-coverage bench/results/raw/e9-firm
python bench/results/2026-10-13-e9-coverage/e9_cells.py bench/results/raw --subsets /tmp/e9sub
```

`--subsets` writes symlink folders by model stretch: `h55/` holds the 8 tasks whose 3 coverage
cells all ran on Haiku 5.5, `h45/` the 26 whose 3 all ran on Haiku 4.5 (`shortestpath`, split 2 and
1, is in neither). For the comparison with blind35, link blind35's cells of the `h45` tasks into one
folder, for example
`for t in $(ls /tmp/e9sub/h45/e9-coverage); do ln -s "$PWD/bench/results/raw/"blind-*/"$t" /tmp/e9sub/h45/blind35/; done`
after `mkdir -p /tmp/e9sub/h45/blind35`. Every number below was printed by these commands on
2026-10-13. Re-running the three pre-registered `paired` commands gave the numbers recorded when the
run finished, digit for digit.

## 3. Numbers pasted from the repo's commands

The tool prints "shown" only when an interval lies wholly on the benefit side; for cost that is
below 0, so its "not shown" on a cost interval above 0 means the coverage arm cost more.

Primary decision (`raw/e9-coverage raw/e9-firm`, delivery):

```
paired firm vs firm, delivery (share), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - firm): -0.2000
95% interval: [-0.3238, -0.0762] (10000 task resamples, seed 0)
verdict: not shown
```

Second decision (`raw/e9-coverage raw/e9-single --arm-b single`, delivery):

```
paired firm vs single, delivery (share), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): -0.2476
95% interval: [-0.3619, -0.1429] (10000 task resamples, seed 0)
verdict: not shown
```

Reported: firm minus single (`raw/e9-firm raw/e9-single --arm-b single`, delivery):

```
paired firm vs single, delivery (share), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single): -0.0476
95% interval: [-0.1143, +0.0095] (10000 task resamples, seed 0)
verdict: not shown
```

Reported: cost per assigned cell, coverage minus firm (`--kpi cost_per_delivery`):

```
paired firm vs firm, cost_per_delivery ($), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - firm): +0.2839
95% interval: [+0.2230, +0.3444] (10000 task resamples, seed 0)
verdict: not shown
```

`python -m antstreet.bench.kpi raw/e9-coverage raw/e9-firm raw/e9-single`:

```
| KPI | e9-coverage/firm (haiku, $0.4000, --slice 0.20 --coverage) | e9-firm/firm (haiku, $0.4000, --slice 0.20) | e9-single/single (haiku, $0.4000) |
| --- | --- | --- | --- |
| 1 Delivery rate | 73% [64-81%] (77/105) | 93% [87-97%] (98/105) | 98% [93-99%] (103/105) |
| 2 False-pass rate | 20% [13-30%] (16/80) | 6% [3-12%] (6/100) | 2% [1-7%] (2/105) |
| 3 Cost per delivered task | $0.4020 | $0.0117 | $0.0030 |
|   events of unknown cost | 0 | 0 | 0 |
| 4 Time to delivery (median) | delivered 5m20s; all counted 5m47s | delivered 1m21s; all counted 1m23s | delivered 0m20s; all counted 0m20s |
| 5 Reliability (pass^k) | 17/35 (k=3) | 31/35 (k=3) | 33/35 (k=3) |
| 6 Investor questions | 1.05 per run (110 in 105 runs) | 0.99 per run (104 in 105 runs) | 0 (the single arm asks none) |
| 7 Check quality | 47/1100 wrong (4%) | 5/819 wrong (1%) | n/a (no boss checks) |
```

The column header says `haiku` for all three: the tool reads the alias the runner was given, not
the model the CLI resolved it to.

`python -m antstreet.bench.table`, one arm folder at a time (the summary row of each):

```
| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| firm | 105 | 35 | 77 | 73% [64-81%] | 92% | $0.2948 | $0.4020 | 64% | 0 | 0 | 5m47s | 17/35 |   <- e9-coverage
| firm | 105 | 35 | 98 | 93% [87-97%] | 98% | $0.0109 | $0.0117 | 58% | 0 | 0 | 1m23s | 31/35 |   <- e9-firm
| single | 105 | 35 | 103 | 98% [93-99%] | 100% | $0.0029 | $0.0030 | 0% | 0 | 0 | 0m20s | 33/35 |   <- e9-single
```

Measured spend of the counted cells: coverage $30.96, firm $1.14, single $0.31 ($32.41), CLI
estimates.

## 4. Counts from `e9_cells.py`

`e9_cells.py` reads each cell's `result.json`, ledger, `coverage.json`, transcript and worker logs,
and prints the following (trailing spaces removed). "Stretch" is the model the coverage cell of the
same task and rep ran on; firm and single cells are grouped by it so that the rows pair.

```
== model ids in the worker logs, cells per arm
e9-coverage {'claude-haiku-4-5-20251001': 78, 'none (no worker ran)': 4, 'claude-haiku-5-5': 23}
e9-firm {'claude-haiku-5-5': 104, 'none (no worker ran)': 1}
e9-single {'claude-haiku-5-5': 105}
coverage cells by stretch: {'4.5': 80, '5.5': 25}

== per arm, on the (task, rep) pairs of each coverage stretch
arm stretch cells delivered false_pass/visible_all capped boss_stopped mean_cost mean_boss_cost median_s mean_visible_checks
e9-coverage 4.5 80 55 15/70 9 2 0.3802 0.2411 397 10.7
e9-coverage 5.5 25 22 1/23 0 2 0.0218 0.0177 173 9.7
e9-firm 4.5 80 74 6/80 0 0 0.0110 0.0062 84 7.9
e9-firm 5.5 25 24 0/24 0 1 0.0104 0.0066 82 7.6
e9-single 4.5 80 79 0/79 0 0 0.0030 0.0000 20 0.0
e9-single 5.5 25 24 0/24 0 0 0.0029 0.0000 20 0.0

== outcomes and hidden-check statuses per arm
e9-coverage {'completed': 92, 'capped': 9, 'boss:crashed': 3, 'boss:completed': 1} {'passed': 715, 'failed': 61, 'timeout': 1}
e9-firm {'completed': 104, 'boss:crashed': 1} {'passed': 761, 'failed': 16}
e9-single {'completed': 105} {'passed': 775, 'failed': 2}

== boss calls (firm-shaped arms), by stretch and purpose
e9-coverage 4.5 coverage_redraft calls 66 not completed {'capped': 1, 'crashed': 2, 'api_error': 1} mean cost $0.1312 median tokens_out of completed 19250.5
e9-coverage 4.5 term_sheet calls 80 not completed {'crashed': 1} mean cost $0.1329 median tokens_out of completed 20351
e9-coverage 5.5 coverage_redraft calls 12 not completed {} mean cost $0.0114 median tokens_out of completed 20525.0
e9-coverage 5.5 term_sheet calls 25 not completed {'crashed': 2} mean cost $0.0122 median tokens_out of completed 21302
e9-firm 5.5 term_sheet calls 105 not completed {'crashed': 1} mean cost $0.0063 median tokens_out of completed 11230.0

== coverage arm: redrafts, and the gaps left at approval
cells by redrafts asked: {0: 35, 1: 54, 2: 12, None: 4}
redrafts asked 78: kept 44, no fewer gaps 27, failed 7
approved cells: 101
  a rule no check cites (waived by the approval): cells 12 rules 18
  a rule whose checks lack its anchor: cells 22 rules 41
  a weak check: cells 6 checks 6
  stubs not run: 0
  stretch 4.5, gate clean at approval: 33/44 delivered
  stretch 4.5, gate with a gap at approval: 22/34 delivered
  stretch 5.5, gate clean at approval: 21/22 delivered
  stretch 5.5, gate with a gap at approval: 1/1 delivered

== cells not 'completed'
e9-coverage bytesize 1 4.5 capped failed |
e9-coverage cronnext 1 4.5 capped failed |
e9-coverage cronnext 2 4.5 capped failed |
e9-coverage cronnext 3 4.5 capped failed |
e9-coverage dedentblock 1 4.5 capped failed |
e9-coverage jsonpointer 2 4.5 boss:crashed failed | boss call ended as crashed
e9-coverage justify 2 4.5 capped delivered |
e9-coverage linediff 1 4.5 boss:completed failed | draft term sheet is invalid: check c04 has a syntax error: line 36: unterminated
e9-coverage lrucache 2 4.5 capped delivered |
e9-coverage lrucache 3 4.5 capped delivered |
e9-coverage mdheadings 1 4.5 capped delivered |
e9-coverage urlquery 1 5.5 boss:crashed failed | boss call ended as crashed
e9-coverage urlquery 3 5.5 boss:crashed failed | boss call ended as crashed
e9-firm wordwrap 2 5.5 boss:crashed failed | boss call ended as crashed

== delivered out of 3 by task: coverage, firm, single; coverage minus firm
bigdecimal    2 3 3  -1  coverage stretch 4.5/4.5/4.5
bytesize      0 3 3  -3  coverage stretch 4.5/4.5/4.5
calc          2 3 3  -1  coverage stretch 4.5/4.5/4.5
cronnext      0 2 3  -2  coverage stretch 4.5/4.5/4.5
csvline       3 3 3  +0  coverage stretch 4.5/4.5/4.5
dedentblock   2 3 3  -1  coverage stretch 4.5/4.5/4.5
duration      2 0 2  +2  coverage stretch 4.5/4.5/4.5
exprtokens    0 3 3  -3  coverage stretch 4.5/4.5/4.5
fracmath      3 1 3  +2  coverage stretch 4.5/4.5/4.5
iniparse      3 3 3  +0  coverage stretch 4.5/4.5/4.5
intervals     3 3 3  +0  coverage stretch 4.5/4.5/4.5
isoweek       1 3 3  -2  coverage stretch 4.5/4.5/4.5
jsonpointer   2 3 3  -1  coverage stretch 4.5/4.5/4.5
justify       3 3 3  +0  coverage stretch 4.5/4.5/4.5
linediff      2 3 3  -1  coverage stretch 4.5/4.5/4.5
lrucache      3 3 3  +0  coverage stretch 4.5/4.5/4.5
luhn          3 3 3  +0  coverage stretch 4.5/4.5/4.5
matrixops     3 3 3  +0  coverage stretch 4.5/4.5/4.5
mdheadings    2 3 3  -1  coverage stretch 4.5/4.5/4.5
minheap       2 3 3  -1  coverage stretch 4.5/4.5/4.5
moneysplit    3 3 3  +0  coverage stretch 4.5/4.5/4.5
prefixtrie    2 3 3  -1  coverage stretch 4.5/4.5/4.5
rangesum      3 3 3  +0  coverage stretch 4.5/4.5/4.5
ringbuffer    3 3 3  +0  coverage stretch 4.5/4.5/4.5
roman         2 3 3  -1  coverage stretch 4.5/4.5/4.5
semver        0 3 3  -3  coverage stretch 4.5/4.5/4.5
shortestpath  2 3 3  -1  coverage stretch 4.5/4.5/5.5
slugify       3 3 3  +0  coverage stretch 5.5/5.5/5.5
tokenbucket   2 3 2  -1  coverage stretch 5.5/5.5/5.5
toposort      3 3 3  +0  coverage stretch 5.5/5.5/5.5
unionfind     3 3 3  +0  coverage stretch 5.5/5.5/5.5
urlquery      1 3 3  -2  coverage stretch 5.5/5.5/5.5
wildcard      3 3 3  +0  coverage stretch 5.5/5.5/5.5
wordwrap      3 2 3  +1  coverage stretch 5.5/5.5/5.5
workdays      3 3 3  +0  coverage stretch 5.5/5.5/5.5

== failed coverage cells: stretch, outcome, gaps at approval, hidden checks failed
bigdecimal 2 4.5 completed redrafts 0 waived 0 anchor_missing 0 weak 0 ['compare']
bytesize 1 4.5 capped redrafts 1 waived 0 anchor_missing 0 weak 0 ['format_binary']
bytesize 2 4.5 completed redrafts 2 waived 1 anchor_missing 0 weak 0 ['format_binary']
bytesize 3 4.5 completed redrafts 1 waived 2 anchor_missing 2 weak 0 ['format_binary', 'parse_errors']
calc 3 4.5 completed redrafts 1 waived 0 anchor_missing 3 weak 0 ['malformed_tokens']
cronnext 1 4.5 capped redrafts 1 waived 0 anchor_missing 1 weak 0 ['invalid_expressions']
cronnext 2 4.5 capped redrafts 1 waived 0 anchor_missing 1 weak 0 ['invalid_expressions']
cronnext 3 4.5 capped redrafts 1 waived 0 anchor_missing 0 weak 0 ['invalid_expressions', 'next_fires']
dedentblock 1 4.5 capped redrafts 0 waived 0 anchor_missing 0 weak 0 ['blank_lines', 'dedent_basic', 'margin', 'properties']
duration 1 4.5 completed redrafts 1 waived 0 anchor_missing 1 weak 0 ['parse_decimals']
exprtokens 1 4.5 completed redrafts 1 waived 0 anchor_missing 1 weak 0 ['identifiers']
exprtokens 2 4.5 completed redrafts 1 waived 0 anchor_missing 1 weak 0 ['identifiers']
exprtokens 3 4.5 completed redrafts 1 waived 0 anchor_missing 3 weak 0 ['identifiers']
isoweek 1 4.5 completed redrafts 1 waived 0 anchor_missing 0 weak 0 ['parse_errors']
isoweek 2 4.5 completed redrafts 1 waived 0 anchor_missing 0 weak 0 ['parse_errors']
jsonpointer 2 4.5 boss:crashed redrafts None waived None anchor_missing None weak None ['escapes', 'invalid_pointers', 'list_indexes', 'missing_and_leaves', 'resolve_basic', 'set_value', 'set_value_errors', 'set_value_isolation']
linediff 1 4.5 boss:completed redrafts None waived None anchor_missing None weak None ['apply', 'apply_errors', 'change_order', 'diff_basic', 'diff_minimal', 'odd_lines', 'scale', 'stats']
mdheadings 2 4.5 completed redrafts 0 waived 0 anchor_missing 0 weak 0 ['titles']
minheap 2 4.5 completed redrafts 0 waived 0 anchor_missing 0 weak 0 ['ties']
prefixtrie 1 4.5 completed redrafts 0 waived 0 anchor_missing 0 weak 0 ['longest_common_prefix']
roman 2 4.5 completed redrafts 1 waived 0 anchor_missing 0 weak 0 ['from_roman_rejects']
semver 1 4.5 completed redrafts 1 waived 0 anchor_missing 5 weak 0 ['parse_invalid_input', 'sort_versions']
semver 2 4.5 completed redrafts 1 waived 0 anchor_missing 4 weak 0 ['parse_invalid_input']
semver 3 4.5 completed redrafts 1 waived 0 anchor_missing 5 weak 0 ['parse_invalid_input']
shortestpath 1 4.5 completed redrafts 1 waived 0 anchor_missing 0 weak 0 ['scale']
tokenbucket 2 5.5 completed redrafts 1 waived 0 anchor_missing 0 weak 0 ['clock_backwards']
urlquery 1 5.5 boss:crashed redrafts None waived None anchor_missing None weak None ['build_encoding', 'build_errors', 'build_structure', 'parse_basic', 'parse_decoding', 'parse_errors', 'parse_repeated', 'roundtrip']
urlquery 3 5.5 boss:crashed redrafts None waived None anchor_missing None weak None ['build_encoding', 'build_errors', 'build_structure', 'parse_basic', 'parse_decoding', 'parse_errors', 'parse_repeated', 'roundtrip']
```

## 5. Why the coverage arm delivered less

Hypotheses are labelled; the confidence is mine.

**The model change explains most of the gap (confidence about 90%).** Evidence, each from the cells:
- 25 of the coverage arm's 28 failed cells are in its Haiku 4.5 stretch (55 of 80 delivered there);
  in its Haiku 5.5 stretch it delivered 22 of 25.
- Paired over the 26 Haiku 4.5 tasks, coverage minus E9's firm (Haiku 5.5) is -0.2308 [-0.3846,
  -0.0641]; over the 8 Haiku 5.5 tasks it is -0.0833 [-0.2917, +0.0833].
- The plain firm moved by +0.3333 [+0.1667, +0.5000] from blind35 (Haiku 4.5, commit `e203f65`) to
  E9 (Haiku 5.5, `90138e1`) on those 26 tasks (46/78 to 72/78). That interval mixes model and commit,
  so it bounds nothing exactly, but a shift that large on the firm's side is enough to produce the
  primary gap without any effect of `--coverage`.
- On Haiku 4.5, coverage at `90138e1` against blind35's firm on the 26 tasks: 54/78 against 46/78,
  +0.1026 [-0.0128, +0.2308].

What would change my mind: a rerun of all three arms on one pinned model id in which coverage minus
firm stays near -0.20.

**At a fixed model, the effect of `--coverage` is not measured.** The 8-task Haiku 5.5 comparison is
24 cells a side, and its interval runs from -0.29 to +0.08. Two of the three Haiku 5.5 coverage
failures are `urlquery` runs in which the boss's first call crashed before any worker started.
*Hypothesis (low confidence):* the rule-citing draft of `--spec` is about twice as long (median
21,302 output tokens on Haiku 5.5, against 11,230 for the plain firm's draft), and longer boss calls
crash more often: the three crashed first calls in the coverage arm wrote 38,255 (`jsonpointer`),
31,860 and 35,800 (`urlquery`) tokens, the firm's one crash 22,389. The crash cause was not traced:
the boss's raw stream is not saved, and 3 against 1 is no evidence of a rate.

**Redrafts did not take budget from the workers.** Boss calls are outside the cell budget. In the 9
capped cells the workers spent $0.30 to $0.36 whatever the boss spent ($0.09 to $0.49), and
blind35's firm on the same 26 Haiku 4.5 tasks was capped in 5 of 78 cells against coverage's 9 of
78. *Hypothesis (low confidence):* coverage's drafts carry more checks (10.7 visible checks a cell on
Haiku 4.5, against 7.8 for blind35's firm), so workers do more before the gate passes and reach the
cap more often. No cell was capped on Haiku 5.5, where the cap buys about ten times the tokens.

**Citing a rule is not testing it (medium confidence).** Of the 24 approved coverage cells that
failed a hidden check, 12 showed a clean gate (every rule cited, every anchor present, no weak
check), 11 had an anchor missing (all of `exprtokens` and `semver`, among others) and 2 had a waived
rule (`bytesize`). On Haiku 4.5 the clean-gate cells delivered 33 of 44 and the cells with a gap 22
of 34; the groups differ in task, so these rates are descriptive. The gate checks that a check
names each rule and is not fooled by a stub; it cannot see whether the check uses the inputs that
break a real product, which is how the firm's checks failed in blind35 (section 4 of
`2026-10-03-blind35`). Which rule each failed hidden check belongs to was not traced.

## 6. Limits

- One commit, one budget, 35 tasks, 3 reps, and two models across the arms (above).
- On Haiku 5.5 the firm and the single agent are at 93% and 98%: the task set is near its ceiling,
  so even a clean rerun on Haiku 5.5 has little room to show a gain from `--coverage` over the firm
  (7 cells at most).
- Costs are the CLI's estimates, not a bill, and depend on its price table for each model.
- Several comparisons are reported; the subset intervals in section 5 are after the fact, chosen
  once the model change was found, and decide nothing.
- The 4 coverage cells and 1 firm cell where the boss stopped the run are counted as not delivered,
  as the plan counts every cell that ran.

## What would change the conclusion

- A rerun with the model pinned by id (for example `--model claude-haiku-5-5 --boss-model
  claude-haiku-5-5`), the three arms interleaved by task so a change outside the repo hits all of
  them, recorded as a dated amendment in `bench/PREREG.md` before it runs. If coverage minus firm then
  lies above 0, `--coverage` is shown to help; if below, it is shown to hurt on that model.
- A harder task set, where the firm on Haiku 5.5 is well below 100%, so a gain has room to show.

## What happens next

- `--coverage` stays off by default and documented as unmeasured at a fixed model.
- Whether to rerun E9, and on which tasks, is the owner's call; this write-up only reports.
