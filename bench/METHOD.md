# Benchmark method

What the benchmark measures, how, and what its numbers can and cannot support.

## Question

Given the same idea, model, tools and budget, does the firm (boss writes checks, worker builds
against them, gate decides) deliver working code more often, or more cheaply per working result,
than a single agent given the idea directly?

## Tasks

- Each task is a folder under `bench/tasks/`: `idea.md`, `meta.json`, `hidden_checks/`, `reference/`,
  and `mutants/` (known-wrong solutions; used only by the draft evaluation below).
- `idea.md` states the module and function names exactly, and every behaviour the hidden checks
  test. There are no hidden requirements.
- Products are standard-library-only Python modules.
- A task is valid only if every hidden check fails on an empty workspace and passes on the
  reference solution. `validate_task` enforces this before any run.
- The task set is identified by a hash of every task file. Each result records it.
  The hash encoding was made unambiguous on 2026-09-30: the same 17 task files were
  `7a212cdcc5f4f466` before and are `c130282a6eec5fe8` after. Results recorded under the old
  value ran against identical files.
- `mutants/` is left out of that hash: no arm sees or is scored on a mutant, so adding one must not
  make old and new results look like they ran against different tasks. A test pins the hash.

## Arms

| | single | firm |
|---|---|---|
| Input | `idea.md` text | `idea.md` text |
| Model | same | same (boss and worker) |
| Tools | Read, Write, Edit in its own folder; no shell | the same for the worker; the boss has none |
| Slice cap | 80% of the cell budget, one slice | `boss fund` defaults, or `--firm-args` |
| Sees checks | none | the idea word for word, then the boss-written checks |
| Extra spend | none | the boss's drafting call (capped separately) |

- Neither arm can run code. Neither ever sees the hidden checks or the reference.
- The firm arm is `boss fund` with the term sheet **approved automatically**. This is the only
  automated investor decision; a real run has a human there, who is also the filter for a wrong
  boss check.
- Extra `boss fund` options given with `--firm-args` are recorded in every result.
- The single arm gets one slice. The firm may use several within the same budget: the gate's
  feedback between slices is part of what is being measured.

## Scoring

- The gate runs the task's hidden checks on the arm's workspace.
- A cell **passes** only if every hidden check passes.
- The per-check pass fraction is reported as a secondary number.
- For the firm, a cell that passed all of its own visible checks but failed a hidden check is
  counted as **gamed**: the boss's checks were satisfied without the idea being met.
- A boss check that the task's reference solution fails is a **wrong check**: it demands
  something the idea does not. Counted per draft, outside the pass rate.

## Cost

- Costs are the CLI's client-side estimates, not a bill.
- The firm's cost includes the boss's drafting call; its share is shown.
- Events with unknown cost are counted separately and never treated as zero.

## Failure classes

Every failing cell gets one class. The runner sets `infrastructure` when it can tell; the rest
start as `unlabelled` and are classified by hand, with the evidence kept in the cell folder.

- **product**: the harness or the firm's own logic is wrong.
- **model**: the run completed and the model's work failed the checks.
- **grading**: a hidden check or the reference is wrong or ambiguous.
- **infrastructure**: login, rate limit, plan limit, API error, or a worker that did not start
  isolated. Excluded from every rate and listed separately.

## What the sample supports

- A pass rate from `n` cells is reported with its Wilson 95% interval. At 70% and 45 cells that is
  roughly ±13 points.
- Detecting a 10-point difference needs roughly 155-234 paired tasks; a 20-point difference
  roughly 57-77. This set is smaller, so **pass-rate differences between arms are descriptive,
  not claims**.
- What a small set can support: cost per passing cell, the boss's share of cost, and how often
  the firm's visible checks were satisfied while hidden checks failed.
- Model output varies between runs. Each task is run several times per arm and all runs are kept.

## Draft evaluation

The arms above are scored on products. The boss's checks are the weak point (some are wrong; some
do not cover the idea), and a full worker run is too costly to iterate a prompt against. So the
checks are scored alone, as a classifier of implementations, with `python -m boss.bench.drafts`.
Only the boss's drafting call costs money; no worker runs.

- **Precision**: the task's reference is a correct implementation, so it must pass every check.
  A check it fails is **wrong**. Reported as wrong checks over checks, and drafts with any.
- **Recall**: each task has known-wrong implementations, its **mutants**. A draft kills a mutant when
  a *sound* check (one the reference passes) fails on it. A mutant that fails only wrong checks is
  not killed: a wrong check rejects everything, so it detects nothing. Reported as mutants killed
  over mutants, and drafts that kill every mutant.
- Layout: `bench/tasks/<id>/mutants/<name>/<module>.py`, one folder per mutant laid out like
  `reference/`. Hand-made mutants are named for their bug and start with a comment saying what is
  wrong; harvested ones are named `<run>_<arm>` and start with a comment saying where they came from.
- Validation refuses a task with fewer than 3 mutants, and a mutant that is not standard-library
  only, does not import, or passes every hidden check (then it is not wrong).
- Mutants never reach a prompt or a workspace; only the scorer reads them.
- Sources: 23 harvested, the rest hand-made (one plausible bug in a copy of the reference).
  Harvested are the products of the `pilot` and `rerun1` runs that failed a hidden check (Haiku
  workers, rep 1, single and firm arms; empty products skipped).
- Rates over drafts carry Wilson 95% intervals. Drafts that are invalid, capped or fail to log in
  are listed and excluded from every rate, never counted as zero.
- Baseline, `--score-existing` on the boss drafts of past runs (17 drafts each, no spend):
  `pilot` 10 of 134 checks wrong, 38 of 65 mutants killed; `rerun1` 4 of 134 wrong, 39 of 65 killed.
- **Limits**: a small hand-picked corpus. With 3 to 6 mutants a task, one mutant is 17 to 33 points
  of that task's recall, so recall is a coarse figure and a task-level difference is not a claim.
  Harvested mutants come from Haiku runs and lean toward the mistakes Haiku makes; hand-made ones
  are the bugs their author thought of. Several harvested mutants of a task share one bug. A mutant
  is only as wrong as the hidden checks say: a wrong hidden check would make a right product a
  mutant. Killing every mutant does not show the checks cover the idea. In `--score-existing`,
  16 of the 23 harvested mutants are firm-arm products built against those very drafts, and 11 of
  them passed every check of their own draft: they survive it by construction, so the baseline
  recall is biased down. Fresh drafts (`--out`) do not have that bias.

## Reproducing

```bash
uv run python -m boss.bench.run --out bench/results/raw/<label> --budget 0.40 --reps 3
uv run python -m boss.bench.table bench/results/raw/<label>
```

Both commands make real model calls or read their results; the first one costs money.

```bash
uv run python -m boss.bench.drafts --out bench/results/raw/<label> --reps 3 [--prompt NAME]
uv run python -m boss.bench.drafts --score-existing bench/results/raw/<run>
```

The first drafts with the boss (about $0.09 a draft, capped at $0.25); the second spends nothing.
Compare prompts in separate `--out` folders: a folder refuses drafts made with other settings.
