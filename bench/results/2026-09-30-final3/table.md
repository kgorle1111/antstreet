# 2026-09-30-final3

Both arms, 3 runs each. Single arm at dca56c1, firm arm at a886934 (after the review fixes). `--slice 0.20`.

Cells: 102. Raw ledgers, logs and products are kept on the machine that ran them, not in the repository.

Task set: c130282a6eec5fe8 | Model: haiku | Budget per cell: $0.4000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | 51 | 17 | 32 | 63% [49-75%] | 92% | $0.0925 | $0.1474 | 0% | 0 | 0 |
| firm | 51 | 17 | 35 | 69% [55-80%] | 94% | $0.2197 | $0.3202 | 40% | 0 | 0 |

Visible vs hidden: 36 of 51 firm cells passed every visible check; 12 of those failed a hidden check.
Wrong boss checks: 20 of 397 checks failed on the reference solution, in 16 drafts.

| task | single | firm |
| --- | --- | --- |
| bigdecimal | 1/3 | 1/3 |
| calc | 1/3 | 0/3 |
| csvline | 3/3 | 3/3 |
| duration | 1/3 | 0/3 |
| intervals | 3/3 | 3/3 |
| jsonpointer | 1/3 | 1/3 |
| justify | 3/3 | 3/3 |
| linediff | 3/3 | 3/3 |
| lrucache | 3/3 | 3/3 |
| matrixops | 2/3 | 3/3 |
| roman | 3/3 | 3/3 |
| semver | 1/3 | 1/3 |
| slugify | 1/3 | 3/3 |
| tokenbucket | 0/3 | 1/3 |
| toposort | 0/3 | 2/3 |
| wildcard | 3/3 | 2/3 |
| workdays | 3/3 | 3/3 |

Pass rates from fewer than ~60 paired tasks cannot show a 20-point difference; treat them as descriptive.
