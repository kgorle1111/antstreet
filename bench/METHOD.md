# Benchmark method

What the benchmark measures, how, and what its numbers can and cannot support.
Every experiment also meets the bar in [STANDARDS.md](STANDARDS.md).

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
- On 2026-10-02, 18 tasks were added, and on 2026-10-03 24 more: the set has 59 tasks, hash `8a5e54e341cdef2a`. Every result
  recorded before then ran on the original 17, whose files and hash were unchanged then.
- On 2026-10-13 the `roman` strict check (one of the original 17) was rewritten to run faster, with
  the same meaning (see `PREREG.md`). The 59-task set moved from `0a83fc97a753b08c` to
  `ed6fd905c106f6a6` and the original 17 from `c130282a6eec5fe8` to `42c28f8aab61d518`. Results
  recorded under the old values ran on the old roman file.
- On 2026-10-21 the `sudokucheck` `random` check (not one of the original 17) was rewritten to run
  faster, with the same meaning (see `PREREG.md`). The 59-task set moved from `ed6fd905c106f6a6`
  to the hash above; the original 17's hash did not change. Results recorded under
  `ed6fd905c106f6a6` ran on the old sudokucheck file.
- `mutants/` is left out of that hash: no arm sees or is scored on a mutant, so adding one must not
  make old and new results look like they ran against different tasks. A test pins the hash.
- A private task set is pre-registered by a different value, a full 64-hex SHA-256 digest over every
  file in the folder, mutants and hidden checks included. `python3 -I scripts/verify_task_set.py DIR
  --expect DIGEST` recomputes it with the standard library alone, prints it with the 16-hex hash,
  and exits 1 if the folder differs. It shows the files are unchanged since registration, not when
  any run happened.

## Strict validation (opt-in)

`validate_task` has keyword-only options that make it stricter; the defaults are the rules above,
so shipped tasks validate exactly as before. `reference_runs=N` runs the reference N times and every
check must pass every time (flakiness). `check_budget_s` caps each hidden check's gate time on the
reference. `min_mutants` demands that many mutants. `timeout_kills=False` counts a mutant as killed
only when some check fails: a mutant that only hangs a check is reported, because a timeout proves
the check is slow, not that it catches the wrong behaviour. They do not apply to imported tasks.

```bash
uv run python -m antstreet.bench.validate bench/tasks            # as CI validates
uv run python -m antstreet.bench.validate <dir> --strict         # x3, 1 s/check, >= 8 mutants, FAIL-only kills
```

The command prints each task's slowest check and exits 1 with what failed and what to change.

## Imported tasks

A task from an external benchmark can be run through both arms, graded by that benchmark's own
tests instead of hidden checks written here.

- Layout: `idea.md` (the external spec, both arms see it word for word; it may embed code),
  `hidden/` (the benchmark's whole pytest tree, subfolders and data files included), `meta.json`
  with an `imported` block (`source`, `test_path` inside the product, `test_count`), and an optional
  `support/` (harness-owned files laid over the product root while grading, e.g. a shim that
  stands in for the PyPI backport `mock`, which the gate's interpreter lacks).
- Convert a download with `python -m antstreet.bench.imported nl2repo <task-dir> <dest-root>`, then run
  with `--tasks <dest-root>`. External task data is never committed here (the source may carry no
  licence); `<dest-root>` is outside the repository.
- `validate_task` skips the reference, mutant and `def test_` rules (there is no reference solution;
  both arms see the spec equally). It still requires the tree to parse and its static test count to
  equal `test_count`, and runs the tree on an empty product: every test file must be collected,
  nothing may pass, and no import the gate lacks may be left unshimmed.
- Grading: after an arm finishes, the hidden tree replaces `test_path` in a copy of its product and
  one sandboxed pytest runs over it (`--continue-on-collection-errors`). Each test's node id and
  status go in the cell's `hidden` map. A test that did not run (collection error, timeout, no
  product) counts as failed, the map is padded to `test_count`, and a cell **passes** only when all
  of them pass. The "hidden checks" column is then the mean per-test pass fraction.
- Not comparable with the external leaderboard: the product is not `pip install`ed, the workers
  cannot run code, the model is Haiku, and the budget is the cell budget. The boss's checks cannot
  be scored against a reference, so `wrong_checks` is not measured, and the draft evaluation does
  not apply to these tasks.
- Time limits: the tree runs in one pytest process under a suite cap of 180 s, and each test
  (setup, call and teardown separately) gets 30 s of wall clock inside it. Both can be set per
  task with `imported.suite_timeout_s` and `imported.test_timeout_s` in `meta.json` (a whole
  number or decimal of seconds, at most 86400; the task set hash covers them). A test that hits
  its own limit is `timeout` and the rest of the suite is graded as usual. A test that ignores the
  alarm is cut by the suite cap: the tests finished by then keep their status, the one running
  and the tests that never started are `timeout`. A `timeout` counts as failed for the pass
  fraction and the cell, but the table and the scorecard count it apart from a wrong answer
  ("Timed out" line, "with a timed-out hidden check"). Ceiling: the progress log that
  keeps results after a suite kill is unsigned (T12), and tests after a hung one are not run
  individually; add that when a suite is found whose uninterruptible hang is common.

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
- The firm arm is `boss fund` with the term sheet **approved automatically**: every question the
  run asks is answered `a`. That approves the term sheet and funds a later round. It is not a
  ruling, so a disputed or blocked task is set aside, as it was before the investor could rule
  (`boss resume` is not used). A real run has a human there, who is also the filter for a wrong
  boss check and the one who rules on a dispute.
- Extra `boss fund` options given with `--firm-args` are recorded in every result. A saved cell
  whose task set, model, budget or `--firm-args` differ from the run's is refused, not reused: a
  second firm arm (another `--firm-args`) needs its own `--out`.
- A third arm, `single-review`, is the single arm with a self-review slice; see its own section.

## Models

`--model` and `--boss-model` are what a cell asks for, not proof of what ran: an alias such as
`haiku` is resolved by the CLI, and E9 was confounded when the alias moved to a new model mid-run.
Experiments therefore pass pinned ids (`claude-haiku-5-5`, `claude-sonnet-5-5`,
`claude-opus-5-5`), never aliases, and every cell records and checks what ran.

- Each result's `models` is every id the cell's records name, sorted: from each worker log
  (`logs/*.jsonl`, or the firm run's `logs/*.jsonl`), the `system/init` event's `model` and every
  assistant turn's `message.model`, which is the CLI's own report; `<synthetic>` (an API error the
  CLI wrote as a turn) names no model and is left out. For the boss's and the roles' calls it is
  the `model_observed` their `boss_call` or `role_call` event records, the id the CLI reported for
  that call; on a ledger written before that field, or a call that reported none, it is the
  `model` it was launched with, so an alias stays visible and `--expect-models` refuses it. Results written before the field have `models: null`, shown as not
  recorded, never as none.
- With `--expect-models ID[,ID...]`, a cell that names any other id is an **infrastructure**
  failure, whatever its product scored, with `failure_reason` naming the id: what was measured is
  not the model the experiment is about. It is excluded from every figure and moved aside and rerun
  like any other infrastructure cell, and three in a row stop the run (`unexpected_model`), since
  a moved alias fails every later cell too. A saved cell is reused only if its `models` are all
  expected.
- The table's header and the KPI card's `models run` row list the ids per arm or column, excluded
  cells included, so a mixed run is visible at a glance.
- The single arm gets one slice. The firm may use several within the same budget: the gate's
  feedback between slices is part of what is being measured.

## The self-review arm (`single-review`)

For experiment E4: does a single agent that reviews its own work do as well as the firm's loop?
It is the `single` arm with a second slice, and it is graded exactly like `single`.

- Slice 1 is the `single` build. If it ended normally or at its cap, the same session is resumed
  once (`--resume`) with the fixed prompt `src/antstreet/prompts/self_review_v1.md`, which asks it to
  review its work against the request and fix what it finds. A build that ended any other way is
  not reviewed and stands as the cell's outcome.
- The two caps share what `single` gets: 80% of the cell budget, split 75% to the build and 25%
  to the review (`BUILD_SHARE` in `bench/run.py`). A $0.40 cell caps the build at $0.24 and the
  review at $0.08. The arm never spends more than `single` may.
- The review prompt does not mention tests, checks, grading, benchmarks or another arm
  (`tests/test_blinding.py` screens it with every other prompt). It carries no checks of any kind:
  the agent re-reads its request and its files and nothing else.
- Results record the arm as `single-review`. `--arms` runs it only when named; it is not in the
  default `single firm`.
- Limit: the review's cost is its own slice, but its words are one fixed prompt; a different
  wording is a different arm.

## Scoring

- The gate runs the task's hidden checks on the arm's workspace. Under the default
  `BOSS_GATE_SANDBOX=auto` that is inside the OS sandbox where the platform has one, the boss's
  checks in the firm arm included. Results recorded before the sandbox existed ran unsandboxed.
  Whether the sandbox changed any recorded outcome was not measured.
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
  isolated. Excluded from every rate and listed separately. The exclusion follows the run's
  outcome, not the product's score: a cell cut off by one of these is excluded even when every
  hidden check passed, and old results are read the same way.

## KPIs

Seven figures, fixed before any new run is analysed: their definitions below are the code's, and a
change to one is a new version of this note, not a re-read of old results. `python -m antstreet.bench.kpi`
prints them, from result files and ledgers only, never from what a model wrote. A **counted** cell is
one that is not an infrastructure failure; infrastructure failures are left out of every figure and
counted beside it. A figure the data cannot give is shown as "n/a" or "not recorded", never as 0.

1. **Delivery rate**: delivered cells over counted cells, with a Wilson 95% interval. A cell is
   delivered when every hidden check passed. It is the one outcome a user pays for.
2. **False-pass rate**: cells where the system said done and a hidden check failed, over cells where
   the system said done, with a Wilson interval. The firm said done when every visible check passed
   and, if the cell had held-out checks, every held-out check passed too. The single arm said done
   when its last status word was `done`, read from the cell's `final_status` and, in results written
   before that field, from its ledger; a cell with neither is left out, and with none the figure is
   "n/a". It says how far to trust "done".
3. **Cost per delivered task**: the known cost of all counted cells, boss calls included, over the
   delivered cells; "n/a" when none was delivered. The spend on cells that did not deliver is in it,
   as it is what the user paid. Events of unknown cost are a separate row, never added as 0.
4. **Time to delivery**: the median wall-clock seconds of delivered cells, beside the median of all
   counted cells. A person waits this long.
5. **Reliability (pass^k)**: tasks delivered on every one of their counted runs over tasks with at
   least one counted run. k is a task's number of counted runs; the table states it, and when it
   differs between tasks, lists each k with its task count. A user runs the product again and
   again; one lucky run is not reliability.
6. **Investor questions**: questions the investor had to answer, per run, from the run's ledger
   (rule below), over the counted firm cells whose ledger was found, with the number of cells
   without one. The single arm asks none: 0 by construction. It is the attention the firm asks for.
7. **Check quality**: boss checks that the reference solution fails over boss checks, summed over
   the counted cells where `wrong_checks` was measured, without an interval (the checks of one draft
   are not independent). "n/a" for the single arm, "not measured" where it was not.

**Step-up rescue** (printed under the table, not an eighth row: the seven stay fixed). It asks
whether paying for a stronger worker after the first was fired bought a delivery. From `hired`
events, slice events and the cell's hidden result only; no ledger key was added for it.

- A **step-up** is a `hired` event whose `data.dispatch.from_tier` is set and whose
  `data.dispatch.tier` ranks above it (`haiku` < `sonnet` < `opus`). A replacement on the same
  tier (the effort step, or the same model hired again under `--no-step-up`) is counted apart as a
  **same-tier replacement** and is never a step-up.
- A **visible rescue** is a step-up whose own worker's slice history reaches DONE when read by
  `rule.decide` on `state.slice_history`, the function the live firm uses, against the checks the
  gate reported for that worker (held-out and dropped checks left out).
- A **delivered rescue** is a visible rescue in a counted cell where every hidden check passed. A
  **false rescue** is a visible rescue in a cell where one did not.
- The **rescue rate** is delivered rescues over step-ups, with a Wilson 95% interval and the number
  of step-ups. With no step-up the line says "no step-ups", never 0/0.
- **$/rescue** is the known cost of every step-up worker's slices over the delivered rescues, the
  spend on step-ups that failed included. A slice of unknown cost (`cost_micros` null, or an
  `interrupted_slice` error of that worker) makes it a lower bound, marked as such, never counted
  as 0. With no delivered rescue it is "n/a" and the spend is shown.
- Figures are split by the route the investor approved (`approved.data.route`: `firm` or
  `one_agent`; `no route recorded` for a run without `--dispatch`). Under `--no-step-up` the
  one-agent route hires no replacement at all while the firm route hires a same-model one, so a
  rescue figure is only compared within one route. Cells whose ledger was not found are counted
  beside it and are in no figure. Infrastructure cells are left out. The single arm hires no
  replacement: "n/a".
- Every figure is tested on synthetic ledgers only; no recorded run has a step-up yet.

**Integration failures** (printed under the step-up rescue block, not an eighth row: the seven
stay fixed). It asks how often a split of the work was each part right and the whole wrong. From
the cell's ledger and hidden result only; no ledger key was added for it.

- A **split cell** is a counted cell whose ledger holds `hired` events (`data.worker`,
  `data.task`) for at least two distinct tasks. The split is read from the hirings, not from the
  term sheet (the ledger does not carry its task list), so a sheet that stopped before a second
  task was hired is not a split. That under-counts splits, never integration failures.
- An **integration failure** is a split cell where all of these hold: the last `round_closed` has
  `passed == total > 0` (the whole term sheet's visible checks passed, so a task that was never
  hired, e.g. the money ran out, cannot hide; a run with no closed round is not counted); for each
  hired task, the worker the product is assembled from (`state.run_state(...).tasks[t].best`, as
  `rundir.assemble_product` picks it) has last gate results (`check_result` events carrying that
  `worker` and a `slice`, read by `state.last_check_statuses`: held-out and dropped checks left
  out) that are all `passed`, a task with no graded check not being a pass; and the cell has at
  least one hidden check that did not pass (`failed` or `timeout`). A cell with no hidden result is
  a split cell, never a failure.
- Reported per column as failures over split cells with a Wilson 95% interval and the number of
  split cells. With no split cell the line says so, never 0/0. The single arm: "n/a". Cells whose
  ledger was not found are counted beside it and are in no figure.
- Fired workers are not judged unless they are the task's best: only the worker the product is
  assembled from stands for a task.

**Counting rule for investor questions.** One question is one decision the run needed from the
investor, and the count is the number of these ledger events:

- `approved` by the investor: the term sheet, a round's funding, or the fix round;
- `stopped` by the investor with the reason `term sheet rejected` or `round N not funded`;
- `ruled` by the investor: a ruling on a disputed check, an unblock note, or a declined fix round;
- `abandoned` by the boss for the reason `disputed`, `blocked` or `refusal`: the task was set aside
  after the investor was asked. This is the benchmark's automatic `a`, which is no ruling, so these
  count as what would have been asked;
- `resumed` and `topped_up` by the investor: each is a step they had to take to go on.

Not counted: the edit-and-re-check loop at the term sheet (the ledger records none of it, so the
count is a lower bound), the second prompt of an unblock (the note, one decision), a stop for
"interrupted before approval", and the boss's own `abandoned` for "already reassigned once". A
declined fix round is recorded even when `--review-cycles 0` offered none, so it can over-count by
one there. The same count is the `Investor questions` line of `boss report`.

Columns are one folder, arm, model, budget and set of firm options. Two columns with the same
label are refused rather than pooled. Where two columns' intervals overlap, no difference between
them is demonstrated; columns that ran different task sets are not comparable at all. Cells of one
task are not independent, so an interval over cells is narrower than the evidence supports.

## What the sample supports

- A pass rate from `n` cells is reported with its Wilson 95% interval. At 70% and 45 cells that is
  roughly ±13 points.
- Detecting a 10-point difference needs roughly 155-234 paired tasks; a 20-point difference
  roughly 57-77. This set is smaller, so **pass-rate differences between arms are descriptive,
  not claims**.
- What a small set can support: cost per passing cell, the boss's share of cost, and how often
  the firm's visible checks were satisfied while hidden checks failed.
- Model output varies between runs. Each task is run several times per arm and all runs are kept.

## Paired comparison

The table pools runs, so a task run more often counts more and the two arms are not compared on
the same tasks. `python -m antstreet.bench.paired DIR_A DIR_B` compares two arms task by task.

- A task is compared when both sides have at least one counted run of it. Infrastructure failures
  are excluded and counted, as in the table.
- Per task and arm, one value: `delivery` is the share of the task's runs that passed every hidden
  check; `pass_fraction` (the secondary KPI) is the mean over its runs of the share of hidden
  checks (cases) that passed, a run with none recorded scoring 0; `pass_all` is 1 when every one of them did and 0 otherwise (KPI 5, pass^k, per task); `time` the median duration of its runs; `cost_per_delivery` the mean cost of its runs
  (all of them, delivered or not: a task that delivered nothing has no cost per delivery, and
  dropping it would favour the arm that fails more); `false_pass` the share of its runs that passed
  every visible check and failed a hidden one (firm arms only).
- The difference A minus B is taken per task. The report gives the number of tasks, the mean
  difference and a 95% percentile interval from 10,000 resamples of tasks with replacement, with a
  fixed seed so the same results give the same interval.
- Beside the interval the report gives an exact one-sided **sign test** on the same per-task
  differences: `wins` (tasks where A is better: difference above 0, below 0 for `false_pass`, cost
  and time), `losses`, ties dropped, `n_nonzero = wins + losses`, and p = P(X >= wins) for
  X ~ Binomial(n_nonzero, 1/2), from `math.comb`. With no non-tied task p = 1. The bootstrap alone
  is optimistic for few tasks: 4 of 30 tasks won and none lost gives an interval of roughly
  [0.011, 0.089] but p = 0.0625.
- The verdict is `shown` only when the interval excludes 0 in A's favour (above 0 for `delivery`,
  `pass_all` and `pass_fraction`, below 0 for `false_pass`, cost and time) AND the sign-test p is
  below 0.025; the rule is printed in the output. Otherwise `not shown`. With one task it is always
  `not shown`: every resample is the same task.
- `pass_all` is refused unless every compared task has the same number of counted runs on both
  sides: pass^4 is easier to meet than pass^5, so an infrastructure cell is rerun (B71), not dropped.
- Results that ran different task sets are refused. A different model or budget between the sides
  prints a warning, since the difference would then not be the arm's.
- Limit: a percentile bootstrap over few tasks is too narrow. Nothing is enforced beyond two tasks,
  so read `shown` from a small set as a lead to repeat, not a finding.

## Draft evaluation

The arms above are scored on products. The boss's checks are the weak point (some are wrong; some
do not cover the idea), and a full worker run is too costly to iterate a prompt against. So the
checks are scored alone, as a classifier of implementations, with `python -m antstreet.bench.drafts`.
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
  That is precision 93% and 97% of checks, recall 58% and 60% of mutants.
- **Limits**: a small hand-picked corpus. With 3 to 6 mutants a task, one mutant is 17 to 33 points
  of that task's recall, so recall is a coarse figure and a task-level difference is not a claim.
  Harvested mutants come from Haiku runs and lean toward the mistakes Haiku makes; hand-made ones
  are the bugs their author thought of. Several harvested mutants of a task share one bug. A mutant
  is only as wrong as the hidden checks say: a wrong hidden check would make a right product a
  mutant. Killing every mutant does not show the checks cover the idea. In `--score-existing`,
  16 of the 23 harvested mutants are firm-arm products built against those very drafts, and 11 of
  them passed every check of their own draft: they survive it by construction, so the baseline
  recall is biased down. Fresh drafts (`--out`) do not have that bias.

## Dispatch arms (E6)

E6 in [PREREG.md](PREREG.md) compares four firm arms at the same per-cell budget, through the
runner's own options and `--firm-args`, so the bench code is unchanged and each result records its
arm in `firm_args`:

```bash
uv run python -m antstreet.bench.run --out bench/results/raw/e6-fixed-haiku --arms firm --reps 3 --budget 0.80 --model haiku --boss-model haiku
uv run python -m antstreet.bench.run --out bench/results/raw/e6-fixed-sonnet --arms firm --reps 3 --budget 0.80 --model sonnet --boss-model sonnet
uv run python -m antstreet.bench.run --out bench/results/raw/e6-dispatch --arms firm --reps 3 --budget 0.80 --model haiku --boss-model haiku --firm-args "--dispatch rules --max-tier sonnet"
uv run python -m antstreet.bench.run --out bench/results/raw/e6-cascade --arms firm --reps 3 --budget 0.80 --model haiku --boss-model haiku --firm-args "--dispatch cascade --max-tier opus"
```

The eight multi-file tasks (`bench/tasks-multi`) take the same four arms with the firm run at three
tasks, three at once, same $0.80 budget and 3 reps:

```bash
uv run python -m antstreet.bench.run --out bench/results/raw/e6-multi-fixed-haiku --tasks bench/tasks-multi --arms firm --reps 3 --budget 0.80 --model haiku --boss-model haiku --firm-args "--max-tasks 3 --parallel 3"
uv run python -m antstreet.bench.run --out bench/results/raw/e6-multi-fixed-sonnet --tasks bench/tasks-multi --arms firm --reps 3 --budget 0.80 --model sonnet --boss-model sonnet --firm-args "--max-tasks 3 --parallel 3"
uv run python -m antstreet.bench.run --out bench/results/raw/e6-multi-dispatch --tasks bench/tasks-multi --arms firm --reps 3 --budget 0.80 --model haiku --boss-model haiku --firm-args "--max-tasks 3 --parallel 3 --dispatch rules --max-tier sonnet"
uv run python -m antstreet.bench.run --out bench/results/raw/e6-multi-cascade --tasks bench/tasks-multi --arms firm --reps 3 --budget 0.80 --model haiku --boss-model haiku --firm-args "--max-tasks 3 --parallel 3 --dispatch cascade --max-tier opus"
```

the gate's `fired` verdict, `slice_end.cost_micros` and `slice_end.model_id`; `boss routing` run
over a project that holds those runs prints the fail rate and mean cost per task kind and tier. Cells
do not share a project, so the arm's starts are all the prior.

A dispatch cell's ledger holds what to count: a `hired` event whose `dispatch` has `from_tier` is
an escalation fired, one with `refused` is a step the round could not fund, and a fired task whose
product later passes is rescued. No command counts them yet (B93): read them from the ledgers.
A cell whose run stopped for a wrong model (T69) is reported apart, not counted as a failure of
the arm; no command separates it yet (B93). The model each worker ran is `slice_end.model_id`.

## Reliability arms (E5)

E5 in [PREREG.md](PREREG.md) runs the firm and the single agent on the 35 tasks of
`2026-10-03-blind35`, 5 runs each, with the same $0.40 cell budget and the firm's `--slice 0.20`
of that run. Each arm has its own folder:

```bash
TASKS=(bigdecimal calc csvline duration intervals jsonpointer justify linediff lrucache matrixops
       roman semver slugify tokenbucket toposort wildcard workdays
       bytesize cronnext dedentblock exprtokens fracmath iniparse isoweek luhn mdheadings minheap
       moneysplit prefixtrie rangesum ringbuffer shortestpath unionfind urlquery wordwrap)
COMMON=(--reps 5 --budget 0.40 --model haiku --boss-model haiku --only "${TASKS[@]}")
uv run python -m antstreet.bench.run --out bench/results/raw/e5-firm --arms firm --firm-args "--slice 0.20" "${COMMON[@]}"
uv run python -m antstreet.bench.run --out bench/results/raw/e5-single --arms single "${COMMON[@]}"
uv run python -m antstreet.bench.paired bench/results/raw/e5-firm bench/results/raw/e5-single --kpi pass_all
uv run python -m antstreet.bench.kpi bench/results/raw/e5-firm bench/results/raw/e5-single
```

Adding `--dry-run` to the two run commands lists 175 cells each. An infrastructure cell is moved
aside and rerun (B71) until each task has 5 counted runs per arm: `--kpi pass_all` refuses a task
whose two sides ran a different number of times.

## Reproducing

```bash
uv run python -m antstreet.bench.run --out bench/results/raw/<label> --budget 0.40 --reps 3
uv run python -m antstreet.bench.table bench/results/raw/<label>
```

Both commands make real model calls or read their results; the first one costs money.

```bash
uv run python -m antstreet.bench.drafts --out bench/results/raw/<label> --reps 3 [--prompt NAME]
uv run python -m antstreet.bench.drafts --score-existing bench/results/raw/<run>
```

The first drafts with the boss (about $0.09 a draft, capped at $0.25); the second spends nothing.
Compare prompts in separate `--out` folders: a folder refuses drafts made with other settings.
