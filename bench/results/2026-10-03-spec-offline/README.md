# 2026-10-03-spec-offline

Does the rule layer in `src/boss/spec.py` find what the boss's checks leave out? Measured on saved
drafts, hand labels and hand-written mutants. No model call and no spend. The full report, as
`python -m boss.bench.spec_eval all o4b --raw bench/results/raw` printed it, is `report.md`.

Criteria were committed before the first run (`bench/spec_truth/CRITERIA.md`, commit `c53720d`); the
splitter and anchor extraction were frozen at `aade360` (later commits changed speed and comments only,
checked identical on all 59 ideas and 3,000 random texts). What was added after seeing numbers is
labelled below; none of it moves a criterion.

## Against the pre-registered criteria

| Step | Criterion | Result | |
|---|---|---|---|
| O1 splitter | every property on 59 ideas and their stripped copies; at most 40 sentences in at least 95% of ideas | properties: 0 failures in 118 texts; 56 of 59 ideas (94.9%) within 40 sentences; `jsonpointer`, `semver`, `wildcard` fall back to one rule per numbered item | **FAIL**, by 0.1 point |
| O2 labels | proposer top-1 agreement at least 70%, else hand labels only | 74 of 128 = 58% | hand labels only (they are) |
| O3 recall | at least 9 of the 15 known-omission cells have a flagged rule that is their failing behaviour | 12 of 15 = 80% | **PASS** |
| O3 burden | median flagged rules per draft at most 4 | 3 over 169 drafts | **PASS** |
| O4 | kill-rate gap (all anchors present minus one missing) at least 25 points, 40 or more triples a side | 89% against 85% = 4.5 points, 605 and 350 triples | **FAIL** |
| O5 | reported only | 598 flags; 266 (44%) on a rule whose hidden checks every saved product of the task passed | |

The pre-registered reading of "O3 passes, O4 fails" is: anchors find omissions but do not predict
kills; keep the structural checks, drop the anchors from the headline.

Predictions recorded before the run: O3 recall passes 65% (hit), O3 burden passes 60% (hit), O4 passes
50% (miss).

## What the numbers do and do not say

- **O3's pass is mostly flag volume.** The 15 cells flag a median of 6 rules each, and their failing
  hidden checks label 22% of all scored rules. Flagging the same number of rules at random would hit
  11.0 of the 15 cells; the verifier hit 12. The recall criterion alone cannot tell it from chance.
  (Chance baseline added after the first run.)
- **By type of missing anchor, in those cells** (a flag is right when its rule belongs to a failing
  hidden check; base rate 22%): `non_ascii` 15 of 21 (71%), `exception` 5 of 5, `magnitude` 1 of 1,
  `type` 2 of 7 (29%), `enum_item` 11 of 39 (28%, the base rate), `literal` 1 of 22 (5%, below it).
  The `literal` anchor is noise. (Added after the first run, from the same 15 cells: a hypothesis for
  the next version, not a result.)
- **O4 failed because it could not see.** The 42 hand mutants of the 17 tasks are killed 88% of the
  time whatever the draft holds, and none is a non-ASCII or float-type mutant (the original evidence
  already noted that only `bigdecimal` and `semver` have hand mutants for these tasks' failing
  behaviours). A ceiling, not evidence either way.
- **O4b, added after the first run, with no criterion:** the 49 saved products that failed exactly one
  hidden check, run against the drafts of their task except the one they were built against.
  When an anchor of the blamed rule is missing from the draft, the draft killed the product 4 times in
  567 (1%); when every anchor is present, 43 of 261 (16%). Anchors look like a necessary condition for
  catching a real wrong product (a missing anchor means almost never caught) and a weak sufficient one
  (present means 16%). The 15.8-point gap is under the O4 bar of 25 points, and the products are the
  hard ones, so read it as direction, not as a pass.
- **Misses.** `bigdecimal` rep 1 (`compare`), `duration` rep 1 (`"- 1s"`) and `toposort` rep 2 (a
  generator as a value): their rules name no literal, type, size or exception. As expected.

## What changed after the first run

- A check that timed out is rerun under a longer limit (the machine was at load 90).
- Splitter speed: 200 KB of `` `a. ` `` took 27 s; now 0.12 s, and an idea over 200,000 characters is refused.
- Added: the chance baseline, precision by anchor type, and O4b. `all` runs the five pre-registered steps;
  `o4b` runs only when named.

## Limits

- The union form gives a draft credit for an anchor in any of its checks. Claim-level checking (the
  design) is stricter and has not been measured: old drafts carry no claims.
- 17 tasks, 169 drafts of which many are the same task, so triples are not independent; intervals are too
  narrow. Hand labels were made by one person (an AI agent) from the ideas and hidden checks, before
  the drafts were read against them; no second reader.
- The 18 later tasks have no labels, so no held-out check of a rule tuned on these 17 exists yet.
- Hand mutants and the benchmark ideas are strict and numbered; real requests split worse.
