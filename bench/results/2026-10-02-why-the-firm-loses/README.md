# 2026-10-02-why-the-firm-loses

Why the firm arm passes no more cells than one agent, at 2.4 times the cost and 2.8 times the time.
Written from saved cells only: no model call, no spend. Every number below was counted from the
ledgers, the term sheets and checks the boss drafted, the products, and the hidden checks re-run on
those products. The raw folders are under `bench/results/raw/` (git-ignored): `final3` (17 tasks x 3
runs x 2 arms), `heldout3` (the firm arm again, with `--held-out 3`) and `nl2repo-decouple`. Model:
Haiku for the boss and every worker, $0.40 a cell, `--slice 0.20`. Tools used: `python -m
boss.bench.table`, `python -m boss.bench.replay`, the ledgers read directly, and `boss.bench.score`
to find which boss checks the reference solution fails.

## Answer

1. **The firm and the single agent fail on the same kind of defect: a behaviour the idea states in
   one sentence and nothing checked.** 15 of the firm's 16 failed cells are that. 10 of the 15 are one
   sentence, "non-ASCII digits are not valid", which appears in 5 of the 17 ideas: none of the 15 boss
   drafts for those 5 tasks has a check for it. The single agent misses it in 6 of 15 cells, the firm in
   10 of 15.
2. **The firm's loop helps only where the boss happened to write the check.** Where a boss check
   covered a behaviour the single agent got wrong, the firm passed it in 10 of 10 cells. Net by task: 4
   better (slugify, toposort, matrixops, tokenbucket), 3 worse (calc, duration, wildcard), 10 the same.
3. **The difference between arms is smaller than the difference between two runs of the firm.** Single
   32/51, firm 35/51 (Fisher p = 0.68). The same firm arm run again passed 28/51 (p = 0.22 against
   35/51), on later code and the same prompts.
4. **Cost.** The boss's call is 69% of the firm's extra $0.127 a cell, and later slices 33% (the first
   slice costs 3% less than the single agent's). 17 of the 26 later slices ($1.65, 15% of all firm
   spend) were funded while every failing check was one the reference solution also fails.
5. **Held-out checks did not predict hidden failures.** In 40 visible-pass cells, 17 failed a hidden
   check; the held-out checks caught 0 of the 17. The one held-out failure was a wrong held-out check.

## 1. Pass counts

Cells that passed every hidden check, out of 3 runs. `held-out run` is the second firm run
(`heldout3`), shown because it measures run-to-run noise.

| task | single | firm | firm, held-out run | task | single | firm | firm, held-out run |
|---|---|---|---|---|---|---|---|
| bigdecimal | 1 | 1 | 1 | roman | 3 | 3 | 3 |
| calc | 1 | 0 | 0 | semver | 1 | 1 | 0 |
| csvline | 3 | 3 | 2 | slugify | 1 | 3 | 2 |
| duration | 1 | 0 | 1 | tokenbucket | 0 | 1 | 0 |
| intervals | 3 | 3 | 3 | toposort | 0 | 2 | 0 |
| jsonpointer | 1 | 1 | 2 | wildcard | 3 | 2 | 1 |
| justify | 3 | 3 | 2 | workdays | 3 | 3 | 2 |
| linediff | 3 | 3 | 3 | **total** | **32** | **35** | **28** |
| lrucache | 3 | 3 | 3 | | | | |
| matrixops | 2 | 3 | 3 | | | | |

- Pass rates: single 63% [49-75], firm 69% [55-80], firm again 55% [41-68].
- The two firm runs share the prompts (`builder_v3.md`, `term_sheet_v1.md`); `briefs.py` and `rule.py`
  changed between them (refusal wording, a replacement worker inherits disputes), and the second adds the
  examiner's call. 10 of the 16 hidden checks the firm failed in the first run failed again in the second.

## 2. Why the firm's 16 failed cells failed

Each cell is classed by the cause of its hidden failure, found by re-running the failing hidden check
on the saved product and reading the boss's checks for that behaviour.

| class | cells | what it is |
|---|---|---|
| (a) The boss's checks omit a behaviour the idea states; the worker stopped when its checks passed | 15 | the table below |
| (b) A wrong boss check made the worker build the wrong thing | 1 | wildcard run 1; also (c) and (e) |
| (c) Budget or slice cap ran out | 0 alone | wildcard run 1: the last slice was capped with visible 6/8 |
| (d) Merge or assembly | 0 | one task, one file; the product is the worker's folder |
| (e) Infrastructure | 0 alone | wildcard run 1, slice 1: the worker could not write ("don't ask mode"), $0.151 spent for nothing |

36 of 51 firm cells passed every visible check; 12 of those failed a hidden check. The other 4 of the
16 failed cells had a visible check failing at the end (calc run 1, duration run 3, tokenbucket run 1,
wildcard run 1); in the first three the worker was right and disputed the wrong check, in the fourth
it followed the wrong check.

Behaviours behind the 15 class (a) cells. A cell can appear in two rows.

| behaviour, with the failing hidden check | firm cells failing | boss drafts with a check for it | single cells failing |
|---|---|---|---|
| Non-ASCII digits rejected: `bigdecimal invalid_input`, `calc malformed_tokens`, `duration parse_decimals`, `jsonpointer list_indexes` and `set_value_errors`, `semver parse_invalid_input` | 10 of 15 | 0 of 15 | 6 of 15 |
| A 2000-operand chain must not hit the recursion limit: `calc associativity` | 2 of 3 | 0 of 3 (longest chain 100) | 1 of 3 |
| `available()` returns a `float`: `tokenbucket basic`, `isinstance(bucket.available(), float)` | 2 of 3 | 1 of 3 | 3 of 3 |
| A sign followed by a space is invalid, `"- 1s"`: `duration parse_negative` | 2 of 3 | 0 of 3 | 0 of 3 |
| `compare("0.5", "0.25")` is 1: `bigdecimal compare` | 1 of 3 | run 1: no (its `c04` has 7 asserts, none compares two fractions) | 0 of 3 on this case (run 2 failed `compare` on negatives) |
| A generator as a dict value works for `layers`: `toposort dependency_only_nodes` | 1 of 3 | 0 of 3 | 1 of 3 |
| Untouched branches of the result are copies: `jsonpointer set_value_isolation` | 1 of 3 | partly: all 3 drafts test copies of some branches; none kills either single product that failed it (section 9) | 2 of 3 |
| A single-item list with an invalid element raises: `semver sort_versions` | 1 of 3 | 0 of 3 (`sort_versions([]) == []` only) | 1 of 3 |

- 5 of the 15 cells have one omitted behaviour and nothing else (bigdecimal run 1, duration run 1,
  tokenbucket runs 1 and 3, toposort run 2). 5 have non-ASCII digits as their only failure (bigdecimal
  run 2, calc run 3, duration run 3, jsonpointer run 3, semver run 3). The other 5 have two omitted
  behaviours.
- The idea states each of these. For example calc rule 2: "an expression of 2000 operands joined by `+`
  is valid and must not hit Python's recursion limit". The calc worker's own status in run 3 says it
  handled 2000+ chains, and that cell passed `associativity`.
- The worker is not special-casing the checks. Every cell failed on behaviour its checks never touched.
- The firm's worker brief already puts the idea first and calls it the source of truth
  (`builder_v3.md`, bullet 1; `briefs.task_prompt`). In 32 of 51 cells the first slice already passed
  every visible check, and the worker reported `done` and stopped there.
- Wildcard run 1, in detail: boss check `c03` asserts `match("[]", "]") == True`. The idea says a `]`
  right after `[` is a member, so `[]` is an unclosed set. The reference fails `c03`. The worker never
  disputed it; the product returns `True` for `match("[]", "]")` and `False` for `match("[]]", "]")`,
  and failed `bracket_edge_cases`, `filter_names` and `invalid_patterns`.

## 3. Where the firm beat the single agent

Tasks where the single agent failed and the firm passed more: slugify (1 to 3), toposort (0 to 2),
matrixops (2 to 3), tokenbucket (0 to 1).

| task | single's failure | boss drafts with a check for it | firm's result |
|---|---|---|---|
| slugify | `max_length_hyphen`: cut at the last hyphen that fits | 3 of 3 (`c06`) | 3 of 3 pass |
| matrixops | `ragged`: a ragged matrix raises | 3 of 3 | 3 of 3 pass |
| toposort | `scale`: 10,000-node chain, time-out | 3 of 3 (`c07`) | 3 of 3 pass `scale` |
| tokenbucket | `basic`: `available()` is a `float` | 1 of 3 (`c01`) | the cell with the check passed |
| bigdecimal | 2 cells with wrong arithmetic (`add("12.50", "0.25")` gave `21.75`) | all 3 drafts test add, subtract, multiply on decimals | 0 of 3 cells with an add, subtract or multiply bug |

- The gain is where the boss wrote a check and the single agent, which cannot run code, did not catch
  its own bug. In the first four rows, a boss check covered the behaviour in 10 firm cells (slugify 3,
  matrixops 3, toposort 3, tokenbucket 1) and the firm passed all 10. The single products that failed
  these behaviours are killed by the drafts that cover them (section 9).
- Most of that gain comes from the worker reading the checks' code in its first brief. The gate's
  feedback slices repaired a real defect in 3 cells: intervals run 2 (a `NameError`), tokenbucket run 2
  (the `float` check), roman run 1 (a refused write). Toposort run 2 fixed a time-out and still failed
  `dependency_only_nodes`. In all, 7 later slices ($0.41, 3.6% of firm spend) were funded because a
  sound check was failing.
- Slice 1 left all visible checks passing in 32 cells, only wrong checks failing in 14, and a sound
  check failing in 5 (the four above plus wildcard run 1).

## 4. What kills the single agent

19 failed cells, one slice each, no feedback.

| cause | cells | where |
|---|---|---|
| Non-ASCII digits accepted | 6 | calc 2, duration 2, jsonpointer 1, semver 1 |
| Another behaviour the idea states, missed | 9 | `available()` float (tokenbucket 3), cut at hyphen (slugify 2), copies (jsonpointer 1), ragged rows (matrixops 1), single-item list (semver 1), generator values (toposort 1) |
| Wrong core logic or a time-out | 4 | bigdecimal 2 (scale and digit alignment), toposort 2 (`layers` disagrees with the oracle; 10,000-node `scale` time-out) |

- A fix must not copy these weaknesses: 15 of 19 are omissions the single agent shares with the firm,
  and 4 of 19 are bugs it cannot see because it cannot run code.
- One single cell ended `crashed` (bigdecimal run 1) and still passed.

## 5. Cost and time

Mean per cell, from the ledgers. Costs are the CLI's estimates.

| | single | firm | firm minus single |
|---|---|---|---|
| Boss call | | $0.0876 (40%) | +$0.0876 |
| Slice 1 | $0.0925 | $0.0898 (41%) | -$0.0027 |
| Slices 2 and later | | $0.0423 (19%) | +$0.0423 |
| **Total** | **$0.0925** | **$0.2197** | **+$0.1272** |
| Cost per passing cell | $0.147 | $0.320 | |
| Median time | 88 s | 244 s | 2.8x |
| Mean time | 100 s | 277 s | boss 122 s, slice 1 94 s, later slices 48 s, other 12 s |

- Slices per firm cell: 1 slice in 35 cells, 2 in 10, 3 in 4, 4 in 1, 6 in 1; 77 slices in all. No slice
  was funded after every visible check had passed (the rule returns done first).
- The boss call writes about 14,900 output tokens; with thinking off, about 4,000 (draft evaluation,
  `drafts-single` and `drafts-single-think0`).
- 16 cells had a wrong boss check (20 checks). They cost $0.303 a cell against $0.182, took a median
  395 s against 220 s, and 96% of the later-slice spend ($2.07 of $2.16) is theirs. They passed 12 of
  16, against 23 of 35 without one: wrong checks cost money here, not passes.
- 17 later slices ($1.647) were funded while every failing check was one the reference also fails;
  10 of the 20 wrong checks were never disputed. A real run has the investor read the checks first,
  so this waste is partly an artefact of the automatic approval.
- Cost if parts are removed (firm total $11.206 over 51 cells, single $4.718):

| removed | total | per cell | note |
|---|---|---|---|
| boss call | $6.74 | $0.132 | no checks to gate; the worker would have only the idea |
| later slices | $9.05 | $0.177 | 3 of 51 cells were repaired in them |
| both | $4.58 | $0.090 | a single agent: $0.0925 measured |
| the 17 wasted slices | $9.56 | $0.187 | pass counts unchanged in the recorded cells |
| boss thinking off (estimate) | $8.16 | $0.160 | draft cost $0.032 against $0.101, scaled |

- `boss.bench.replay` on the same ledgers: a policy that fires after 1 stalled slice saves $0.60 (8.9%)
  and fires 10 workers, 3 of which later passed a new check. Firing alone does not remove the waste.

## 6. The held-out run

`heldout3`: the firm arm, 51 cells, 3 held-out checks each, written by the examiner from the idea and
the public names. Passed 28/51, mean cost $0.2777 (the examiner is $0.058 of that), median 332 s.

Visible-pass cells (40; one cell ended on the usage limit and one had no held-out checks):

| | hidden failed | hidden passed |
|---|---|---|
| held-out failed | 0 | 1 |
| held-out passed | 17 | 22 |

- Held-out checks caught 0 of 17 hidden failures (sensitivity 0%). The one held-out failure
  (lrucache run 3, `h02`) is a wrong check: the reference fails it.
- `held_out_wrong` is not recorded in these results (the field was added later). Computed here by
  running the reference on every held-out folder: 1 wrong of 150 checks.
- The examiner picks one example from a sentence that lists several. Duration run 1: its held-out
  check for "`.5`, `1.`, `1.5.5`, `1e3`, `1_0` and non-ASCII digits are not valid" tests `.5s` only;
  the product failed `parse_decimals` on non-ASCII digits and passed all 3 held-out checks.
- 17 of 40 visible-pass cells (43%) failed a hidden check here, against 12 of 36 (33%) in `final3`.
- The same hidden checks fail: `calc malformed_tokens` 3 of 3, `semver parse_invalid_input` 3 of 3,
  `tokenbucket basic` 3 of 3, `toposort dependency_only_nodes` 3 of 3.

## 7. NL2Repo (`decouple`)

Single 67/67, firm 62/67. The firm's 5 failed tests:

| tests | what they need | boss checks that touch it |
|---|---|---|
| `test_env_bool_true`, `test_env_bool_false`, `test_ini_bool_true`, `test_ini_bool_false` | `config('Key1int', default=1, cast=bool)` is `True`; `default=0` is `False` (a non-string default) | none: `c04` tests `cast=bool` on a string only |
| `test_ini_repo_keyerror` | `config.repository['UndefinedKey']` raises `KeyError`; the product let configparser's `NoOptionError` through | none: `c08` tests reading keys, not a missing one |

- The spec embeds these tests word for word (the idea is 39 KB and includes the test code). The single
  agent read them all; the boss's 8 checks sampled the spec, and the worker's last status was
  "Waiting for gate to run checks to identify any implementation issues".
- Cost $0.282 (boss $0.121, 43%) against $0.229; 264 s against 187 s. One cell, so no rate.

## 8. Fixes, ranked

Effects are in cells of the 51-cell firm run (35 passed) and are estimates, not measurements.

| # | change | kind | evidence | expected effect | confirm with |
|---|---|---|---|---|---|
| 1 | **Coverage step for the boss.** Each check names the idea's numbered rules it covers; a draft is refused if a rule has none, and a sentence that lists examples gets one assertion per example (parametrized). | prompt (`term_sheet_v1.md`) and code (`termsheet.py` validator, schema field) | 15 of 16 failures are omissions; 0 of 15 drafts test non-ASCII digits; where a check covered a behaviour, the firm passed it in 10 of 10 cells | up to 15 of the 16 failures; 5 to 12 if the draft covers half to most of the omitted behaviours (confidence 60% that it flips at least 5) | draft-only, about $1.7 a prompt (17 drafts at $0.10): kill rate of the new drafts on the 35 failing `final3` products (section 9, now 31%; 8% on the non-ASCII ones); then one paid 51-cell run, about $11 |
| 2 | **Worker brief: the checks are a minimum.** Say the gate also runs checks the worker cannot see, restore the single arm's line "handle the edge cases the request states", and have the worker walk the idea sentence by sentence before `done`. The brief already says the idea is the source of truth. | prompt (`builder_v3.md`) | the two arms' worker prompts differ today (section 10); the firm failed non-ASCII in 10 of 15 cells against 6 of 15 (p = 0.27); single's own prompt has the line and still missed 15 of 19 | 0 to 5 cells; about 2 (confidence 35% for at least 2) | paid: the 5 tasks that state non-ASCII digits, 15 cells, about $3.30, then 51 cells |
| 3 | **Stop funding a worker that reports `done` twice with the same checks failing.** Escalate to the investor, do not continue or fire. | code (`rule.py`) | 17 slices, $1.65, funded on wrong checks only; 12 of the 16 cells with a wrong check passed anyway | 0 cells; -$0.03 a cell (-15%) | free: extend `boss.bench.replay` to count slices after that point and any later new pass; no model call |
| 4 | **Boss thinking off** (`--boss-thinking 0`, exists). | config | draft $0.032 against $0.101; 5 of 16 drafts with a wrong check against 2 of 16; 36 against 40 of 61 mutants killed; a wrong check costs about $0.12 a cell | -$0.04 to -$0.06 a cell (-17% to -27%), about -85 s (not measured); pass effect unknown, within noise | draft numbers exist; a pass effect needs a paid 51-cell run, about $8 |
| 5 | **Worker-written tests the gate runs.** The worker adds `tests/` from the idea; the gate runs them after each slice. The worker cannot run them itself: it has no shell. | code (`gate.py`, `briefs.py`, a new class of check outside the approved term sheet) | 4 of 19 single failures are core bugs the boss's checks also catch; omissions need the worker to think of the sentence, and the single agent did not in 15 of 19 | 0 to 4 cells; +$0.03 to $0.05 a cell (a guess) | paid, 51 cells, about $13 |
| 6 | **Held-out checks as the verdict.** Do not. | none | 0 of 17 caught; 1 false alarm in 40; $0.058 a cell and about +90 s | 0 cells flipped; it only relabels failures | already measured |
| 7 | **Skip the boss for small ideas.** | code | not testable here: the 17 ideas are 0.8 to 4.3 KB with 5 to 13 rules; the smallest (slugify, 842 bytes) is where the firm gained most; the 7 tasks that tie at 3 of 3 cost the firm $0.110 more a cell | unknown | needs tasks of different sizes |

- Not ranked: "stop funding once the visible checks pass" is already how the rule works (0 of 77 slices
  came after every visible check passed).
- Fixes 1 and 2 are independent; fix 3 and 4 only lower cost. Fix 1 is the only one aimed at the cause
  of 15 of 16 failures.
- Fix 1 is graded by this benchmark's own hidden checks, which test each sentence of the idea. A real
  idea is vaguer, so the effect on real use is unknown.

## 9. A free measurement for fix 1

Every `final3` product that failed a hidden check (19 single, 16 firm) was run through the other
`final3` boss drafts of its task (2 for a firm product, 3 for a single one). A draft kills the product
when one of its sound checks (one the reference passes) fails on it. This is recall on defects that
really happened, and it needs no model call. Wrong checks are left out: running the reference on all
102 drafts found 39, which is the 20 and the 19 in the two runs' tables.

| failed products | products | draft-product pairs | killed |
|---|---|---|---|
| all | 35 | 89 | 28 (31%) |
| with a non-ASCII-digit failure | 16 (10 firm, 6 single) | 38 | 3 (8%) |
| the rest | 19 (6 firm, 13 single) | 51 | 25 (49%) |
| single products | 19 | 57 | 23 (40%) |
| firm products | 16 | 32 | 5 (16%) |

- The draft evaluation's recall is 58% to 66% on its mutants. On products that really failed, a draft
  detects 31% and on the non-ASCII-digit ones 8%.
- The pattern follows the coverage in section 2: `slugify max_length_hyphen`, `matrixops ragged`,
  `toposort scale` and the `bigdecimal` arithmetic products are killed by 3 of 3 drafts; `tokenbucket
  basic` by 1 of 3; `jsonpointer` isolation, `semver`, and `toposort` generator by 0 of 3.
- Firm products are the ones that passed their own draft, so their rate is low by construction.
- Use: score a new boss prompt's 17 drafts on these 35 products, about $1.7. A coverage step (fix 1)
  should lift the 31% before any worker runs.

## 10. Where this contradicts or adds to the existing write-ups

- `bench/METHOD.md` calls a visible-pass, hidden-fail cell **gamed**. In all 12 such `final3` cells the
  hidden failure is a behaviour no boss check tested; none is a worker special-casing a check. "Uncovered"
  describes it better.
- `bench/METHOD.md` (Arms) and `src/boss/bench/run.py` say both arms get the same input. The worker
  prompts differ: the single arm's `solo_v1.md` says "Your work will be judged by checks you cannot see.
  Handle the edge cases the request states"; the firm's `builder_v3.md` says the gate runs the checks
  shown in the task. The table does not list this difference.
- `bench/results/README.md` says the firm moved from behind to level with the single agent (69% against
  63%). A second firm run on the same prompts passed 55% (28/51). Treat the firm's rate as 55 to 69%.
- The draft evaluation's recall (58% to 66% of mutants killed) overstates coverage of the idea's
  enumerated edge cases: 0 of 15 drafts test non-ASCII digits, and only `bigdecimal` and `semver` have
  hand-made mutants at all (neither is a non-ASCII-digit one); `calc`, `duration` and `jsonpointer` have
  only mutants harvested from earlier runs.
- `bench/results/README.md`: "all 4 firings were in cells with an undisputed wrong check, and the
  product passed" holds (jsonpointer run 1 twice, slugify run 2, wildcard run 3). It also holds that all
  10 disputes were wrong checks. New: 10 of the 20 wrong checks were never disputed, and wildcard run 1
  followed one and failed.
- The `held_out_wrong` field is documented as recorded; the `heldout3` results do not have it.
- No `final3` ledger has a `scope: product` event (`heldout3` does). In `heldout3` the product verdict
  equals the best worker's result in all 51 cells, so class (d), assembly, is 0 there too.

## Limits

- One model (Haiku) for boss and workers; 3 runs per task; 17 tasks. Differences of 3 cells are noise.
- Cells are classed by reading the failing hidden check, the product and the boss's checks. The counts
  of "boss drafts with a check" come from reading the check code for the behaviour, by search and by hand.
- Section 5's "boss thinking off" row scales the boss's cost by the draft evaluation's ratio; time saved
  is not measured.
- The `heldout3` run is not an exact repeat: its code is later than `final3`'s firm arm (`a886934`).
