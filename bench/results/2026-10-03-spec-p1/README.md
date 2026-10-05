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

## The mapper pass: not run

All 16 calls of the paid mapper pass ended as `usage_limit` at no cost, then and again on a retry
afterwards: the plan's limit, not the mapper. Nothing was kept (the first 16 were moved aside as
infrastructure and the pass now stops on such an outcome instead of saving it). Spend so far is the
$2.3187 above; $1.68 of the $4.00 cap is unused. Rerun when the limit has reset:

```
python -m boss.bench.spec_p1 map --drafts bench/results/raw/spec-p1/v3 --max-spend 1.60
python -m boss.bench.spec_p1 mapper-report --drafts bench/results/raw/spec-p1/v3
```

The thinking-off pass was not run (it needed at least $0.60 left after the mapper pass).

## Reading the numbers (after the numbers above were committed)

- **P1 did not clear the bar, so P2 as designed is not run.** (a) and (b) rose over their baselines
  in point estimate (35% against 31%; 31% against 8%) but not to the line, and with 34 and 16 pairs the
  intervals ([21-52%], [14-56%]) cannot separate the result from the baseline or from the line.
  (c) went the wrong way: 6.1% wrong checks against 1.6% (default thinking) and 5.5% (thinking off) in
  earlier drafts, in drafts that are longer.
- **The prompt did not make the boss write the omitted tests.** Of the five tasks whose idea names
  non-ASCII input, only `calc` and `semver` drafts contain a non-ASCII character in any check;
  `bigdecimal`, `duration` and `jsonpointer` drafts contain none, though the prompt tells the boss to
  try "unusual characters" a rule mentions. The 5 non-ASCII kills are `calc` 4 and `duration` 1. The
  boss still cites a rule without testing what it names.
- **(e) cannot fail.** The ceiling is 12 checks and 8 of the 16 usable drafts have 12: the mean cannot
  pass 12. The criterion was written before that was seen; it did not bind.
- **Post-hoc, claim level, not a criterion** (computed after the numbers above; free): reading each
  draft's own citations with `boss.spec.verify`, a rule that the failing product's failing hidden
  check tests is shown to the investor as uncovered or anchor-missing for 16 of the 34 products, and
  for **16 of 16 products in the non-ASCII subset**. The 18 products with no flag fail on rules that
  name no literal, size, type or exception (`compare`, `"- 1s"`, generator values, ragged rows,
  `max_length` cut points), as in the offline evaluation. The flags per draft are few: at most 4
  rules (uncovered plus anchor-missing) in any draft. So the layer's measured value is in what the
  investor is shown, not in the boss's draft; a benchmark that auto-approves (P2 as designed) cannot
  measure it, and a human is who the view is for.
- **Cost.** $0.136 a draft (range $0.077 to $0.236), 35% over the earlier one-call draft: more checks
  and a longer prompt.
- **Known splitter v1 limit** (reported by the held-out labeller): some behaviour sentences are marked
  as context and can never be flagged. B91.

## Options that need a decision, not made here

1. Do not run P2. Keep `--spec` off by default (as it is) and say so in the docs (D41).
2. Test the one thing P1 points at, offline and for about $1.5: a single repair call per draft that
   still has uncovered or anchor-missing rules ("these rules have no test that contains what they
   name"), then P1's scoring again. It is the "auto repair call" the design left out until P1 said
   more than 20% of drafts leave rules uncovered: here 9 of 16 usable drafts have at least one.
   Confidence that it lifts (a) to 45%: about 45%; that it keeps (c) under 5%: about 50% (more checks).
3. Validate the verifier's flags on the 18 held-out tasks (free, `--population held-out`) before
   anything else is built on them.
