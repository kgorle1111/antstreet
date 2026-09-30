# 2026-09-30-rerun1

Firm arm only, 1 run each, at b9513f5: idea in the brief, fixed reserve, disputed checks. `--slice 0.20`.

Cells: 17. Raw ledgers, logs and products are kept on the machine that ran them, not in the repository.

Task set: 7a212cdcc5f4f466 | Model: haiku | Budget per cell: $0.4000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| firm | 17 | 17 | 9 | 53% [31-74%] | 87% | $0.2058 | $0.3888 | 44% | 0 | 0 |

Visible vs hidden: 12 of 17 firm cells passed every visible check; 6 of those failed a hidden check.

| task | firm |
| --- | --- |
| bigdecimal | 0/1 |
| calc | 0/1 |
| csvline | 0/1 |
| duration | 0/1 |
| intervals | 1/1 |
| jsonpointer | 0/1 |
| justify | 1/1 |
| linediff | 1/1 |
| lrucache | 1/1 |
| matrixops | 1/1 |
| roman | 1/1 |
| semver | 0/1 |
| slugify | 1/1 |
| tokenbucket | 0/1 |
| toposort | 0/1 |
| wildcard | 1/1 |
| workdays | 1/1 |

Pass rates from fewer than ~60 paired tasks cannot show a 20-point difference; treat them as descriptive.
