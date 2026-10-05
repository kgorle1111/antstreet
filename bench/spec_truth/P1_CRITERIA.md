# P1: the draft-only paid evaluation of the rules prompt, criteria fixed before it is run

Written and committed before any paid call of P1. `src/boss/prompts/term_sheet_v3.md` and the
code that uses it are frozen at the commit that precedes this file; a change after the numbers are
seen is a new prompt version and is reported as such, not as a pass of these criteria.

P1 is the pre-registered step between the offline evaluation (`CRITERIA.md`) and P2, a 51-cell
firm run. **P2 is not run here.**

## What is run

- **Drafts**: the 17 original tasks, one draft each, Haiku, the CLI's default thinking, with
  `python -m boss.bench.drafts --prompt term_sheet_v3.md`. The boss gets the idea and its rules.
- **Scored on**: the 35 saved `final3` products that failed a hidden check (19 from the single arm,
  16 from the firm arm). A draft kills a product when one of its sound checks (one the task's
  reference solution passes) fails on it. Every draft is run against every failing product of its
  task: 35 pairs when all 17 drafts are usable. None of these products was built against a v3
  draft.
- **Non-ASCII subset**: the failing products whose failing hidden check is `bigdecimal
  invalid_input`, `calc malformed_tokens`, `duration parse_decimals`, `jsonpointer list_indexes` or
  `set_value_errors`, or `semver parse_invalid_input`: 16 products (10 firm, 6 single).
- **Baseline** (`2026-10-02-why-the-firm-loses`, section 9): the boss's earlier drafts, each run
  against the other drafts' failing products: 28 of 89 pairs killed (31%), and 3 of 38 (8%) on the
  non-ASCII subset. Wrong checks 2 of 124 (1.6%); the one-call draft averaged 7.8 checks; the staged
  draft was refused 13 times in 17.

## Criteria (all five must hold to go on to P2)

| | Criterion | Baseline |
|---|---|---|
| (a) | Kill rate on the failing products is at least 45% | 31% |
| (b) | Kill rate on the non-ASCII subset is at least 40% | 8% |
| (c) | Wrong checks (the reference solution fails them) are at most 5% of the checks of the usable drafts | 1.6% |
| (d) | At most 2 of the 17 drafts are invalid or failed (refused by the gate, capped, timed out) | staged: 13 of 17 |
| (e) | The mean number of checks per usable draft is at most 12 | 7.8 |

A task whose draft is invalid or failed contributes no pairs to (a) and (b) and counts in (d).
The point estimates decide, as written; intervals are reported beside them (Wilson, over pairs,
which are not independent: one draft per task, products of one task share it).

## Spend

- Hard cap **$4.00** for all of P1, measured from the cost each call reports (the CLI's estimate;
  a call that reports none counts at its $0.25 cap). Every pass stops before a call that could take
  the measured spend past the cap.
- Order: (1) the 17 drafts with `term_sheet_v3.md`, at most $2.60; (2) the spec mapper over the
  usable drafts, with what remains of the cap; (3) a second set of 17 drafts with the boss's
  thinking off, only if at least $0.60 is left after (2). Passes (2) and (3) have no criterion.
- Estimate before running: pass (1) 17 x about $0.10 = $1.7 (measured: $0.101 a draft with default
  thinking, $0.032 with it off, `2026-09-30-drafts-and-audit`); pass (2) 17 x about $0.08 = $1.4.

## Reported, not gated

Mutants written for the tasks and harvested mutants (the earlier drafts killed 66%); the coverage of each
draft by `boss.spec.verify` (rules uncovered, waived, anchored, anchor-missing; the headline); rules
cited per check; cost per draft; the mapper's unconfirmed citations against the verifier's
`anchor_missing`; and what each invalid draft was refused for.

## Priors, recorded before running

All five criteria hold: 45%. Criterion (a) alone: 60%. The failure I expect most: the boss cites a rule
and writes a check that merely names what the rule mentions.

## Limits stated in advance

- One draft per task: 35 pairs is a small sample, and the baseline's 89 pairs came from other drafts.
- The 35 products were built by Haiku against v1 drafts or no drafts; products from a firm that used
  v3 drafts would differ.
- The benchmark ideas are strict and numbered; a real request is vaguer.
- The held-out 18 tasks are labelled apart and are not part of P1.
