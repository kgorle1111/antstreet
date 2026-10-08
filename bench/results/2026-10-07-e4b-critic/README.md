# 2026-10-07-e4b-critic

E4b from `bench/PREREG.md`: the E4 critic arm again, with room to finish. Does a firm with a
fresh-context critic that is allowed to complete its call deliver more than a single agent that reviews
its own work? Written from saved cells only: no model call, no spend. The raw folder is
`bench/results/raw/e4b-critic`, git-ignored. E4's arms (`e4-selfrev`, `e4-firm`, `e4-critic`) were not
rerun; they are the cells described in `2026-10-07-e4-critic/README.md`. Numbers in section 3 are pasted
from `python -m boss.bench.kpi`, `python -m boss.bench.table` and `python -m boss.bench.paired`; the
counts in section 4 come from the script shown there. Model: Haiku for the boss and every worker, $0.40
a cell.

## Answer

1. **E4b is not shown, by the slimmest margin.** The rule compares the E4b critic arm with E4's
   self-review on paired delivery. The difference is +0.0952 [-0.0000, +0.1905]. The lower bound is
   exactly zero (a negative zero at four places); the rule requires it above zero. It is not, so the
   claim is not shown.
2. **The picture is consistently positive, and it is not a result.** Delivery 74/105 (70%) against 61%
   (self-review), 60% (E4 firm) and 67% (E4 critic arm). False passes are the lowest of the four arms:
   19 of 80 cells that passed every visible check (24%). Wrong boss checks: 34 of 833 (4%). Tasks
   delivered on all 3 runs: 17 of 35, the same as self-review.
3. **Reported beside the rule, not decisive.** E4b against E4's plain firm: +0.1048 [+0.0286, +0.1810].
   That interval lies above zero, but it is a secondary comparison, not the pre-registered decision, and
   several comparisons are reported here, so one interval clearing zero among them is weaker evidence
   than it would be alone. E4b against E4's critic arm: +0.0381 [-0.0381, +0.1143], zero inside.
4. **The price is real and certain.** Cost per assigned cell, E4b minus self-review: +$0.1844
   [+0.1547, +0.2152], wholly on the costly side. Cost per delivered task $0.5865 against $0.3756 (1.56x).
   Median time of delivered cells 7m18s against 2m28s (2.96x).
5. **The critic finished this time.** 94 of 105 critic calls completed, 10 were capped and none timed
   out (E4: 68 completed, 35 capped, 1 timed out, 1 never asked). A verified finding reached the
   investor in 29 cells, and a fix round ran in 20 (section 4).

## What this shows, and what it does not

Shows, on 35 tasks and Haiku:
- With a critic that can finish and an investor who always says yes, the firm's delivery is 9.5 points
  above self-review's at the point estimate, and the interval touches zero: it allows 0.0 to +19.0.
- The direction is the same in every comparison and in the false-pass rate, which falls arm by arm (39%,
  33%, 28%, 24%).
- Whatever the critic adds, it adds at a large price in time and money (section 3).

Does not show:
- That the critic helps. The decision rule was not met. This write-up does not round +0.0952
  [-0.0000, +0.1905] in the product's favour: the verdict is not shown.
- Power. 35 tasks x 3 reps can detect about a 10-point effect; the observed difference is at that edge,
  so an effect of this size and a smaller or null one are both consistent with the data.
- That the +0.1048 over E4's firm is a finding. It is a secondary comparison, one of four reported; with
  that many looks, one interval clearing zero happens by chance fairly often. It does not change the
  verdict.
- That a human-filtered critic would do the same. The benchmark answers yes to every critic finding
  (`bench/PREREG.md`, E4), so a wrong finding becomes a check and a fix task. A real investor would
  filter those out. This is a worst case for wrong findings and a best case for effort spent on them,
  and the auto-approved checks are part of what was measured.
- Anything about Sonnet or another budget. One model, one budget, 35 tasks.
- An equal-budget comparison. Worst-case caps per cell are $0.32 (self-review), $0.65 (firm) and $1.35
  (firm with the $0.40 critic), so the arms had different budgets. Cost is reported beside delivery, so
  a win bought by spending more counts as a cost.

## 1. Method

- Code: E4's commit (`4ba91ad`) with exactly two changes: the critic's per-call cap is $0.40 (was
  $0.15), and the critic call's time limit is 900 s (was 300 s). The builder prompt and everything else
  match E4's other arms; a run from a later `main` (builder_v5) is not E4b.
- **The second change is an amendment.** In the first 7 E4b cells, 4 critic calls hit the 300 s time
  limit (E4 had 1 in 105), so with the $0.40 cap the time limit, not the critic, would have decided
  them. The amendment is dated 2026-10-07 in `bench/PREREG.md` ("Changes to this plan") and was made
  before any E4b result was read. Those 7 cells, plus one stale cut-off cell left by the pause, were set
  aside unread to `bench/results/raw/superseded-2026-10-07-e4b-300s-timeout`, and E4b restarted from
  zero with both changes.
- blind35: 35 tasks (`bench/tasks`) x 3 reps = 105 cells, 0 infrastructure exclusions. All cells record
  task set `0a83fc97a753b08c`. Arm: firm with critic, `--budget 0.40 --firm-args "--slice 0.20 --roles
  critic --fix-budget 0.30"`, fresh in its own `--out`, the same blinded prompts as E4, Haiku for the
  boss and the workers. After the build a fresh-context critic writes tests for the bugs it thinks it
  found; a finding is verified only if its test fails on the product. Verified findings become checks and
  fund a fix round, with the investor's yes (the benchmark answers yes).
- The firm arm is `boss fund` with the term sheet approved automatically, as in `bench/METHOD.md`.
  Delivered means every hidden check passed. No held-out checks.
- The comparison arms are E4's saved self-review, firm and critic cells, not rerun: nothing in their
  arms changed.
- Decision rule (`bench/PREREG.md`, E4b): the E4b critic arm beats E4's self-review on paired delivery
  (bootstrap over tasks, 10,000 resamples, seed 0), or E4b is not shown. E4b against E4's firm, against
  E4's critic arm, the cost per assigned cell and time are reported, not decisive.
- The paired `cost_per_delivery` KPI is the tool's name for the cost per assigned cell: each task's
  mean cost over all its runs, delivered or not (`src/boss/bench/paired.py`). It is not the pooled cost
  per delivered task in the KPI table.

## 2. Reproduction

The numbers below were produced from the saved cells and checked against the analysis run earlier the
same day with the same commands: every number is identical. The paired difference is A minus B. The
tool prints "shown" when an interval lies wholly on the benefit side and "not shown" otherwise; the cost
interval lies above 0, the costly side, so its verdict word means nothing there. The decision is the
first block in section 3, and it says "not shown".

## 3. Numbers pasted from the repo's commands

`python -m boss.bench.paired raw/e4b-critic raw/e4-selfrev --arm-a firm --arm-b single-review --kpi delivery`
(the decision rule):

```
paired firm vs single-review, delivery (share), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single-review): +0.0952
95% interval: [-0.0000, +0.1905] (10000 task resamples, seed 0)
verdict: not shown
```

E4b against E4's plain firm (`raw/e4b-critic raw/e4-firm`, both arms `firm`, delivery). The tool's
verdict word is "shown"; this is a secondary comparison, not the decision:

```
paired firm vs firm, delivery (share), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - firm): +0.1048
95% interval: [+0.0286, +0.1810] (10000 task resamples, seed 0)
verdict: shown
```

E4b against E4's critic arm (`raw/e4b-critic raw/e4-critic`, delivery):

```
paired firm vs firm, delivery (share), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - firm): +0.0381
95% interval: [-0.0381, +0.1143] (10000 task resamples, seed 0)
verdict: not shown
```

Cost per assigned cell, `--kpi cost_per_delivery`, E4b against self-review:

```
paired firm vs single-review, cost_per_delivery ($), task set 0a83fc97a753b08c
tasks: 35 (not on both sides: 0; infrastructure cells excluded: 0)
mean difference (firm - single-review): +0.1844
95% interval: [+0.1547, +0.2152] (10000 task resamples, seed 0)
verdict: not shown
```

`python -m boss.bench.kpi raw/e4-selfrev raw/e4-firm raw/e4-critic raw/e4b-critic` (the last column is
E4b):

```
| KPI | e4-selfrev/single-review (haiku, $0.4000) | e4-firm/firm (haiku, $0.4000, --slice 0.20) | e4-critic/firm (haiku, $0.4000, --slice 0.20 --roles critic --fix-budget 0.30) | e4b-critic/firm (haiku, $0.4000, --slice 0.20 --roles critic --fix-budget 0.30) |
| --- | --- | --- | --- | --- |
| 1 Delivery rate | 61% [51-70%] (64/105) | 60% [50-69%] (63/105) | 67% [57-75%] (70/105) | 70% [61-78%] (74/105) |
| 2 False-pass rate | 39% [29-49%] (34/88) | 33% [23-44%] (24/73) | 28% [19-39%] (21/75) | 24% [16-34%] (19/80) |
| 3 Cost per delivered task | $0.3756 | $0.3856 | $0.5590 | $0.5865 |
|   events of unknown cost | 0 | 0 | 1 | 0 |
| 4 Time to delivery (median) | delivered 2m28s; all counted 2m42s | delivered 3m36s; all counted 4m05s | delivered 8m01s; all counted 8m13s | delivered 7m18s; all counted 7m53s |
| 5 Reliability (pass^k) | 17/35 (k=3) | 12/35 (k=3) | 19/35 (k=3) | 17/35 (k=3) |
| 6 Investor questions | 0.00 per run (0 in 105 runs) | 1.11 per run (117 in 105 runs) | 1.37 per run (144 in 105 runs) | 1.35 per run (142 in 105 runs) |
| 7 Check quality | not measured | 47/772 wrong (6%) | 39/824 wrong (5%) | 34/833 wrong (4%) |
```

Reading the table: the pooled cost per delivered task is 1.56x self-review's for E4b ($0.5865 /
$0.3756); the median time of delivered cells is 2.96x (438 s / 148 s). The false-pass rate counts cells
that passed every visible check and then failed a hidden one; its denominator is not the same in the
four arms (88, 73, 75, 80), so read the intervals, which overlap. Reliability is 17/35 in E4b, equal to
self-review and below E4's critic arm (19/35).

`python -m boss.bench.table raw/e4b-critic`:

```
Task set: 0a83fc97a753b08c | Model: haiku | Budget per cell: $0.4000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| firm | 105 | 35 | 74 | 70% [61-78%] | 92% | $0.4133 | $0.5865 | 21% | 0 | 0 | 7m53s | 17/35 |

Visible vs hidden: 80 of 105 firm cells passed every visible check; 19 of those failed a hidden check.
Wrong boss checks: 34 of 833 checks failed on the reference solution, in 29 drafts.

| task | firm |
| --- | --- |
| bigdecimal | 2/3 |
| bytesize | 0/3 |
| calc | 2/3 |
| cronnext | 0/3 |
| csvline | 3/3 |
| dedentblock | 3/3 |
| duration | 0/3 |
| exprtokens | 2/3 |
| fracmath | 2/3 |
| iniparse | 3/3 |
| intervals | 3/3 |
| isoweek | 0/3 |
| jsonpointer | 2/3 |
| justify | 3/3 |
| linediff | 3/3 |
| lrucache | 3/3 |
| luhn | 1/3 |
| matrixops | 3/3 |
| mdheadings | 2/3 |
| minheap | 2/3 |
| moneysplit | 3/3 |
| prefixtrie | 2/3 |
| rangesum | 3/3 |
| ringbuffer | 3/3 |
| roman | 3/3 |
| semver | 1/3 |
| shortestpath | 3/3 |
| slugify | 3/3 |
| tokenbucket | 1/3 |
| toposort | 2/3 |
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
passed. This is the script used for E4, unchanged. The groups are not compared with a no-critic
counterfactual, so they say what happened, not what the critic caused.

```python
import collections, glob, json, sys

root = sys.argv[1]  # the e4b-critic folder
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

Output on the 105 E4b cells (the delivered total, 6+0+16+2+50 = 74, matches the KPI table):

```
critic call failed (capped): 6/10 delivered
critic never asked: 0/1 delivered
finding verified, fix round ran: 16/20 delivered
finding verified, no fix round: 2/9 delivered
ok, nothing verified: 50/65 delivered
verified findings: 36 | rejected findings: 17
```

- **Critic call outcomes: completed 94, capped 10, timeout 0.** In one cell (`wildcard` rep 1) the
  ledger holds no critic call and the cell did not deliver; I did not trace why.
- **Findings that became checks: 36 verified findings, in 29 cells** (20 + 9); 17 findings were
  rejected. Each verified finding was offered to the investor, which the benchmark answers yes to.
- **The fix round ran in 20 of those 29 cells** (the transcripts say "Funding a worker to fix them" in
  20 cells, matching the ledger). In the other 9 the ledger records `ruling: declined` and no second
  approval; I did not trace why no round was funded.
- The 20 fix-round cells delivered 16 times (80%). The 10 cells where the critic was capped delivered 6
  times (60%); the 65 where it completed and verified nothing, 50 times (77%). The groups differ in
  difficulty (a critic that finds something is working on a product that has something wrong), so these
  rates do not compare arms.

## 5. Things that look wrong, and limits

- **The lower bound prints as -0.0000.** It is a small negative number that rounds to zero at four
  places. Either way it is not above zero, and the rule needs it above zero.
- **E4b's advantage may not come from the critic's findings.** In 65 cells the critic found nothing;
  any gain comes from the 29 cells with a finding, 20 of which ran a fix round, and the larger critic
  budget changes the cost of every cell. Nothing here separates a critic effect from luck.
- **Self-review is a different shape of agent**, not only a different budget: one session, no boss
  draft, no checks written first. Its good delivery (61%) at $0.2289 a cell is the number to beat.
- **Cost is the CLI's client-side estimate**, not a bill. E4b has no event of unknown cost.
- **35 tasks, 3 reps, one model.** One cell is about 1 point of delivery. Differences under about 10
  points are not detectable.
- Time includes the boss draft and any wait for the investor, the critic call and the fix round. I did
  not separate the parts.
- E4b is a separate run from E4's arms, made later the same day; part of any gap is ordinary
  run-to-run noise, and nothing here measures that noise.

## What happens next

- The critic stays a recommended option, not the default: it did not meet the bar the plan set, and it
  costs about 1.6x as much per delivered task and about 3x the time.
- A powered re-test after launch settles it: more tasks and runs, so that an effect near 10 points can
  be told from zero.
- E8 builds on this result.
