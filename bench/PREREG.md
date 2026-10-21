# Pre-registration: where a firm should beat one agent

Commands recorded before 2026-10-08 use the old module name; run them with
`python -m antstreet...` instead of `python -m boss...`.

Written 2026-10-03, before any of these runs. The hypotheses, arms, metrics, sample sizes and
decision rules below are fixed; a change after a run starts is recorded here with its date and
reason, and the run it affects is reported under both rules. Why these five and not others:
[EVIDENCE.md](EVIDENCE.md).

## What every experiment shares

The standards every experiment meets, and how each is held, are in [STANDARDS.md](STANDARDS.md).

- **Metrics.** The seven KPIs defined in [METHOD.md](METHOD.md) (delivery rate, false-pass rate,
  cost per delivered task, time to delivery, reliability, investor effort, check quality). Each
  experiment names its primary KPI; the others are reported, not decided on.
- **Blinding.**
  - No arm sees a hidden check or the reference solution (`tests/test_bench_run.py` pins it).
  - No text any model is given says it is measured or names another arm (`tests/test_blinding.py`).
  - Every graded result comes from tests, never from a model's opinion. If a judged quality score
    is ever added, the judge gets the products with arm labels removed and order shuffled.
  - The analysis is the fixed KPI command and the paired test below, run once per experiment.
- **Fair baselines.** A firm win counts only against the single agent at the SAME dollar budget
  per task, and, where named, against a stronger single model at that budget. A win that only
  comes from spending more is reported as a cost, not as a win.
- **The test.** Paired by task: for each task, the difference in the primary KPI between arms,
  averaged over runs; a 95% interval from 10,000 bootstrap resamples of tasks. A benefit is claimed
  only when that interval excludes zero in the firm's favour. Otherwise the result is "not shown",
  whatever the point estimate.
- **Honest limits.** 35 single-module tasks (59 when the next 24 land) and 8 multi-file tasks:
  only large effects can be shown. Each experiment states the smallest effect it can see.

## E1. An independent checker lowers the false-pass rate

- **Claim.** Most of the firm's "done" claims that are wrong come from checks that miss a rule. A
  checker that never talks to the builders catches some of them (EVIDENCE: separate evaluator,
  SpecBench).
- **Feature.** `--held-out 3` (the examiner); the run is marked not delivered when a held-out check
  fails.
- **Arms.** firm; firm `--held-out 3`; single at the firm's mean dollar spend.
- **Primary KPI.** False-pass rate: the system said done, and a hidden check failed.
- **Not shown if.** The firm with held-out checks does not have a lower false-pass rate than the
  firm without them, by the paired test.

## E2. A strong planner with cheap builders is cheaper per delivered task

- **Claim.** A stronger model drafting the checks, with cheap builders, delivers more per dollar
  than either model alone (EVIDENCE: advisor strategy, +2.7 points at -11.9% cost).
- **Feature.** `--boss-model sonnet` with Haiku workers.
- **Arms.** firm (Sonnet boss, Haiku workers); single Haiku; single Sonnet; all at the same
  per-task budget.
- **Primary KPI.** Cost per delivered task.
- **Not shown if.** Single Sonnet at the same budget delivers at an equal or lower cost per task.

## E3. Parallel waves are faster on work that splits

- **Claim.** On tasks of independent modules, building them at once cuts the time to a delivered
  product without lowering the delivery rate (EVIDENCE: parallel breadth, centralised agents).
- **Feature.** `--max-tasks 3 --parallel 3`.
- **Arms.** firm `--max-tasks 3 --parallel 3`; firm default; single; on `bench/tasks-multi`.
- **Primary KPI.** Time to delivery; delivery rate must not drop by the paired test.
- **Not shown if.** Median time to delivery is not at least 1.3x faster, or interface failures
  cancel the gain.

## E4. A clean-context reviewer finds what the builder missed

- **Claim.** A reviewer with a fresh context finds real bugs that the builder's own review does
  not (EVIDENCE: clean-context code review).
- **Feature.** `--roles critic` (a fresh-context critic whose findings become checks only with the
  investor's yes; the benchmark answers yes).
- **Arms.** firm `--roles critic`; firm; single, then the same session asked to review its own
  work, at the same budget.
- **Primary KPI.** Delivery rate.
- **Not shown if.** The critic arm does not beat the self-review arm by the paired test.

## E4b. The same critic, with room to finish

Added 2026-10-07, after E4's result and before any E4b run.

- **Why.** In E4 the critic's call failed in 36 of 105 cells: 35 were cut off at its $0.15 cap
  (completed calls cost up to $0.149, capped ones about $0.17), so E4 mostly measured a critic that
  could not finish (bench/results/2026-10-07-e4-critic). E4's result stands as published; E4b asks
  the question E4 could not: with enough budget, does the critic beat self-review?
- **Change, and only this change.** The critic's per-call cap is $0.40 instead of $0.15. The code
  is E4's commit (4ba91ad) with that one change applied, so the builder prompt and everything else
  match E4's other arms; a run from a later `main` (which uses builder_v5) is not E4b.
- **Arms.** firm `--roles critic` with the $0.40 cap, run fresh: blind35's 35 tasks x 3 reps, Haiku
  boss and workers, `--budget 0.40 --firm-args "--slice 0.20 --roles critic --fix-budget 0.30"`,
  in its own `--out` (`bench/results/raw/e4b-critic`). Compared with E4's saved self-review and
  firm cells, which are not rerun: nothing in their arms changed.
- **Primary KPI and decision.** As E4: delivery, paired by task, 10,000 task resamples, seed 0.
  Shown only if the paired interval of firm+critic (E4b) minus self-review (E4) lies above 0.
  Reported beside it, not decided on: E4b vs E4's firm, E4b vs E4's critic arm, the cost per
  assigned cell, the share of critic calls that complete, and time.
- **Infrastructure.** Cells stopped by a usage limit or a login failure are moved aside and rerun
  (B71) until all 105 are counted; the run stops after 3 such failures in a row.
- **Cost.** About $40-50 (E4's critic arm averaged about $0.37 a cell; a finishing critic adds up to
  $0.25 a cell). Worst case per cell $1.35. Needs the owner's go; pre-registered 2026-10-07, not run.

## E5. The firm is more reliable across runs

- **Claim.** Firing stalled workers and retrying inside a budget makes a task pass every time
  more often (EVIDENCE: weak; no direct measurement found).
- **Arms.** firm; single at the firm's mean dollar spend; 5 runs per task.
- **Primary KPI.** Reliability: tasks delivered on all 5 runs.
- **Not shown if.** pass^5 is not higher by the paired test.

## E6. Per-task dispatch lowers cost per delivered task without lowering delivery

Added 2026-10-04, before any E6 run.

- **Claim.** Running every worker on the model its task was given (Haiku first, one step up when
  the gate fires a worker for no progress or a slice limit, a one-agent route for one-file ideas)
  delivers at a lower cost per delivered task than a fixed Sonnet or a fixed Haiku, with no loss
  of delivery. The step reaches only the cells that fail a visible check (18 of the 51 failed
  cells in the blind 35-task run); the other 33 failed a hidden check no builder-side step can see.
- **Feature.** `--dispatch rules` (`docs/DECISIONS.md` D43 to D45).
- **Arms.** Same code, same blinded prompts, same per-cell budget of $0.80, through `--firm-args`:
  `fixed-haiku` (`--model haiku --boss-model haiku`), `fixed-sonnet` (`--model sonnet --boss-model
  sonnet`), `dispatch` (`--model haiku --boss-model haiku --firm-args "--dispatch rules --max-tier
  sonnet"`). The single Haiku arm of the blind 35-task run is a reference row only. Sets:
  `bench/tasks` (35 tasks, 3 runs) and `bench/tasks-multi` (8 tasks, 3 runs, `--max-tasks 3
  --parallel 3`, which the dispatch arm adds `--dispatch rules` to).
- **Fourth arm, `cascade`** (added 2026-10-04, before any E6 run). The same code, prompts, sets and
  per-cell budget, with `--firm-args "--dispatch cascade --max-tier opus"`: Haiku first, then Sonnet,
  then Opus, then Opus at one effort step higher, one rung per task per verified failure (D46). It is
  compared on the primary KPI below (cost per assigned cell) against `fixed-haiku`, `fixed-sonnet` and `dispatch` (v1) at
  $0.80 a cell, by the same paired bootstrap. Adopt only if it wins at equal delivery: its interval
  below zero against all three, and the delivery guard below met against each. Each benchmark cell
  is its own project, so no cell has a history and every start is the prior (Haiku); this arm
  tests the ladder, not the data-driven start (B105). At $0.80 an Opus rung is funded only if the
  earlier rungs left $0.55 free in the round; rungs refused for money are reported apart (`hired`
  with no worker after a `fired`, `abandoned` reason `cascade: ...`) and count as a failure of the arm.
- **Primary KPI.** Cost per assigned cell (each cell's total cost, boss call included, delivered
  or not), paired by task (a task's mean over its runs) with a 10,000-resample bootstrap of tasks:
  `python -m boss.bench.paired --kpi cost_per_delivery`. With the delivery guard met, a lower cost
  per assigned cell at no lower delivery means a lower cost per delivered task. Reported beside it,
  not decided on: the pooled cost per delivered task (TOTAL spend over all assigned cells divided by
  delivered cells) from `python -m boss.bench.kpi`; it has no interval, because a task that
  delivered nothing has no ratio.
- **Delivery guard.** Dispatch minus each fixed arm, 95% interval with a lower bound at or above
  -0.10 (the blind run's own interval was [-0.076, +0.124], so this is the narrowest guard the
  sample supports). Every assigned cell counts in the denominator, a cell that stopped for a wrong
  model (T69) included: it is never relabelled `infrastructure`. Those stops are still reported
  apart.
- **Not shown if.** Dispatch is default-on only if its paired cost-per-assigned-cell interval (the primary KPI) is below zero
  against fixed Sonnet AND (below zero against fixed Haiku, or delivery is higher with the interval
  above zero). Otherwise it stays opt-in and fixed Haiku stays the default.
- **Reported apart.** Escalations fired, refused and rescued (a fired task that later delivered);
  cells whose run stopped for a wrong model (T69), counted in the guard as above (no command
  separates them yet, B93).
- **Cost.** Every Sonnet figure is an assumption (3 times Haiku on the same tokens, the ratio
  `budget.py` uses): no Sonnet or Opus cell has ever run. About $160 for both sets (range $110 to
  $210). Stage 1 first, about $55: 12 tasks, 3 runs, plus the 8 multi-file tasks once; stop if
  dispatch never escalates or an escalated cell never delivers. Needs the owner's yes before any
  spend.

## E4c. The same critic, with a fix round after a locked round

Added 2026-10-10, after E4b's result and before any E4c run.

- **Why.** In E4b, 9 of the 29 cells with a verified critic finding got no fix round: round 1
  closed below its unlock threshold and the code offered nothing after that stop
  (`ops/e4/e4b-declined-trace-2026-10-08.md`). The critic found real bugs nobody fixed.
- **Change, and only this change.** `antstreet fund --fix-after-stop` (PR #80: commit 7458b55 and
  its review fixes 15c06ad and 6447e6e): when the run ended only because a round closed locked,
  verified findings are offered as checks and the investor's yes tops up that round by the fix
  budget, which reopens it; a finding whose task was set aside is not offered. Every other stop is
  unchanged. The run uses E4b's code state (`bench/e4b-runner`, 1a9b9e1: 4ba91ad + the $0.40
  critic cap + the 900 s critic limit) with those three commits ported to it, on branch
  `bench/e4c-runner` (the write-up records its SHA); a run from a later main (builder_v5) is not
  E4c.
- **Arm.** firm on blind35, 35 tasks x 3 reps, Haiku boss and workers pinned to
  `claude-haiku-4-5-20251001` (`--model` and `--boss-model`), the model E4's and E4b's cells ran on,
  `--budget 0.40 --firm-args "--slice 0.20 --roles critic --fix-budget 0.30 --fix-after-stop"`, fresh in its own
  `--out` (`bench/results/raw/e4c-critic-fix-after-stop`). E4's self-review cells and E4b's cells
  are not rerun.
- **Primary KPI and decision.** As E4: delivery, paired by task, 10,000 task resamples, seed 0.
  Shown only if the paired interval of E4c minus E4's self-review lies above 0.
- **Reported, not decided on.** E4c vs E4b paired delivery (isolates the flag; with ~9/105 cells
  affected it is underpowered and expected near zero); how many cells the flag fired in and how
  many of those delivered; cost per assigned cell; critic completion share; time.
- **Infrastructure.** As E4b: usage-limit and login failures are moved aside and rerun; the run
  stops after 3 such failures in a row. That stop is a pause: the cause is fixed and the run resumes
  until every cell is counted. No decision is computed on a partial set; if the cells cannot all be
  counted, the result is reported as "not run to completion", with no verdict.
- **Cost.** About $44-48 (E4b averaged about $0.41 a cell; the flag adds at most the $0.30 fix,
  plus at most one reserve, in the roughly 9 affected cells). Worst case per cell stays at or
  under E4b's $1.35.

## E9. Checks that cover every rule raise delivery

Added 2026-10-10, before any E9 run. (E7 and E8 are reserved for experiments planned earlier.)

- **Why.** Most failed firm runs failed on a rule the idea states and no check tests
  (`bench/results/2026-10-02-why-the-firm-loses`, section 2). In blind35 the firm delivered 64/105
  and the single agent 62/105: +0.019 [-0.076, +0.124], not shown.
- **Feature.** `antstreet fund --coverage` (PR #82): before any worker is paid, every scored rule of
  the idea must be cited by a check, and no check may pass on any of three stub products written by
  code. The boss redrafts with the gaps named, at most 2 more calls, each booked; a redraft is kept
  only when it has fewer gaps. What is left is shown above the term sheet.
- **Arms.** All three run fresh from one commit, the `main` commit that merges PR #82 (the write-up
  records the SHA), on blind35's 35 tasks (the 17 of `blind-orig17` and the 18 of `blind-new18`,
  listed in `bench/results/2026-10-03-blind35`), 3 reps, Haiku boss and workers, `--budget 0.40`:
  1. coverage: firm, `--coverage --firm-args "--slice 0.20"`, `--out bench/results/raw/e9-coverage`;
  2. firm: firm, `--firm-args "--slice 0.20"`, `--out bench/results/raw/e9-firm`;
  3. single: `--out bench/results/raw/e9-single`.
  blind35's saved cells are not reused: `main` has moved since `e203f65` (`builder_v5.md` among
  other changes), so only same-commit arms isolate `--coverage`.
- **Primary KPI and decision.** Delivery, paired by task, 10,000 task resamples, seed 0. `--coverage`
  is shown to help only if the paired interval of coverage minus firm lies above 0.
- **Second decision, named now.** The firm with coverage is shown to beat the single agent only if
  the paired interval of coverage minus single lies above 0. It is a separate claim; a pass on one
  is never reported as a pass on the other.
- **Reported, not decided on.** firm minus single (does today's firm differ from blind35's
  +0.019?); false-pass rate per arm; in how many cells the boss redrafted, and the rule gaps and weak
  checks left at approval; cost per assigned cell; time.
- **Infrastructure.** As E4b: usage-limit and login failures are moved aside and rerun; the run
  stops after 3 such failures in a row. That stop is a pause: the cause is fixed and the run resumes
  until every cell is counted. No decision is computed on a partial set; if the cells cannot all be
  counted, the result is reported as "not run to completion", with no verdict.
- **Cost.** About $55-65: coverage $25-35 (blind35's firm averaged $0.21 a cell, about $23 for 105,
  plus at most two Haiku boss redrafts a cell; the stub runs cost nothing), firm about $23, single
  about $9 (blind35's single averaged $0.088). Worst case $0.40 a cell, $126 in all.

## SG1. Spec-gap questions surface rules the drafted checks miss

Added 2026-10-10, before any live run of it. A component eval, not a firm-against-single arm, so
it takes an SG id and the shared paired test above does not apply.

- **Claim.** After the boss drafts its checks, one more call (`antstreet.questions`, prompt
  `spec_gaps_v1.md`) asks the investor at most 5 yes/no questions, and at least one of them is
  about a rule the idea states that the drafted checks would miss.
- **Sets.** *Known*: `bench/spec_gaps/cases.json`, 10 rules the boss's checks missed in a
  false-pass cell of `2026-10-03-false-pass-audit`. The prompt names their gap classes (non-ASCII,
  result types, iterators), so this measures recall on known gaps only. *Held out*:
  `bench/spec_gaps/heldout.json`, about 10 rules quoted from `bench/tasks/*/idea.md`, chosen
  before any held-out run and without reading model output, outside the classes the prompt names
  and outside the known set.
- **Fixed.** Prompt frozen at `spec_gaps_v1`; no prompt change is made on any held-out result.
  Model: the default boss model (`haiku`). One live run per case
  (`python -m antstreet.bench.spec_gaps --cases <set> live --yes-spend --out <file>`), which drafts checks as
  `boss fund` does, then asks. A case whose call fails for the model's own reasons scores as
  missed; a login or usage-limit failure stops the run and is reported, not scored.
- **Primary metric.** Held-out recall: the share of held-out cases whose rule is surfaced by at
  least one question, hand-checked. A question surfaces a rule when its answer decides the rule's
  behaviour for some input the rule covers. The regex scorer (`score`) is reported beside it with
  every disagreement listed; where they differ, the hand check decides. Reported, not decided on:
  known-set recall, and the share of cases whose questions are at most 5 and all yes/no. 95%
  Wilson intervals for each proportion.
- **Decision.** "Useful beyond known gaps" only if held-out hand-checked recall is at least 5 of
  10 (50%). Below that: "not shown". Known-set recall is not evidence of generalisation, whatever
  it is.
- **Limits fixed now.** About 10 cases a set, one model, one run per case, so a Wilson interval
  at 5/10 is about [24%, 76%]; only a large effect can be told from chance. Each case's checks are
  a fresh draft, not the draft of the original false-pass cell.
- **Cost.** About $0.30 a set by `estimate`; owner approved about $2-3 in all; stop above $4.

## E10 (DRAFT). Routed teams against single agents on CLI-Tool-Bench Python

DRAFT — not registered until merged with the frozen pool's digest filled in. Written 2026-10-21,
before any E10 cell, pilot included. Until a commit fills every `<...>` below and merges, nothing
here is a pre-registration (S1), and this heading takes its `E10.` form, counted with the others,
only in that commit.

- **Why.** Every earlier experiment ran Haiku on tasks a single Haiku mostly solves (blind35: firm
  64/105, single 62/105). A pilot of new, larger private tasks (hard-v1, 2026-10-16) did not make
  them harder: Haiku 5.5 delivered three of five on 3/3, 2/3 and 3/3 runs, the other two missed by
  1-4 checks, and its misses were mostly spec ambiguities. E10 asks the fund's question on an
  external pool where a single Haiku fails: does a routed team, a stronger boss with cheap workers, deliver
  more than one agent at the same dollar budget per task?
- **Pool, by contract.** CLI-Tool-Bench (arXiv 2604.06742), its Python subset (34 tasks upstream):
  a natural-language spec of a command-line tool, graded by running the product on inputs and
  comparing with an oracle. The converter (branch `feat/bench-clitoolbench`, not merged when this
  was drafted) is described by what it must do, not by its code:
  - Freeze once, outside the repository: clone each oracle repo at a pinned commit, install it,
    generate its cases with the fuzzer seeded (the upstream fuzzer is unseeded), run each case
    against the oracle and record argv, stdin, input files, exit code, stdout and file-system
    change. Network and third-party code run only here, never during a cell.
  - Keep only the deterministic tiers. Each frozen case carries its own comparison, exact (EM) or
    the benchmark's fuzzy match (FM), fixed per case before the digest. The upstream SM tier is an
    LLM judge (GPT-5.4) and is dropped: no model scores any result (S7).
  - Write each task in the imported layout (`bench/METHOD.md`, "Imported tasks"): the upstream spec
    as `idea.md`, word for word, the same for every arm; one pytest test per frozen case in
    `hidden/`; `meta.json` with the `imported` block, the oracle's repo, commit and creation date,
    and the entry point both arms are told to provide.
  - Validate before the digest: every case passes on the oracle on 3 runs, none passes on an empty
    product, every test collects. A task that fails this, or whose oracle repo is gone (one is
    already 404), or that the owner's dependency rule excludes, is dropped before the digest with
    its reason listed. After the digest no task is dropped and no case changed; a grading defect
    found later is reported, and the result is given with and without that task (S1).
  - The pool is that folder: `N_pool` = `<N_POOL>` tasks (at most 34), ids `<POOL_IDS>`, digest
    `<POOL_DIGEST>` (64 hex, `task_set_digest`, checked with `python3 -I
    scripts/verify_task_set.py <POOL_DIR> --expect <POOL_DIGEST>`), 16-hex set hash `<SET_HASH>`.
    The folder lives outside the repository.
- **Pass rule, fixed now.** A cell delivers when every frozen case of its task passes; a case that
  did not run (collection error, timeout, no product) fails. This is stricter than the upstream
  headline: many upstream misses are output-format fidelity (side-effect match 45.7% falls to 23.5%
  at EM, per the E10 source brief of 2026-10-21, not public), so delivery here will be low for
  every arm. That is the rule anyway; no case is relaxed after any cell runs. The secondary figure, the case pass fraction, gives partial credit.
- **Arms.** All model ids pinned (S2). One per-cell budget `B` for every arm (S8, below). The firm
  arms take `--max-tasks 3`, so a boss may split the tool into up to three tasks (the integration
  KPI needs a split to exist), `--boss-cap 2.00 --boss-timeout 900` (the $0.25 and 300 s defaults
  were set on small specs; an Opus draft of a long spec would be cut off), and otherwise the `fund`
  defaults (`--slice 0.10`, `--stall-slices 2 --max-slices 6`, one round).
  1. `single-haiku`: single, `claude-haiku-5-5`.
  2. `single-sonnet`: single, `claude-sonnet-5-5`.
  3. `single-opus`: single, `claude-opus-5-5`.
  4. `firm-sonnet`: boss `claude-sonnet-5-5`, workers start on `claude-haiku-5-5`, `--dispatch rules
     --max-tier sonnet --tier-models haiku=claude-haiku-5-5,sonnet=claude-sonnet-5-5`: a fired worker
     is replaced once by a pinned Sonnet worker.
  5. `firm-opus`: boss `claude-opus-5-5`, the same worker ladder (Haiku, then Sonnet).
  6. `firm-sonnet-nostep`: arm 4 plus `--no-step-up`, the U2 control: same route and pins, a fired
     worker replaced on the same model.
- **Equal budget.** `B` = 2 x the median cost of the pilot's `single-opus` cells, rounded up to the
  cent, recorded in a dated change below before any stage-S cell (owner decision, 2026-10-14).
  Planning value about $8 (range $4-16). Every arm's `--budget` is `B`. As in every earlier
  experiment, the single arm's one slice is capped at 80% of `B` and the firm's boss calls are
  booked on top of `B` (worst case `B` + $2.00 a draft), so the firm may spend more: each arm's
  mean cost per assigned cell is reported beside every verdict, and a firm win that came with a
  higher spend is reported as a cost, not a win. Wall clock is not equalised: a single agent has
  one slice of at most 15 minutes, a firm worker that much per slice.
- **Stages.**
  1. *Pilot.* 3 tasks drawn from the pool by `random.Random(0).sample(sorted(ids), 3)`, every arm, 1
     rep, at a pilot budget of $10 a cell. It measures per-cell cost and time, checks every cell's
     model ids, and checks grading end to end. It fixes `B` and nothing else; its cells are never
     counted in S or D, and its tasks stay in the pool. If 2 or 3 of the `single-opus` cells end
     `capped`, their median is censored: `B` is then $16 and the censoring is recorded.
  2. *Stage S (selection, S5).* `single-haiku` only, every pool task, 3 reps, at `B`. A task is kept
     when it has 3 counted runs and at most 1 delivered (delivered ≤ 1/3). Infrastructure cells are
     moved aside and rerun until each task has 3 counted runs. A dated change then records the
     kept ids, their count `K` and the SHA-256 of the sorted, newline-joined ids, before any
     stage-D cell.
  3. *Stage D (decision).* Fresh cells only (no stage-S or pilot cell is reused), `--only` the kept
     ids, 3 reps, every arm, with `--expect-set-digest <POOL_DIGEST>`. Run in two parts so the
     cheaper arms run first: **D1** = arms 1, 2, 4 and 6 (every primary comparison lives here);
     **D2** = arms 3 and 5, after D1 and only on the owner's go. Within each part the arms are
     interleaved task by task (S3). Every D cell runs from one recorded commit.
- **If too few tasks survive.** `K` ≥ 20: stage D runs. 10 ≤ `K` < 20: stage D runs only on the
  owner's yes, and its verdicts are labelled as below with the larger MDE. `K` < 10: no stage D;
  stage S is published as the result ("too few hard tasks to compare"). The keep rule is never
  loosened to raise `K`.
- **Pilot-scale, said now (S6).** The pool is below the 50-task floor: at most 34 tasks, likely
  20-34 after selection. E10 on this pool is a pilot-scale decision: each verdict is computed by
  the fixed test and reported with its minimum detectable effect beside it, and a "shown" from it
  is a lead to repeat on a larger pool, not a finding. With an assumed SD of the per-task paired
  difference of 0.4 (hard-v1's assumption, not measured), the effect detectable with 80% power at
  the 95% level is about 2.8 x 0.4 / √K: 0.19 at K = 34, 0.20 at 30, 0.25 at 20, 0.35 at 10 (19 to
  35 points of delivery). After stage D the observed SD replaces the assumption and the MDE is
  reported from it.
- **Seen-possible (S4).** The oracle repos were created 2024-03 to 2026-03, before the 5.5 models'
  training ended. Every task is reported as "seen-possible", never "unseen"; each task's repo
  creation date is listed with its result. No claim is split on it.
- **Primary KPI.** Delivery (pass rule above), paired by task, 10,000 task resamples, seed 0 (S9).
- **Hypotheses, each a separate claim (a pass on one is never reported as a pass on another).**
  - **H1 (primary).** `firm-sonnet` delivers more than `single-sonnet` at `B`: shown only if the
    paired interval of `firm-sonnet` minus `single-sonnet` lies above 0. Direction: firm higher.
    Confidence it is shown: 10%. Most likely outcome (60%): not shown, point estimate at or below 0.
  - **H2.** `firm-sonnet` delivers more than `single-haiku` at `B`: shown only if that interval lies
    above 0. Confidence: 35%. Stage S selected these tasks on `single-haiku`'s failures, so only
    fresh cells are compared (S5).
  - **H3.** `firm-opus` delivers more than `single-opus` (D2): as H1. Confidence: 10%.
  - **H4 (U2).** `firm-sonnet` delivers more than `firm-sonnet-nostep`: as H1. Confidence: 5%; the
    U2 design expects 4-8 step-ups per 100 firm runs, too few to move delivery.
- **Secondary KPI, named now.** Hidden-check pass fraction: per task, the mean over its counted runs
  of the cell's passed cases over its cases, paired the same way, for H1-H4. Reported, never
  decided on.
- **Headlines beside delivery, reported per arm, not decided on.** Both answer outside critiques:
  wrong boss checks ("garbage in, garbage out") and work that fails when the workers' parts meet.
  - **False-pass rate** (KPI 2), with its Wilson interval: the firm said done when every visible
    check passed; the single arm when its last status was `done`. Every hidden case here is
    external, so a false pass is not the boss's own check grading itself.
  - **Integration failure**: counted firm cells whose approved term sheet had 2 or more tasks, where
    every task's worker passed all its visible checks and at least one hidden case failed, over the
    counted firm cells with 2 or more tasks where every visible check passed; beside it, the share
    of firm cells that split at all. "n/a" for single arms. With fewer than 10 split cells in an
    arm, the counts are given without a rate.
- **Reported, not decided on.** Cost per assigned cell and the pooled cost per delivered task (S8);
  `paired --kpi cost_per_delivery` for H1-H4; time; investor questions; the step-up rescue
  supplement for arms 4-6 (step-ups, rescue rate with its Wilson interval, $/rescue, same-tier
  replacements; METHOD "Step-up rescue"); cells with a timed-out hidden case; the infrastructure
  exclusions per arm, by kind. Check quality is not measured (no reference in our format).
- **Prerequisites, each merged with tests before the stage that needs it.** Before the pilot: the
  converter, the frozen pool and its digest (owner's OK for the one-time network freeze). Before
  stage D: `paired --kpi hidden_fraction` (the secondary above) and a command counting
  integration failures from result files and ledgers, both tested on synthetic cells. Until they
  exist the two figures are not reported; they are never hand-computed for a verdict.
- **Stop rules.**
  - *Infrastructure.* The runner stops after 3 cells in a row end in the same infrastructure kind
    (login, usage limit, unexpected model, no model recorded). A stop is a pause: the cause is
    fixed, the cut cells moved aside, and the run resumes until every cell is counted. The runner's
    count restarts with each invocation, so the stage-D driver also stops when an invocation exits
    non-zero. No verdict is computed on a partial set; cells that cannot all be counted give "not
    run to completion".
  - *Provider drift.* Every invocation passes `--expect-models` with exactly its arm's ids: a cell
    that names any other id is an infrastructure failure, never counted, and three in a row stop
    the run. A provider change under the same id cannot be seen by this guard; interleaving (S3)
    puts it on both sides of each D1 and D2 comparison, and only D2-against-D1 comparisons, which
    are not interleaved, are exposed to it.
  - *Budget.* Each stage stops when its known spend passes its ceiling: pilot $60, stage S $55, D1
    $750, D2 $1,250 (the high column below, rounded up). After the pilot each later stage is
    re-estimated from the pilot's per-cell medians in the same dated change that fixes `B`; a
    stage also stops at 1.5 x its re-estimate. A budget stop is a pause for the owner, who may fund
    the rest; otherwise "not run to completion".
  - *Floor.* If no pilot cell delivers (0 of 18), the owner decides before any stage-S cell whether
    E10 runs with delivery primary as written or, by a dated change, makes the case pass fraction
    primary. That choice is made before any stage-S or stage-D result exists.
- **Machine (S11).** `--jobs 1` (a slice cut off mid-run has its spend on no ledger line, so one
  cell at a time keeps such a loss visible and small). A run is
  detached (`nohup` under `caffeinate -dimsu`), on mains power, with no other test suite, build or
  benchmark running. `uptime` is written to the run log before and after every invocation, with
  the commit SHA, `claude --version` and the OS version; a part whose 1-minute load average stayed
  above 4 for an invocation is reported with it. Cells cut by sleep or a kill are moved aside and
  rerun, never deleted.
- **Licence and publication (S10).** The CLI-Tool-Bench repository has no LICENSE (the oracle repos
  are MIT or Apache). Until its authors answer, the converter, the commands, the digest, every
  result file, ledger and product are published, and the frozen task files are not; text from a
  spec inside a published file (term sheets, transcripts) is withheld or redacted the same way.
  Anyone can rebuild the pool with the converter and check it against `<POOL_DIGEST>`.
- **Cost.** Per-cell figures are planning estimates, not measurements: single Haiku from the E10
  brief ($0.05-0.20, up to $0.50 if tasks are 2.5x the size it assumed), the rest from the hard-v1
  design, each 0.5x-2x. No CLI-Tool-Bench cell has run. Stage D assumes `K` = 30 (low 20, high 34),
  3 reps.

  | Arm | $/cell low-mid-high | Pilot (3 cells) | Stage S (`N_pool` x 3) | D (K x 3), mid | D low-high |
  |---|---|---|---|---|---|
  | single-haiku | 0.05-0.10-0.50 | $0.30 | $10 ($5-51) | $9 | $3-51 |
  | single-sonnet | 1.00-2.00-4.00 | $6 | | $180 | $60-408 |
  | firm-sonnet | 0.35-0.70-1.40 | $2.10 | | $63 | $21-143 |
  | firm-sonnet-nostep | 0.35-0.70-1.40 | $2.10 | | $63 | $21-143 |
  | single-opus | 2.00-4.00-8.00 | $12 | | $360 | $120-816 |
  | firm-opus | 1.00-2.00-4.00 | $6 | | $180 | $60-408 |

  Pilot $28.50 ($14-58). Stage S $10 ($5-51). D1 (arms 1, 2, 4, 6): 90 task-reps x $3.50 = $315
  ($105-745). D2 (arms 3, 5): 90 x $6.00 = $540 ($180-1,224). Total about $894 (range $304-2,078),
  of which $354 is spent before D2 (pilot, S, D1). Worst case if every cell spent its whole budget
  at `B` = $8: $6.40 a single cell (80% of `B`), at least $10 a firm cell (`B` plus a $2.00 boss
  draft), so D1 alone could reach 90 x $32.80 = $2,952; the budget stops above end any stage long
  before that.
  Needs the owner's yes per stage before any spend.
- **Commands.** `<POOL_DIR>`, `<POOL_DIGEST>`, `<B>` and the id lists are filled by the commit that
  registers this entry (pool, digest) and by the dated changes after the pilot (`B`) and stage S
  (kept ids).

  ```bash
  H=claude-haiku-5-5 S=claude-sonnet-5-5 O=claude-opus-5-5
  POOL=<POOL_DIR> DIGEST=<POOL_DIGEST>
  python3 -I scripts/verify_task_set.py "$POOL" --expect "$DIGEST"
  FIRM="--max-tasks 3 --boss-cap 2.00 --boss-timeout 900 --dispatch rules --max-tier sonnet --tier-models haiku=$H,sonnet=$S"
  arm() {  # arm NAME OUT_PREFIX BUDGET REPS [runner args...]
    local name=$1 out=$2 budget=$3 reps=$4; shift 4
    local common=(--tasks "$POOL" --expect-set-digest "$DIGEST" --budget "$budget" --reps "$reps" --jobs 1)
    case $name in
      single-haiku)  set -- --arms single --model $H --expect-models $H "$@" ;;
      single-sonnet) set -- --arms single --model $S --expect-models $S "$@" ;;
      single-opus)   set -- --arms single --model $O --expect-models $O "$@" ;;
      firm-sonnet)   set -- --arms firm --model $H --boss-model $S --firm-args "$FIRM" --expect-models $H,$S "$@" ;;
      firm-sonnet-nostep) set -- --arms firm --model $H --boss-model $S --firm-args "$FIRM --no-step-up" --expect-models $H,$S "$@" ;;
      firm-opus)     set -- --arms firm --model $H --boss-model $O --firm-args "$FIRM" --expect-models $H,$S,$O "$@" ;;
    esac
    uptime; uv run python -m antstreet.bench.run --out "bench/results/raw/$out-$name" "${common[@]}" "$@"; local rc=$?; uptime; return $rc
  }

  # Pilot: 3 tasks, every arm, 1 rep, $10 a cell.
  PILOT=$(uv run python -c "import random,sys; from pathlib import Path; from antstreet.bench.tasks import load_tasks; print(' '.join(random.Random(0).sample(sorted(t.id for t in load_tasks(Path(sys.argv[1]))), 3)))" "$POOL")
  for t in $PILOT; do for a in single-haiku single-sonnet firm-sonnet firm-sonnet-nostep single-opus firm-opus; do
    arm $a e10-pilot 10.00 1 --only $t || exit 1; done; done
  uv run python -m antstreet.bench.kpi bench/results/raw/e10-pilot-*

  # Stage S: single Haiku, every task, 3 reps, at B; then the keep rule.
  arm single-haiku e10-s <B> 3
  uv run python - bench/results/raw/e10-s-single-haiku <<'EOF'
  import hashlib, sys
  from collections import defaultdict
  from pathlib import Path
  from antstreet.bench.results import load_results
  runs = defaultdict(list)
  for r in load_results(Path(sys.argv[1])):
      if r.arm == "single" and r.counted:
          runs[r.task].append(r.passed)
  short = sorted(t for t, v in runs.items() if len(v) != 3)
  if short:
      sys.exit(f"not 3 counted runs: {short}; rerun their infrastructure cells first")
  kept = sorted(t for t, v in runs.items() if sum(v) <= 1)
  print(len(kept), "of", len(runs), "kept:", " ".join(kept))
  print("kept-ids sha256:", hashlib.sha256("\n".join(kept).encode()).hexdigest())
  EOF

  # Stage D: fresh cells, kept ids, 3 reps, at B, interleaved task by task.
  KEPT="<KEPT_IDS>"
  for t in $KEPT; do for a in single-haiku single-sonnet firm-sonnet firm-sonnet-nostep; do   # D1
    arm $a e10-d <B> 3 --only $t || exit 1; done; done
  for t in $KEPT; do for a in single-opus firm-opus; do                                        # D2
    arm $a e10-d <B> 3 --only $t || exit 1; done; done

  # Decisions (S9), each pasted whole into the write-up.
  D=bench/results/raw/e10-d
  uv run python -m antstreet.bench.paired $D-firm-sonnet $D-single-sonnet --kpi delivery          # H1
  uv run python -m antstreet.bench.paired $D-firm-sonnet $D-single-haiku --kpi delivery           # H2
  uv run python -m antstreet.bench.paired $D-firm-opus $D-single-opus --kpi delivery              # H3
  uv run python -m antstreet.bench.paired $D-firm-sonnet $D-firm-sonnet-nostep --arm-b firm --kpi delivery  # H4
  uv run python -m antstreet.bench.kpi $D-*
  ```

  `paired` warns when the two sides' worker models differ (H1-H3): expected here, since the model
  is part of what each arm is.

  Each stage is run detached as a script holding these lines (`nohup caffeinate -dimsu bash
  e10-<stage>.sh > e10-<stage>.log 2>&1 &`), after the same lines with `--dry-run` have listed its
  cells and checked the digest. The scripts and logs are published with the results.
- **Not in E10.** `--fix-after-stop` with the critic (E4c's question) and a pilot recorded at a
  loose firing policy (`--stall-slices 4 --max-slices 10`, to calibrate the breakers) need their own
  entries. hard-v1 and NL2Repo are other pools, not this one.

## Not tested, and why

Debate, personas and extra roles (product manager, consultant, demo writer, judge) show no gain at
equal compute in the literature. They stay off by default and are not claimed to improve results.

## Changes to this plan

- 2026-10-03: the baseline runs before this plan (final3, new18) gave the single arm a sentence
  saying hidden checks would judge it, which the firm's builder did not get. Both arms now get the
  same instruction (`solo_v2`, `builder_v4`); `bench/results/2026-10-03-blind35/` is the baseline
  every experiment here compares against.
- 2026-10-04: added E6 (per-task dispatch), before any run of it.
- 2026-10-04: added E6's fourth arm, `cascade`, before any run of it.
- 2026-10-05: E6's decision rule uses the paired cost per assigned cell, the interval the code computes; the pooled cost per delivered task is reported beside it. No E6 run had happened.
- 2026-10-05: the `cascade` arm is compared on the primary KPI (cost per assigned cell), as every arm
  is since that day's rule change. No E6 run had happened.
- 2026-10-05, before any E4 run: E4 runs blind35's 35 tasks x 3 reps, Haiku boss and workers, all
  three arms fresh, each in its own `--out`. Firm arms: `--budget 0.40 --firm-args "--slice 0.20"`,
  the critic arm adding `--roles critic --fix-budget 0.30`. Self-review: `--arms single-review
  --budget 0.40` (slice caps $0.24 + $0.08). Worst-case spend per cell: self-review $0.32, firm $0.65
  (rounds $0.40 + the boss draft cap $0.25), firm with critic $1.10 (plus the critic cap $0.15 and the
  fix round $0.30). The same budget for every arm cannot be set: the boss and critic caps alone are
  $0.40, and every round keeps a $0.10 reserve, so a $0.40 firm-with-critic cell would leave its
  workers about $0.06. Cost per cell is reported beside delivery under the fair-baselines rule, so a
  win bought by spending more counts as a cost. The decision rule (firm with critic against
  self-review, paired delivery) is unchanged; firm with critic against firm is reported beside it.
- 2026-10-05, before any E5 run: E5's arms, sample and test are fixed. "Single at the firm's mean
  dollar spend" cannot be forced: the single agent stops on its own. In `blind35` its 105 cells cost
  $0.0883 on average and $0.1879 at most, none capped, under a cap of $0.32 (`SLICE_SHARE` 0.8 of a
  $0.40 cell). The cap equal to the firm's mean spend ($0.2149, `--budget 0.268625`) is above every
  one of those cells too, so it would change nothing but the label. So E5 gives both arms the same
  cell budget, $0.40 (the fair-baselines rule; the single cap of $0.32 is above the firm's mean
  spend), and reports each arm's actual mean spend beside the result. Tasks: the 35 `blind35` tasks,
  so each has 3 earlier runs per arm at the same settings; the 24 others have none. 5 runs per task
  and arm, Haiku boss and workers, firm `--slice 0.20` as in `blind35`; commands in
  [METHOD.md](METHOD.md), "Reliability arms (E5)". Infrastructure cells are moved aside and rerun
  until every task has 5 counted runs per arm (B71); `paired --kpi pass_all` refuses a task whose
  runs differ in number. Primary KPI: `python -m boss.bench.paired bench/results/raw/e5-firm
  bench/results/raw/e5-single --kpi pass_all`, task resamples 10,000, seed 0. Decision: "shown"
  only when the 95% interval of firm minus single pass^5 lies above 0; otherwise "not shown",
  whatever the point estimate. In `blind35` only 6 of 35 tasks were delivered on every run by one
  arm and not the other, so the smallest gain this can show is 4 tasks gained with none lost
  (+0.11); with 1 lost it takes 7, with 2 lost 9. Reported, not decided on:
  `python -m boss.bench.kpi` on both folders, and `paired` with `--kpi delivery` and
  `cost_per_delivery`.
- 2026-10-07: added E4b (the critic with a $0.40 cap), after E4's result and before any E4b run.
- 2026-10-07, before any E4b result was read: the critic call's time limit rises from 300 s to 900 s for E4b. In the first 7 E4b cells, 4 critic calls hit the 300 s limit (E4 had 1 in 105), so with the $0.40 cap the time limit, not the critic, would have decided them. Those 7 cells are set aside unread and E4b restarts from zero with both changes; everything else is unchanged.
- 2026-10-10: added E4c (the E4b critic with --fix-after-stop), before any E4c run.
- 2026-10-10: added E9 (the firm with `--coverage` against a same-commit firm and single agent), before any E9 run.
- 2026-10-13, before any E4c run: E4c pins `claude-haiku-4-5-20251001`. The CLI's `haiku` alias now resolves to `claude-haiku-5-5` (seen in E9's cells), while E4's self-review cells, E4c's baseline, ran on `claude-haiku-4-5-20251001`; without the pin E4c would compare two models. Nothing else changes.
- 2026-10-10: added SG1 (spec-gap questions, known and held-out sets), before any live run of it.
- 2026-10-10, after the SG1 runs: the "about $0.30 a set" cost line was 6 times low (measured $1.72 a set, thinking tokens were not counted); `estimate` is corrected. Nothing else in SG1 changed; the result is in `bench/results/2026-10-10-spec-gaps/README.md`.
- 2026-10-10, after the SG1 runs, wording only: the registered `live` command lacked the `--out <file>` the runner requires (the runs passed it), and the code now stops only on the registered login and usage-limit failures (any other failed call scores as missed, as registered; no SG1 call failed that way). No rule or bar changed.
- 2026-10-13, after the E9 run (a record, not a change to its rule): E9's runner passed the `haiku` alias, and the alias moved from `claude-haiku-4-5-20251001` to `claude-haiku-5-5` while the arms ran one after another, so 80 of the coverage arm's cells ran on Haiku 4.5 and every firm and single cell on Haiku 5.5. E9's verdict stands as computed; its write-up reports it as not a fair test of `--coverage`. Later experiments pin dated model ids.
- 2026-10-13, E4c stopped by owner decision before completion: experiments now use the latest models only (`claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`), and E4c's baseline ran on `claude-haiku-4-5-20251001`. It had 2 complete cells and 2 partial ones; no result was read and no verdict is computed ("not run to completion", as its infrastructure rule says). The cells are kept, not deleted. Its question, a fix round after a locked round (`--fix-after-stop`), moves to the next experiment on a harder benchmark.
- 2026-10-13, a fix to a task, not to the plan: the `roman` strict check (`test_from_roman_strict.py`) looked up each of 19,607 strings in a 3,999-entry dict, and the gate's comparison guard walked that dict on every lookup, so it took 13.8 s through the gate instead of 0.04 s. It now uses `dict.get`, which the guard does not wrap, and asserts the keys are exact `str` so the lookup still runs no product code; what it accepts and rejects is unchanged. The 59-task set hash moves from `0a83fc97a753b08c` to `ed6fd905c106f6a6`, and the original 17's from `c130282a6eec5fe8` to `42c28f8aab61d518` (`roman` is one of them). Earlier mutant-kill data for `roman` counted two false kills: with a 10 s limit the mutants `from_roman_strips_whitespace` and `to_roman_accepts_bool` were "killed" by this check timing out, though it passes them; `from_roman_rejects` and `to_roman_types` kill them. Published numbers are kept as recorded, and the `roman` mutant-kill figures in them are not directly comparable with a run on the new file. The validation limit returns from 120 s to 30 s.
- 2026-10-21: E10 drafted, before any E10 cell (pilot included). It is a draft, not a
  registration, until the commit that fills in the frozen pool's digest merges.
