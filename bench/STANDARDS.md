# Benchmark standards

The rules every AntStreet experiment follows, so a result can be checked, rerun and argued with, and
so a miss is published like a win. [PREREG.md](PREREG.md) holds each experiment's own plan;
[METHOD.md](METHOD.md) says how cells are run and graded; this file is the bar both must meet.

Each standard says how it is held: **enforced** (code refuses to break it, with the mechanism named),
**checked** (a test or a script catches a breach after the fact), or **rule** (a written commitment,
reviewed by hand). A standard is never described as stronger than that.

## S1. Pre-registered before any cell runs

Hypothesis, arms, models, task set (by hash), primary KPI, decision rule, sample size, stop rules
and cost estimate are merged into [PREREG.md](PREREG.md) before the first cell. A change after a
run starts is dated under "Changes to this plan" and the run it affects is reported under both
rules. **Rule**; the dated change log is the record.

## S2. Models pinned by id

Every arm names exact model ids (for example `claude-haiku-5-5`), never an alias: an alias can move
mid-run, which is what made E9 an unfair test. Each cell records the model ids its own logs name,
and `--expect-models` makes a cell on any other id an infrastructure failure that is rerun, never
counted. Routed teams pin each dispatch tier with `fund --tier-models`. **Enforced** once a run
passes `--expect-models`; **rule** that every experiment does.

## S3. Arms interleaved

All arms of an experiment run in one invocation, task by task (`--arms single firm`), so the cells
being compared run close together in time. That shrinks, but does not remove, the chance that
something outside the repository (a model alias, a provider change, machine load) differs between
arms; S2's model guard catches the model case, and the rest is reported when found.
**Rule**; the runner orders cells task by task when given several arms.

## S4. Tasks the models have not seen

External benchmarks are preferred when they post-date the models' training. For older ones (for
example NL2Repo-Bench, whose libraries are famous), results are split by how likely the model has
seen the code, and "unseen" is never claimed. Internal tasks written for an experiment stay private
until it runs; their set's SHA-256 is in the pre-registration before any cell, and the tasks are
published with the results. **Rule**. **Enforced** once a run passes `--expect-set-digest`, which refuses a folder that is not
the registered one before any cell; without it the runner only compares the 16-hex task-set hash
when resuming a saved cell, and the tests pin the shipped sets' hashes.

## S5. Difficulty selected on separate runs

Tasks are picked as hard on one batch of runs (where a single agent fails), and the decision uses
fresh runs only. Selecting and comparing on the same runs would favour the team by regression to
the mean. **Rule**.

## S6. Large enough to see an effect

A pool has at least 50 tasks and each arm at least 3 runs per task where cost allows. Every
experiment states the smallest effect it can detect; a pool smaller than its stop size is reported,
not decided on. **Rule**.

## S7. Graded by hidden tests, not by a model

Hidden tests decide: deterministic, run in the OS sandbox, never shown to any arm. A timeout is
reported apart from a failure. A task's reference passes its hidden checks before the task is used,
and its known-wrong solutions fail them. No language model scores any result. **Enforced** for
hidden-check secrecy and task validation (`tests/test_bench_tasks.py`, `tests/test_blinding.py`).

## S8. Fair baselines

A team is compared with a single agent at the same dollar budget per task, and, where named, with a
stronger single model at that budget. A win that only comes from spending more is reported as a
cost, not a win. **Rule**; the budget per cell is recorded on every result.

## S9. One fixed statistical test

Paired by task, 10,000 bootstrap resamples of tasks, seed 0. A benefit is claimed only when the 95%
interval excludes zero in the team's favour; otherwise the verdict is "not shown", whatever the
point estimate. No decision is computed on a partial set of cells; infrastructure exclusions are
counted and reported. **Enforced** by `python -m antstreet.bench.paired`, which every write-up pastes.

## S10. Everything published

Every cell, its signed ledger, the scripts and the exact commands are published with the write-up,
with enough instruction for someone else to rerun it. Misses are published like wins. **Rule**.

## S11. A quiet, awake machine

Grading has hard timeouts, so a run is detached from the shell that started it, the machine cannot
sleep, and no other heavy work runs beside it. Cells interrupted by sleep or a kill are moved aside
and rerun, never deleted. **Rule**.

## S12. Wording follows the verdict

A result's headline is its decision rule's verdict. A hypothesis is labelled as one, with a
confidence. Hand-scored numbers get an independent check before they are published. **Rule**.
