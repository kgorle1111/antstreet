# Command line

Every command and option, the environment variables the tool reads, exit codes, and what a run
leaves on disk. `tests/test_docs_cli.py` reads the real argparse parsers and fails if an option or
command is missing here, is documented but does not exist, or has a different default.

Related: [ARCHITECTURE.md](ARCHITECTURE.md), [LEDGER.md](LEDGER.md), [ROLES.md](ROLES.md).

Every command also accepts `-h` and `--help`.

## `boss`

`boss [--version] <command> ...` where the command is `fund`, `resume`, `report`, `status`,
`roles` or `doctor`.

| Option | Default | Meaning |
|---|---|---|
| `--version` | off | Print `boss <version>` and exit 0. |

- A command is required. Without one, argparse prints usage and exits 2.
- Commands run against a project folder (`--dir`). Runs are stored under `<dir>/.boss/runs/`.

## `boss fund`

`boss fund [options] IDEA`. Drafts a term sheet, asks you to approve it, then builds the idea.

Argument: `idea`, what to build, in plain words.

- A blank idea, or one whose first non-blank character is `-` (it would read as an option), is
  refused with a message and exit 2. No run folder is made and nothing is spent. To give an idea
  that starts with `-`, put some other word first.
- `--rounds`, `--max-tasks`, `--max-slices` and `--stall-slices` must be whole numbers of 1 or
  more. `--max-minutes` must be a positive number. `--boss-thinking` must be a whole number. Any
  other value is a usage error (exit 2) before anything is spent.
- Ctrl-C after approval, while workers are running, stops the run, prints `boss resume <id>` and
  exits 130. Nothing already recorded is lost. Ctrl-C earlier (during the boss's call or the
  review) is not handled: Python's own interrupt applies.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder. |
| `--budget` | required | Budget for the funding rounds in dollars, such as `0.50` or `$0.50`. Positive, at most 6 decimals. The boss's own drafting call is charged on top of it. |
| `--model` | `haiku` | Worker model. |
| `--rounds` | `1` | Funding rounds to split the budget into. With more than one, the budget splits equally (the earliest rounds take any remainder), the count is capped at the number of checks, and each round after the first needs your yes. |
| `--slice` | `$0.10` | Dollars a worker may spend in one slice, before the gate looks again. At least $0.005; a smaller slice is never funded (exit 2). |
| `--reserve` | `$0.10` | Dollars held back from every slice cap: what one response can cost past the cap. |
| `--max-tasks` | `1` | Most tasks the boss may split the work into. Above 1 the multi-task prompt is used. |
| `--profile` | none | Worker profile: one of `generalist`, `backend_engineer`, `ai_engineer`, `test_engineer`, `refactorer`. Its skills are added to the worker's prompt. Without it the worker gets the bare builder prompt. `boss roles` lists each profile's skills. |
| `--parallel` | `1` | Tasks to work on at once. A task still has one worker at a time, and at most two in all (the first and one replacement). Slices that run together each leave room for the reserve of every earlier one, so a small round funds fewer at once. Only useful with `--max-tasks` above 1. |
| `--max-slices` | `6` | Fire a worker after this many slices that count. |
| `--stall-slices` | `2` | Fire a worker after this many counted slices in a row with no new passing check. |
| `--max-minutes` | none | Stop the run after this many minutes of wall clock, counted from the start of this `fund` or `resume`. Checked before each slice, so a slice in progress can run past it. |
| `--no-firing` | off | Keep funding stalled workers. A worker is still fired at the slice limit. |
| `--boss-model` | `haiku` | Model for the boss's own call. |
| `--boss-thinking` | none | Thinking tokens the boss may use; 0 turns thinking off. Without it the CLI's default applies. |

What it asks you:

- `[a]pprove, [r]eject, or [e]dit files and re-check?` after showing the term sheet. `edit` lets
  you change `term_sheet.json` and the check files, then re-validates them. End of input counts as
  reject.
- `Round N: X/Y checks pass. Fund $Z more? [y]es / [n]o` before each round after the first. End
  of input counts as no.

Limits that are not options: a run stops at 60 slices or 16 workers, when spend passes the sum of
its round budgets plus one reserve per round, or when a worker's folder passes 200 MiB (the gate
copies it for every check). See [ARCHITECTURE.md](ARCHITECTURE.md#fixed-limits).

A budget per round below one reserve plus $0.005 is refused before anything is spent.

When a disputed check or a blocked worker needs you, the run asks (`boss resume` asks the same):

- `[d]rop the check / [k]eep it (the worker must satisfy it) / [s]et the task aside`, once per
  check a worker disputes. Drop: the check is no longer run or counted. Keep: the worker must make
  it pass.
- `[u]nblock it with a note / [s]et the task aside`, when a worker says it cannot go on. A note
  is on one line, at most 1000 characters, and goes into the worker's next brief.
- Anything else, or end of input, sets the task aside for the rest of the run. Your rulings are
  ledger events (`ruled`); the approved term sheet and checks are not edited.

## `boss resume`

`boss resume [--dir DIR] [RUN]`. Continues a run from its ledger: one that was interrupted (exit
130), paused, stopped, or ended early.

Argument: `run`, a run id. Default: the latest run in the folder.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder. |

- It reads `term_sheet.json` and the configuration recorded when the run started, so a resumed
  run keeps its own slice, reserve, firing and limit settings. There are no options to change them.
- Running it is your decision to lift a stop: it prints why the run stopped and writes `resumed`.
  The approval, the budget and every hard limit are checked again as the loop goes, so a lifted
  stop can stop again at once. The wall-clock limit (`--max-minutes`) counts from the start of
  each `resume`, so a resumed run gets the whole time again.
- An interrupted round continues. A round that closed below its unlock threshold stays locked. A
  task that was set aside stays set aside.
- A slice that started and never ended is charged to its round at its cap. If the last slice was
  never gated, or a firing or a question to you was owed, it is done first.
- On a run that already finished it changes nothing and prints the report.
- Refused with exit 1, spending nothing: no run found; no usable `term_sheet.json`; a damaged
  ledger; the run never got as far as hiring (start again with `boss fund`); the term sheet or a
  check no longer matches your approval.
- A ledger whose last line was cut by a hard kill is repaired first: the cut line is removed and
  `resume` prints it. A ledger damaged anywhere else is refused.
- If another `boss` process is still writing the run's ledger, `resume` ends with a Python
  traceback (`LedgerLockedError`), not a message. Nothing is changed. Not fixed yet.
- Exit codes are those of `boss fund`.

## `boss report`

`boss report [--dir DIR] [RUN]`. Prints the board report of a run, computed from its ledger.

Argument: `run`, a run id. Default: the latest run in the folder.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder. |

## `boss status`

`boss status [--dir DIR] [RUN]`. Prints one line: the last event, checks passing, estimated spend.

Argument: `run`, as for `report`.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder. |

## `boss roles`

`boss roles [--dir DIR]`. Prints the organisation as a tree: the investor, the boss, then the
departments, and under them each role and each worker profile with its purpose, its gate, its
skills, and whether it is on by default. Every specialist role is marked `off by default`. See
[ROLES.md](ROLES.md).

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Accepted like the other commands. Not used: nothing is read from the project. |

It reads the code only. It makes no model call, reads no run and writes nothing. Exit 0.

## `boss doctor`

`boss doctor [--dir DIR] [--live]`. Checks what a run needs and prints a fix line for each failure.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder; `.boss/` inside it must be writable. |
| `--live` | off | Verify the login with one real call: model `haiku`, cap $0.05, 120 s. If that works, make a second real call to test the worker path rules (see below): model `haiku`, cap $0.05, 120 s. Both are paid, at most $0.10 by their caps. |

Checks, in order: Python 3.12 or newer; a POSIX system; `pytest` importable; the `claude` binary on
`PATH`; its version is 2.1.277 or newer; the login; the worker path rules (only with `--live`, and
only when the login check passed); a writable `.boss/`; the gate sandbox. The
sandbox line names the tool found (`sandbox-exec` or `bwrap`). With no working tool it is a warning
with the fix, not a failure, and the exit code stays 0. It fails under `BOSS_GATE_SANDBOX=require`
or for a value that is not `auto`, `require` or `off`. See [SANDBOX.md](SANDBOX.md). Without `--live` the login
check trusts `claude auth status`, which can report a login the API then rejects. With an
`ANTHROPIC_API_KEY` set and no `--live`, the login check passes without a call.

The worker path rules check runs one real worker slice, isolated as a run would, and asks the
worker to write a file outside its own folder. It passes when the write was refused. It fails when
the file appears, when the worker did not start isolated, or when the call could not run. If the
worker did not try the write, it passes with a warning (`inconclusive`) and the exit code stays 0:
run `--live` again. The other checks make no paid call. The two costs are the CLI's estimates.

## Exit codes of `boss`

| Code | Meaning |
|---|---|
| `0` | `fund`, `resume`: every check passed. `report`, `status`, `roles`, `doctor`: success. |
| `1` | `fund`: the boss produced no usable term sheet, you rejected it, or a worker did not start isolated (a hook event later in the run counts). `resume`: nothing to resume, a damaged ledger, or the approval no longer matches. `report`, `status`: no runs, unknown run, or empty ledger. `doctor`: a check failed. |
| `2` | Usage error: bad or missing arguments, a blank idea, a count that is not a whole number of 1 or more, a slice below $0.005, or a budget too small to fund one slice. |
| `3` | `fund`, `resume`: the run ended with checks not passing. This includes a run that stopped early (a hard limit, a declined round, a pause, a lost login) and prints `Ended early: <reason>` and the `boss resume` command. |
| `130` | `fund`, `resume`: interrupted with Ctrl-C. Continue with `boss resume`. |

A ledger with a damaged line makes `report` and `status` fail with an error that names the file
and line.

## Benchmark commands

These make real model calls only through `run`. See [../bench/METHOD.md](../bench/METHOD.md).

## `python -m boss.bench.run`

Runs benchmark cells (one task, one arm, one repetition) and scores each with the task's hidden
checks. A cell whose `result.json` already exists is skipped, so a run can be repeated to finish.

| Option | Default | Meaning |
|---|---|---|
| `--tasks` | `bench/tasks` | Folder of task folders. |
| `--out` | required | Results folder for this run. |
| `--arms` | `single firm` | Which arms to run: `single`, `firm`, or both. |
| `--reps` | `1` | Repetitions per task and arm. |
| `--budget` | required | Dollars per cell. The boss's drafting call is on top. |
| `--model` | `haiku` | Worker model, both arms. |
| `--boss-model` | `haiku` | Boss model, firm arm. |
| `--only` | all tasks | Task ids to run. |
| `--firm-args` | none | Extra `boss fund` options for the firm arm, in one quoted string. Recorded in every result. |
| `--jobs` | `2` | Cells to run at once. |
| `--dry-run` | off | Print the cells and the task set hash, then exit. |

Exit codes: `0` after the cells ran (whether or not they passed); `1` when no task matches
`--only`; `2` for a usage error. A task that fails validation stops the run with an error before
any cell starts.

## `python -m boss.bench.drafts`

Scores the checks the boss drafts, without running any worker. For each task and repetition the
boss drafts checks from the idea; each draft is then run against the task's reference solution
(precision: the reference must pass every check) and against its known-wrong implementations
(recall: each must fail a check the reference passes). The only spend is the boss's drafting call.
See [../bench/METHOD.md](../bench/METHOD.md).

| Option | Default | Meaning |
|---|---|---|
| `--tasks` | `bench/tasks` | Folder of task folders. |
| `--out` | none | Folder for the drafts and their scores. Required unless `--score-existing` is given. |
| `--only` | all tasks | Task ids to draft for. |
| `--reps` | `1` | Drafts per task. |
| `--boss-model` | `haiku` | Model for the boss's call. |
| `--boss-thinking` | none | Thinking tokens per draft. |
| `--prompt` | `term_sheet_v1.md` | Term-sheet prompt file under `src/boss/prompts`. |
| `--jobs` | `2` | Drafts to make and score at once. |
| `--dry-run` | off | List the drafts and exit. |
| `--score-existing` | none | Score the boss drafts already saved in a `boss.bench.run` results folder; spends nothing. |

- A folder refuses drafts made with other settings (prompt, its content hash, model, thinking).
  Use a fresh `--out` to compare prompts.
- Exit codes: `0`; `1` when no task matches, a results folder cannot be read or holds no drafts, or
  the prompt cannot be used; `2` for a usage error.

## `python -m boss.bench.table`

`python -m boss.bench.table [--out OUT] RESULTS_DIR`. Prints the results table as markdown.

Argument: `results_dir`, a folder written by `run`.

| Option | Default | Meaning |
|---|---|---|
| `--out` | stdout | Write the table to this file instead. |

Exit codes: `0`; `1` when no results are found or a result file is invalid; `2` for a usage error.

## `python -m boss.bench.replay`

`python -m boss.bench.replay [--stall N ...] [--max-slices N ...] RESULTS_DIR`. Replays firing
policies over recorded ledgers and prints, for each combination, how many workers would have been
fired, how many of those later passed a new check, and the spend saved.

Argument: `results_dir`, a folder holding `ledger.jsonl` files.

| Option | Default | Meaning |
|---|---|---|
| `--stall` | `1 2 3` | Stall-slice values to try. |
| `--max-slices` | `4 6 8` | Slice-limit values to try. |

Exit codes: `0`; `1` when a ledger cannot be read or none has slice data; `2` for an invalid
policy value or a usage error.

## Environment variables

| Variable | Read by | Meaning |
|---|---|---|
| `BOSS_CLAUDE_BIN` | `boss fund`, `boss doctor`, `bench.run` | Path or name of the `claude` executable. Default `claude`. Not passed on to children. |
| `ANTHROPIC_API_KEY` | every command that calls the CLI | If set and non-empty: billing is `api`, the CLI runs with `--bare` instead of `--safe-mode`, and the key is passed to the CLI and masked in logs. The `--bare` mode is not verified against the real CLI. |
| `HOME` | worker and boss calls | Passed on so the CLI finds its login. |
| `PATH` | worker and boss calls | Passed on so the CLI can start. |
| `USER` | worker and boss calls | Passed on. |
| `LANG` | worker and boss calls | Passed on. |
| `TMPDIR` | worker and boss calls | Passed on. |
| `CLAUDE_CONFIG_DIR` | worker and boss calls | Passed on so the CLI finds its login. |
| `BOSS_GATE_SANDBOX` | `boss doctor`, the gate (so `boss fund`, `boss resume` and the benchmarks) | `auto` (default): run each check inside an OS sandbox when the platform has a working one, else unsandboxed. `require`: refuse to run a check without one. `off`: never. Any other value is an error. See [SANDBOX.md](SANDBOX.md). |
| `MAX_THINKING_TOKENS` | the `claude` CLI | Set by `boss fund` for the boss's call when `--boss-thinking` is given. Never taken from your environment. |
| `BOSS_LIVE` | `tests/test_end_to_end.py` only | `1` enables the one test that makes a real model call. |

- Nothing else from your environment reaches a worker or boss process. The gate builds its own
  environment for checks: a temporary `HOME` and `TMPDIR`, a short `PATH`, `LANG`, and
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
- Only `boss.cli`, `boss.bench.run`, `boss.bench.drafts`, `boss.gate` and `boss.sandbox` read the
  process environment.

## Run folder

`boss fund` creates `.boss/runs/<id>/`, where `<id>` looks like `20260930T101500Z-3fa9c1`
(UTC time, then six hex digits). `.boss/` is ignored by git.

| Path | What it holds |
|---|---|
| `ledger.jsonl` | Every event. See [LEDGER.md](LEDGER.md). |
| `term_sheet.json` | The term sheet, with `approved_by_investor` true once you approve. |
| `checks/` | The check files, `test_c01.py` and so on. Outside every workspace; copied fresh for each gate run. |
| `workspaces/<worker>/` | One folder per worker (`w1`, `w2`, ...). A replacement's folder also holds `previous_attempt/`. |
| `logs/<worker>.jsonl` | The worker's raw stream, with secrets masked. |
| `product/` | The built files, assembled from each task's best worker at the end of a run. |
| `report.md` | The board report, saved when `boss fund` or `boss resume` finishes. |

`workspaces/`, `logs/` and `product/` exist only once a worker has been hired. `report.md` is
written by `fund` and `resume`; `boss report` prints it again from the ledger without writing.

## Benchmark cell folder

`python -m boss.bench.run --out DIR` writes one folder per cell: `DIR/<task>/<arm>/rep<N>/`.

| Path | Arm | What it holds |
|---|---|---|
| `result.json` | both | The scored result. Its presence marks the cell done. |
| `ledger.jsonl` | single | The single agent's events. |
| `workspace/` | single | The single agent's files, scored by the hidden checks. |
| `logs/solo.jsonl` | single | The single agent's raw stream. |
| `transcript.txt` | firm | What `boss fund` printed. |
| `.boss/runs/<id>/` | firm | A complete run folder, as above. Its `product/` is scored. |
