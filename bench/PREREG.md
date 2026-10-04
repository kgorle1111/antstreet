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

## E5. The firm is more reliable across runs

- **Claim.** Firing stalled workers and retrying inside a budget makes a task pass every time
  more often (EVIDENCE: weak; no direct measurement found).
- **Arms.** firm; single at the firm's mean dollar spend; 5 runs per task.
- **Primary KPI.** Reliability: tasks delivered on all 5 runs.
- **Not shown if.** pass^5 is not higher by the paired test.

## Not tested, and why

Debate, personas and extra roles (product manager, consultant, demo writer, judge) show no gain at
equal compute in the literature. They stay off by default and are not claimed to improve results.

## Changes to this plan

None yet.
