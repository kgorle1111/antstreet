# Command line

Every command and option, the environment variables the tool reads, exit codes, and what a run
leaves on disk. `tests/test_docs_cli.py` reads the real argparse parsers and fails if an option or
command is missing here, is documented but does not exist, or has a different default.

Related: [ARCHITECTURE.md](ARCHITECTURE.md), [LEDGER.md](LEDGER.md), [ROLES.md](ROLES.md).

Every command also accepts `-h` and `--help`.

## `antstreet`

`antstreet [--version] <command> ...` where the command is `fund`, `approve`, `resume`, `topup`, `report`,
`status`, `verify`, `roles`, `doctor`, `mcp` or `audit` (which has three steps of its own: `audit plan`, `audit check`
and `audit report`, and with no step does the next one).

| Option | Default | Meaning |
|---|---|---|
| `--version` | off | Print `antstreet <version>` and exit 0. |

- A command is required. Without one, argparse prints usage and exits 2.
- Commands run against a project folder (`--dir`). Runs are stored under `<dir>/.boss/runs/`.
  `antstreet audit` is the exception: it audits a git repository you name and keeps its runs in the
  audit store (see `antstreet audit plan`).

## `antstreet fund`

`antstreet fund [options] IDEA`. Drafts a term sheet, asks you to approve it, then builds the idea.

Argument: `idea`, what to build, in plain words.

- A blank idea, or one whose first non-blank character is `-` (it would read as an option), is
  refused with a message and exit 2. No run folder is made and nothing is spent. To give an idea
  that starts with `-`, put some other word first.
- `--rounds`, `--max-tasks`, `--max-slices` and `--stall-slices` must be whole numbers of 1 or
  more. `--max-minutes` must be a positive number. `--boss-thinking` must be a whole number. Any
  other value is a usage error (exit 2) before anything is spent.
- Ctrl-C after approval, while workers are running, stops the run, prints `antstreet resume <id>` and
  exits 130. Nothing already recorded is lost. Ctrl-C earlier, while the boss or a role is being
  called, ends the run with a message and exit 130: nothing was funded, what the calls so far cost
  is on the ledger, and there is nothing to resume. Ctrl-C at the approval question counts as
  reject.
- With no terminal to ask on (standard input is not a TTY: Claude Code's Bash tool, a pipe, CI),
  `fund` does not ask. It prints the term sheet, every check and the roles' notes, keeps the
  paid-for draft unapproved, records the run's configuration (`started`) and a `stopped` event
  with the reason `awaiting the investor's approval`, prints the one command that approves
  exactly that text (`antstreet approve RUN --sheet VALUE`), and exits 4. No worker is hired. Before
  this, end of input at the question was a rejection, after the draft was already paid for.
- The dispatch options are checked before anything is spent (exit 2): `--max-tier` needs `--dispatch
  rules` or `cascade`; with either, `--model` must be `haiku`, `sonnet` or `opus` (or a full id of
  one), may not be above `--max-tier`, and `--reserve` may not be given (the reserve is per model).
  Under `--dispatch rules` the term sheet also shows `Route: one agent (one file, N checks)` when
  everything is built in one file, or `Route: firm (K tasks, files ...)`. On the one-agent route a
  fired worker is replaced only by a stronger one; in the firm it is replaced as before. You may
  set `"route": "firm"` on a one-file sheet; `"one_agent"` on a sheet with several files is refused.
- `--roles` is checked before anything is spent. An unknown name, or a role without the roles it
  needs, is a usage error (exit 2) that says what to change. `--fix-budget` below one reserve plus
  $0.005 is refused the same way, and so is `--fix-after-stop` without `--roles critic`.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder. |
| `--budget` | required | Budget for the funding rounds in dollars, such as `0.50` or `$0.50`. Positive, at most 6 decimals. The boss's own drafting call is charged on top of it. |
| `--model` | `haiku` | Worker model. |
| `--rounds` | `1` | Funding rounds to split the budget into. With more than one, the budget splits equally (the earliest rounds take any remainder), the count is capped at the number of checks, and each round after the first needs your yes. |
| `--slice` | `$0.10` | Dollars a worker may spend in one slice, before the gate looks again. At least $0.005; a smaller slice is never funded (exit 2). |
| `--reserve` | by `--model` | Dollars held back from every slice cap: what one response can cost past the cap. `$0.10` for `haiku` and any model not recognised, `$0.30` for `sonnet`, `$0.50` for `opus` (a name that contains the family). An explicit value wins and is recorded on `started`. |
| `--max-tasks` | `1` | Most tasks the boss may split the work into. Above 1 the multi-task prompt is used. |
| `--profile` | none | Worker profile: one of `generalist`, `backend_engineer`, `ai_engineer`, `test_engineer`, `refactorer`. Its skills are added to the worker's prompt. Without it the worker gets the bare builder prompt. `antstreet roles` lists each profile's skills. |
| `--worker-thinking` | none | Thinking tokens per worker slice; 0 turns thinking off. Unset keeps the CLI's own default. Recorded on `started`, so `antstreet resume` keeps it. |
| `--held-out` | `0` | Held-out checks to ask the examiner for, 0 to 8; 0 is off. The examiner sees the idea and the names the product must expose, never a visible check. You read and approve its checks with the term sheet; no worker is shown them; the finished product must pass them too. Its call is paid from round 1's budget, and is skipped (and said) when round 1 could not then fund a worker slice. See `docs/ROLES.md`. |
| `--dispatch` | `off` | `off`: every worker runs on `--model`, as always. `rules`: the term sheet shows a route and one dispatch row per task (agent, model, effort, what happens if its worker is fired, context size, slice cap) and a worst case in dollars; you can edit `route` and each task's `dispatch` in `term_sheet.json` with `[e]dit`, and what you approve is hashed with the rest of the sheet. A worker the gate fired for no progress or a slice limit is replaced one tier up (once per task); no other event changes a model. Every slice records the hash of the exact text the worker was given and the model the CLI says it ran, and a model other than the one launched stops the run. See D43 to D45 in `docs/DECISIONS.md`. `cascade`: `rules` plus a ladder per task, `haiku`, `sonnet`, `opus`, then `opus` once more at one effort step higher (every rung but the last at effort `off`, the last at `default`), then you are asked. Each rung is climbed only after the gate fired the one before for no progress or a slice limit, and each gets the previous worker's findings in its brief. The tier a task starts on is chosen per task kind (files owned and checks, bucketed) as the one with the lowest expected cost, from the attempts recorded in this project's own earlier runs (`antstreet routing` shows how); below 5 attempts of a kind and tier a fixed prior is used and the table says `prior` instead of `measured, n=...`. The table shows each task's kind, where its start came from, the ladder after it, and a worst case that prices every rung. A task with no check is refused: the gate is the only verifier. See D46 in `docs/DECISIONS.md`. |
| `--max-tier` | none | With `--dispatch rules` or `cascade`: the dearest model dispatch may use, `haiku`, `sonnet` or `opus`. Without it dispatch stays at `sonnet`. A sheet that names a dearer tier, in the first plan or in an edit, is refused before it can be approved and again before anyone is hired. |
| `--spec` | off | The boss's checks must cite the rules of your idea, which code cuts out of your own sentences and numbers R01, R02, ...; each check names the 1 to 5 rules it tests, and the boss may list rules it leaves untested, with a reason. Before you approve you see the coverage, uncovered rules first, then claims a check cannot be testing (the check does not contain a non-ASCII string, the exception, the size or the type the rule names), then the boss's waivers; literals and list items are shown apart and not scored. The rule list is saved as `rules.json`, hashed in your approval, and a coverage summary is recorded in it. One task only (`--max-tasks 1`), not with the staged draft (`--roles system_designer,tester`). Refused before any spend when the idea has more than 40 numbered items or paragraphs, or no sentence stating a behaviour. |
| `--coverage` | off | Turns on `--spec`, then tests the boss's checks twice, in code, before any worker is paid. Rules: a scored rule no check cites (uncovered, or waived by the boss) or whose citing checks lack what it names (anchor missing). Strength: a check that passes on a stub product is weak. There is no product yet, so code writes three: every name the checks import from the task's Python files is a function that returns `None`, returns its first argument unchanged, or raises `NotImplementedError` (one gate run each). An empty workspace only proves a check imports something; a stub defines the names, so a check that asserts nothing a wrong product gets wrong passes it. While either finds a gap the boss redrafts with the gaps named by id (never its own text), at most 2 more calls, each booked as a `boss_call` with `purpose` `coverage_redraft`; a redraft is kept only when it has fewer gaps, and a failed one leaves the draft as it was. What is left is shown under the rule coverage as the COVERAGE GATE: approving that text is your waiver of every rule no check cites, and each weak check is named (a check edited since is said to be unmeasured). The measurement is saved as `coverage.json`, and a run started with `--coverage` cannot be approved while that file is missing or unreadable; your approval records `investor_waived` and `weak` in its `spec` summary. Off by default until its benchmark run. |
| `--parallel` | `1` | Tasks to work on at once. A task still has one worker at a time, and at most two in all (the first and one replacement). Slices that run together each leave room for the reserve of every earlier one, so a small round funds fewer at once. Only useful with `--max-tasks` above 1. |
| `--max-slices` | `6` | Fire a worker after this many slices that count. |
| `--stall-slices` | `2` | Fire a worker after this many counted slices in a row with no new passing check. |
| `--max-minutes` | none | Stop the run after this many minutes of wall clock, counted from the start of this `fund` or `resume`. Checked before each slice, so a slice in progress can run past it. |
| `--no-firing` | off | Keep funding stalled workers. A worker is still fired at the slice limit. |
| `--boss-model` | `haiku` | Model for the boss's own call. |
| `--boss-thinking` | none | Thinking tokens the boss may use; 0 turns thinking off. Without it the CLI's default applies. Roles use it too. |
| `--roles` | none | Specialist roles to run around the build, comma separated, or `all`. Names are those `antstreet roles` prints. Each role is one capped model call; its spend is a `role_call` event. `user_agent` needs `product_manager`; `tester` needs `product_manager` and `system_designer`; `system_designer` needs `tester`. A role's model is `--boss-model`. [ROLES.md](ROLES.md) says when each runs. |
| `--review-cycles` | `1` | Times the critic may review the finished product and offer a fix round. With 0 the critic still runs and its findings are shown, but you are asked nothing. |
| `--fix-budget` | two slices plus one reserve | Dollars for a fix round after the critic's findings: `$0.30` with the default slice and reserve. At least one reserve plus $0.005. |
| `--fix-after-stop` | off | Needs `--roles critic`. When the run ended only because a round closed below its unlock threshold (no limit, pause, stop or awaited ruling), the critic's findings are still offered: a yes adds the checks and records the fix money as your `topped_up` of that round, which reopens it; no round is added. A finding of a task that was set aside is not offered: the reopened round would have no worker for it. Every other stop still offers nothing. Recorded on the run, so `resume` keeps it. |

What it asks you:

- `[a]pprove, [r]eject, or [e]dit files and re-check?` after showing the term sheet. `edit` lets
  you change `term_sheet.json` and the check files, then re-validates them. `y` or `yes` also
  approves and `n` or `no` also rejects, as at every other question. End of input counts as reject.
- `Round N: X/Y checks pass. Fund $Z more? [y]es / [n]o` before each round after the first. End
  of input counts as no.
- With the critic on, after the build: `Add these N checks and fund a fix round of $X? [y]es / [n]o`,
  once per review cycle and only when the critic has verified findings and the run did not end
  early. It shows each proposed check and its code first. `y`, `yes`, `a` and `approve` are yes;
  anything else, and end of input, is no. Ctrl-C ends the command with exit 130 and is not an answer:
  `antstreet resume` asks the critic again and puts the question again. When a round of the sheet never
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

When a disputed check or a blocked worker needs you, the run asks (`antstreet resume` asks the same):

- `[d]rop the check / [k]eep it (the worker must satisfy it) / [s]et the task aside`, once per
  check a worker disputes. Drop: the check is no longer run or counted. Keep: the worker must make
  it pass.
- `[u]nblock it with a note / [s]et the task aside`, when a worker says it cannot go on. A note
  is on one line, at most 1000 characters, and goes into the worker's next brief.
- Anything else, or end of input, sets the task aside for the rest of the run. Your rulings are
  ledger events (`ruled`); the approved term sheet and checks are not edited.
- With no terminal to ask on (Claude Code's Bash tool, a pipe), a dispute is not asked and the
  task is not set aside: the run stops (exit 4) with the dispute pending, recorded as a `stopped`
  event, and prints the `antstreet approve RUN --dispute CHECK --ruling drop|keep` lines that rule on
  it. Rule on each, then `antstreet resume RUN` goes on from your rulings.

## `antstreet approve`

`antstreet approve [--dir DIR] [--sheet VALUE | --dispute CHECK --ruling drop|keep] [RUN]`.
Approves a term sheet that `antstreet fund` left waiting because it had no terminal to ask on, or
rules on a dispute a run stopped on for the same reason. Spends nothing; `antstreet resume` then
builds it.

Argument: `run`, a run id. Default: the latest run in the folder.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder. |
| `--sheet` | none | The 16-character value printed with the term sheet you read. Without it, `approve` prints the term sheet as it is on disk now, every check, the roles' notes and that value, and writes nothing. |
| `--dispute` | none | A check whose dispute the run stopped on, with no terminal to ask on. Needs `--ruling`; not with `--sheet`. |
| `--ruling` | none | With `--dispute`: `drop` (the check is no longer run or counted) or `keep` (the worker must make it pass). |

- With `--sheet`, the term sheet and checks on disk are validated and rendered again, and the
  approval is recorded only if that text is exactly the one the value names (its SHA-256, first 16
  hex characters). A sheet, check, held-out check or rule list changed since it was shown, or a
  mistyped value, is refused (exit 1) and nothing is written. Read it again with `antstreet approve
  RUN` and approve what is there now.
- The approval is the same signed `approved` event an approval at the question writes, plus
  `shown_sha256`, the full hash of the text approved. `term_sheet.json` gets
  `approved_by_investor: true`.
- Refused with exit 1, writing nothing: no run found; a run `fund` did not leave waiting, or one
  already approved; a damaged ledger; a ledger another process is writing.
- With `--dispute CHECK --ruling drop|keep`, it records your ruling on a dispute the run stopped
  on: the same signed `ruled` event a ruling at the question writes. Refused with exit 1, writing
  nothing, unless the run's latest stop waits on that check and it is not ruled yet; exit 2 when
  `--dispute` and `--ruling` are not given together, or come with `--sheet`.
- It is your act, not an agent's. From Claude Code, type it yourself with the `!` prefix, and do
  not grant it to the agent: an agent running as you can run any command you can.

## `antstreet resume`

`antstreet resume [--dir DIR] [RUN]`. Continues a run from its ledger: one that was interrupted (exit
130), paused, stopped, or ended early.

Argument: `run`, a run id. Default: the latest run in the folder.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder. |
| `--review-cycles` | `1` | As for `antstreet fund`. |
| `--fix-budget` | two slices plus one reserve | As for `antstreet fund`; the slice and reserve are the run's own. |

- It reads `term_sheet.json` and the configuration recorded when the run started, so a resumed
  run keeps its own slice, reserve, firing and limit settings. There are no options to change them.
- Running it is your decision to lift a stop: it prints why the run stopped and writes `resumed`.
  The approval, the budget and every hard limit are checked again as the loop goes, so a lifted
  stop can stop again at once. The wall-clock limit (`--max-minutes`) counts from the start of
  each `resume`, so a resumed run gets the whole time again.
- An interrupted round continues. A round that closed below its unlock threshold stays locked
  until you reopen it with `antstreet topup`. A task that was set aside stays set aside.
- A slice that started and never ended is charged to its round at its cap. If the last slice was
  never gated, or a firing or a question to you was owed, it is done first.
- The roles are the ones recorded when the run started. Their first stage (stories, staged draft,
  audit) is not run again; the consultant answers disputes; the critic, the demo and the judge of
  the usage note run after the build unless the ledger shows they already did, so a second
  `resume` of a finished run adds nothing.
- On a run that already finished it changes nothing and prints the report.
- Refused with exit 1, spending nothing: no run found; no usable `term_sheet.json`; a damaged
  ledger; the run never got as far as hiring (start again with `antstreet fund`); the run is still
  awaiting your approval (`antstreet approve RUN`); the term sheet or a check no longer matches your
  approval.
- A ledger whose last line was cut by a hard kill is repaired first: the cut line is removed and
  `resume` prints it. A ledger damaged anywhere else is refused.
- If another `antstreet` process is still writing the run's ledger, `resume` says so and exits 1.
  Nothing is changed, not even a cut-off last line.
- Exit codes are those of `antstreet fund`.

## `antstreet topup`

`antstreet topup [--dir DIR] [RUN] --round N --amount D`. Adds money to one round of an existing run:
you pay more for the same term sheet. It records one `topped_up` event (actor `investor`, the round,
`micros`) and spends nothing itself; `antstreet resume` continues the run.

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
  stays locked on `antstreet resume` until you top it up. A top-up recorded after the lock reopens that
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
- If another `antstreet` process is still writing the run's ledger, `topup` says so and exits 1.
  Nothing is changed, not even a cut-off last line.
- There is no upper limit on `--amount`: check the figure, `0.20` is twenty cents.
- Exit 0 once the event is written.

## `antstreet report`

`antstreet report [--dir DIR] [RUN]`. Prints the board report of a run, computed from its ledger. A run with held-out checks shows their result apart from the visible checks (`Held-out checks: 2 of 3 passed on the product; the workers never saw them.`); a run that asked for them and got none says why. One line says whether the checks ran sandboxed (`Checks ran sandboxed: 12 of 12.`), with a WARNING when any ran unconfined and "not recorded" for a ledger written before the flag existed (T39).

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

## `antstreet status`

`antstreet status [--dir DIR] [--json] [RUN]`. Prints one line: the last event, checks passing, estimated spend.

Argument: `run`, as for `report`.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder. |
| `--json` | off | Print one JSON object instead, for tools such as the Claude Code approve pane: `run`, `awaiting` (true while `antstreet fund` left the term sheet waiting for `antstreet approve`), `last_actor`, `last_event`, `checks_passed`, `checks_total`, `spend_micros`, `unknown_cost_events`. The exit codes are the same; a refusal (no run, a damaged ledger) is still a plain line. |

## `antstreet verify`

`antstreet verify [--dir DIR] [--adopt-unsigned] [RUN]`. Checks a run's integrity and nothing else: the
ledger's hash chain, its line and investor signatures, and every saved worker prompt against the
hash its `slice_start` recorded. Offline, no model call. Prints one line when everything holds,
otherwise one line per problem. Argument: `run`, as for `report`; a run id that is not a folder
under `.boss/runs/` is a usage error.

A run with unsigned lines and no anchor (one older than line signing, or one rewritten without the
key: the two look the same) is refused by every command until you adopt it with
`--adopt-unsigned`. Adopting runs every other check, then anchors the ledger as it is now, so you
vouch for its current content; it never adopts a signed line that does not verify, and it changes
nothing for a run that already has an anchor (`docs/LEDGER.md`).

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder. |
| `--adopt-unsigned` | off | Vouch for a run with unsigned lines and no anchor as it is now. |

## `antstreet roles`

`antstreet roles [--dir DIR]`. Prints the organisation as a tree: the investor, the boss, then the
departments, and under them each role and each worker profile with its purpose, its gate, its
skills, and whether it is on by default. Every specialist role is marked `off by default`. See
[ROLES.md](ROLES.md).

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Accepted like the other commands. Not used: nothing is read from the project. |

It reads the code only. It makes no model call, reads no run and writes nothing. Exit 0.

## `antstreet routing`

`antstreet routing [--dir DIR] [--max-tier TIER]`. Prints what `--dispatch cascade` would choose for this
project: for each task kind and tier, the attempts recorded, the verified-fail rate and the mean
cost per attempt, whether the chooser uses that data (`measured, n=...`) or the prior, and the start
tier it picks per kind and why. A run counts only if the investor key vouches for its ledger, its
term sheet and its checks match a signed approval; every other run is listed as left out, with the
reason. Without a key, nothing is read.

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder whose `.boss/runs` are read. |
| `--max-tier` | `sonnet` | The top of the ladder to price: `haiku`, `sonnet` or `opus`. |

It makes no model call and writes nothing. Exit 0.

## `antstreet doctor`

`antstreet doctor [--dir DIR] [--live]`. Checks what a run needs and prints a fix line for each failure.

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

## `antstreet mcp`

`antstreet mcp [--dir DIR]`. Serves the project's runs read-only to an MCP client: one JSON-RPC 2.0
message per line on stdin and stdout, until stdin closes (exit 0). It answers the `initialize`
handshake (protocol 2025-11-25 and earlier) and `server/discover` (2026-07-28).

| Option | Default | Meaning |
|---|---|---|
| `--dir` | `.` | Project folder whose `.boss/runs/` the tools read. No tool takes a path. |

Tools: `list_runs`, `status`, `report`, `verify_ledger` and `doctor`. `status` and `report` run the
commands above; `verify_ledger` checks the hash chain, the investor signatures, the anchor and the
saved prompts; `doctor` never runs `--live`. None of them funds, resumes, tops up or approves, and
none makes a model call. A `run` argument must be one word of letters, digits, `.`, `_` or `-`
starting with a letter or digit, and one of the project's runs. A tool result is cut at 60,000
characters, and a request line over 1,048,576 characters is refused.

## `antstreet audit`

`antstreet audit [--repo REPO] [--request FILE]`, with no step, does the next step for the repo, using
the code of `plan` and `check` below unchanged:

1. It looks for a sealed run that covers `HEAD`: the newest approved run in the audit store whose
   sealed base is `HEAD` or an ancestor of it and, when there is a request (below), that sealed
   that request. Picking reads the term sheets only; `check` verifies the ledger and the approval
   before it trusts the run.
2. No such run: it says so and runs `antstreet audit plan` with the request and base `HEAD` (you approve
   as usual). Without a request it seals nothing and exits 1, saying how to give one.
3. A run whose base is `HEAD`: nothing to check yet. It says so and exits 0.
4. A run whose base is behind `HEAD`: it runs `antstreet audit check RUN --head HEAD --claim done` and
   exits as that does.

Each case ends with the next command to run. The request is `--request FILE` or, without it,
`.antstreet/request.md` in the repo when that file exists. It is never the last commit message: at
plan time `HEAD` is the base, so its message describes work already done. `plan` needs a clean
tree, so commit the request file (or ignore it) first. A new request text seals a new run; the same
text finds its run. Without a request, it checks the newest run that covers `HEAD` and says which run and which
sealed request that is, so a verdict for a different change is never silent. To audit a branch, a run other than the newest, or with `--claim none`, use the
steps.

| Option | Default | Meaning |
|---|---|---|
| `--repo` | `.` | The git checkout. |
| `--request` | none | The change request to seal checks for, when no run covers `HEAD`. |
| `--stop-hook` | none | `notify` or `block`. For the Claude Code plugin's Stop hook (`hooks/audit-check.sh`); see below. |

With `--stop-hook` it never seals, never reads a request and never asks. It prints nothing and
exits 0 when `REPO` is not a git checkout, when no run covers `HEAD`, when `HEAD` is the base, or
when the hook already checked this commit. Otherwise it runs `check` on `HEAD` with `--claim done`
and agent label `claude-code-stop`, and prints one line of JSON for Claude Code: a `systemMessage`
for you with the verdict, the number of counted checks that failed, a note when the working tree
has uncommitted changes (only the commit is checked) and the `antstreet audit report` command. With
`block` and a `refuted` verdict it adds `"decision": "block"` and a `reason` the agent reads:
`N of M sealed checks failed; the human has the details`. No check id, description or code is
printed in either mode, so the agent being audited learns nothing of what the checks test. Any
error after a run is picked prints nothing and exits 1; the hook script turns that into a generic
notice. A step with `--stop-hook` is a usage error (exit 2).

## `antstreet audit plan`

`antstreet audit plan --request FILE [--repo REPO] [--base REF] [--held-out N] [--boss-model MODEL] [--questions]`. Seals
checks for a change request before the change is looked at, so that a commit an agent makes later
can be tested against them. It asks the boss for checks once, runs them on the base commit, shows
you every check and what it does there, and asks whether to approve. It never writes to `REPO`.

| Option | Default | Meaning |
|---|---|---|
| `--repo` | `.` | The git checkout to audit: the folder that holds `.git`. |
| `--request` | required | A text file with the change request, up to 64 KiB, not starting with `-`. |
| `--base` | `HEAD` | The branch, tag or full commit hash the change is made from: `HEAD` as it is before the agent starts. A revision expression (`HEAD~1`, `a..b`, `x:path`) is refused. |
| `--held-out` | `0` | Checks an examiner writes as well, from the request and the names the checks import, 0 to 8; 0 is off. You read and approve them with the rest. |
| `--boss-model` | `haiku` | Model for the boss's own call. |
| `--questions` | off | After the draft, one more boss call (`src/antstreet/prompts/spec_gaps_v1.md`) lists up to 5 rules the request leaves open, or states but no check tests, as yes/no questions, each with a check drafted for either answer. You answer `y`, `n` or `s`: a yes or a no adds that answer's check to the term sheet before it runs on the base, a skip records a waiver. The checks are then shown folded, one line each with its file's SHA-256; `v` prints them in full. Off by default until its live eval has run (`python -m antstreet.bench.spec_gaps`). |

- Refused with exit 1, before anything is written: a working tree that is not clean (a staged or
  modified file, or an untracked one that is not ignored); a ref that is not a plain name or hash; an
  audit store inside the repo; a request that is empty, too big or starts with `-`.
- The boss is shown the request and the base's public surface: file paths and, for each Python file
  outside tests, the names and signatures it exposes. It is never shown a function body, a test, or
  any change (`src/antstreet/prompts/audit_checks_v1.md`). The call has no tools.
- Each check then runs on the base, in the gate, and is shown with what happened: **fails on the
  base: counted** (it separates a finished change from an unfinished one), **passes on the base:
  shown, not counted**, **cannot run here: not counted** (it needs a module that is not installed
  and that neither the base nor the request names), or **timed out on the base: not counted**. If
  no check fails on the base you are told every verdict would be inconclusive, and can reject.
- **Environment.** The checks import from the base, the standard library, pytest and, when the repo
  has one, the site-packages of its own `.venv` (what `uv sync` or `python -m venv .venv` makes).
  Nothing is installed. That folder is the repo's code, so it is used only when the gate runs inside
  an OS sandbox, which may read it and nothing else of the environment; only if it is for the
  Python that runs the checks (a compiled module built for another one would fail and look like a
  failing check); and only if it resolves inside the repo, away from `.boss` and the audit store. It
  joins the import path last and is never run as an interpreter: its `.pth` files and
  `sitecustomize` do not run, and it cannot replace pytest or the gate's plugin. The output's
  `Environment:` line says which was used, or why not and what to run (`uv sync`). Without it, a
  check that imports a third-party module is **cannot run here**.
- You approve or reject as for `antstreet fund`; the approval is signed with the audit store's investor
  key. The sheet's budget figure is a placeholder: the audit funds no worker.
- **Questions** (`--questions`). Each answer is a signed `ruled` event (`ruling` `answered`) in the
  run's ledger, written before the approval; the checks an answer adds are hashed by the approval
  like the rest. The question text is the model's: it is cut to one line of 200 characters with
  secrets masked and control characters made visible, and a question is dropped unless it is a
  yes/no question and both of its checks parse, define a test and fail on an empty workspace. A
  failed questions call is booked and the plan goes on without questions. The questions, the
  answers and the checks stay in the audit store; nothing of them is written to the repo.
- **No terminal.** When stdin is not a terminal, `antstreet audit plan` reads nothing from it: another
  program could have filled it. It stops with exit 4 and prints what it waits for: the questions
  (with `--questions`) and the `antstreet audit approve RUN --answers ...` command, or the term sheet in
  full and the `antstreet audit approve RUN --sheet VALUE` command. Before this, such a plan read end of
  input as a rejection.
- The base commit and the request's SHA-256 are in the one synthetic task's brief, so they are inside
  the hash your approval covers: editing either, a check, or a held-out file voids it.
- Prints the run id and the **seal**, one SHA-256 over the approved term sheet, every check file and
  every held-out file. Record the seal somewhere the agent cannot change; `antstreet audit check` writes
  it into every verdict.
- The **audit store** is `$BOSS_AUDIT_HOME`, or `~/.boss-audit` when it is unset. It is laid out like
  a project: `.boss/runs/<id>/` holds `ledger.jsonl`, `term_sheet.json`, `checks/` and, with
  `--held-out`, `held_out/`; `.boss/investor.key` and `.boss/anchors/` are as in a project. The
  folders it creates are mode 0700. No check text is written to the repo, the boss's prompt or any
  working folder, and a store inside the repo is refused. This keeps the checks from an agent that
  works in the repo and reads only what it is given. It does not stop one that runs as the same
  operating-system user and looks in `~/.boss-audit`: that needs another user or a container
  (T51).
- The draft's cost is a `boss_call` event with `purpose` `audit_checks`, the questions' one with
  `purpose` `spec_gaps`; the examiner's is a `role_call`.
- Exit 0 when sealed. Exit 1 when you reject, the boss's output is unusable, or a refusal above.
  Exit 4 with no terminal: the run waits for `antstreet audit approve`. Exit 130 on Ctrl-C.

## `antstreet audit approve`

`antstreet audit approve [RUN] [--answers A,B,...] [--sheet VALUE] [--repo REPO]`. Carries on an audit
plan made with no terminal. Run it yourself: the answers and the approval are the investor's, never
the audited agent's (in Claude Code, with the `!` prefix; the plugin's hook denies the agent any
`approve`).

Argument: `run`, the id `antstreet audit plan` printed. Default: the latest run in the store.

| Option | Default | Meaning |
|---|---|---|
| `--answers` | none | One answer per question, comma-separated, in the order shown: `y`, `n` or `s` (skip). The run first exports the base commit from `--repo` and runs the checks on it; only if that works are the answers recorded (once), and then it prints the term sheet in full with the `--sheet` value. If the base run fails, nothing is recorded and the same answers can be given again. |
| `--sheet` | none | The value printed with the term sheet you read: approves exactly that text and prints the seal. A check or the sheet changed since it was printed means a different text: nothing is approved. |
| `--repo` | `.` | The audited checkout, used with `--answers` to export the base commit. It is read, never written. |

- Without `--answers` or `--sheet`, prints what the run waits for again.
- Refused with exit 1, nothing written: a run that is not waiting for the investor; `--sheet` before
  the questions are answered; `--answers` that are not one valid answer per question, or given
  twice; a repo without the base commit; a `--sheet` value that is not the text on disk now.
- Exit 0 when sealed, 4 after the answers (the run now waits for the approval), 1 as above, 2 for
  both `--answers` and `--sheet` at once.

## `antstreet audit check`

`antstreet audit check [RUN] [--head REF] [--repo REPO] [--claim done|none] [--claim-text FILE] [--agent LABEL] [--no-strength] [--max-mutants N] [--strength-timeout SECONDS]`.
Runs the sealed checks of audit run `RUN` on a commit and writes the gate's verdict to its ledger as a signed
`audited` event.

Argument: `run`, the id `antstreet audit plan` printed. Default: the latest run in the store.

| Option | Default | Meaning |
|---|---|---|
| `--head` | `HEAD` | The branch, tag or full commit hash to audit. |
| `--repo` | `.` | The git checkout that holds the head and the sealed base. |
| `--claim` | `none` | What the agent said of its own work: `done`, or `none`. Only a claim of `done` can be refuted. v1 does not read the agent's words to decide this. |
| `--claim-text` | none | A file with the agent's own words, up to 64 KiB. Kept as a SHA-256 only. |
| `--agent` | none | A label for the agent (1 to 64 letters, digits and `. _ : @ / + -`), to report by. |
| `--no-strength` | off | Skip the check strength below. |
| `--max-mutants` | `30` | The most mutants the check strength runs (1 to 500). Over it, mutants are taken evenly across all of them. |
| `--strength-timeout` | `300.0` | Seconds for every mutant together. No mutant starts after it; one already running finishes. |

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
- Check strength, also beside the verdict and never part of it: mutants of the head's code are
  made from the lines the change added or edited (Python files outside tests; a file that does
  not parse is skipped): a comparison flipped (`<` to `<=`, `==` to `!=`, ...), `+` and `-` swapped,
  `and` and `or` swapped, a number plus one, `True` and `False` swapped, a returned value made
  `None`, a `raise` dropped, an `if` condition negated. Each counted check that passes on the head
  is run against each mutant through the gate, **only inside an OS sandbox** (without one, none
  runs and the output says why), with the repo's `.venv` as above. The output reads `c01 kills 4/9`
  per check, and a check that kills none is flagged `WEAK, it would pass broken code`. A mutant
  may change nothing a check can see (an equivalent mutant), so a kill count says how much a check
  bites, not what share of wrong implementations it catches.
- The checks see the same environment as in `antstreet audit plan`, found again in `--repo` (its
  `.venv`), for the base and the head alike; the `Environment:` line says which.
- The output names failing checks by id and description, never by code.
- The `audited` event is written only after all of the above, signed with the store's key.
- Exit 0 for `unrefuted` and `no_claim`. Exit 3 for `refuted` and `inconclusive`. Exit 1 for any
  refusal above. Exit 2 for a bad option.

## `antstreet audit report`

`antstreet audit report [RUN] [--all] [--agent LABEL]`. Prints each run's verdicts and the false-pass
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

## Exit codes of `antstreet`

| Code | Meaning |
|---|---|
| `0` | `fund`, `resume`: every check passed. `approve`: the term sheet was shown, or approved. `topup`, `report`, `status`, `roles`, `doctor`: success. `verify`: the run verifies. `mcp`: stdin closed. `audit plan`, `audit approve`: checks sealed. `audit check`: verdict `unrefuted` or `no_claim`. `audit report`: success. `audit` with no step: as the step it ran, or nothing to check yet; with `--stop-hook`, every case but an error. |
| `1` | `fund`: the boss produced no usable term sheet, you rejected it, a worker did not start isolated (a hook event later in the run counts), or, under `--dispatch rules`, the CLI ran a model other than the one launched. `report`: a saved prompt is missing or does not match its recorded hash. `resume`: nothing to resume, a damaged ledger, a run still awaiting approval, or the approval no longer matches. `approve`: no run waiting for an approval, a sheet changed since it was shown, or a damaged or busy ledger. `topup`: no run, no usable term sheet, a damaged ledger, or a ledger another process is writing. `report`, `status`: no runs, unknown run, or empty ledger. `doctor`: a check failed. `verify`: a damaged or unverifiable ledger, an empty ledger, or a saved prompt that is missing or changed. `audit`: you rejected the checks, or a refusal: a dirty tree, a ref that is not a plain name, a head that does not descend from the base, a ledger, approval, signature or check file that does not verify, or a repository git cannot read safely; with no step, no run covers `HEAD` and there is no request; with `--stop-hook`, any error after a run was picked. |
| `2` | Usage error: bad or missing arguments, a blank idea, a count that is not a whole number of 1 or more, a slice below $0.005, a budget too small to fund one slice, roles that cannot run together, or a `--fix-budget` too small to fund one slice. `topup`: a round the run does not have, or one that closed unlocked. `verify`: no runs, or a run id that does not exist. `audit`: a bad option, such as a `--claim` that is not `done` or `none`. |
| `3` | `audit check`: the verdict is `refuted` or `inconclusive`. `fund`, `resume`: the run ended with checks not passing. This includes a run that stopped early (a hard limit, a declined round, a pause, a lost login) and prints `Ended early: <reason>` and the `antstreet resume` command. |
| `4` | No terminal to ask on. `fund`: the drafted term sheet waits for `antstreet approve`; nothing was funded. `fund` or `resume`: a worker's dispute of a check waits for `antstreet approve --dispute`. `audit plan`, `audit approve --answers`: the run waits for `antstreet audit approve`. |
| `130` | `fund`, `resume`, `audit plan`: interrupted with Ctrl-C. Continue with `antstreet resume` (before the term sheet is approved there is nothing to resume; run `antstreet fund` again). |

A ledger with a damaged line makes `report` and `status` fail with an error that names the file
and line.

## Benchmark commands

`run` makes real model calls for every cell. `drafts` and `audit` make one call per draft. `table`,
`kpi` and `replay` make none. See [../bench/METHOD.md](../bench/METHOD.md).

## `python -m antstreet.bench.run`

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
| `--firm-args` | none | Extra `antstreet fund` options for the firm arm, in one quoted string. Recorded in every result. |
| `--held-out` | `0` | Held-out checks for the firm arm to ask the examiner for, 0 to 8; 0 is off. It adds `--held-out N` to the firm arm's `antstreet fund` and records `held_out_passed`, `held_out_total` and `held_out_wrong` (held-out checks the task's reference solution fails, as `wrong_checks` does for the visible ones; the table shows it only when measured) in each firm result. The single arm ignores it. |
| `--coverage` | off | The firm arm runs `antstreet fund --coverage`: it adds `--coverage` to the firm arm's options, so `firm_args` records it. The single arm ignores it. |
| `--jobs` | `2` | Cells to run at once. |
| `--dry-run` | off | Print the cells and the task set hash, then exit. |

Before any cell it runs `claude auth status` (no model call) with the environment a worker gets,
and refuses to start when the CLI is not logged in or the login cannot be read; with
`ANTHROPIC_API_KEY` set it does not check. That check cannot see a login whose refresh will fail,
so the run also stops once 3 cells in a row end in the same infrastructure failure (`login`,
`usage_limit`, `api_error`, ...), and says which cells were not started. Those 3 cells are saved;
move their folders aside before running again, since a saved cell is never run again.

Exit codes: `0` after the cells ran (whether or not they passed); `1` when no task matches
`--only`, when the login check refuses, or when the run stopped on an infrastructure failure;
`2` for a usage error. A task that fails validation stops the run with an error before any cell
starts.

## `python -m antstreet.bench.drafts`

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
| `--prompt` | `term_sheet_v1.md` | Term-sheet prompt file under `src/antstreet/prompts`. `term_sheet_v3.md` also passes the idea's rules and keeps `rules.json` and `claims.json` in each draft's folder. |
| `--jobs` | `2` | Drafts to make and score at once. |
| `--max-spend` | none | Dollars. Makes the drafts one at a time and stops before a call that could take the measured spend past this (a call may cost up to its $0.25 cap; a cost the CLI did not report counts at that cap). |
| `--dry-run` | off | List the drafts and exit. |
| `--score-existing` | none | Score the boss drafts already saved in a `antstreet.bench.run` results folder; spends nothing. |

- A folder refuses drafts made with other settings (prompt, its content hash, model, thinking).
  Use a fresh `--out` to compare prompts.
- Exit codes: `0`; `1` when no task matches, a results folder cannot be read or holds no drafts, or
  the prompt cannot be used; `2` for a usage error.

## `python -m antstreet.bench.table`

`python -m antstreet.bench.table [--out OUT] RESULTS_DIR`. Prints the results table as markdown.

Argument: `results_dir`, a folder written by `run`.

| Option | Default | Meaning |
|---|---|---|
| `--out` | stdout | Write the table to this file instead. |

Exit codes: `0`; `1` when no results are found or a result file is invalid; `2` for a usage error.

## `python -m antstreet.bench.paired`

`python -m antstreet.bench.paired [options] DIR_A DIR_B`. Compares two arms by task and prints the
number of tasks, the mean difference, its 95% interval and a verdict, `shown` or `not shown`.
See [../bench/METHOD.md](../bench/METHOD.md). It reads results and makes no model call.

Arguments: `dir_a` and `dir_b`, results folders written by `run` (they may be the same folder).

| Option | Default | Meaning |
|---|---|---|
| `--arm-a` | `firm` | The arm taken from `DIR_A`: `single`, `firm` or `single-review`. |
| `--arm-b` | `single` | The arm taken from `DIR_B`. The difference is A minus B. |
| `--kpi` | `delivery` | `delivery`, `pass_all`, `false_pass`, `cost_per_delivery` or `time`; `false_pass` needs both arms to be `firm`, and `pass_all` the same number of counted runs of every task on both sides. |
| `--resamples` | `10000` | Task resamples for the interval. |
| `--seed` | `0` | Seed of the resampling; the same seed gives the same interval. |

Exit codes: `0`; `1` when a folder holds no results for its arm, the two sides ran different task
sets, no task is on both sides, `pass_all` finds tasks with different numbers of counted runs, or a
result file is invalid; `2` for a usage error. A different model or budget between the sides prints
a warning and still runs.

## `python -m antstreet.bench.kpi`

`python -m antstreet.bench.kpi RESULTS_DIR [RESULTS_DIR ...]`. Prints the fixed KPI scorecard as one
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

## `python -m antstreet.bench.replay`

`python -m antstreet.bench.replay [--stall N ...] [--max-slices N ...] RESULTS_DIR`. Replays firing
policies over recorded ledgers and prints, for each combination, how many workers would have been
fired, how many of those later passed a new check, and the spend saved.

Argument: `results_dir`, a folder holding `ledger.jsonl` files.

| Option | Default | Meaning |
|---|---|---|
| `--stall` | `1 2 3` | Stall-slice values to try. |
| `--max-slices` | `4 6 8` | Slice-limit values to try. |

Exit codes: `0`; `1` when a ledger cannot be read or none has slice data; `2` for an invalid
policy value or a usage error.

## `python -m antstreet.bench.audit`

Scores the check auditor, a role that gives an opinion on each check of a draft: does the idea say
what the check demands? The benchmark knows which checks are wrong (the task's reference solution
fails them), so the auditor's flags can be counted against that. The auditor stays advisory until
these numbers say it is worth its cost.

It audits drafts that are already saved, from a `antstreet.bench.run` results folder or a
`antstreet.bench.drafts` output folder. It makes one model call per draft, capped at $0.15 a call
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

## `python -m antstreet.roles.judge template`

`python -m antstreet.roles.judge template --rubric ID --artifacts DIR --out FILE`. Writes a case file
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

## `python -m antstreet.roles.judge calibrate`

`python -m antstreet.roles.judge calibrate --cases FILE --out FILE [--model M] [--dry-run]`. Runs the
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

## `python -m antstreet.roles.judge show`

`python -m antstreet.roles.judge show FILE`. Prints a calibration file. Makes no model call.

Argument: `file`, a calibration file written by `calibrate`.

Exit codes: `0`; `1` when the file cannot be read.

## Environment variables

| Variable | Read by | Meaning |
|---|---|---|
| `BOSS_CLAUDE_BIN` | `antstreet fund`, `antstreet resume`, `antstreet doctor`, `bench.run`, `bench.drafts`, `bench.audit`, `roles.judge` | Path or name of the `claude` executable. Default `claude`. Not passed on to children. |
| `ANTHROPIC_API_KEY` | every command that calls the CLI | If set and non-empty: billing is `api`, the CLI runs with `--bare` instead of `--safe-mode`, and the key is passed to the CLI and masked in logs. The `--bare` mode is not verified against the real CLI. |
| `HOME` | worker and boss calls | Passed on so the CLI finds its login. |
| `PATH` | worker and boss calls | Passed on so the CLI can start. |
| `USER` | worker and boss calls | Passed on. |
| `LANG` | worker and boss calls | Passed on. |
| `TMPDIR` | worker and boss calls | Passed on. |
| `CLAUDE_CONFIG_DIR` | worker and boss calls | Passed on so the CLI finds its login. |
| `BOSS_GATE_SANDBOX` | `antstreet doctor`, the gate (so `antstreet fund`, `antstreet resume` and the benchmarks) | `auto` (default): run each check inside an OS sandbox when the platform has a working one, else unsandboxed. `require`: refuse to run a check without one. `off`: never. Any other value is an error. See [SANDBOX.md](SANDBOX.md). |
| `MAX_THINKING_TOKENS` | the `claude` CLI | Set by `antstreet fund` for the boss's call when `--boss-thinking` is given. Never taken from your environment. |
| `BOSS_AUDIT_HOME` | `antstreet audit plan`, `check`, `report` | The folder that holds the audit store. Default `~/.boss-audit`, under the `HOME` the command sees. A store inside the audited repo is refused. |
| `BOSS_LIVE` | `tests/test_end_to_end.py` only | `1` enables the one test that makes a real model call. |

- Nothing else from your environment reaches a worker or boss process. The gate builds its own
  environment for checks: a temporary `HOME` and `TMPDIR`, a short `PATH`, `LANG`, and
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
- Only `antstreet.cli`, `antstreet.bench.run`, `antstreet.bench.drafts`, `antstreet.bench.audit`, `antstreet.roles.judge`,
  `antstreet.gate` and `antstreet.sandbox` read the process environment.

## Run folder

`antstreet fund` creates `.boss/runs/<id>/`, where `<id>` looks like `20260930T101500Z-3fa9c1`
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
| `report.md` | The board report, saved when `antstreet fund` or `antstreet resume` finishes. |
| `stories.json` | The product manager's stories, when that role ran. |
| `critic-N/` | Scratch for the critic's Nth review: `critic_checks/` holds the tests it wrote, including the ones that were not verified. |
| `demo/` | `demo.py` and `USAGE.md` as installed in `product/`. Kept because `product/` is rebuilt on every run, and a `resume` copies them back. |
| `demo_scratch/` | Where the demo writer ran its script against a copy of the product. |

A run started with `--spec` also has `rules.json`, the rule list of its idea; with `--coverage`, `coverage.json` too (the redrafts asked for, the weak checks with the stubs they passed, the SHA-256 of every check file as measured, and why the stubs could not run, if they could not). A run that asked for held-out checks also has `held_out/` (their files and a `manifest.json`;
never inside a workspace or `product/`) and, if the examiner's output was refused,
`examiner_refused.json`; `antstreet fund --held-out N` creates them. `workspaces/`, `logs/` and `product/`
exist only once a worker has been hired. `report.md` is
written by `fund` and `resume`; `antstreet report` prints it again from the ledger without writing.

## Benchmark cell folder

`python -m antstreet.bench.run --out DIR` writes one folder per cell: `DIR/<task>/<arm>/rep<N>/`.

| Path | Arm | What it holds |
|---|---|---|
| `result.json` | both | The scored result. Its presence marks the cell done. The single arm's records `final_status`, the status word of its last slice; the firm's leaves it null, as its claim is its checks. |
| `ledger.jsonl` | single | The single agent's events. |
| `workspace/` | single | The single agent's files, scored by the hidden checks. |
| `logs/solo.jsonl` | single | The single agent's raw stream. |
| `transcript.txt` | firm | What `antstreet fund` printed. |
| `.boss/runs/<id>/` | firm | A complete run folder, as above. Its `product/` is scored. |

A `single-review` cell holds the same files as a `single` cell; its ledger and stream have two slices.
