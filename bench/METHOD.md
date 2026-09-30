# Benchmark method

What the benchmark measures, how, and what its numbers can and cannot support.

## Question

Given the same idea, model, tools and budget, does the firm (boss writes checks, worker builds
against them, gate decides) deliver working code more often, or more cheaply per working result,
than a single agent given the idea directly?

## Tasks

- Each task is a folder under `bench/tasks/`: `idea.md`, `meta.json`, `hidden_checks/`, `reference/`.
- `idea.md` states the module and function names exactly, and every behaviour the hidden checks
  test. There are no hidden requirements.
- Products are standard-library-only Python modules.
- A task is valid only if every hidden check fails on an empty workspace and passes on the
  reference solution. `validate_task` enforces this before any run.
- The task set is identified by a hash of every task file. Each result records it.

## Arms

| | single | firm |
|---|---|---|
| Input | `idea.md` text | `idea.md` text |
| Model | same | same (boss and worker) |
| Tools | Read, Write, Edit in its own folder; no shell | the same for the worker; the boss has none |
| Slice cap | 80% of the cell budget | 80% of the cell budget |
| Sees checks | none | the boss-written term-sheet checks, in the prompt |
| Extra spend | none | the boss's drafting call (capped separately) |

- Neither arm can run code. Neither ever sees the hidden checks or the reference.
- The firm arm is `boss fund` with the term sheet **approved automatically**. This is the only
  automated investor decision; a real run has a human there.
- One round, one worker, one slice. Funding rounds and firing are not part of this benchmark yet.

## Scoring

- The gate runs the task's hidden checks on the arm's workspace.
- A cell **passes** only if every hidden check passes.
- The per-check pass fraction is reported as a secondary number.
- For the firm, a cell that passed all of its own visible checks but failed a hidden check is
  counted as **gamed**: the boss's checks were satisfied without the idea being met.

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

## Reproducing

```bash
uv run python -m boss.bench.run --out bench/results/raw/<label> --budget 0.40 --reps 3
uv run python -m boss.bench.table bench/results/raw/<label>
```

Both commands make real model calls or read their results; the first one costs money.
