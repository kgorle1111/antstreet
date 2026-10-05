# 2026-10-03-blind35

Both arms, 3 runs each, 35 tasks, both arms given the same blinded instruction (`solo_v2.md`,
`builder_v4.md`). One frozen copy of commit `e203f65`, `--slice 0.20`.

Cells: 210. Raw ledgers, logs and products are kept on the machine that ran them, not in the repository.

Task set: 0a83fc97a753b08c | Model: haiku | Budget per cell: $0.4000

| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell | cost/pass | boss share | unknown-cost events | infrastructure excluded | median time/cell | tasks passed every run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | 105 | 35 | 62 | 59% [49-68%] | 92% | $0.0883 | $0.1496 | 0% | 0 | 0 | 1m25s | 18/35 |
| firm | 105 | 35 | 64 | 61% [51-70%] | 92% | $0.2149 | $0.3525 | 43% | 0 | 0 | 3m34s | 16/35 |

Visible vs hidden: 87 of 105 firm cells passed every visible check; 33 of those failed a hidden check.
Wrong boss checks: 28 of 813 checks failed on the reference solution, in 20 drafts.

| task | single | firm |
| --- | --- | --- |
| bigdecimal | 0/3 | 1/3 |
| bytesize | 0/3 | 0/3 |
| calc | 0/3 | 0/3 |
| cronnext | 0/3 | 0/3 |
| csvline | 3/3 | 3/3 |
| dedentblock | 3/3 | 3/3 |
| duration | 0/3 | 0/3 |
| exprtokens | 1/3 | 1/3 |
| fracmath | 3/3 | 3/3 |
| iniparse | 3/3 | 3/3 |
| intervals | 3/3 | 3/3 |
| isoweek | 0/3 | 0/3 |
| jsonpointer | 1/3 | 1/3 |
| justify | 3/3 | 3/3 |
| linediff | 3/3 | 3/3 |
| lrucache | 3/3 | 2/3 |
| luhn | 2/3 | 0/3 |
| matrixops | 2/3 | 3/3 |
| mdheadings | 0/3 | 2/3 |
| minheap | 3/3 | 2/3 |
| moneysplit | 3/3 | 3/3 |
| prefixtrie | 1/3 | 1/3 |
| rangesum | 3/3 | 3/3 |
| ringbuffer | 3/3 | 3/3 |
| roman | 3/3 | 3/3 |
| semver | 0/3 | 0/3 |
| shortestpath | 3/3 | 3/3 |
| slugify | 0/3 | 3/3 |
| tokenbucket | 0/3 | 0/3 |
| toposort | 0/3 | 1/3 |
| unionfind | 3/3 | 3/3 |
| urlquery | 3/3 | 1/3 |
| wildcard | 1/3 | 2/3 |
| wordwrap | 3/3 | 3/3 |
| workdays | 3/3 | 2/3 |

Pass rates from fewer than ~60 paired tasks cannot show a 20-point difference; treat them as descriptive.
