# 2026-09-30-pilot

First run. 17 tasks, both arms, 1 run each. Firm: one slice, worker not shown the idea.

Cells: 34. Raw ledgers, logs and products are kept on the machine that ran them, not in the repository.

Task set: 7a212cdcc5f4f466, 8c04e5da92cfd00b | Model: haiku | Budget per cell: $0.4000
WARNING: results mix task sets, models or budgets; do not compare.

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | 17 | 17 | 10 | 59% [36-78%] | 90% | $0.0909 | $0.1545 | 0% | 0 | 0 |
| firm | 17 | 17 | 8 | 47% [26-69%] | 83% | $0.1945 | $0.4133 | 51% | 0 | 0 |

Visible vs hidden: 11 of 17 firm cells passed every visible check; 5 of those failed a hidden check.

| task | single | firm |
| --- | --- | --- |
| bigdecimal | 1/1 | 0/1 |
| calc | 0/1 | 0/1 |
| csvline | 1/1 | 1/1 |
| duration | 0/1 | 0/1 |
| intervals | 1/1 | 1/1 |
| jsonpointer | 0/1 | 0/1 |
| justify | 1/1 | 1/1 |
| linediff | 1/1 | 1/1 |
| lrucache | 1/1 | 1/1 |
| matrixops | 1/1 | 1/1 |
| roman | 1/1 | 1/1 |
| semver | 0/1 | 0/1 |
| slugify | 0/1 | 0/1 |
| tokenbucket | 0/1 | 0/1 |
| toposort | 0/1 | 0/1 |
| wildcard | 1/1 | 0/1 |
| workdays | 1/1 | 1/1 |

Pass rates from fewer than ~60 paired tasks cannot show a 20-point difference; treat them as descriptive.
