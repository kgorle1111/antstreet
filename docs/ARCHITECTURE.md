# Architecture

How `boss` is put together, what each part may and may not do, and the rules the design relies on.
`tests/test_docs_architecture.py` fails when this file and the code disagree about which modules
exist, which ledger events the loop writes, or the fixed limits in the last table.

Related: [LEDGER.md](LEDGER.md) (event schema), [CLI.md](CLI.md) (commands, run folder),
[DECISIONS.md](DECISIONS.md) (why), [THREAT_MODEL.md](THREAT_MODEL.md) (what is defended).

## Roles

| Role | What it is | Ledger actor |
|---|---|---|
| Investor | The human. Gives the idea and budget, reads every check, approves, rejects or edits. Later rules on a disputed check or a blocked task, and lifts a stop with `boss resume`. | `investor` |
| Boss | One model call with no tools. Drafts tasks and pytest checks. Nothing else. | `boss` |
| Worker | A headless `claude` CLI session. Tools: `Read`, `Write`, `Edit`, all scoped to its own folder. No shell. | `worker:<name>` |
| Rule | Plain code (`rule.decide`). Decides from a worker's slice history: continue, done, fire, escalate, retry. | `rule` |
| Gate | Plain code (`gate.run_gate`). Runs each check in its own pytest process. The only source of "passed". | `gate` |
| Ledger | Append-only JSONL file. Every spend and decision. Every report figure comes from it. | none |

- The actor `boss` also appears on events the loop itself writes (`started`, `hired`,
  `reassigned`, `abandoned`, `round_closed`, `paused`, `stopped`). Those are code, not a model
  call. Only `boss_call` is a model call.
- The loop (`firm.py`) is not an actor. It reads the ledger, asks the rule, and writes events.

## Module map

One row per file under `src/boss/` and `src/boss/bench/`. "Never" is a rule the module keeps.

| Module | Owns | Never |
|---|---|---|
| `__init__.py` | The package version, read from installed metadata. | Hold logic. |
| `approval.py` | Showing the term sheet, the approve/reject/edit loop, content hashes, `require_approval`. | Set approval without an investor answer; accept a hash that does not match the files on disk. |
| `boss.py` | The boss's one model call: command line, draft schema, turning a draft into a term sheet. | Take ids, file names, money or round plan from the model; give the boss a tool. |
| `briefs.py` | What a worker is told: first brief, continuation after a gate run, reassignment brief. | Call a model; present a worker's earlier words as instructions. |
| `budget.py` | Round budgets, top-ups, remaining money, slice caps, the reserve, unlock test, round plan. Charges a slice that did work with no cost, or that never ended, at its cap. | Use floats; read a clock. |
| `cli.py` | The `boss` command: parsing, validating counts and amounts, wiring, exit codes, `resume`. | Decide pass, fire or money itself. |
| `doctor.py` | Preflight checks (including the gate sandbox), each with a one-line fix. | Raise on an expected failure; print an environment value. |
| `errors.py` | Names the outcome of one CLI run from its stream signals. | Trust `subtype` alone. |
| `firm.py` | The round loop: hire, fund a slice, gate it, ask the rule, write events. | Keep state outside the ledger; record a pass itself; spend before approval matches. |
| `gate.py` | Running checks against a fresh copy of the workspace, inside the OS sandbox when there is one; the verdict. | Read the exit code alone; run a check from the workspace; modify the original workspace. |
| `handoff.py` | Copying a fired worker's files and notes for its replacement. | Call a model; follow a symlink. |
| `ledger.py` | The event schema, the exclusive appender, the reader, totals, `repair_torn_tail` (no command calls it yet). | Edit or delete a line, except an incomplete last one in `repair_torn_tail`; add an unknown cost as 0. |
| `limits.py` | Hard run limits: spend ceiling, slices, workers, wall clock. | Depend on the round budget or the rule. |
| `redact.py` | Masking secrets and control characters in text that is stored or shown (`safe_text`), in linear time. | Return text that still contains a matched secret. |
| `report.py` | The board report, computed from events. | Read anything but events; fold an unknown cost into a total as 0. |
| `retry.py` | Pure decisions on infrastructure failures: wait, pause, give up. | Sleep; read a clock; touch a process. |
| `rule.py` | The firing decision from a worker's slice history. | Read model output or state outside the history it is given. |
| `rulings.py` | The investor's questions on a disputed check or a blocked task, and reading `ruled` events back. | Decide for the investor; change the approved term sheet. |
| `rundir.py` | Run folder layout, the event recorder, assembling `product/`. | Copy a file into a path another task owns; follow a symlink. |
| `runner.py` | Running one slice as a supervised child process; isolation check at init and on any later hook event; stopping it. | Leave a child running; start in a workspace holding agent config. |
| `sandbox.py` | Building the command that runs one check inside a macOS `sandbox-exec` or Linux `bwrap` sandbox; probing that the tool works. | Run a check; put a path into profile text; trust a tool it has not probed. |
| `state.py` | Rebuilding run state (workers, tasks, rounds, stops, sessions, dropped checks) from events. | Read anything but events. |
| `stream.py` | Reading the CLI's `stream-json` output; usage and cost. | Raise on malformed input; turn a missing cost into 0. |
| `termsheet.py` | Term sheet types, JSON round trip, validation. | Accept a wrong JSON type; skip the empty-workspace run of every check. |
| `worker.py` | The exact worker command, the environment allowlist, status cleaning, the isolation test. | Offer a shell tool; pass a variable that is not on the allowlist. |
| `bench/__init__.py` | The package marker for the benchmark. | Hold logic. |
| `bench/drafts.py` | Drafting checks per task with the boss and scoring each draft (`python -m boss.bench.drafts`). | Start a worker; show the boss a hidden check, the reference or a mutant. |
| `bench/replay.py` | Replaying a firing policy over recorded ledgers, offline. | Call a model; use a different rule from the live one; walk past DONE or ESCALATE. |
| `bench/results.py` | One benchmark cell's result record and its load checks. | Accept a wrongly typed field. |
| `bench/run.py` | Running benchmark cells through the single and firm arms. | Copy hidden checks or the reference into a workspace or a prompt. |
| `bench/score.py` | Scoring a draft's checks: precision on the reference, recall on the mutants. | Spend money; count a mutant killed only by a wrong check as caught. |
| `bench/table.py` | The results table with intervals. | Count an infrastructure failure in a rate; treat unknown cost as 0. |
| `bench/tasks.py` | Task format, validation, the task set hash. | Accept a task whose checks pass on an empty workspace or fail on its reference. |

Prompts are files, not code: `src/boss/prompts/term_sheet_v1.md` (one task),
`term_sheet_v2.md` (several tasks), `builder_v3.md` (every worker) and `solo_v1.md` (the
benchmark's single agent).

## Life of a run

`boss fund "<idea>" --budget 0.40`

1. `cli` refuses, with exit 2, a `--slice` below the smallest slice cap or a budget per round
   below one reserve plus one minimum slice. Count options that are not whole numbers of 1 or more
   never get this far (argparse exits 2).
2. It creates `.boss/runs/<id>/` and opens `ledger.jsonl` with an exclusive lock.
3. The boss is called once. Its check code is written to `checks/`. The call is recorded as
   `boss_call` in round 0, outside every round's budget, also when it fails or its draft is
   invalid.
4. The draft is validated: structure, then every check run on an empty workspace. Any problem
   ends the run (`stopped`, exit 1).
5. With `--rounds N` above 1, the round plan is replaced by an equal split.
6. The investor reads the term sheet and every check, and approves, rejects or edits. Approval is
   an `approved` event holding hashes of the term sheet and each check file.
7. `run_firm` verifies the approval, writes `started` once (the run's configuration), then for each
   round asks for the investor's yes (rounds after the first) and runs the round.
8. The round loop picks the first task whose checks do not all pass, checks the hard limits,
   computes the slice cap, gets or hires a worker, and verifies the approval again.
9. It records `slice_start`, runs the slice (a `claude` process in the worker's folder), records
   `slice_end`, and, unless the slice failed for infrastructure reasons, runs the gate and records
   one `check_result` per check.
10. The rule decides from the ledger alone. The loop writes the matching event (table below) and
    goes to step 8.
11. When the round ends, `round_closed` is written. The run ends when every check passes, a limit
    stops it, or the next round is not unlocked or not funded.
12. `product/` is assembled from each task's best worker. The report is rendered from the ledger,
    saved as `report.md` and printed. Exit 0 if every check passed, else 3.

`boss resume [run]` continues a run that was interrupted (Ctrl-C, exit 130), paused or stopped:

1. It reloads `term_sheet.json` and the configuration from `started`. A run with no `started`
   event never hired anyone and cannot be resumed.
2. If the run is stopped, it writes `resumed` (actor `investor`) after saying why it stopped. The
   command is the investor's act; nothing else lifts a stop.
3. It calls `run_firm` as in step 7. Approval, budget and every hard limit are checked again as
   the loop goes; a round that was interrupted stays open and continues; a round that closed below
   its unlock threshold stays locked.
4. A slice with a `slice_start` and no `slice_end` is charged to its round at its cap. If the last
   slice was never gated, the loop gates it; a firing or an escalation that was owed is carried out.

## Control flow of `firm.py`

Each row is one decision in `_Firm.run`, `_run_round`, `_current_worker`, `_slice` or `_act`.
"None" means no ledger event.

| Decision | Ledger event | Next step |
|---|---|---|
| Approval missing or not matching at start | None; `NotApprovedError` is raised | Nothing is spent |
| Start of `run_firm`, first time | `started` (actor `boss`, holds the configuration) | Nothing else is written on a resume |
| A `stopped` event exists and no `resumed` after it | None | Run ends ("stopped earlier") |
| Round already has `round_closed` with `unlocked` false | None | Run ends (the round stays locked, also after a resume) |
| Round already has `round_closed` | None | Next round |
| Round not approved, investor answers no or input ends | `stopped` (actor `investor`) | Run ends |
| Round not approved, investor answers yes | `approved` (actor `investor`, `round`) | Run the round |
| No task with failing checks and not abandoned | None | Round ends; `round_closed` |
| Hard limit reached | `stopped` (actor `rule`) | Run ends; the round stays open, no `round_closed` |
| Round cannot fund a cap of at least the minimum after the reserve | None (a message is printed) | Round ends; `round_closed` |
| Task's worker exists and is not fired | None | Fund its next slice |
| Task's worker fired, task already had two workers | `abandoned` (`already reassigned once`) | Next task |
| Task has no worker | `hired` (a workspace folder left by an interrupted hire is deleted first) | Fund its first slice |
| Task's worker fired, one worker so far | `reassigned`, then `hired` | Fund the replacement; files offered under `previous_attempt/` |
| Approval no longer matches, or a check file is missing or unreadable, before a slice or a gate run | `stopped` (actor `rule`) | Run ends; the round stays open |
| The worker's last slice has no `check_result` (an interruption) | `check_result` per check, as below | Rule decides |
| A slice is funded (cap known, approval verified) | `slice_start` (with a `session` id: new unless a slice in that session already got past infrastructure) | Run the slice in the worker's folder |
| Worker did not start isolated, or a hook event appears after init | `error` (actor worker, cost unknown), then `stopped` | `IsolationError` reaches the CLI; exit 1 |
| Slice finished, any outcome | `slice_end`; then `check_result` per check (a check the investor dropped is not run), unless the outcome is infrastructure | Rule decides |
| Slice finished, worker disputes a check that fails now, not disputed before, not ruled on | `disputed` (actor worker) | Rule decides |
| Rule: infrastructure outcome, attempts left | None (a message is printed, then a sleep) | Same task and worker again |
| Rule: infrastructure outcome, plan usage limit | `paused` | Run ends; the round stays open |
| Rule: infrastructure outcome, login lost or attempts used | `stopped` (actor `boss`, with `fix`) | Run ends; the round stays open |
| Rule: worker reports `blocked` with no refused tool call, or the model refused | `blocked` (unless already written), then the investor is asked | Next row |
| Investor unblocks with a note | `ruled` (`unblocked`, with the note) | Fund the same worker; the note is in its next brief |
| Investor sets the task aside, or gives no clear answer | `abandoned` | Next task |
| Rule: the worker's only failing checks are ones it disputes, and they are at most half of the task's checks | The investor is asked once per disputed check | Next two rows |
| Investor drops a disputed check | `ruled` (`dropped`, actor `investor`) | The check is no longer run or counted; unlock thresholds follow |
| Investor keeps a disputed check | `ruled` (`kept`) | Dispute settled; the worker is told to satisfy it |
| Investor sets the task aside, or gives no clear answer | `abandoned` (`disputed`) | Next task |
| Rule: fire (slice limit, or no progress with firing on; also a worker that disputes too much) | `fired` (actor `rule`) | Reassign once, else abandon |
| Rule: fire for no progress with `--no-firing` | None | Fund the same worker again |
| Rule: continue or done | None | Next slice, or next task |
| Round ends, checks passing equal total (dropped checks are not in the total) | `round_closed` | Run ends |
| Round ends below its unlock threshold | `round_closed` (`unlocked` false) | Run ends |
| Round ends, unlocked, another round exists | `round_closed` (`unlocked` true) | Ask the investor for the next round |

## Invariants

The design relies on these. Each has a test; [THREAT_MODEL.md](THREAT_MODEL.md) cites them.

- **Only the gate produces "passed".** `rule` and `state` take pass or fail from `check_result`
  events. A worker's own `done` is a note.
- **The loop keeps no state outside the ledger.** Before every decision it rebuilds the run with
  `state.run_state`. Calling `run_firm` again on the same ledger continues the run; `boss resume` does
  that. A stop holds until a `resumed` event from the investor lifts it.
- **Money is integer micro-dollars.** The CLI's float estimate is converted once, in `stream.py`.
  Nothing stored is a float. Dollars appear only in text for people and CLI flags.
- **Unknown cost is never zero.** It is `None` from `stream.py` to the report. A slice that did
  work and reported no cost, and a slice that started and never ended, are charged at their cap
  when the round's remaining money is computed.
- **The investor's approval is bound to content.** Hashes cover the term sheet and each check
  file. They are verified at run start, before every slice and before every gate run.
- **Checks live outside the workspace** and are copied fresh into every gate run.
- **Model output never chooses money, ids, file names or paths.** The code computes them.
- **A ruling is a ledger event, never an edit.** The investor's `ruled` events leave the approved
  term sheet and check files as they were; a dropped check is skipped by reading the ledger.
- **A new session id for every attempt that is not a proven resume.** A session is resumed only
  after a slice in it got past infrastructure.
- **A worker cannot run a shell.** Its tool list must equal `Read`, `Write`, `Edit` (plus the
  CLI's structured-output tool) or the run is refused.
- **Infrastructure failures are never counted against a worker.**
- **At most two workers per task**: the first, and one replacement.
- **A slice cap leaves one reserve unspent**, and a second layer of hard limits stops the run.
- **The ledger has one writer at a time** (exclusive lock), validates each event before writing,
  and flushes to disk after each. Any invalid line makes reading fail with its line number.

## Fixed limits

Values in code, checked by the test.

| Name | Value | Where |
|---|---|---|
| Workers per task | 2 | `firm.MAX_WORKERS_PER_TASK` |
| Default worker slice | $0.10 | `firm.DEFAULT_SLICE_MICROS` |
| Reserve held back from every cap | $0.10 | `budget.RESERVE_MICROS` |
| Smallest slice cap | $0.005 | `budget.MIN_SLICE_MICROS` |
| Slices in a whole run | 60 | `limits.RunLimits.max_slices` |
| Workers in a whole run | 16 | `limits.RunLimits.max_workers` |
| Stall slices before firing | 2 | `rule.FiringPolicy.stall_slices` |
| Counted slices before firing | 6 | `rule.FiringPolicy.max_slices` |
| Infrastructure attempts | 4 | `retry.infra_action` |
| One worker slice, wall clock | 900 s | `runner.DEFAULT_TIMEOUT_S` |
| One check, wall clock | 60 s | `gate.DEFAULT_TIMEOUT_S` |
| One check on an empty workspace | 30 s | `termsheet.empty_workspace_problems` |
| One boss call, wall clock | 300 s | `boss.DEFAULT_TIMEOUT_S` |
| One boss call, cap | $0.25 | `boss.DEFAULT_CAP_MICROS` |
| Checks in a draft | 1 to 8 | `boss.MAX_CHECKS` |
| Oldest supported `claude` CLI | 2.1.277 | `worker.MIN_CLI_VERSION` |

## Not built

- Container isolation for the code the gate runs. An OS sandbox exists (`docs/SANDBOX.md`): run and
  tested on macOS, never run on Linux, and not a guard against a forged verdict.
- Calling `ledger.repair_torn_tail`. A run whose last ledger line was cut by a hard kill cannot
  be read or resumed until the line is cut by hand.
- An investor ruling on a task that was already set aside. It stays set aside for the run,
  resumed or not.
- A writer for `topped_up` and `denied` events. The budget code reads `topped_up`; nothing writes it.
- Pausing before a plan window runs out. `retry.plan_pressure` exists and the loop does not call it.
- Workers in parallel. One worker runs at a time.
- A reserve per model. There is one figure for all.
- API-key (`--bare`) mode verified against the real CLI.
