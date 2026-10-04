# Benchmark results

One folder per run: `table.md` (what `python -m boss.bench.table` printed) and `results.jsonl`
(every cell's `result.json`, one per line); the later folders hold a write-up (`README.md`), and
`2026-10-03-blind35` also a `table.md`. Raw ledgers, worker logs and products stay on the
machine that ran them (`bench/results/raw/`, git-ignored): they hold absolute paths.

Costs are the CLI's client-side estimates. Model: Haiku. Budget: $0.40 per cell.

## What the runs show

| Run | Arm | Passed | Pass rate [95% CI] | Hidden checks | Mean cost/cell | Cost/pass |
|---|---|---|---|---|---|---|
| pilot | single | 10/17 | 59% [36-78%] | 90% | $0.091 | $0.154 |
| pilot | firm | 8/17 | 47% [26-69%] | 83% | $0.194 | $0.413 |
| rerun1 | firm | 9/17 | 53% [31-74%] | 87% | $0.206 | $0.389 |
| final3 (unblinded) | single | 32/51 | 63% [49-75%] | 92% | $0.093 | $0.147 |
| final3 (unblinded) | firm | 35/51 | 69% [55-80%] | 94% | $0.220 | $0.320 |
| blind35 | single | 62/105 | 59% [49-68%] | 92% | $0.088 | $0.150 |
| blind35 | firm | 64/105 | 61% [51-70%] | 92% | $0.215 | $0.353 |

- **`blind35` is the run to read.** Both arms got the same instruction and neither was told about
  hidden checks. 35 tasks, 3 runs each: the firm delivered 64 of 105, the single agent 62 of 105.
  Paired by task the difference is +0.019 [-0.076, +0.124]: **no delivery benefit is shown.** By task
  the firm did better on 6, worse on 5 and the same on 24. See `2026-10-03-blind35/README.md`.
- `final3` is labelled unblinded: its single arm was told "Your work will be judged by checks you
  cannot see" and the firm's workers got no such sentence, and its two arms ran on different commits.
  The same holds for `new18` (see its note). Its 69% against 63% is not a fair comparison. `pilot`
  and `rerun1` also ran before the arms' prompts were made equal (commit `6b6111a`); whether they
  had the same imbalance was not checked.
- In `blind35` the firm costs 2.4 times as much per cell ($0.215 against $0.088) and 2.4 times as
  much per passing cell. Paired by task, cost per delivery is +$0.127 [+0.109, +0.145] and time
  +142 s [+122, +165] higher for the firm: both intervals lie wholly on the costly side. 43% of the
  firm's spend is the boss's draft (`final3`: 40%).
- 33 of the 87 firm cells that passed every one of the boss's checks failed a hidden check in
  `blind35` (`final3`: 12 of 36): the boss's checks do not cover the idea.
- The boss wrote 28 wrong checks out of 813 in `blind35` (the reference solution fails them), in 20
  of 105 drafts (`final3`: 20 of 397, in 16 of 51).

## Disputes and firings (final3, unblinded, firm arm)

- Workers disputed 10 checks. **All 10 were wrong**: the reference solution fails each of them.
  With rerun1, that is 13 of 13.
- The rule fired 4 workers. **All 4 were in cells with a wrong check the worker had not disputed**,
  and the product in each of those 3 cells passed every hidden check. Those firings were caused by the
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

## Drafts and auditor (2026-09-30-drafts-and-audit)

Scored from saved cells; no worker ran and the write-up made no model call. Task set `c130282a6eec5fe8`,
Haiku. See `2026-09-30-drafts-and-audit/README.md` for the method, the refusal reasons and the spend.

| Tool | Cells | Result | Mean cost |
|---|---|---|---|
| One-call draft, thinking default | 16 scored of 17 | 2 of 124 checks wrong; 40 of 61 mutants killed | $0.101/draft |
| One-call draft, thinking off | 16 scored of 17 | 7 of 128 checks wrong; 36 of 61 mutants killed | $0.032/draft |
| Staged draft | 4 scored, 12 invalid, 1 failed | 29 of the 32 refusals are a quote the gate would not accept | $0.157/call |
| Check auditor | 27 audited, 7 rejected, 0 failed | precision 9/9 [70-100%], recall 9/12 [47-91%] | $0.081/call |

- Thinking off cuts the draft cost 3.1 times; the wrong-check intervals overlap ([3-36%] and [14-56%] of drafts).
- The staged draft is not usable today: 4 of 17 tasks get a draft.
- The auditor stays advisory. 7 of its 34 cells ended at the plan's usage limit and were not retried.
- Measured spend of every saved cell: $10.62 (119 cells, 1 of unknown cost).
