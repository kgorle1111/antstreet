# Staged drafts (product manager, system designer, tester): the re-run

`--prompt staged` (`bench/results/raw/drafts-staged`). 15 of the 17 cells were re-run on 2026-09-30 after the quote-matching gate fix; roman and slugify are the first attempt's cells. No model call was made to produce this page.

Task set: c130282a6eec5fe8 | Prompt: staged | Boss model: haiku | Thinking tokens: default

| drafts | invalid | failed | checks/draft | mean cost/draft | unknown-cost calls |
| --- | --- | --- | --- | --- | --- |
| 4 | 12 | 1 | 12.0 | $0.1570 | 1 |

Precision: a correct implementation (the reference) must pass every check.
- wrong checks: 1 of 48 failed on the reference (precision 98%)
- drafts with a wrong check: 1/4 = 25% [5-70%]

Recall: an incorrect implementation (a mutant) must fail a sound check.
- mutants killed by sound checks: 13 of 16 (recall 81%)
- mutants failing only wrong checks, not counted: 0
- drafts that kill every mutant: 2/4 = 50% [15-85%]

| task | drafts | wrong/checks | killed/mutants | kill all | excluded |
| --- | --- | --- | --- | --- | --- |
| bigdecimal | 1 | 0/16 | 2/4 | 0/1 | 0 |
| calc | 0 | 0/0 | 0/0 | 0/0 | 1 |
| csvline | 0 | 0/0 | 0/0 | 0/0 | 1 |
| duration | 0 | 0/0 | 0/0 | 0/0 | 1 |
| intervals | 0 | 0/0 | 0/0 | 0/0 | 1 |
| jsonpointer | 0 | 0/0 | 0/0 | 0/0 | 1 |
| justify | 1 | 0/16 | 4/4 | 1/1 | 0 |
| linediff | 0 | 0/0 | 0/0 | 0/0 | 1 |
| lrucache | 0 | 0/0 | 0/0 | 0/0 | 1 |
| matrixops | 0 | 0/0 | 0/0 | 0/0 | 1 |
| roman | 1 | 0/4 | 4/4 | 1/1 | 0 |
| semver | 0 | 0/0 | 0/0 | 0/0 | 1 |
| slugify | 1 | 1/12 | 3/4 | 0/1 | 0 |
| tokenbucket | 0 | 0/0 | 0/0 | 0/0 | 1 |
| toposort | 0 | 0/0 | 0/0 | 0/0 | 1 |
| wildcard | 0 | 0/0 | 0/0 | 0/0 | 1 |
| workdays | 0 | 0/0 | 0/0 | 0/0 | 1 |

Drafts that were invalid or failed are excluded from every rate above.
