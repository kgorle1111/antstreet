# Single-call drafts, thinking off (0 tokens)

The same prompt and tasks with `--boss-thinking 0` (`bench/results/raw/drafts-single-think0`). No model call was made to produce this page.

Task set: c130282a6eec5fe8 | Prompt: term_sheet_v1.md | Boss model: haiku | Thinking tokens: 0

| drafts | invalid | failed | checks/draft | mean cost/draft | unknown-cost calls |
| --- | --- | --- | --- | --- | --- |
| 16 | 0 | 1 | 8.0 | $0.0322 | 0 |

Precision: a correct implementation (the reference) must pass every check.
- wrong checks: 7 of 128 failed on the reference (precision 95%)
- drafts with a wrong check: 5/16 = 31% [14-56%]

Recall: an incorrect implementation (a mutant) must fail a sound check.
- mutants killed by sound checks: 36 of 61 (recall 59%)
- mutants failing only wrong checks, not counted: 10
- drafts that kill every mutant: 5/16 = 31% [14-56%]

| task | drafts | wrong/checks | killed/mutants | kill all | excluded |
| --- | --- | --- | --- | --- | --- |
| bigdecimal | 1 | 0/8 | 2/4 | 0/1 | 0 |
| calc | 1 | 0/8 | 1/3 | 0/1 | 0 |
| csvline | 1 | 0/8 | 3/3 | 1/1 | 0 |
| duration | 1 | 2/8 | 1/3 | 0/1 | 0 |
| intervals | 1 | 0/8 | 4/4 | 1/1 | 0 |
| jsonpointer | 1 | 1/8 | 0/3 | 0/1 | 0 |
| justify | 1 | 2/8 | 2/4 | 0/1 | 0 |
| linediff | 1 | 0/8 | 2/4 | 0/1 | 0 |
| lrucache | 1 | 1/8 | 2/4 | 0/1 | 0 |
| matrixops | 1 | 0/8 | 4/4 | 1/1 | 0 |
| roman | 1 | 0/8 | 4/4 | 1/1 | 0 |
| semver | 1 | 0/8 | 2/5 | 0/1 | 0 |
| slugify | 1 | 0/8 | 4/4 | 1/1 | 0 |
| tokenbucket | 1 | 0/8 | 2/5 | 0/1 | 0 |
| toposort | 1 | 0/8 | 0/3 | 0/1 | 0 |
| wildcard | 1 | 1/8 | 3/4 | 0/1 | 0 |
| workdays | 0 | 0/0 | 0/0 | 0/0 | 1 |

Drafts that were invalid or failed are excluded from every rate above.
