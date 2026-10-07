# 2026-10-07-router-offline

The cascade's start-tier router, checked against saved benchmark cells. No model call, no spend.
This is groundwork for a post-launch decision: dispatch stays opt-in (`--dispatch cascade`), and no
default changes here. Numbers come from `evaluate.py` in this folder, run on commit `7c51377` plus
this branch:

    uv run python bench/results/2026-10-07-router-offline/evaluate.py bench/results/raw

## Answer

1. **The data can't support any start other than Haiku, and the router picks Haiku for every
   cell.** On a cold start the router picks `haiku/off` for 205 of 205 cells. Replayed with pooled
   history (leave-one-task-out, the B105 replay), it picks Haiku for 205 of 205: 201 from
   measured data and 4 from the prior. The cascade climbs only when the gate fires a worker for no
   progress or a slice limit. That happened to 6 of 182 first Haiku workers that reached a verdict
   (3.3%, 95% CI [1.5%, 7.0%]). Under `budget.py`'s price ratios, starting on Sonnet only pays
   once that rate passes about 72% (D46). The highest bucket is `files=2-3` at 3/36 (8.3%, upper
   bound 21.8%).
2. **A Haiku classification call is not worth building for the climb.** Picture an oracle that
   starts on Sonnet exactly where the gate later fires Haiku. It saves $0.0094 a cell. One $0.002
   call costs 21% of that, before any classification error. The design is below, and it stays
   off.
3. **Always starting on Sonnet loses on cost per delivered task.** Haiku-start/router costs $0.487
   to $0.510 per delivered task; always-Sonnet costs $0.995 to $0.524. Sonnet only ties if it
   delivers every one of the 97 cells Haiku missed and also uses 91% or less of Haiku's tokens.
4. **The one place a non-Haiku start might pay is a hypothesis, not a finding.** Haiku delivered
   83% of the shortest third of ideas (under 2,389 characters) and 26% of the longest third (3,397
   or more). On `files=2-3` it delivered 31%. Most of those misses passed every visible check and
   failed a hidden one, so the gate never sees them and the cascade never climbs. A Sonnet start
   on that subset would pay only if Sonnet delivers at least 41% of the long-idea misses, or 51%
   of the multi-file misses. No Sonnet cell exists, so this is unobserved. E6 stage 1 should
   pre-register it as a question before any rule depends on it.

## Labels: what a Haiku-only benchmark can observe

205 firm cells from `blind-orig17`, `blind-new18`, `new18`, `e3-base` and `e3-par`. A cell counts
only if the cell's investor key vouches for its ledger, term sheet and checks. Every cell ran a
Haiku boss and Haiku workers, at $0.40 a cell (`--slice 0.20`). `final3`, `heldout3`, `rerun1` and
`pilot` predate the investor key, so they are left out.

| outcome | cells | cheapest tier that delivers |
|---|---|---|
| delivered (every hidden check passed) | 108 | haiku, observed |
| the gate fired the first worker (the cascade would climb) | 5 (+1 that later delivered) | unobserved |
| a hidden check failed, every visible check passed (the gate is blind) | 81 | unobserved; the cascade never climbs |
| a visible check failed and the first worker reached no verdict (budget or rounds ran out) | 10 | unobserved; no climb |
| a visible check failed after a verdict | 1 | unobserved |

So the label "cheapest tier that delivers" is known for 108 of 205 cells, and all 108 say Haiku.
For the other 97, the benchmark cannot say whether Sonnet, Opus or nothing would deliver.

## Features (router inputs, from the term sheet only)

| feature | Haiku gate-fail | Haiku delivered |
|---|---|---|
| kind `files=1 checks=6+` | 3/142 (2.1%) | 93/159 (58%) |
| kind `files=2-3 checks=6+` | 3/36 (8.3%) | 13/42 (31%) |
| kind `files=1 checks=3-5` | 0/4 | 2/4 |
| idea under 2,389 chars | 0/54 | 55/66 (83%) |
| idea 2,389 to 3,396 | 3/66 (4.5%) | 35/69 (51%) |
| idea 3,397 or more | 3/62 (4.8%) | 18/70 (26%) |
| difficulty (bench only, never a router input): easy / medium / hard | 1/24, 5/130, 0/28 | 56%, 54%, 43% |

Held-out presence and check content (for example, the share of checks that test a raised error)
are not used. No cell ran with held-out checks, and check content would mean reading the check
files at routing time. Add them once E6 records them with some variation.

## Router design

1. **Measured history first (unchanged, D46).** For each task kind (`files=` and `checks=`
   buckets), the router starts on the tier with the lowest `E[T] = c_T + p_T * E[T+1]`, using this
   project's own verified runs. This applies once a kind and tier have 5 attempts or more.
2. **Cold start (this PR).** Below 5 attempts, the same chooser runs on the priors. On every shape
   seen here it picks Haiku. Effort is the first rung of the ladder from that tier, which is `off`.
   The reason now says so: `cold start, under 5 verified attempts of this kind on haiku: lowest
   expected cost $0.344 (vs sonnet $0.759, opus $1.139)`. No feature threshold moves a start up,
   because none is supported by the data (above).
3. **Recorded and shown.** Every start is recorded under `routed` on the investor's signed
   `approved` event, as `{tier, effort, kind, source, why, features}` with `features =
   {idea_chars, tasks, files, checks}`. This follows the existing `route` field on that event. The
   term sheet prints `Router's start for t1: haiku/off, <why>` above the worst-case line, which
   already prices every rung. The sheet's own `dispatch` remains what runs, and the investor may
   still edit it. Every E6 cascade cell then becomes a labelled row for fitting the router.
4. **Optional Haiku classifier (designed, not built, off).** The trigger would be a cold start
   (no measured kind) on a long or multi-file task, which is the only region where the hypothesis
   in point 4 above could make a non-Haiku start pay. Input would be the idea and the check
   descriptions, never check code or anything from the benchmark. Output would be one of
   `{haiku, sonnet}` plus a reason, clamped to the whitelist and shown and recorded like any
   start. Build it only if E6 stage 1 shows Sonnet delivers 41% or more of long-idea Haiku misses.
   Until then it cannot recover its cost (point 2 of the answer).

## Caveats

- **Only Haiku ran.** Every Sonnet and Opus figure is a price ratio (3x and 5x on the same tokens),
  not a measurement. "Sonnet delivers everything Haiku delivered" is an assumption.
- **Repetitions are correlated.** The 205 cells are about 43 tasks with 3 to 6 runs each. The Wilson
  intervals treat cells as independent, so the true intervals are wider.
- **The idea-length terciles were cut on this same data.** The 41% and 51% break-evens are post hoc
  and must be pre-registered before E6 tests them.
- **The cost model leans slightly against Haiku.** For the 6 gate failures, the cost of a Sonnet
  rung was added on top of the observed cell cost. That observed cost already includes v1's
  same-model second worker.
- **E6 cells will differ.** E6 runs at $0.80 a cell. With a larger round, more first workers may
  reach a verdict, so the gate-fail rate may rise; 10 cells here ran out of budget before one.
- **Pooled history is not one project's history.** The replay is the B105 approximation.

## Proposed ids (not added)

On main the highest ids are B105 and D46. Open PRs propose B106 to B109 and D47.

- **B110:** replace the Haiku prior's `p_fail` of 0.17 (visible-check failures) with the
  gate-verified rate, 3.3% (6/182), once E6 confirms it at $0.80 a cell. It changes no start.
- **B111:** the Haiku classification call for cold-start long or multi-file tasks. The trigger is
  E6 stage 1 showing Sonnet delivers 41% or more of long-idea Haiku misses.
- **B112:** pre-register E6 stage 1's stratified question, Sonnet's delivery on long-idea and
  multi-file cells that Haiku misses on hidden checks only.
- **D48:** the router records its start, reason and features on the signed approval, and it starts
  on Haiku at cold start until a measured kind says otherwise.
