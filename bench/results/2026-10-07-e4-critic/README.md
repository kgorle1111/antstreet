# 2026-10-07-e4-critic

E4 from `bench/PREREG.md`: does a firm with a fresh-context critic deliver more than a single agent
that reviews its own work? Written from saved cells only: no model call, no spend. The raw folders are
`bench/results/raw/e4-selfrev`, `e4-firm` and `e4-critic`, git-ignored. Numbers in section 3 are pasted
from `python -m boss.bench.kpi`, `python -m boss.bench.table` and `python -m boss.bench.paired`; the
counts in section 4 come from the script shown there. Model: Haiku for the boss and every worker, $0.40
a cell. Code at commit `4ba91ad`.

## Answer

1. **E4 is not shown.** The rule compares the critic arm (firm `--roles critic`) with self-review on
   paired delivery. The difference is +0.0571 [-0.0381, +0.1619]. Zero is inside the interval.
2. **A positive trend, not a result.** The critic arm has the best delivery (70/105, 67%), the fewest
   false passes (21 of 75 cells that passed every visible check, 28%) and the best reliability (19 of 35
   tasks delivered on all 3 runs), but the interval crosses zero. It costs about 1.5x as much per
   delivered task ($0.5590 against $0.3756) and takes about 3x as long (median 8m01s against 2m28s for
   delivered cells).
3. **Critic against plain firm, reported beside the rule:** +0.0667 [-0.0190, +0.1524]. Zero is inside
   the interval.
4. **Plain firm against self-review:** -0.0095 [-0.1143, +0.0952]. The firm without a critic did not
   deliver more than the single agent reviewing itself.
5. **The cost is real and certain.** Cost per assigned cell, critic minus self-review: +$0.1437
   [+0.1207, +0.1678]; critic minus firm: +$0.1413 [+0.1167, +0.1653]. Both intervals lie wholly on the
   costly side.
6. **The critic did little in most cells.** Its call failed in 36 of 105 cells (35 ended `capped`, 1
   timed out), and in 43 more it verified nothing. A verified finding reached the investor in 25 cells,
   and a fix round ran in 19 (section 4).

## What this shows, and what it does not

Shows, on 35 tasks and Haiku:
- With a fresh-context critic and an investor who always says yes, delivery is not demonstrably above a
  single agent that reviews its own work. The point estimate is +5.7 points; the interval allows -3.8
  to +16.2.
- Whatever the critic adds, it adds at a large price in time and money (section 3).

Does not show:
- That the critic does not help. 35 tasks x 3 reps can detect about a 10-point effect, not smaller. A
  real gain of 4 to 8 points is as consistent with this data as zero.
- That a human-filtered critic would do the same. The benchmark answers yes to every critic finding
  (`bench/PREREG.md`, E4), so a wrong finding becomes a check and a fix task. A real investor would
  filter those out. This is a worst case for wrong findings and a best case for effort spent on them.
- Anything about Sonnet or another budget. One model, one budget, 35 tasks.
- An equal-budget comparison. It cannot be set: the boss and critic caps alone are $0.40, and every
  round keeps a $0.10 reserve (`bench/PREREG.md`, 2026-10-05). The worst-case caps per cell are $0.32
  (self-review), $0.65 (firm) and $1.10 (firm with critic), so the arms had different budgets. Cost is
  reported beside delivery, so a win bought by spending more counts as a cost.
- Why the critic's call fails so often. I have not traced the 35 `capped` calls. The ledger records
  `outcome: capped` and the run goes on without the critic's output.

## 1. Method

- blind35: 35 tasks (`bench/tasks`) x 3 reps = 105 cells per arm, 315 counted, 0 infrastructure
  exclusions. All cells record task set `0a83fc97a753b08c`.
- Arms, each fresh in its own `--out`, the same blinded prompts, Haiku for the boss and the workers:
  - self-review (`e4-selfrev`): `--arms single-review --budget 0.40`. The single agent builds, then
    its session is resumed once to review its own work. Slice caps $0.24 + $0.08, worst case $0.32.
  - firm (`e4-firm`): `--budget 0.40 --firm-args "--slice 0.20"`. Worst case $0.65 (rounds $0.40 + the
    boss draft cap $0.25).
  - firm with critic (`e4-critic`): the firm's options plus `--roles critic --fix-budget 0.30`. After
    the build a fresh-context critic writes tests for the bugs it thinks it found; a finding is
    verified only if its test fails on the product. Verified findings become checks and fund a fix
    round, with the investor's yes (the benchmark answers yes). Worst case $1.10 (plus the critic cap
    $0.15 and the fix round $0.30).
- The firm arms are `boss fund` with the term sheet approved automatically, as in `bench/METHOD.md`.
  Delivered means every hidden check passed. No held-out checks.
- **Run history.** The first run, on 2026-10-05, hit the plan's usage limit; its cells were moved aside
  to `bench/results/raw/superseded-2026-10-07-e4-usage-limit/` (excluded under B71). A rerun on
  2026-10-07 failed on an expired login that the CLI reported in a new format, which the cell
  classifier did not recognise; those cells were moved to
  `raw/superseded-2026-10-07-e4-auth-expired/` and the classifier was fixed in PR #48. The counted
  cells are those in the three folders. By run-folder date, 13 of the 105 critic cells were run on
  2026-10-05 and 92 on 2026-10-07.
- Decision rule (`bench/PREREG.md`, E4 and its 2026-10-05 change): the critic arm beats self-review on
  paired delivery (bootstrap over tasks, 10,000 resamples, seed 0), or E4 is not shown. Critic against
  firm, firm against self-review and the cost intervals are reported, not decisive.
- The paired `cost_per_delivery` KPI is the tool's name for the cost per assigned cell: each task's
  mean cost over all its runs, delivered or not (`src/boss/bench/paired.py`). It is not the pooled cost
  per delivered task in the KPI table.

## 2. Reproduction

The numbers below were produced from the saved cells and checked against a second run of the same
commands: every line is identical. The paired difference is A minus B. The tool prints "not shown"
whenever the interval does not lie below 0 on time and cost (it looks for a benefit); the cost
intervals here lie above 0, the costly side.

## 3. Numbers pasted from the repo's commands

`python -m boss.bench.paired raw/e4-critic raw/e4-selfrev --arm-a firm --arm-b single-review --kpi delivery`
(the decision rule):

```
paired firm vs single-review, delivery (share), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single-review): +0.0571
95% interval: [-0.0381, +0.1619] (10000 task resamples, seed 0)
verdict: not shown
```

Critic against plain firm (`raw/e4-critic raw/e4-firm`, both arms `firm`, delivery):

```
paired firm vs firm, delivery (share), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - firm): +0.0667
95% interval: [-0.0190, +0.1524] (10000 task resamples, seed 0)
verdict: not shown
```

Plain firm against self-review (`raw/e4-firm raw/e4-selfrev`, arms `firm` and `single-review`, delivery):

```
paired firm vs single-review, delivery (share), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single-review): -0.0095
95% interval: [-0.1143, +0.0952] (10000 task resamples, seed 0)
verdict: not shown
```

Cost per assigned cell, `--kpi cost_per_delivery`, critic against self-review and critic against firm:

```
paired firm vs single-review, cost_per_delivery ($), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single-review): +0.1437
95% interval: [+0.1207, +0.1678] (10000 task resamples, seed 0)
verdict: not shown

paired firm vs firm, cost_per_delivery ($), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - firm): +0.1413
95% interval: [+0.1167, +0.1653] (10000 task resamples, seed 0)
verdict: not shown
```

`python -m boss.bench.kpi raw/e4-selfrev raw/e4-firm raw/e4-critic`:

```
| KPI | e4-selfrev/single-review (haiku, $0.4000) | e4-firm/firm (haiku, $0.4000, --slice 0.20) | e4-critic/firm (haiku, $0.4000, --slice 0.20 --roles critic --fix-budget 0.30) |
| --- | --- | --- | --- |
| 1 Delivery rate | 61% [51-70%] (64/105) | 60% [50-69%] (63/105) | 67% [57-75%] (70/105) |
| 2 False-pass rate | 39% [29-49%] (34/88) | 33% [23-44%] (24/73) | 28% [19-39%] (21/75) |
| 3 Cost per delivered task | $0.3756 | $0.3856 | $0.5590 |
|   events of unknown cost | 0 | 0 | 1 |
| 4 Time to delivery (median) | delivered 2m28s; all counted 2m42s | delivered 3m36s; all counted 4m05s | delivered 8m01s; all counted 8m13s |
| 5 Reliability (pass^k) | 17/35 (k=3) | 12/35 (k=3) | 19/35 (k=3) |
| 6 Investor questions | 0.00 per run (0 in 105 runs) | 1.11 per run (117 in 105 runs) | 1.37 per run (144 in 105 runs) |
| 7 Check quality | not measured | 47/772 wrong (6%) | 39/824 wrong (5%) |

Sample sizes (counted cells over tasks; infrastructure failures excluded):
  e4-selfrev/single-review (haiku, $0.4000): 105 cells over 35 tasks (0 excluded)
  e4-firm/firm (haiku, $0.4000, --slice 0.20): 105 cells over 35 tasks (0 excluded)
  e4-critic/firm (haiku, $0.4000, --slice 0.20 --roles critic --fix-budget 0.30): 105 cells over 35 tasks (0 excluded)

Intervals are Wilson 95%. Overlapping intervals mean no demonstrated difference.
```

Reading the table: the pooled cost per delivered task is 1.49x self-review's for the critic arm
($0.5590 / $0.3756); the median time of delivered cells is 3.25x (481 s / 148 s). The critic arm's one
unknown-cost event makes its cost a floor. The false-pass rate counts cells that passed every visible
check and then failed a hidden one; its denominator is not the same in the three arms (88, 73, 75), so
read the intervals, which overlap.

`python -m boss.bench.table raw/e4-selfrev`, `raw/e4-firm`, `raw/e4-critic`:

`raw/e4-selfrev`:

```
Task set: 0a83fc97a753b08c | Model: haiku | Budget per cell: $0.4000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single-review | 105 | 35 | 64 | 61% [51-70%] | 90% | $0.2289 | $0.3756 | 0% | 0 | 0 | 2m42s | 17/35 |

| task | single-review |
| --- | --- |
| bigdecimal | 3/3 |
| bytesize | 0/3 |
| calc | 0/3 |
| cronnext | 0/3 |
| csvline | 3/3 |
| dedentblock | 3/3 |
| duration | 2/3 |
| exprtokens | 0/3 |
| fracmath | 3/3 |
| iniparse | 3/3 |
| intervals | 3/3 |
| isoweek | 0/3 |
| jsonpointer | 0/3 |
| justify | 3/3 |
| linediff | 3/3 |
| lrucache | 3/3 |
| luhn | 0/3 |
| matrixops | 3/3 |
| mdheadings | 1/3 |
| minheap | 3/3 |
| moneysplit | 2/3 |
| prefixtrie | 1/3 |
| rangesum | 3/3 |
| ringbuffer | 3/3 |
| roman | 3/3 |
| semver | 0/3 |
| shortestpath | 2/3 |
| slugify | 2/3 |
| tokenbucket | 0/3 |
| toposort | 0/3 |
| unionfind | 3/3 |
| urlquery | 2/3 |
| wildcard | 1/3 |
| wordwrap | 3/3 |
| workdays | 3/3 |

Pass rates from fewer than ~60 paired tasks cannot show a 20-point difference; treat them as descriptive.
```

`raw/e4-firm`:

```
Task set: 0a83fc97a753b08c | Model: haiku | Budget per cell: $0.4000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| firm | 105 | 35 | 63 | 60% [50-69%] | 89% | $0.2314 | $0.3856 | 40% | 0 | 0 | 4m05s | 12/35 |

Visible vs hidden: 73 of 105 firm cells passed every visible check; 24 of those failed a hidden check.
Wrong boss checks: 47 of 772 checks failed on the reference solution, in 36 drafts.

| task | firm |
| --- | --- |
| bigdecimal | 1/3 |
| bytesize | 0/3 |
| calc | 0/3 |
| cronnext | 0/3 |
| csvline | 2/3 |
| dedentblock | 3/3 |
| duration | 0/3 |
| exprtokens | 1/3 |
| fracmath | 1/3 |
| iniparse | 3/3 |
| intervals | 3/3 |
| isoweek | 0/3 |
| jsonpointer | 2/3 |
| justify | 3/3 |
| linediff | 2/3 |
| lrucache | 2/3 |
| luhn | 2/3 |
| matrixops | 3/3 |
| mdheadings | 1/3 |
| minheap | 2/3 |
| moneysplit | 3/3 |
| prefixtrie | 3/3 |
| rangesum | 3/3 |
| ringbuffer | 3/3 |
| roman | 3/3 |
| semver | 1/3 |
| shortestpath | 2/3 |
| slugify | 3/3 |
| tokenbucket | 0/3 |
| toposort | 1/3 |
| unionfind | 3/3 |
| urlquery | 2/3 |
| wildcard | 1/3 |
| wordwrap | 2/3 |
| workdays | 2/3 |

Pass rates from fewer than ~60 paired tasks cannot show a 20-point difference; treat them as descriptive.
```

`raw/e4-critic`:

```
Task set: 0a83fc97a753b08c | Model: haiku | Budget per cell: $0.4000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| firm | 105 | 35 | 70 | 67% [57-75%] | 92% | $0.3727 | $0.5590 | 24% | 1 | 0 | 8m13s | 19/35 |

Visible vs hidden: 75 of 105 firm cells passed every visible check; 21 of those failed a hidden check.
Wrong boss checks: 39 of 824 checks failed on the reference solution, in 33 drafts.

| task | firm |
| --- | --- |
| bigdecimal | 1/3 |
| bytesize | 0/3 |
| calc | 0/3 |
| cronnext | 0/3 |
| csvline | 3/3 |
| dedentblock | 3/3 |
| duration | 1/3 |
| exprtokens | 1/3 |
| fracmath | 3/3 |
| iniparse | 3/3 |
| intervals | 3/3 |
| isoweek | 0/3 |
| jsonpointer | 0/3 |
| justify | 3/3 |
| linediff | 3/3 |
| lrucache | 3/3 |
| luhn | 2/3 |
| matrixops | 3/3 |
| mdheadings | 1/3 |
| minheap | 2/3 |
| moneysplit | 3/3 |
| prefixtrie | 3/3 |
| rangesum | 3/3 |
| ringbuffer | 3/3 |
| roman | 3/3 |
| semver | 1/3 |
| shortestpath | 3/3 |
| slugify | 2/3 |
| tokenbucket | 0/3 |
| toposort | 3/3 |
| unionfind | 3/3 |
| urlquery | 1/3 |
| wildcard | 1/3 |
| wordwrap | 3/3 |
| workdays | 3/3 |

Pass rates from fewer than ~60 paired tasks cannot show a 20-point difference; treat them as descriptive.
```


## 4. What the critic did

Counted by script from each critic cell's ledger (`.boss/runs/*/ledger.jsonl`) and `result.json`: one
critic `role_call` per cell, whose data says whether the call completed and how many findings were
verified (their test fails on the product) or rejected (it did not). A fix round is a second `approved`
event in the ledger (the amended term sheet). Delivered is `CellResult.passed`: every hidden check
passed. The fix round and the delivery below are not compared with a no-critic counterfactual, so they
say what happened, not what the critic caused.

```python
import collections, glob, json, sys

root = sys.argv[1]  # the e4-critic folder
groups = collections.defaultdict(lambda: [0, 0])
found = rejected = 0
for led in sorted(glob.glob(root + "/*/firm/rep*/.boss/runs/*/ledger.jsonl")):
    ev = [json.loads(line) for line in open(led)]
    r = json.load(open(led.split("/.boss/")[0] + "/result.json"))
    delivered = bool(r["hidden"]) and all(v == "passed" for v in r["hidden"].values())
    calls = [
        e["data"] for e in ev if e["event"] == "role_call" and e["data"].get("role") == "critic"
    ]
    fix_round = (
        sum(e["event"] == "approved" for e in ev) > 1
    )  # the 2nd approval is the amended sheet
    if not calls:
        g = "critic never asked"
    elif calls[0]["result"] != "ok":
        g = "critic call failed (" + calls[0]["outcome"] + ")"
    else:
        found += calls[0]["verified"]
        rejected += calls[0]["rejected"]
        g = (
            "ok, nothing verified"
            if not calls[0]["verified"]
            else (
                "finding verified, fix round ran" if fix_round else "finding verified, no fix round"
            )
        )
    groups[g][0] += delivered
    groups[g][1] += 1
for g, (d, n) in sorted(groups.items()):
    print(f"{g}: {d}/{n} delivered")
print("verified findings:", found, "| rejected findings:", rejected)
```

Output on the 105 critic cells (the delivered total, 20+1+0+13+2+34 = 70, matches the KPI table):

```
critic call failed (capped): 20/35 delivered
critic call failed (timeout): 1/1 delivered
critic never asked: 0/1 delivered
finding verified, fix round ran: 13/19 delivered
finding verified, no fix round: 2/6 delivered
ok, nothing verified: 34/43 delivered
verified findings: 25 | rejected findings: 13
```

- **Findings that became checks: 25**, one in each of 25 cells (the other 43 completed calls found
  nothing that verified; 13 findings were rejected). Each of the 25 was offered to the investor, which
  the benchmark answers yes to.
- **The fix round ran in 19 of those 25 cells** (the transcripts say "Funding a worker to fix them" 19
  times). In the other 6 the run had already ended early because round 1 closed below its unlock
  threshold, so no fix round was offered (the ledger records these 6 as `ruled: declined`).
- **The critic call failed in 36 of 104 asked cells**: 35 `capped`, 1 timeout. In the remaining cell
  (1 of 105) the ledger holds no critic call and the cell did not deliver. I did not trace why. A
  failed critic leaves the cell a plain firm cell that still paid for the critic call.
- The 19 fix-round cells delivered 13 times (68%). The 36 cells where the critic failed delivered 21
  times (58%); the 43 where it verified nothing, 34 times (79%). The groups differ in difficulty (a
  critic that finds something is working on a product that has something wrong), so these rates do not
  compare arms.

## 5. Things that look wrong, and limits

- **The critic's call failed in a third of cells** (section 4), and each failed call still cost money
  (one example: $0.1775 against the $0.15 critic cap, 32,000 output tokens, in `bigdecimal` rep 1).
  A critic that does not time out may behave differently. This write-up tests the critic as built, not
  a critic that always finishes.
- **The critic arm's advantage over plain firm may not come from the critic.** In 43 cells it found
  nothing, and in 36 it failed; any gain is from the 25 cells with a finding, 19 of which ran a fix
  round. Nothing here separates a critic effect from luck in 19 cells.
- **Self-review is a different shape of agent**, not only a different budget: one session, no boss
  draft, no checks written first. Its good delivery (61%) at $0.2289 a cell is the number to beat.
- **Cost is the CLI's client-side estimate**, not a bill. One critic-arm event is of unknown cost, so
  its cost is a floor.
- **35 tasks, 3 reps, one model.** One cell is about 1 point of delivery. Differences under about 10
  points are not detectable.
- Time includes the boss draft and any wait for the investor; for the critic arm it includes the
  critic call and the fix round. I did not separate the parts.
- The critic arm mixes 13 cells run on 2026-10-05 with 92 run on 2026-10-07 (by run-folder date). I did
  not check the other two arms' split, or whether the provider's behaviour differed between the days.
