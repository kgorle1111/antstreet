# P1: the rules prompt, draft only

Criteria: `bench/spec_truth/P1_CRITERIA.md`, committed before any paid call.

| | Criterion | Result | Baseline | |
|---|---|---|---|---|
| (a) | kill rate on the failing products >= 45% | 12/34 = 35% [21%-52%] | 28/89 = 31% [23%-42%] | NOT met |
| (b) | kill rate on the non-ASCII subset >= 40% | 5/16 = 31% [14%-56%] | 3/38 = 8% [3%-21%] | NOT met |
| (c) | wrong checks <= 5% of checks | 11/179 = 6.1% | 2/124 = 1.6% | NOT met |
| (d) | invalid or failed drafts <= 2 of 17 | 1 of 17 | 13 of 17 (staged) | met |
| (e) | mean checks per usable draft <= 12 | 11.2 | 7.8 | met |

All five met: **False**. P2 is not run by this step.

Spend of the drafts, as the cells recorded it: $2.3187.

## Per draft

| task | status | checks | wrong | mutants killed | rules | uncovered | waived | anchored | unanchored | anchor-missing | cites/check | killed products | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bigdecimal | scored | 12 | 0 | 2/4 | 17 | 0 | 0 | 2 | 14 | 1 | 2.3 | 2/4 | $0.1872 |
| calc | scored | 12 | 0 | 1/3 | 23 | 1 | 0 | 7 | 12 | 3 | 1.8 | 4/5 | $0.0846 |
| csvline | scored | 10 | 0 | 3/3 | 26 | 1 | 2 | 1 | 22 | 0 | 2.3 | 0/0 | $0.1491 |
| duration | scored | 12 | 1 | 2/3 | 22 | 0 | 0 | 3 | 18 | 1 | 2.2 | 2/5 | $0.1740 |
| intervals | scored | 12 | 0 | 3/4 | 18 | 0 | 0 | 1 | 17 | 0 | 2.2 | 0/0 | $0.1129 |
| jsonpointer | scored | 12 | 2 | 1/3 | 12 | 0 | 0 | 5 | 5 | 2 | 1.5 | 0/4 | $0.1209 |
| justify | scored | 10 | 0 | 4/4 | 14 | 0 | 0 | 2 | 12 | 0 | 1.8 | 0/0 | $0.0768 |
| linediff | scored | 11 | 0 | 4/4 | 20 | 0 | 1 | 2 | 17 | 0 | 1.7 | 0/0 | $0.2357 |
| lrucache | scored | 11 | 1 | 4/4 | 24 | 0 | 1 | 2 | 21 | 0 | 2.6 | 0/0 | $0.2031 |
| matrixops | scored | 12 | 1 | 4/4 | 23 | 0 | 0 | 1 | 22 | 0 | 2.2 | 1/1 | $0.1028 |
| roman | scored | 8 | 0 | 4/4 | 11 | 0 | 0 | 2 | 8 | 1 | 1.8 | 0/0 | $0.0884 |
| semver | scored | 11 | 0 | 3/5 | 13 | 0 | 0 | 3 | 6 | 4 | 2.0 | 0/4 | $0.1469 |
| slugify | scored | 11 | 2 | 4/4 | 10 | 0 | 0 | 3 | 7 | 0 | 1.3 | 2/2 | $0.0835 |
| tokenbucket | scored | 11 | 1 | 1/5 | 17 | 3 | 0 | 3 | 10 | 1 | 1.5 | 0/5 | $0.1473 |
| toposort | scored | 12 | 0 | 3/3 | 20 | 1 | 0 | 4 | 15 | 0 | 1.8 | 1/4 | $0.1074 |
| wildcard | invalid | - | - | - | - | - | - | - | - | - | - | - | $0.1754 |
| workdays | scored | 12 | 3 | 3/4 | 16 | 0 | 0 | 1 | 15 | 0 | 1.8 | 0/0 | $0.1226 |

## Drafts that were not usable

- wildcard: invalid (completed): draft term sheet is invalid: R12 is cited by c12 and untested
