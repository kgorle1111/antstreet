# Command line

Every command and option, the environment variables the tool reads, exit codes, and what a run
leaves on disk. `tests/test_docs_cli.py` reads the real argparse parsers and fails if an option or
command is missing here, is documented but does not exist, or has a different default.

Related: [ARCHITECTURE.md](ARCHITECTURE.md), [LEDGER.md](LEDGER.md), [ROLES.md](ROLES.md).

Every command also accepts `-h` and `--help`.

## `boss`

`boss [--version] <command> ...` where the command is `fund`, `resume`, `topup`, `report`,
`status`, `roles`, `doctor` or `audit` (which has three steps of its own: `audit plan`, `audit check`
and `audit report`).

| Option | Default | Meaning |
|---|---|---|
| `--version` | off | Print `boss <version>` and exit 0. |

- A command is required. Without one, argparse prints usage and exits 2.
- Commands run against a project folder (`--dir`). Runs are stored under `<dir>/.boss/runs/`.
  `boss audit` is the exception: it audits a git repository you name and keeps its runs in the
  audit store (see `boss audit plan`).

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
  exits 130. Nothing already recorded is lost. Ctrl-C earlier, while the boss or a role is being
  called, ends the run with a message and exit 130: nothing was funded, what the calls so far cost
  is on the ledger, and there is nothing to resume. Ctrl-C at the approval question counts as
  reject.
- The dispatch options are checked before anything is spent (exit 2): `--max-tier` needs `--dispatch
  rules`; with `--dispatch rules`, `--model` must be `haiku`, `sonnet` or `opus` (or a full id of
  one), may not be above `--max-tier`, and `--reserve` may not be given (the reserve is per model).
  Under `--dispatch rules` the term sheet also shows `Route: one agent (one file, N checks)` when
  everything is built in one file, or `Route: firm (K tasks, files ...)`. On the one-agent route a
  fired worker is replaced only by a stronger one; in the firm it is replaced as before. You may
  set `"route": "firm"` on a one-file sheet; `"one_agent"` on a sheet with several files is refused.
- `--roles` is checked before anything is spent. An unknown name, or a role without the roles it
  needs, is a usage error (exit 2) that says what to change. `--fix-budget` below one reserve plus
  $0.005 is refused the same way.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder. |
| `--budget` | required | Budget for the funding rounds in dollars, such as `0.50` or `$0.50`. Positive, at most 6 decimals. The boss's own drafting call is charged on top of it. |
| `--model` | `haiku` | Worker model. |
| `--rounds` | `1` | Funding rounds to split the budget into. With more than one, the budget splits equally (the earliest rounds take any remainder), the count is capped at the number of checks, and each round after the first needs your yes. |
| `--slice` | `$0.10` | Dollars a worker may spend in one slice, before the gate looks again. At least $0.005; a smaller slice is never funded (exit 2). |
| `--reserve` | by `--model` | Dollars held back from every slice cap: what one response can cost past the cap. `$0.10` for `haiku` and any model not recognised, `$0.30` for `sonnet`, `$0.50` for `opus` (a name that contains the family). An explicit value wins and is recorded on `started`. |
| `--max-tasks` | `1` | Most tasks the boss may split the work into. Above 1 the multi-task prompt is used. |
| `--profile` | none | Worker profile: one of `generalist`, `backend_engineer`, `ai_engineer`, `test_engineer`, `refactorer`. Its skills are added to the worker's prompt. Without it the worker gets the bare builder prompt. `boss roles` lists each profile's skills. |
| `--worker-thinking` | none | Thinking tokens per worker slice; 0 turns thinking off. Unset keeps the CLI's own default. Recorded on `started`, so `boss resume` keeps it. |
| `--held-out` | `0` | Held-out checks to ask the examiner for, 0 to 8; 0 is off. The examiner sees the idea and the names the product must expose, never a visible check. You read and approve its checks with the term sheet; no worker is shown them; the finished product must pass them too. Its call is paid from round 1's budget, and is skipped (and said) when round 1 could not then fund a worker slice. See `docs/ROLES.md`. |
| `--dispatch` | `off` | `off`: every worker runs on `--model`, as always. `rules`: the term sheet shows a route and one dispatch row per task (agent, model, effort, what happens if its worker is fired, context size, slice cap) and a worst case in dollars; you can edit `route` and each task's `dispatch` in `term_sheet.json` with `[e]dit`, and what you approve is hashed with the rest of the sheet. A worker the gate fired for no progress or a slice limit is replaced one tier up (once per task); no other event changes a model. Every slice records the hash of the exact text the worker was given and the model the CLI says it ran, and a model other than the one launched stops the run. See D43 to D45 in `docs/DECISIONS.md`. |
| `--max-tier` | none | With `--dispatch rules`: the dearest model dispatch may use, `haiku`, `sonnet` or `opus`. Without it dispatch stays at `sonnet`. A sheet that names a dearer tier, in the first plan or in an edit, is refused before it can be approved and again before anyone is hired. |
| `--spec` | off | The boss's checks must cite the rules of your idea, which code cuts out of your own sentences and numbers R01, R02, ...; each check names the 1 to 5 rules it tests, and the boss may list rules it leaves untested, with a reason. Before you approve you see the coverage, uncovered rules first, then claims a check cannot be testing (the check does not contain a non-ASCII string, the exception, the size or the type the rule names), then the boss's waivers; literals and list items are shown apart and not scored. The rule list is saved as `rules.json`, hashed in your approval, and a coverage summary is recorded in it. One task only (`--max-tasks 1`), not with the staged draft (`--roles system_designer,tester`). Refused before any spend when the idea has more than 40 numbered items or paragraphs, or no sentence stating a behaviour. |
| `--parallel` | `1` | Tasks to work on at once. A task still has one worker at a time, and at most two in all (the first and one replacement). Slices that run together each leave room for the reserve of every earlier one, so a small round funds fewer at once. Only useful with `--max-tasks` above 1. |
| `--max-slices` | `6` | Fire a worker after this many slices that count. |
| `--stall-slices` | `2` | Fire a worker after this many counted slices in a row with no new passing check. |
| `--max-minutes` | none | Stop the run after this many minutes of wall clock, counted from the start of this `fund` or `resume`. Checked before each slice, so a slice in progress can run past it. |
| `--no-firing` | off | Keep funding stalled workers. A worker is still fired at the slice limit. |
| `--boss-model` | `haiku` | Model for the boss's own call. |
| `--boss-thinking` | none | Thinking tokens the boss may use; 0 turns thinking off. Without it the CLI's default applies. Roles use it too. |
| `--roles` | none | Specialist roles to run around the build, comma separated, or `all`. Names are those `boss roles` prints. Each role is one capped model call; its spend is a `role_call` event. `user_agent` needs `product_manager`; `tester` needs `product_manager` and `system_designer`; `system_designer` needs `tester`. A role's model is `--boss-model`. [ROLES.md](ROLES.md) says when each runs. |
| `--review-cycles` | `1` | Times the critic may review the finished product and offer a fix round. With 0 the critic still runs and its findings are shown, but you are asked nothing. |
| `--fix-budget` | two slices plus one reserve | Dollars for a fix round after the critic's findings: `$0.30` with the default slice and reserve. At least one reserve plus $0.005. |
| `--fix-after-stop` | off | Needs `--roles critic`. When the run ended only because a round closed below its unlock threshold (no limit, pause, stop or awaited ruling), the critic's findings are still offered: a yes adds the checks and records the fix money as your `topped_up` of that round, which reopens it; no round is added. Every other stop still offers nothing. Recorded on the run, so `resume` keeps it. |

What it asks you:

- `[a]pprove, [r]eject, or [e]dit files and re-check?` after showing the term sheet. `edit` lets
  you change `term_sheet.json` and the check files, then re-validates them. End of input counts as
  reject.
- `Round N: X/Y checks pass. Fund $Z more? [y]es / [n]o` before each round after the first. End
  of input counts as no.
- With the critic on, after the build: `Add these N checks and fund a fix round of $X? [y]es / [n]o`,
  once per review cycle and only when the critic has verified findings and the run did not end
  early. It shows each proposed check and its code first. `y`, `yes`, `a` and `approve` are yes;
  anything else, and end of input, is no. Ctrl-C ends the command with exit 130 and is not an answer:
  `boss resume` asks the critic again and puts the question again. When a round of the sheet never
  opened, the fix round takes its place and that round follows it.

Limits that are not options: a run stops at 60 slices or 16 workers, when spend passes the sum of
its round budgets plus one reserve per round, or when a worker's folder passes 200 MiB (the gate
copies it for every check). See [ARCHITECTURE.md](ARCHITECTURE.md#fixed-limits).

A `--budget` below one reserve plus $0.005 is refused before anything is spent. With `--rounds`
above 1 the number of rounds depends on how many checks the boss drafts, so rounds are planned
with this run's reserve (`--reserve`, or the model's) as a floor: a plan has fewer rounds, down to
one, rather than a round below one reserve plus $0.005. The plan is checked again after the draft,
before approval; if a round is still below that, the run stops (exit 1) with the draft paid for
and nobody hired.

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
| `--review-cycles` | `1` | As for `boss fund`. |
| `--fix-budget` | two slices plus one reserve | As for `boss fund`; the slice and reserve are the run's own. |

- It reads `term_sheet.json` and the configuration recorded when the run started, so a resumed
  run keeps its own slice, reserve, firing and limit settings. There are no options to change them.
- Running it is your decision to lift a stop: it prints why the run stopped and writes `resumed`.
  The approval, the budget and every hard limit are checked again as the loop goes, so a lifted
  stop can stop again at once. The wall-clock limit (`--max-minutes`) counts from the start of
  each `resume`, so a resumed run gets the whole time again.
- An interrupted round continues. A round that closed below its unlock threshold stays locked
  until you reopen it with `boss topup`. A task that was set aside stays set aside.
- A slice that started and never ended is charged to its round at its cap. If the last slice was
  never gated, or a firing or a question to you was owed, it is done first.
- The roles are the ones recorded when the run started. Their first stage (stories, staged draft,
  audit) is not run again; the consultant answers disputes; the critic, the demo and the judge of
  the usage note run after the build unless the ledger shows they already did, so a second
  `resume` of a finished run adds nothing.
- On a run that already finished it changes nothing and prints the report.
- Refused with exit 1, spending nothing: no run found; no usable `term_sheet.json`; a damaged
  ledger; the run never got as far as hiring (start again with `boss fund`); the term sheet or a
  check no longer matches your approval.
- A ledger whose last line was cut by a hard kill is repaired first: the cut line is removed and
  `resume` prints it. A ledger damaged anywhere else is refused.
- If another `boss` process is still writing the run's ledger, `resume` says so and exits 1.
  Nothing is changed, not even a cut-off last line.
- Exit codes are those of `boss fund`.

## `boss topup`

`boss topup [--dir DIR] [RUN] --round N --amount D`. Adds money to one round of an existing run:
you pay more for the same term sheet. It records one `topped_up` event (actor `investor`, the round,
`micros`) and spends nothing itself; `boss resume` continues the run.

Argument: `run`, a run id. Default: the latest run in the folder.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder. |
| `--round` | required | The round to add money to, a whole number of 1 or more. |
| `--amount` | required | Dollars to add, more than 0 and at most 6 decimal places, e.g. `0.20`. |

- The round's budget becomes its term-sheet amount plus every top-up, and the run's spend ceiling
  grows with it. The command prints the new budget and what is left, and says so when that is
  still less than a slice needs (the reserve plus the smallest slice).
- A round that closed below its unlock threshold (its budget ran out, or too few checks passed)
  stays locked on `boss resume` until you top it up. A top-up recorded after the lock reopens that
  round: the loop funds it again, with no new approval, and closes it again when it ends. A round
  whose lock was already lifted by an earlier top-up needs another one to be reopened a second
  time. A top-up of a round that is open, or not yet opened, only adds to its budget.
- Only an event whose actor is `investor` counts: a `topped_up` event written by a worker, a role
  or the loop adds nothing and reopens nothing.
- Refused with exit 2, writing nothing: a bad `--round` or `--amount`; a round the term sheet does
  not have; a round that closed with its checks unlocked (the run has moved on, so the money would
  never be spent).
- Refused with exit 1, writing nothing: no run found; no usable `term_sheet.json`; a damaged
  ledger. A ledger whose last line was cut by a hard kill is repaired first, as `resume` does.
- If another `boss` process is still writing the run's ledger, `topup` says so and exits 1.
  Nothing is changed, not even a cut-off last line.
- There is no upper limit on `--amount`: check the figure, `0.20` is twenty cents.
- Exit 0 once the event is written.

## `boss report`

`boss report [--dir DIR] [RUN]`. Prints the board report of a run, computed from its ledger. A run with held-out checks shows their result apart from the visible checks (`Held-out checks: 2 of 3 passed on the product; the workers never saw them.`); a run that asked for them and got none says why. One line says whether the checks ran sandboxed (`Checks ran sandboxed: 12 of 12.`), with a WARNING when any ran unconfined and "not recorded" for a ledger written before the flag existed (T39).

A **KPIs** section follows the spend. All of it comes from the ledger: `Delivered` (every check
passes on the assembled product, or NO, or "not recorded" for a ledger with no product verdict),
`Held-out checks` and `False pass` (every visible check passed but a held-out one failed; "not
measured" when the run had no held-out checks), `Cost` (an unknown cost is listed beside it, never
as 0), `Time` (first to last ledger event, so it includes any wait for you) and `Investor
questions` (the count rule is in `bench/METHOD.md`).

Argument: `run`, a run id. Default: the latest run in the folder.

For a run made with `--dispatch rules`, each worker is one line (`w2 on t1: sonnet/default,
escalated from haiku (fired: no progress), $0.0300, 1 slice, delivered; ran as claude-sonnet-...`),
and the report rehashes every saved prompt (`logs/<worker>-s<N>.prompt.txt`) against the hash its
`slice_start` recorded. A file that is missing or changed is printed as `CONTEXT CHECK FAILED` and
the command exits 1.

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

## `boss audit plan`

`boss audit plan --repo REPO --request FILE --base REF [--held-out N] [--boss-model MODEL]`. Seals
checks for a change request before the change is looked at, so that a commit an agent makes later
can be tested against them. It asks the boss for checks once, runs them on the base commit, shows
you every check and what it does there, and asks whether to approve. It never writes to `REPO`.

| Option | Default | Meaning |
|---|---|---|
| `--repo` | required | The git checkout to audit: the folder that holds `.git`. |
| `--request` | required | A text file with the change request, up to 64 KiB, not starting with `-`. |
| `--base` | required | The branch, tag or full commit hash the change is made from. A revision expression (`HEAD~1`, `a..b`, `x:path`) is refused. |
| `--held-out` | `0` | Checks an examiner writes as well, from the request and the names the checks import, 0 to 8; 0 is off. You read and approve them with the rest. |
| `--boss-model` | `haiku` | Model for the boss's own call. |

- Refused with exit 1, before anything is written: a working tree that is not clean (a staged or
  modified file, or an untracked one that is not ignored); a ref that is not a plain name or hash; an
  audit store inside the repo; a request that is empty, too big or starts with `-`.
- The boss is shown the request and the base's public surface: file paths and, for each Python file
  outside tests, the names and signatures it exposes. It is never shown a function body, a test, or
  any change (`src/boss/prompts/audit_checks_v1.md`). The call has no tools.
- Each check then runs on the base, in the gate, and is shown with what happened: **fails on the
  base: counted** (it separates a finished change from an unfinished one), **passes on the base:
  shown, not counted**, **cannot run here: not counted** (it needs a module that is not installed
  and that neither the base nor the request names), or **timed out on the base: not counted**. If
  no check fails on the base you are told every verdict would be inconclusive, and can reject.
- You approve or reject as for `boss fund`; the approval is signed with the audit store's investor
  key. The sheet's budget figure is a placeholder: the audit funds no worker.
- The base commit and the request's SHA-256 are in the one synthetic task's brief, so they are inside
  the hash your approval covers: editing either, a check, or a held-out file voids it.
- Prints the run id and the **seal**, one SHA-256 over the approved term sheet, every check file and
  every held-out file. Record the seal somewhere the agent cannot change; `boss audit check` writes
  it into every verdict.
- The **audit store** is `$BOSS_AUDIT_HOME`, or `~/.boss-audit` when it is unset. It is laid out like
  a project: `.boss/runs/<id>/` holds `ledger.jsonl`, `term_sheet.json`, `checks/` and, with
  `--held-out`, `held_out/`; `.boss/investor.key` and `.boss/anchors/` are as in a project. The
  folders it creates are mode 0700. No check text is written to the repo, the boss's prompt or any
  working folder, and a store inside the repo is refused. This keeps the checks from an agent that
  works in the repo and reads only what it is given. It does not stop one that runs as the same
  operating-system user and looks in `~/.boss-audit`: that needs another user or a container
  (T51).
- The draft's cost is a `boss_call` event with `purpose` `audit_checks`; the examiner's is a
  `role_call`.
- Exit 0 when sealed. Exit 1 when you reject, the boss's output is unusable, or a refusal above.
  Exit 130 on Ctrl-C.

## `boss audit check`

`boss audit check RUN --head REF [--repo REPO] [--claim done|none] [--claim-text FILE] [--agent LABEL]`.
Runs the sealed checks of audit run `RUN` on a commit and writes the gate's verdict to its ledger as a signed
`audited` event.

Argument: `run`, the id `boss audit plan` printed.

| Option | Default | Meaning |
|---|---|---|
| `--head` | required | The branch, tag or full commit hash to audit. |
| `--repo` | `.` | The git checkout that holds the head and the sealed base. |
| `--claim` | `none` | What the agent said of its own work: `done`, or `none`. Only a claim of `done` can be refuted. v1 does not read the agent's words to decide this. |
| `--claim-text` | none | A file with the agent's own words, up to 64 KiB. Kept as a SHA-256 only. |
| `--agent` | none | A label for the agent (1 to 64 letters, digits and `. _ : @ / + -`), to report by. |

- Verified before anything runs, each refused with exit 1 and nothing written: the run's ledger
  (hash chain, anchor, every signature), the investor key exists, the term sheet is marked approved
  and its signed approval matches the term sheet, every check file and every held-out file, the
  sealed base is in the repo, and **the head descends from the base**.
- Both trees are exported from git objects only, never checked out. A **counted** check is one that
  fails on the base, found by running every check there again, so no stored status can be edited.
  Only counted checks run on the head.
- Verdict, from the claim and the head:

  | Verdict | When |
  |---|---|
  | `refuted` | claim `done`, and a counted check fails on the head. |
  | `unrefuted` | claim `done`, at least one counted check, every one passes, none could not run, and no text of the sealed checks is in the change. Not proof. |
  | `inconclusive` | claim `done`, no counted check failed, and: no check fails on the base, or a counted check could not run on the head (timeout, or a module that is not installed), or the change quotes the sealed checks (below). |
  | `no_claim` | the claim is `none`, whatever the checks say. |

- Claim mode: `pre_registered` when the range has at least one commit and **every** commit is dated
  after the seal (the investor's `approved` event); otherwise `post_hoc`. Commit dates are chosen by
  whoever commits and can be forged either way; the mode is a record, not a proof. The output says so
  for a post-hoc claim.
- Leak scan: the added lines of the diff are searched for what the sealed checks contain: a test name of four or more
  words, or a string literal of 16 or more characters, that the request does not itself contain. A hit
  is listed as `c01 test name` or `c01 string literal` and turns an otherwise passing verdict into
  `inconclusive`; a refutation stands.
- Also run, and listed beside the verdict but not part of it: the base's own `tests/` folder
  against the head's code. It lists base test files the head no longer has, and base tests that
  pass on the base and fail on the head's code, so a test the agent deleted or weakened still speaks.
  A request that changes behaviour breaks old tests honestly, so these are for you to read.
- The output names failing checks by id and description, never by code.
- The `audited` event is written only after all of the above, signed with the store's key.
- Exit 0 for `unrefuted` and `no_claim`. Exit 3 for `refuted` and `inconclusive`. Exit 1 for any
  refusal above. Exit 2 for a bad option.

## `boss audit report`

`boss audit report [RUN] [--all] [--agent LABEL]`. Prints each run's verdicts and the false-pass
rate. Reads only `audited` events the gate wrote and the store's key vouches for: a ledger with a
forged or edited one makes the command fail, so part of the store is never reported on.

Argument: `run`, an audit run id. Default: the latest.

| Option | Default | Meaning |
|---|---|---|
| `--all` | off | Every run in the store. |
| `--agent` | none | Only this agent's verdicts. |

- A later verdict on the same head, run and agent replaces an earlier one.
- False-pass rate = `refuted` / (claimed `done` and not `inconclusive`), with a 95% Wilson interval,
  per agent label and per claim mode. **Pre-registered and post-hoc verdicts are separate rows and
  are never added together.**
- The rate is a floor: an unrefuted claim is not a correct one, because the sealed checks catch only
  some wrong implementations (the design's working figure is about 60%), so the true rate is at
  least what is shown.
- Exit 0, also when there are no verdicts yet. Exit 1 for an unknown run, an empty store, or a ledger
  that does not verify.

## Exit codes of `boss`

| Code | Meaning |
|---|---|
| `0` | `fund`, `resume`: every check passed. `topup`, `report`, `status`, `roles`, `doctor`: success. `audit plan`: checks sealed. `audit check`: verdict `unrefuted` or `no_claim`. `audit report`: success. |
| `1` | `fund`: the boss produced no usable term sheet, you rejected it, a worker did not start isolated (a hook event later in the run counts), or, under `--dispatch rules`, the CLI ran a model other than the one launched. `report`: a saved prompt is missing or does not match its recorded hash. `resume`: nothing to resume, a damaged ledger, or the approval no longer matches. `topup`: no run, no usable term sheet, a damaged ledger, or a ledger another process is writing. `report`, `status`: no runs, unknown run, or empty ledger. `doctor`: a check failed. `audit`: you rejected the checks, or a refusal: a dirty tree, a ref that is not a plain name, a head that does not descend from the base, a ledger, approval, signature or check file that does not verify, or a repository git cannot read safely. |
| `2` | Usage error: bad or missing arguments, a blank idea, a count that is not a whole number of 1 or more, a slice below $0.005, a budget too small to fund one slice, roles that cannot run together, or a `--fix-budget` too small to fund one slice. `topup`: a round the run does not have, or one that closed unlocked. `audit`: a bad option, such as a `--claim` that is not `done` or `none`. |
| `3` | `audit check`: the verdict is `refuted` or `inconclusive`. `fund`, `resume`: the run ended with checks not passing. This includes a run that stopped early (a hard limit, a declined round, a pause, a lost login) and prints `Ended early: <reason>` and the `boss resume` command. |
| `130` | `fund`, `resume`, `audit plan`: interrupted with Ctrl-C. Continue with `boss resume` (before the term sheet is approved there is nothing to resume; run `boss fund` again). |

A ledger with a damaged line makes `report` and `status` fail with an error that names the file
and line.

## Benchmark commands

`run` makes real model calls for every cell. `drafts` and `audit` make one call per draft. `table`,
`kpi` and `replay` make none. See [../bench/METHOD.md](../bench/METHOD.md).

## `python -m boss.bench.run`

Runs benchmark cells (one task, one arm, one repetition) and scores each with the task's hidden
checks. A cell whose `result.json` already exists is skipped, so a run can be repeated to finish.

| Option | Default | Meaning |
|---|---|---|
| `--tasks` | `bench/tasks` | Folder of task folders. |
| `--out` | required | Results folder for this run. |
| `--arms` | `single firm` | Which arms to run: `single`, `firm` and `single-review` (the single agent, then its own session resumed once to review its work; never run unless named). |
| `--reps` | `1` | Repetitions per task and arm. |
| `--budget` | required | Dollars per cell. The boss's drafting call is on top. |
| `--model` | `haiku` | Worker model, both arms. |
| `--boss-model` | `haiku` | Boss model, firm arm. |
| `--only` | all tasks | Task ids to run. |
| `--firm-args` | none | Extra `boss fund` options for the firm arm, in one quoted string. Recorded in every result. |
| `--held-out` | `0` | Held-out checks for the firm arm to ask the examiner for, 0 to 8; 0 is off. It adds `--held-out N` to the firm arm's `boss fund` and records `held_out_passed`, `held_out_total` and `held_out_wrong` (held-out checks the task's reference solution fails, as `wrong_checks` does for the visible ones; the table shows it only when measured) in each firm result. The single arm ignores it. |
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
| `--prompt` | `term_sheet_v1.md` | Term-sheet prompt file under `src/boss/prompts`. `term_sheet_v3.md` also passes the idea's rules and keeps `rules.json` and `claims.json` in each draft's folder. |
| `--jobs` | `2` | Drafts to make and score at once. |
| `--max-spend` | none | Dollars. Makes the drafts one at a time and stops before a call that could take the measured spend past this (a call may cost up to its $0.25 cap; a cost the CLI did not report counts at that cap). |
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

## `python -m boss.bench.paired`

`python -m boss.bench.paired [options] DIR_A DIR_B`. Compares two arms by task and prints the
number of tasks, the mean difference, its 95% interval and a verdict, `shown` or `not shown`.
See [../bench/METHOD.md](../bench/METHOD.md). It reads results and makes no model call.

Arguments: `dir_a` and `dir_b`, results folders written by `run` (they may be the same folder).

| Option | Default | Meaning |
|---|---|---|
| `--arm-a` | `firm` | The arm taken from `DIR_A`: `single`, `firm` or `single-review`. |
| `--arm-b` | `single` | The arm taken from `DIR_B`. The difference is A minus B. |
| `--kpi` | `delivery` | `delivery`, `false_pass`, `cost_per_delivery` or `time`; `false_pass` needs both arms to be `firm`. |
| `--resamples` | `10000` | Task resamples for the interval. |
| `--seed` | `0` | Seed of the resampling; the same seed gives the same interval. |

Exit codes: `0`; `1` when a folder holds no results for its arm, the two sides ran different task
sets, no task is on both sides, or a result file is invalid; `2` for a usage error. A different
model or budget between the sides prints a warning and still runs.

## `python -m boss.bench.kpi`

`python -m boss.bench.kpi RESULTS_DIR [RESULTS_DIR ...]`. Prints the fixed KPI scorecard as one
markdown table: a row per KPI, a column per arm. The seven KPIs and their definitions are in
[../bench/METHOD.md](../bench/METHOD.md).

Argument: `results_dir`, one or more folders written by `run`. A column is one folder, arm, model,
budget and set of firm options, labelled by all of them, so arms from different folders and
settings sit side by side. The command reads each cell's ledger where the runner left one
(`ledger.jsonl` for the single arm, `.boss/runs/<id>/ledger.jsonl` for the firm arm); a cell
without a readable ledger shows "not recorded" for the figures that need it. Columns that ran
different task sets get a WARNING line above the table. It has no options.

Exit codes: `0`; `1` when no results are found, a result file is invalid, or two columns would carry
the same label (the same folder name twice, or one folder and arm holding two task sets); `2` for a
usage error.

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

## `python -m boss.bench.audit`

Scores the check auditor, a role that gives an opinion on each check of a draft: does the idea say
what the check demands? The benchmark knows which checks are wrong (the task's reference solution
fails them), so the auditor's flags can be counted against that. The auditor stays advisory until
these numbers say it is worth its cost.

It audits drafts that are already saved, from a `boss.bench.run` results folder or a
`boss.bench.drafts` output folder. It makes one model call per draft, capped at $0.15 a call
(the auditor's cap), unless `--dry-run`. The real cost per call has not been measured.

| Option | Default | Meaning |
|---|---|---|
| `--results` | required | One or more folders of saved drafts. Their names must differ. |
| `--tasks` | `bench/tasks` | Folder of task folders. |
| `--out` | required | Folder for the audits. |
| `--only` | all tasks | Task ids to audit. |
| `--model` | `haiku` | Model for the auditor. |
| `--thinking` | none | Thinking tokens per audit. |
| `--jobs` | `2` | Audits to make and score at once. |
| `--dry-run` | off | List the audits and the cost ceiling, then exit. |
| `--retry-failed` | off | Audit again the cells that failed to run. |

- A folder refuses audits made with other settings (task set, prompt, model, thinking). Use a fresh
  `--out` to compare.
- Exit codes: `0` after the audits ran; `1` when no task matches, a folder cannot be read, no draft
  is found, or `--out` holds audits made with other settings; `2` for a usage error.

## `python -m boss.roles.judge template`

`python -m boss.roles.judge template --rubric ID --artifacts DIR --out FILE`. Writes a case file
with one unlabelled case for each file in a folder (not files that start with a dot), for a person to score by hand. The judge
is advisory, and its scores are labelled `uncalibrated` until a calibration shows it agrees with a
person. Makes no model call. See [ROLES.md](ROLES.md).

| Option | Default | Meaning |
|---|---|---|
| `--rubric` | required | Id of the rubric the cases are scored against. |
| `--artifacts` | required | Folder of UTF-8 text files, one case each. |
| `--out` | required | The case file to write. It is never overwritten. |

Fill in every context and every score (1 to 5) in the file, then run `calibrate`. Exit codes: `0`;
`1` for an unreadable case file, rubric or folder.

## `python -m boss.roles.judge calibrate`

`python -m boss.roles.judge calibrate --cases FILE --out FILE [--model M] [--dry-run]`. Runs the
judge on every case of a labelled case file, compares its scores with yours, and saves and prints
the result. It prints the number of calls and the most they can cost (each call is capped at $0.15)
before it makes any. It will not overwrite `--out`.

| Option | Default | Meaning |
|---|---|---|
| `--cases` | required | The labelled case file. |
| `--out` | required | The calibration file to write. It must not exist. |
| `--model` | `haiku` | Model for the judge. |
| `--dry-run` | off | Show the calls and their cost ceiling, make none. |

Exit codes: `0`; `1` for an unreadable case file, rubric or calibration, or an `--out` that exists.

## `python -m boss.roles.judge show`

`python -m boss.roles.judge show FILE`. Prints a calibration file. Makes no model call.

Argument: `file`, a calibration file written by `calibrate`.

Exit codes: `0`; `1` when the file cannot be read.

## Environment variables

| Variable | Read by | Meaning |
|---|---|---|
| `BOSS_CLAUDE_BIN` | `boss fund`, `boss resume`, `boss doctor`, `bench.run`, `bench.drafts`, `bench.audit`, `roles.judge` | Path or name of the `claude` executable. Default `claude`. Not passed on to children. |
| `ANTHROPIC_API_KEY` | every command that calls the CLI | If set and non-empty: billing is `api`, the CLI runs with `--bare` instead of `--safe-mode`, and the key is passed to the CLI and masked in logs. The `--bare` mode is not verified against the real CLI. |
| `HOME` | worker and boss calls | Passed on so the CLI finds its login. |
| `PATH` | worker and boss calls | Passed on so the CLI can start. |
| `USER` | worker and boss calls | Passed on. |
| `LANG` | worker and boss calls | Passed on. |
| `TMPDIR` | worker and boss calls | Passed on. |
| `CLAUDE_CONFIG_DIR` | worker and boss calls | Passed on so the CLI finds its login. |
| `BOSS_GATE_SANDBOX` | `boss doctor`, the gate (so `boss fund`, `boss resume` and the benchmarks) | `auto` (default): run each check inside an OS sandbox when the platform has a working one, else unsandboxed. `require`: refuse to run a check without one. `off`: never. Any other value is an error. See [SANDBOX.md](SANDBOX.md). |
| `MAX_THINKING_TOKENS` | the `claude` CLI | Set by `boss fund` for the boss's call when `--boss-thinking` is given. Never taken from your environment. |
| `BOSS_AUDIT_HOME` | `boss audit plan`, `check`, `report` | The folder that holds the audit store. Default `~/.boss-audit`, under the `HOME` the command sees. A store inside the audited repo is refused. |
| `BOSS_LIVE` | `tests/test_end_to_end.py` only | `1` enables the one test that makes a real model call. |

- Nothing else from your environment reaches a worker or boss process. The gate builds its own
  environment for checks: a temporary `HOME` and `TMPDIR`, a short `PATH`, `LANG`, and
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
- Only `boss.cli`, `boss.bench.run`, `boss.bench.drafts`, `boss.bench.audit`, `boss.roles.judge`,
  `boss.gate` and `boss.sandbox` read the process environment.

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
| `logs/<worker>-s<N>.prompt.txt` | Under `--dispatch rules`: the exact text of slice N, its system prompt, a NUL byte and its user prompt. Its SHA-256 is on the slice's `slice_start`. |
| `product/` | The built files, assembled from each task's best worker at the end of a run. |
| `report.md` | The board report, saved when `boss fund` or `boss resume` finishes. |
| `stories.json` | The product manager's stories, when that role ran. |
| `critic-N/` | Scratch for the critic's Nth review: `critic_checks/` holds the tests it wrote, including the ones that were not verified. |
| `demo/` | `demo.py` and `USAGE.md` as installed in `product/`. Kept because `product/` is rebuilt on every run, and a `resume` copies them back. |
| `demo_scratch/` | Where the demo writer ran its script against a copy of the product. |

A run started with `--spec` also has `rules.json`, the rule list of its idea. A run that asked for held-out checks also has `held_out/` (their files and a `manifest.json`;
never inside a workspace or `product/`) and, if the examiner's output was refused,
`examiner_refused.json`; `boss fund --held-out N` creates them. `workspaces/`, `logs/` and `product/`
exist only once a worker has been hired. `report.md` is
written by `fund` and `resume`; `boss report` prints it again from the ledger without writing.

## Benchmark cell folder

`python -m boss.bench.run --out DIR` writes one folder per cell: `DIR/<task>/<arm>/rep<N>/`.

| Path | Arm | What it holds |
|---|---|---|
| `result.json` | both | The scored result. Its presence marks the cell done. The single arm's records `final_status`, the status word of its last slice; the firm's leaves it null, as its claim is its checks. |
| `ledger.jsonl` | single | The single agent's events. |
| `workspace/` | single | The single agent's files, scored by the hidden checks. |
| `logs/solo.jsonl` | single | The single agent's raw stream. |
| `transcript.txt` | firm | What `boss fund` printed. |
| `.boss/runs/<id>/` | firm | A complete run folder, as above. Its `product/` is scored. |

A `single-review` cell holds the same files as a `single` cell; its ledger and stream have two slices.
