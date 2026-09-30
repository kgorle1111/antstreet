# Benchmark results

One folder per run: `table.md` (what `python -m boss.bench.table` printed) and `results.jsonl`
(every cell's `result.json`, one per line). Raw ledgers, worker logs and products stay on the
machine that ran them (`bench/results/raw/`, git-ignored): they hold absolute paths.

Costs are the CLI's client-side estimates. Model: Haiku. Budget: $0.40 per cell.

## What the runs show

| Run | Arm | Passed | Pass rate [95% CI] | Hidden checks | Mean cost/cell | Cost/pass |
|---|---|---|---|---|---|---|
| pilot | single | 10/17 | 59% [36-78%] | 90% | $0.091 | $0.154 |
| pilot | firm | 8/17 | 47% [26-69%] | 83% | $0.194 | $0.413 |
| rerun1 | firm | 9/17 | 53% [31-74%] | 87% | $0.206 | $0.389 |
| final3 | single | 32/51 | 63% [49-75%] | 92% | $0.093 | $0.147 |
| final3 | firm | 35/51 | 69% [55-80%] | 94% | $0.220 | $0.320 |

- The firm went from losing to a single agent (47% against 59%) to level with it (69% against 63%).
  The intervals overlap: **this does not show the firm is better.** By task, the firm did better
  on 4, worse on 3 and the same on 10.
- The firm costs 2.4 times as much per cell and 2.2 times as much per passing cell. 40% of its
  spend is the boss's draft.
- 12 of the 36 firm cells that passed every one of the boss's checks failed a hidden check: the
  boss's checks do not cover the idea.
- The boss wrote 20 wrong checks out of 397 (the reference solution fails them), in 16 of 51 drafts.

## Disputes and firings (final3, firm arm)

- Workers disputed 10 checks. **All 10 were wrong**: the reference solution fails each of them.
  With rerun1, that is 13 of 13.
- The rule fired 4 workers. **All 4 were in cells with a wrong check the worker had not disputed**,
  and in 3 of those cells the product passed every hidden check. Those firings were caused by the
  boss's wrong checks, not by the workers.
- Nothing here is a large sample. It is why a check auditor is being built and why it will be
  scored against the reference before it is switched on.

## Draft quality (scored without worker runs)

`python -m boss.bench.drafts --score-existing` on the boss's drafts from two runs:

| Drafts from | Wrong checks | Drafts with a wrong check | Known-wrong implementations caught |
|---|---|---|---|
| pilot | 10 of 134 (7%) | 5 of 17 | 38 of 65 (58%) |
| rerun1 | 4 of 134 (3%) | 4 of 17 | 39 of 65 (60%) |

Recall is biased down: 16 of the 23 harvested wrong implementations were built against these
same drafts. See `bench/METHOD.md`.
