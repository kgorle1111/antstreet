# Pre-registration: where a firm should beat one agent

Written 2026-10-03, before any of these runs. The hypotheses, arms, metrics, sample sizes and
decision rules below are fixed; a change after a run starts is recorded here with its date and
reason, and the run it affects is reported under both rules. Why these five and not others:
[EVIDENCE.md](EVIDENCE.md).

## What every experiment shares

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
- **Primary KPI.** Cost per delivered task: the TOTAL spend over all assigned cells of an arm,
  delivered or not, each cell including its boss call, divided by the number of delivered cells,
  compared between arms paired by task with a 10,000-resample bootstrap of tasks. What the code
  computes differs, and the analysis reports both: `python -m boss.bench.kpi` prints exactly this
  ratio, pooled over the arm's counted cells; `python -m boss.bench.paired --kpi cost_per_delivery`
  pairs the per-task MEAN cost of a counted cell (all of a task's runs, delivered or not), with no
  division by deliveries, because a task that delivered nothing has no ratio and dropping it would
  favour the arm that fails. The pooled ratio is the headline; the paired interval is on cost per
  assigned cell.
- **Delivery guard.** Dispatch minus each fixed arm, 95% interval with a lower bound at or above
  -0.10 (the blind run's own interval was [-0.076, +0.124], so this is the narrowest guard the
  sample supports). Every assigned cell counts in the denominator, a cell that stopped for a wrong
  model (T69) included: it is never relabelled `infrastructure`. Those stops are still reported
  apart.
- **Not shown if.** Dispatch is default-on only if its cost-per-delivered interval is below zero
  against fixed Sonnet AND (below zero against fixed Haiku, or delivery is higher with the interval
  above zero). Otherwise it stays opt-in and fixed Haiku stays the default.
- **Reported apart.** Escalations fired, refused and rescued (a fired task that later delivered);
  cells whose run stopped for a wrong model (T69) are reported apart, not counted as a
  failure of the arm (no command separates them yet, B92).
- **Cost.** Every Sonnet figure is an assumption (3 times Haiku on the same tokens, the ratio
  `budget.py` uses): no Sonnet or Opus cell has ever run. About $160 for both sets (range $110 to
  $210). Stage 1 first, about $55: 12 tasks, 3 runs, plus the 8 multi-file tasks once; stop if
  dispatch never escalates or an escalated cell never delivers. Needs the owner's yes before any
  spend.

## Not tested, and why

Debate, personas and extra roles (product manager, consultant, demo writer, judge) show no gain at
equal compute in the literature. They stay off by default and are not claimed to improve results.

## Changes to this plan

- 2026-10-04: added E6 (per-task dispatch), before any run of it.
