# Architecture

How `boss` is put together, what each part may and may not do, and the rules the design relies on.
`tests/test_docs_architecture.py` fails when this file and the code disagree about which modules
exist, which ledger events the loop writes, or the fixed limits in the last table.

Related: [LEDGER.md](LEDGER.md) (event schema), [CLI.md](CLI.md) (commands, run folder),
[DECISIONS.md](DECISIONS.md) (why), [THREAT_MODEL.md](THREAT_MODEL.md) (what is defended).

## Roles

| Role | What it is | Ledger actor |
|---|---|---|
| Investor | The human. Gives the idea and budget, reads every check, approves, rejects or edits. Later rules on a disputed check or a blocked task, adds money to a round with `boss topup`, and lifts a stop with `boss resume`. | `investor` |
| Boss | One model call with no tools. Drafts tasks and pytest checks. Nothing else. | `boss` |
| Worker | A headless `claude` CLI session. Tools: `Read`, `Write`, `Edit`, all scoped to its own folder. No shell. | `worker:<name>` |
| Rule | Plain code (`rule.decide`). Decides from a worker's slice history: continue, done, fire, escalate, retry. | `rule` |
| Gate | Plain code (`gate.run_gate`). Runs each check in its own pytest process. The only source of "passed". | `gate` |
| Ledger | Append-only JSONL file. Every spend and decision. Every report figure comes from it. | none |

- The actor `boss` also appears on events the loop itself writes (`started`, `hired`,
  `reassigned`, `abandoned`, `round_closed`, `paused`, `stopped`). Those are code, not a model
  call. Only `boss_call` is a model call.
- The loop (`firm.py`) is not an actor. It reads the ledger, asks the rule, and writes events.
- Specialist roles (`src/boss/roles/`) are not in this table. Each is one model call with no tools,
  behind a gate in code, and its spend is booked as a `role_call` event under the actor
  `role:<name>`. Every role is off unless `boss fund --roles` names it, and `pipeline.py` is the
  only module that calls one; [ROLES.md](ROLES.md) says where each runs and when one is switched
  on.
- A worker profile (`boss fund --profile`) is the same worker with skills added to its prompt. It
  changes what the worker is told, not what it may do.

## Module map

One row per file under `src/boss/`, `src/boss/roles/`, `src/boss/skills/` and `src/boss/bench/`. "Never" is a rule the module keeps.

| Module | Owns | Never |
|---|---|---|
| `__init__.py` | The package version, read from installed metadata. | Hold logic. |
| `approval.py` | Showing the term sheet (and the held-out checks, if any), the approve/reject/edit loop, content hashes, `require_approval`. The approval is signed by the ledger writer, like every investor event. | Set approval without an investor answer; accept a hash that does not match the files on disk, or a signature that does not verify. |
| `boss.py` | The boss's one model call: command line, draft schema, turning a draft into a term sheet. | Take ids, file names, money or round plan from the model; give the boss a tool. |
| `briefs.py` | What a worker is told: first brief, continuation after a gate run, reassignment brief, and the note about checks the investor added. | Call a model; present a worker's earlier words as instructions. |
| `budget.py` | Round budgets, top-ups, remaining money, slice caps, the reserve, unlock test, round plan. Charges a slice that did work with no cost, or that never ended, at its cap, until a later slice resumes its session and reports the total that covers it. | Use floats; read a clock. |
| `cli.py` | The `boss` command: parsing, validating counts, amounts and role lists, wiring, exit codes, `resume`, `topup`, `roles`; the `--profile`, `--parallel`, `--roles`, `--review-cycles` and `--fix-budget` options. | Decide pass, fire or money itself; call a role (it hands the pipeline to the loop). |
| `doctor.py` | Preflight checks, each with a one-line fix: the gate sandbox, and with `--live` one real worker slice that tries to write outside its folder. | Raise on an expected failure; print an environment value. |
| `errors.py` | Names the outcome of one CLI run from its stream signals and its stderr. | Trust `subtype` alone. |
| `firm.py` | The round loop: hire, fund up to `parallel` slices at once, gate each, ask the rule, write events; pause before the plan limit; gate the assembled `product/`, with the held-out checks when the run has any. | Keep state outside the ledger; record a pass itself; spend before approval matches; write the ledger from any thread but its own; let a held-out result reach a per-worker decision. |
| `gate.py` | Running checks against a fresh copy of the workspace, inside the OS sandbox when there is one; the verdict. | Read the exit code alone; accept a pass without the plugin's signed proof; run a check from the workspace; modify the original workspace. |
| `gitrepo.py` | Reading a git repository the user did not write: resolve a ref to a commit, is the tree clean, ancestry, commits between, diff, export a commit's tree. Every call is an argv list in a scrubbed environment with plumbing only, and history is read in an object-only copy of the repository. | Run a program the repository's config names (`core.fsmonitor`, filters, `diff.external`, hooks); pass a ref git could read as an option; check anything out; write to the repository. |
| `audit.py` | `boss audit plan`, and what plan and check share: the audit store's layout (a project's, in `~/.boss-audit`), the seal (the base commit and the request's hash in the term sheet's one task, so inside the signed approval), the base's public surface, and how a check's result on a tree is read (failing, passing, blocked, timeout). | Write to the audited repository or put check text anywhere outside the store; show the boss a function body, a test or any change; count a check that passes on the base; record a verdict. |
| `audit_check.py` | `boss audit check`: verifying the run first, exporting both trees from git objects, the verdict, the claim mode, the leak scan, the base's tests run over the head's code, and writing the signed `audited` event. | Run anything before the ledger, the approval and the check files verify; accept a head that does not descend from the sealed base; let a leak or a base-test failure alone produce `refuted`; print a check's code; write a verdict it did not compute. |
| `audit_report.py` | `boss audit report`: the verdicts the store's key vouches for, the false-pass rate with its Wilson interval per agent and claim mode. | Add a pre-registered verdict to a post-hoc one; read an `audited` event that does not verify; present the rate as more than a floor. |
| `_gate_plugin.py` | The pytest plugin inside every gate run: writes a signed proof that each collected test really ran and passed. Copied by the gate, never imported by boss. | Import `boss`; read pytest's reports as evidence. |
| `handoff.py` | Copying a fired worker's files and notes for its replacement. | Call a model; follow a symlink. |
| `held_out.py` | The `held_out/` folder of a run: its manifest, its content hashes, and the gate its files must pass (ids, parse, a test function, failing on an empty workspace). | Hold a check's body anywhere but that folder; let a file it does not list stand. |
| `ledger.py` | The event schema, the exclusive appender that chains each line to the one before, refuses a cut-off last line, signs every investor event and anchors the last line when it has the project's key path, the reader that checks the chain and (with that path) the signatures and the anchor, totals, `repair_torn_tail` (called by `boss resume`). | Edit or delete a line, except an incomplete last one in `repair_torn_tail`; add an unknown cost as 0; append to a ledger the key does not vouch for; hand a reader an investor event it has not verified. |
| `limits.py` | Hard run limits: spend ceiling, slices, workers, wall clock, and the size of a worker's folder. | Depend on the round budget or the rule. |
| `pipeline.py` | The roles the investor chose, around the loop: before approval (stories, staged draft, audit, judge, notes under the sheet), while a dispute is open (the consultant's line), after the build (the critic and the fix round, the demo, the judge of the usage note). Booking every role call, the `started` event's `roles`, and what a resume still owes. | Decide anything: a note binds nothing, a proposal changes the run only when the investor says yes; record an amendment by anyone but the investor; call a role that was not chosen; write a role's model text to the screen unmade safe. |
| `redact.py` | Masking secrets and control characters in text that is stored or shown (`safe_text`), in linear time. | Return text that still contains a matched secret. |
| `kpi.py` | The investor-question count and the run facts the KPIs use (product verdict, held-out grades, the single arm's last status word, the ledger's time span), all from events. | Read model text or anything but events; count a figure the ledger does not hold as 0. |
| `report.py` | The board report, computed from events, including one line per `role_call`; the held-out results (or why there are none) apart from the visible checks. | Read anything but events; fold an unknown cost into a total as 0; let a held-out result replace a visible one. |
| `retry.py` | Pure decisions on infrastructure failures: wait, pause, give up. | Sleep; read a clock; touch a process. |
| `roles/__init__.py` | `registry()`: every role, collected from the `SPECS` of the modules in the package. | List a role by hand; accept two roles with one name. |
| `roles/advisory.py` | The check auditor (an opinion on each check against the idea) and the consultant (an opinion on one disputed check). | Change a check or a ruling; accept an opinion whose quote is not a fragment of the idea. |
| `roles/base.py` | What every role is: `RoleSpec`, the one tool-less call (`call_role`), the ledger fields for its spend. | Give a role a tool; write to the ledger itself. |
| `roles/builders.py` | Worker profiles: which skills follow the base builder prompt. | Grant a tool or a permission; change the base prompt. |
| `roles/critic.py` | Reading a finished product against the idea and proposing one test per claim. | Count a finding whose test the gate did not see fail; add a check to an approved term sheet. |
| `roles/delivery.py` | The demo writer: a demo script and a usage note for a finished product. | Show output the code did not capture from a gated run; accept a script that imports more than the standard library and the product. |
| `roles/engineering.py` | The system designer and the tester, the staged draft (`draft_staged`) that chains them, and the term sheet assembled from their output. | Take ids or file names from the model; skip `termsheet.validate`. |
| `roles/examiner.py` | The examiner: held-out checks written from the idea and the public names alone, its gate, and `run_examiner` (booking the call, storing the checks, telling the investor when none were kept). | Show it a visible check's body, description or file name; keep a check whose quote is not a fragment of the idea or that passes on an empty workspace. |
| `roles/judge.py` | The judge, which scores an artifact against a rubric, and the calibration that compares it with a person. | Hand out a score with no quote from the artifact; mark a judgement calibrated anywhere but `judge_artifact`. |
| `roles/org.py` | The organisation chart, built from each role's department and parent (`python -m boss.roles.org`). | Draw roles that do not form a tree under the boss. |
| `roles/planning.py` | Funding rounds that unlock in story-priority order. | Call a model. |
| `roles/product.py` | The product manager (user stories) and the user agent (what the stories miss or misread). | Let the user agent edit the stories. |
| `roles/stories.py` | The shape of user stories and acceptance criteria, and the word-for-word quote check against the idea. | Accept a criterion whose source is not a fragment of the idea. |
| `rule.py` | The firing decision from a worker's slice history. | Read model output or state outside the history it is given. |
| `rulings.py` | The investor's questions on a disputed check or a blocked task, and reading `ruled` events back. | Decide for the investor; change the approved term sheet. |
| `rundir.py` | Run folder layout (the project's investor key path, the ledger writer and reader that use it), the event recorder, counting a folder's bytes against the size limit, assembling `product/`. | Copy a file into a path another task owns; follow a symlink. |
| `runner.py` | Running one slice as a supervised child process; isolation check at init and on any later hook event; cutting its log at 50 MB; stopping it. | Leave a child running; start in a workspace holding agent config. |
| `sandbox.py` | Building the command that runs one check inside a macOS `sandbox-exec` or Linux `bwrap` sandbox; probing that the tool works. | Run a check; put a path into profile text; trust a tool it has not probed. |
| `signing.py` | The investor's per-project key file (`.boss/investor.key`), the HMAC on every investor event, and the anchor file (`.boss/anchors/<run>`: the HMAC of the ledger's line count and last line hash). | Print, log or put the key in an error; create it readable by anyone but the owner; sign an event that is not yet chained. |
| `skills/__init__.py` | Loading and parsing skill files: a header of `name`, `version` and `description`, then a body. | Accept another header; load a body over 4,000 characters. |
| `state.py` | Rebuilding run state (workers, tasks, rounds, stops, sessions, dropped checks) from events. | Read anything but events. |
| `stream.py` | Reading the CLI's `stream-json` output; usage and cost. | Raise on malformed input; turn a missing cost into 0. |
| `termsheet.py` | Term sheet types, JSON round trip, validation. | Accept a wrong JSON type; skip the empty-workspace run of every check. |
| `worker.py` | The exact worker command, the environment allowlist, status cleaning, the isolation test. | Offer a shell tool; pass a variable that is not on the allowlist. |
| `bench/__init__.py` | The package marker for the benchmark. | Hold logic. |
| `bench/audit.py` | Auditing saved drafts with the check auditor and scoring its flags against the reference solution (`python -m boss.bench.audit`). | Show the auditor the reference or a mutant; spend money under `--dry-run`. |
| `bench/drafts.py` | Drafting checks per task, with the boss's one call or the three-role staged draft, and scoring each draft (`python -m boss.bench.drafts`). | Start a worker; show the boss a hidden check, the reference or a mutant. |
| `bench/imported.py` | Converting a downloaded external task into an imported bench task folder (`python -m boss.bench.imported`). | Write task data into the repository; overwrite an existing task. |
| `bench/paired.py` | A paired comparison of two arms by task: the mean per-task difference of one KPI with a task-level bootstrap interval (`python -m boss.bench.paired`). | Compare results of different task sets; count an infrastructure failure; call one task enough to show a difference. |
| `bench/replay.py` | Replaying a firing policy over recorded ledgers, offline. | Call a model; use a different rule from the live one; walk past DONE or ESCALATE. |
| `bench/results.py` | One benchmark cell's result record and its load checks. | Accept a wrongly typed field. |
| `bench/run.py` | Running benchmark cells through the single, single-review and firm arms; for the firm arm, passing `--held-out N` through and recording the held-out passed and total. | Copy hidden checks or the reference into a workspace or a prompt. |
| `bench/score.py` | Scoring a draft's checks (precision on the reference, recall on the mutants) and a critic's verified findings against the reference. | Spend money; count a mutant killed only by a wrong check as caught. |
| `bench/table.py` | The results table with intervals. | Count an infrastructure failure in a rate; treat unknown cost as 0. |
| `bench/kpi.py` | The fixed KPI scorecard of benchmark results: one column per folder, arm, model, budget and firm options. | Count an infrastructure failure in a figure; show an unknown cost or an unrecorded figure as 0; pool columns that share a label. |
| `bench/tasks.py` | Task format, validation, the task set hash. | Accept a task whose checks pass on an empty workspace or fail on its reference. |

Prompts are files, not code. The boss and the benchmark use `src/boss/prompts/term_sheet_v1.md`
(one task), `term_sheet_v2.md` (several tasks), `builder_v4.md` (every worker) and `solo_v2.md` (the
benchmark's single agent) and `self_review_v1.md` (the `single-review` arm's second slice). Each role
has its own: `product_manager_v1.md`, `user_agent_v1.md`,
`system_designer_v1.md`, `tester_v1.md`, `critic_v1.md`, `judge_v1.md`, `demo_writer_v1.md`,
`check_auditor_v1.md`, `consultant_v1.md` and `examiner_v1.md`. `boss audit plan` has one of its
own, `audit_checks_v1.md`. Skills are Markdown files under `src/boss/skills/`
that a role's or a worker profile's system prompt is built from; [ROLES.md](ROLES.md) says how they fit.

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
5. With `--rounds N` above 1, the round plan is replaced by an equal split (or by story priority when roles draft), with
   fewer rounds if the run's reserve plus $0.005 would not fit in each.
6. The investor reads the term sheet and every check, and approves, rejects or edits. Approval is
   an `approved` event holding hashes of the term sheet and each check file, and of the held-out
   files when the run has them. With `--held-out N`, `boss fund` first has the examiner write
   them (`Pipeline.examine`, which calls `roles.examiner.run_examiner`), between steps 4 and 6.
7. `run_firm` verifies the approval, writes `started` once (the run's configuration), then for each
   round asks for the investor's yes (rounds after the first) and runs the round.
8. The round loop plans a wave: the first tasks whose checks do not all pass, at most `--parallel`
   of them (default 1). For each it checks the hard limits, computes the slice cap, gets or hires a
   worker, and verifies the approval again. Each later slice of a wave leaves one more reserve
   unspent.
9. It records `slice_start` for each, runs the slices (a `claude` process in each worker's folder;
   one thread each when there are several), then records every `slice_end`, so no known cost is
   lost. Unless a slice failed for infrastructure reasons, it runs the gate on that worker's
   folder and records one `check_result` per check.
10. The rule decides from the ledger alone. The loop writes the matching event (table below) and
    goes to step 8. Only the loop's own thread writes the ledger.
11. When the round ends, `round_closed` is written. The run ends when every check passes, a limit
    stops it, or the next round is not unlocked or not funded.
12. `product/` is assembled from each task's best worker. The gate then runs every required check
    on `product/` and records one `check_result` per check with `scope: product`; that count
    decides the exit code, and the loop says so when it differs from the workers' folders. When
    the run has held-out checks (`FirmConfig.held_out`, the examiner's, approved with the term
    sheet), they are run on `product/` too and recorded with `scope: held_out`; the exit code
    needs them to pass as well. The report is rendered from the ledger, saved as `report.md` and
    printed, with the two results apart. Exit 0 if every check passed, else 3.

`boss resume [run]` continues a run that was interrupted (Ctrl-C, exit 130), paused or stopped:

1. `repair_torn_tail` cuts a last ledger line that a hard kill left incomplete, and says so. A
   damaged ledger that this does not fix ends the command with exit 1.
2. It reloads `term_sheet.json` and the configuration from `started` (so the same `--profile`,
   `--parallel` and limits). A run with no `started` event never hired anyone and cannot be
   resumed.
3. If the run is stopped, it writes `resumed` (actor `investor`) after saying why it stopped. The
   command is the investor's act; nothing else lifts a stop.
4. It calls `run_firm` as in step 7. Approval, budget and every hard limit are checked again as
   the loop goes; a round that was interrupted stays open and continues; a round that closed below
   its unlock threshold stays locked until the investor tops it up.
5. A slice with a `slice_start` and no `slice_end` is charged to its round at its cap. If the last
   slice was never gated, the loop gates it; a firing, an escalation or a half-asked set of
   disputes that was owed is carried out. A product verdict cut short is completed: only the
   checks with no `scope: product` result are run, and likewise the held-out checks with no
   `scope: held_out` result.

`boss topup [run] --round N --amount D` records the investor's money for one round:

1. It repairs a cut last ledger line as `resume` does, loads `term_sheet.json`, and takes the
   ledger's exclusive lock; a lock held by another process ends the command with exit 1.
2. Holding the lock it reads the ledger and refuses a round the term sheet does not have, or one
   that closed unlocked (exit 2).
3. It writes one `topped_up` event (actor `investor`, the round, `micros`) and prints the round's
   new budget. It spends nothing: the next `boss resume` runs the loop, which counts the event in
   `budget.round_budget` (so also in the spend ceiling) and, for a locked round, treats the lock
   as lifted (`state.run_state`).

## Control flow of `firm.py`

Each row is one decision in `_Firm.run`, `_run_round`, `_current_worker`, `_slice` or `_act`.
"None" means no ledger event.

| Decision | Ledger event | Next step |
|---|---|---|
| Approval missing or not matching at start | None; `NotApprovedError` is raised | Nothing is spent |
| Start of `run_firm`, first time | `started` (actor `boss`, holds the configuration) | Nothing else is written on a resume |
| A `stopped` event exists and no `resumed` after it | None | Run ends ("stopped earlier") |
| Round already has `round_closed` with `unlocked` false, and no investor `topped_up` for it since | None | Run ends (the round stays locked, also after a resume) |
| Round already has `round_closed` | None | Next round |
| Round not approved, investor answers no or input ends | `stopped` (actor `investor`) | Run ends |
| Round not approved, investor answers yes | `approved` (actor `investor`, `round`) | Run the round |
| No task with failing checks and not abandoned | None | Round ends; `round_closed` |
| Hard limit reached | `stopped` (actor `rule`) | Run ends; the round stays open, no `round_closed` |
| Round cannot fund a cap of at least the minimum after the reserve | None (a message is printed) | Round ends; `round_closed` |
| Task's worker exists and is not fired | None | Fund its next slice |
| Task's worker fired, task already had two workers | `abandoned` (`already reassigned once`) | Next task |
| Task has no worker | `hired` (holds the `prompt` file and the `profile`, null when none; a workspace folder left by an interrupted hire is deleted first) | Fund its first slice |
| Task's worker fired, one worker so far | `reassigned`, then `hired` | Fund the replacement; files offered under `previous_attempt/` |
| Approval no longer matches, a check file is missing or unreadable, or a worker's folder is over the size limit (200 MB), before a slice or a gate run | `stopped` (actor `rule`) | Run ends; the round stays open |
| The worker's last slice has no `check_result` (an interruption) | `check_result` per check, as below | Rule decides |
| A slice is funded (cap known, approval verified), one per task in a wave | `slice_start` (with a `session` id: new unless a slice in that session already got past infrastructure) | Run the slice in the worker's folder; the wave's slices run at once |
| The investor approved more checks (an `approved` event with `added_checks`) since the worker's last slice | None | The worker's next brief shows those checks' code and says they must pass |
| Worker did not start isolated, or a hook event appears after init | `error` (actor worker, cost unknown), then `stopped` | `IsolationError` reaches the CLI; exit 1 |
| Slice finished, any outcome | `slice_end` for every slice of the wave first; then `check_result` per check for each (a check the investor dropped is not run), unless the outcome is infrastructure | Rule decides |
| Slice finished, worker disputes a check that fails now, not disputed before, not ruled on | `disputed` (actor worker) | Rule decides |
| Rule: infrastructure outcome, attempts left | None (a message is printed, then a sleep) | Same task and worker again |
| Rule: infrastructure outcome, plan usage limit | `paused` | Run ends; the round stays open |
| A slice reported a plan window at or above `plan_pause_at` (0.95) and a task still has failing checks | `paused` (actor `boss`, with `reason` and `until_epoch`) | Run ends; the round stays open |
| Rule: infrastructure outcome, login lost or attempts used | `stopped` (actor `boss`, with `fix`) | Run ends; the round stays open |
| Rule: worker reports `blocked` with no refused tool call, or the model refused | `blocked` (unless already written), then the investor is asked | Next row |
| Investor unblocks with a note | `ruled` (`unblocked`, with the note) | Fund the same worker; the note is in its next brief |
| Investor sets the task aside, or gives no clear answer | `abandoned` | Next task |
| Rule: the worker's only failing checks are ones it disputes (or an earlier worker of its task did, unruled), and they are at most half of the task's checks | The investor is asked once per disputed check | Next two rows |
| Investor drops a disputed check | `ruled` (`dropped`, actor `investor`) | The check is no longer run or counted; unlock thresholds follow |
| Investor keeps a disputed check | `ruled` (`kept`) | Dispute settled; the worker is told to satisfy it |
| Investor sets the task aside, or gives no clear answer | `abandoned` (`disputed`) | Next task |
| Rule: fire (slice limit, or no progress with firing on; also a worker that disputes too much) | `fired` (actor `rule`) | Reassign once, else abandon |
| Rule: fire for no progress with `--no-firing` | None | Fund the same worker again |
| Rule: continue or done | None | Next slice, or next task |
| Round ends, checks passing equal total (dropped checks are not in the total) | `round_closed` | Run ends |
| Round ends below its unlock threshold | `round_closed` (`unlocked` false) | Run ends |
| Round ends, unlocked, another round exists | `round_closed` (`unlocked` true) | Ask the investor for the next round |
| The run ends and `product/` is assembled | `check_result` (actor `gate`, `scope` `product`) for each required check that has no product result yet | The count of passing checks is the run's result; nothing is run when the product folder is over the size limit or the checks no longer match the approval |
| The same, for a run with held-out checks | `check_result` (actor `gate`, `scope` `held_out`) for each held-out check that has no result yet | The run passes only when these pass too; no per-worker decision reads them |

## Invariants

The design relies on these. Each has a test; [THREAT_MODEL.md](THREAT_MODEL.md) cites them.

- **Only the gate produces "passed".** `rule` and `state` take pass or fail from `check_result`
  events. A worker's own `done` is a note.
- **What is delivered is gated.** Each task is gated in its own worker's folder; at the end the
  checks run again on the assembled `product/`, and that result is the run's.
- **A worker never sees a held-out check.** They are stored outside every workspace, graded only
  on `product/`, approved by the investor with the term sheet, and ignored by `state` and `rule`.
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
  and flushes to disk after each. Any invalid line makes reading fail with its line number. With
  several slices at once, only the loop's thread writes: slices return their results to it.
- **A worker's folder and a slice's log are bounded.** A folder over 200 MB is never gated (the run
  stops), and a log is cut at 50 MB.

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

The reserve row is Haiku's, and the figure for any model not recognised. `budget.reserve_for`
scales it for larger models: 3x for Sonnet, 5x for Opus (output-price ratios, not measured).

## The roles around the loop

`boss fund --roles a,b` makes `cli.py` build a `Pipeline` (`pipeline.py`) and hand it to the loop.
With no roles every method of it does nothing and writes nothing.

1. **Before approval.** `Pipeline.plan` runs the product manager, then the user agent, then the
   designer and the tester (`draft_staged`) in place of the boss's call, then the check auditor and
   the judge of the stories. Each note is shown under the term sheet by `review_term_sheet`. A
   failed product manager or staged draft falls back to the boss's own call (`draft_boss`, passed
   in by `cli.py`). The approval covers the sheet and the check files only, so the notes do not
   change its hashes.
2. **While the loop runs.** `Pipeline.advisor` is the `advise` function `run_firm` calls before it
   asks about a disputed check. It calls the consultant and returns one line, or nothing if the
   call failed.
3. **After the loop.** `Pipeline.after_build` runs only if something was built. The critic reviews
   `product/`; its verified findings become checks for the task that owns the module they import,
   plus a new last round. If the investor says yes, `pipeline.py` records an investor `approved` event
   with `hashes`, `round` and `added_checks`, rewrites `term_sheet.json`, and `cli.py` runs the
   loop again on the amended sheet. The demo writer and the judge of `USAGE.md` run only if
   every required check passes.

Every role call is booked as a `role_call` in round 0 by `Pipeline._book`, whether it worked or
not. A failure is told to the investor and never read as "no findings". What a resume still owes
is counted from `role_call` events: one critic call per review cycle, and one demo call and one
usage judgement per build of the product (the last `slice_end`).

## The audit commands

`boss audit` reuses the run's ledger, the investor's signed approval and the gate; it adds no loop
and funds no worker. It answers one question: did a change somebody else's agent made do what the
request asked?

1. `plan`: `gitrepo` resolves the base to a hash and refuses a dirty tree; the base is exported to a
   temporary folder; `audit.public_surface` reduces it to paths and names; one boss call (no tools,
   `audit_checks_v1.md`, the request and the surface as fenced data) returns checks; each check runs
   on the base, in the gate; the investor approves through `review_term_sheet` with what each check
   did on the base shown under the sheet. Everything lands in `<store>/.boss/runs/<id>/`, never in the
   repository. Nothing the boss was shown comes from the change, because the change need not exist.
2. `check`: the ledger is read with the store's key (chain, anchor, signatures); `require_approval`
   matches the term sheet, the check files and the held-out folder; the base commit is read back out
   of the signed term sheet; the head must descend from it. Both trees are exported; every check runs
   on the base again to find the counted ones; the counted ones run on the head. The diff is scanned
   for the checks' text, the base's `tests/` run over the head's code, and `decide` turns it into a
   verdict, which the gate writes as a signed `audited` event.
3. `report`: reads the verified `audited` events and computes the false-pass rate per agent and mode.

The verdict is the gate's alone. A model chose the checks and an investor approved them, but nothing a
model says is read after that: no claim is parsed, no output of the agent is shown to a model.

## Not built

- Container isolation for the code the gate runs. An OS sandbox exists (`docs/SANDBOX.md`): run and
  tested on macOS, never run on Linux, and not a guard against a forged verdict: the gate's
  signed proof stops generic forgery but not code that reads its nonce (T12).
- An investor ruling on a task that was already set aside. It stays set aside for the run,
  resumed or not.
- A writer for `denied` events. Nothing writes it.
- In `boss audit` v1: installing dependencies for the checks, non-Python code, checks that need a
  network, a service or a database, monorepos with several environments, retrying a flaky check,
  Windows, a GitHub Action, scanning an agent's transcript for a leak, and reading an agent's words
  to find its claim. The store is private to its owner and outside the repo, which does not stop an
  agent that runs as the same operating-system user (T51); that needs another user or a container.
  The audit's signatures are HMACs under a local key, so only the store's owner can check them
  (B80). See B77 to B84 in [BACKLOG.md](BACKLOG.md).
- A measured reserve for Sonnet and Opus. Their figures scale Haiku's by output price; only Haiku was measured.
- API-key (`--bare`) mode verified against the real CLI.
