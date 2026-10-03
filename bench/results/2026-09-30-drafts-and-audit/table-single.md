# Single-call drafts, thinking at the CLI default

The boss's one-call term sheet, 17 tasks, 1 draft each. Printed by `python -m boss.bench.drafts` from the saved cells (`bench/results/raw/drafts-single`). No model call was made to produce this page.

Task set: c130282a6eec5fe8 | Prompt: term_sheet_v1.md | Boss model: haiku | Thinking tokens: default

| drafts | invalid | failed | checks/draft | mean cost/draft | unknown-cost calls |
| --- | --- | --- | --- | --- | --- |
| 16 | 1 | 0 | 7.8 | $0.1009 | 0 |

Precision: a correct implementation (the reference) must pass every check.
- wrong checks: 2 of 124 failed on the reference (precision 98%)
- drafts with a wrong check: 2/16 = 12% [3-36%]

Recall: an incorrect implementation (a mutant) must fail a sound check.
- mutants killed by sound checks: 40 of 61 (recall 66%)
- mutants failing only wrong checks, not counted: 2
- drafts that kill every mutant: 5/16 = 31% [14-56%]

| task | drafts | wrong/checks | killed/mutants | kill all | excluded |
| --- | --- | --- | --- | --- | --- |
| bigdecimal | 1 | 0/8 | 2/4 | 0/1 | 0 |
| calc | 1 | 0/8 | 1/3 | 0/1 | 0 |
| csvline | 1 | 1/8 | 3/3 | 1/1 | 0 |
| duration | 1 | 1/6 | 1/3 | 0/1 | 0 |
| intervals | 1 | 0/7 | 4/4 | 1/1 | 0 |
| jsonpointer | 1 | 0/8 | 2/3 | 0/1 | 0 |
| justify | 1 | 0/8 | 4/4 | 1/1 | 0 |
| linediff | 1 | 0/8 | 3/4 | 0/1 | 0 |
| lrucache | 1 | 0/8 | 2/4 | 0/1 | 0 |
| matrixops | 1 | 0/7 | 3/4 | 0/1 | 0 |
| roman | 1 | 0/8 | 4/4 | 1/1 | 0 |
| semver | 1 | 0/8 | 2/5 | 0/1 | 0 |
| slugify | 1 | 0/8 | 3/4 | 0/1 | 0 |
| tokenbucket | 1 | 0/8 | 1/5 | 0/1 | 0 |
| toposort | 1 | 0/8 | 1/3 | 0/1 | 0 |
| wildcard | 0 | 0/0 | 0/0 | 0/0 | 1 |
| workdays | 1 | 0/8 | 4/4 | 1/1 | 0 |

Drafts that were invalid or failed are excluded from every rate above.
