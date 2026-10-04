# 2026-10-03-spec-p1

P1, the draft-only paid evaluation of `term_sheet_v3.md`, against the criteria committed before any
paid call (`bench/spec_truth/P1_CRITERIA.md`, commit `5bdb3c6`). The prompt and the code that uses it
were not changed after that commit. This note holds the numbers; reading them comes after.

Commands (from a checkout; `bench/results/raw` is git-ignored):

```
python -m boss.bench.drafts --out bench/results/raw/spec-p1/v3 --prompt term_sheet_v3.md --max-spend 2.60 --only <the 17 original tasks>
python -m boss.bench.spec_p1 score --drafts bench/results/raw/spec-p1/v3 --raw <saved cells>
```

Haiku, the CLI's default thinking, one draft per task. The full table is `report.md`.

## Result against the five criteria

| | Criterion | Result | Baseline | |
|---|---|---|---|---|
| (a) | kill rate on the failing products >= 45% | 12/34 = 35% [21%-52%] | 28/89 = 31% | not met |
| (b) | kill rate on the non-ASCII subset >= 40% | 5/16 = 31% [14%-56%] | 3/38 = 8% | not met |
| (c) | wrong checks <= 5% of the checks | 11/179 = 6.1% | 2/124 = 1.6% | not met |
| (d) | at most 2 of 17 drafts invalid or failed | 1 of 17 (`wildcard`) | 13 of 17 (staged) | met |
| (e) | mean checks per usable draft <= 12 | 11.2 | 7.8 | met |

All five met: no. **P1 does not clear the bar for P2.** P2 was not run.

- 34 pairs, not 35: the invalid `wildcard` draft has one failing product, which contributes no pair.
- `wildcard` was refused by the gate for "R12 is cited by c12 and untested": the boss cited a rule
  and also listed it as untested. The call was paid for ($0.1754).

## Spend

The 17 drafts cost **$2.3187** as the cells recorded it (CLI estimates; none unreported), within the
pass cap of $2.60 and the $4.00 total. Per draft $0.077 to $0.236, mean $0.136, against $0.101 for a
one-call draft in an earlier run.
