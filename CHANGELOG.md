# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Version 0.0.1 has not been released, so every change so far is under Unreleased. Each line says
what changed for someone using the tool, not which commit did it.

## [Unreleased]

### Added

- `boss approve RUN [--sheet V]`: approves a term sheet `boss fund` left waiting, only if it is
  exactly the text shown with that value; the signed `approved` event adds `shown_sha256`.
- `boss status --json`: one JSON object (`run`, `awaiting`, last event, checks, spend) for tools.
- A Claude Code mod in the plugin: an approve pane that shows a waiting term sheet and approves
  it only on a press of its Approve button, timing each approval in `.boss/approve-timings.jsonl`.
- `boss verify [RUN]`: an offline check of a run's hash chain, signatures and saved prompts, with no model call. Exit 0 when it all verifies, 1 with one line per problem, 2 for no such run.
- `boss mcp`: a read-only MCP server on stdio for any MCP client (`list_runs`, `status`, `report`, `verify_ledger`, `doctor` without `--live`); no tool can spend or approve.
- A Claude Code plugin in the repository (`/antstreet:fund`, `/antstreet:report`,
  `/antstreet:status`), installable once the repository is public and `antstreet` is on PyPI.
- `/antstreet:fund` drafts the term sheet and stops; you approve it yourself with
  `! uvx antstreet approve ...`, and a plugin hook denies the agent any `approve`.
- Licensed under the Apache License 2.0 (`LICENSE`, and `license` in the package metadata).
- `boss audit plan --repo R --request FILE --base REF [--held-out N]`: seals checks for a change request from the base commit's names alone, kept in `~/.boss-audit` and never in the repo; you approve them, signed; it prints a run id and a seal.
- `boss audit check RUN --head REF`: runs the sealed checks on a commit and signs a verdict: `refuted`, `unrefuted` (not proof), `inconclusive` or `no_claim`. It refuses a head off the base, an edited check and a forged approval.
- `boss audit check` calls a claim `pre_registered` only when every commit is dated after the seal (dates can be forged), flags a change that quotes the checks, and lists base tests the head deleted or broke.
- `boss audit report [RUN | --all] [--agent L]`: verdicts, and the false-pass rate with a Wilson interval per agent and claim mode. Pre-registered and post-hoc results are never added together; the rate is a floor.
- Ledger: the `audited` event, signed with the project's key like an investor's event, and `purpose` `audit_checks` on `boss_call`.
- Security: threats T51 to T54 (the audit store read by the agent, checks fitted to the change, a leak in the diff, a forged seal).
- `boss audit plan` and `check` run the checks with the repo's own `.venv` packages, read-only in the sandbox and never installed, so a check that imports a dependency is no longer `blocked`; without one, the `Environment:` line says why and to run `uv sync`.
- `boss audit plan --request FILE` and `boss audit check --claim done` are enough inside the repo: `--repo` defaults to `.`, `--base` and `--head` to `HEAD`, and the run to the latest.
- `boss fund --dispatch cascade` (off by default): each task climbs haiku, sonnet, opus, then opus at
  more effort, one rung per verified failure, with the findings handed on, then asks you.
- The cascade starts each task on the tier with the lowest expected cost for its kind, from this
  project's own past runs, or a stated prior below 5 attempts; the table prints it and a worst case.
- `boss routing` prints the attempts, fail rate and mean cost behind that choice and names any run
  the investor key does not vouch for, which is left out (D46, T70, T71).
- E6 in `bench/PREREG.md` gains a fourth arm, `cascade`.
- `boss fund --dispatch rules [--max-tier T]` (off by default): the term sheet shows a route (one
  agent for a one-file idea, else the firm) and a table of each task's model, effort and step-up.
- Under dispatch you can edit the route and each task's model before approving; the approval
  covers them, and a value outside the whitelist is refused before approval and again at hire.
- Under dispatch a worker the gate fired for no progress or a slice limit is replaced one tier up,
  once per task. Nothing else changes a model. The worst case is printed in dollars first.
- Under dispatch each slice records a hash of the exact text the worker was given, saved as
  `logs/<worker>-s<N>.prompt.txt`, and the model the CLI says it ran; a wrong model stops the run.
- `boss report` prints who did what on which model at what cost, and re-verifies the saved
  prompts (D43 to D45, T63 to T69).
- A pre-registered experiment E6 in `bench/PREREG.md`: fixed Haiku, fixed Sonnet and dispatch at the
  same per-cell budget.
- The single arm's `result.json` records `final_status`, the status word of its last slice, and the
  KPI scorecard reads it before the ledger (B70).
- `boss fund --spec` (off by default): the boss's checks cite the rules of your idea, and you see
  which rules no check covers before you approve. The rule list and a coverage summary are in your
  signed approval. One task; not with the staged draft.
- `boss fund --roles spec_mapper` (with `--spec`): a second reader, blind to the boss's claims, says
  which rules each check asserts; the note lists citations it could not confirm.
- `term_sheet_v3.md`, the prompt `--spec` uses; the check ceiling is 12 with rules, 8 without.
- A check may cite a rule of the request (`R07`) in its `criteria`, beside a story criterion.
- `python -m boss.bench.spec_eval`: the offline evaluation of that layer on saved drafts, with hand labels
  in `bench/spec_truth/` and the criteria it is judged by fixed in `bench/spec_truth/CRITERIA.md`.
- Security: threats T55 to T62 (the spec layer: a rule cited but not tested, an edited rule list, a forged coverage summary, waivers, a hostile idea, the mapper, a prompt tuned to the benchmark, spend).
- `python -m boss.bench.paired DIR_A DIR_B`: compares two arms task by task (delivery, false
  pass, cost, time) with a task-level bootstrap interval and a verdict of `shown` or `not shown`;
  refuses results from different task sets.
- A `single-review` benchmark arm: the single agent resumes its own session once to review its
  work, within the single arm's total cap (75% build, 25% review). It runs only when asked for.
- A fixed seven-KPI scorecard (`python -m boss.bench.kpi`: delivery, false pass, cost and time per
  delivery, pass^k, investor questions, check quality) and a KPIs section in `boss report`;
  definitions are in `bench/METHOD.md`.
- `boss topup [RUN] --round N --amount D`: you add money to a round; only your top-up reopens a
  round that ran out.
- `boss report` says whether every check ran sandboxed, and warns when any ran unconfined.
- The worker reserve is set per model (Haiku $0.10, Sonnet $0.30, Opus $0.50); `--reserve` still wins.
- `--worker-thinking N` sets the thinking budget of every worker slice; unset keeps the CLI's default.
- Imported benchmark tasks, graded per test by an external suite: `python -m boss.bench.imported`.
- The benchmark records the held-out checks the reference solution fails (`held_out_wrong`).
- CI is set up to run the Linux (bwrap) gate sandbox with `BOSS_GATE_SANDBOX=require`.
- 42 benchmark tasks (text, data structures, numbers, dates, protocols, algorithms, stateful systems): 59 tasks,
  and recall on 276 known-wrong solutions; earlier results stay on the original 17. Plus 8 multi-file tasks.
- Type checking: `uv run mypy` (strict, over `src/boss`) runs locally and in CI after the format check.
- `bench/calibration/`: 20 unlabelled cases each for the stories and usage rubrics, and `score.py` to
  label them; until you do and run `calibrate`, every judgement stays `uncalibrated`.
- Held-out checks, off by default: an examiner writes checks from your idea and the product's
  public names alone. You approve them with the term sheet; they run once on `product/`, unseen
  by any worker. Ask for them with `boss fund --held-out N` (0 to 8).
- The report shows held-out results apart ("Held-out checks: 2 of 3 passed on the product; the
  workers never saw them."). A run passes only when they pass too. If the examiner fails you are
  told and the run goes on without them.
- Ledger: `scope` `held_out` on `check_result`, `held_out_hashes` on `approved`, `held_out` in the
  `started` configuration, and examiner `role_call` events with `requested`, `kept`, `problems`.
- The benchmark can ask each firm cell for held-out checks and records how many the product passed
  in `held_out_passed` and `held_out_total`; older results still load.
- `boss fund "<idea>" --budget D`: an LLM boss drafts a term sheet of tasks and pytest checks, you
  approve, reject or edit it, and headless `claude` workers build the idea against the checks.
- `boss report`, `boss status` and `boss doctor [--live]`. `doctor` names a fix for every failed
  check, and `--live` verifies the login with one real call.
- An append-only ledger of every spend and decision, and a board report generated from it.
- A gate that runs each check in its own isolated pytest process and is the only source of "passed".
- Workers that start isolated (`--safe-mode`, or `--bare` with an API key), are refused if the CLI
  reports a different configuration, and can only read, write and edit files in their own folder.
- Funding in capped slices with the gate run after each: `--slice`, `--reserve`, `--rounds`
  (each later round needs your yes), `--model` and `--boss-model`.
- A firing rule for stalled workers (`--stall-slices`, `--max-slices`, `--no-firing`), with one
  reassignment per task: the replacement gets the old files and the gate's findings.
- Several tasks per idea with `--max-tasks`; tasks that own the same path are refused.
- Waiting, pausing or stopping with a fix line when the provider fails (login, rate limit, plan
  usage limit); those failures never count against a worker.
- Every worker is given your idea word for word above the boss's brief; the builder prompt names it
  the source of truth.
- Disputed checks: a worker can say a check contradicts your idea. The check never counts as
  passing, and the report shows the dispute. When the claim is credible you are asked what to do.
- Your rulings: drop a disputed check (it is no longer run or counted), keep it (the worker must
  satisfy it), or set the task aside; unblock a blocked worker with a note. Each is a `ruled` event.
- `boss resume [run]` continues an interrupted, paused or stopped run from its ledger, with the
  settings it started with. It lifts a stop on your behalf; approval, budget and limits are
  checked again.
- Ledger events `started` (the run's settings) and `resumed`, and a `session` key on `slice_start`.
- Checks run in an OS sandbox where the platform has a working tool (`sandbox-exec` on macOS,
  `bwrap` on Linux): no network, writes only in the check's own folder. Tested on macOS only.
- `BOSS_GATE_SANDBOX` (`auto`, `require` or `off`) sets whether a check needs the sandbox, and
  `boss doctor` reports its state.
- `python -m boss.bench.drafts` scores the boss's checks with no worker run: precision on the
  reference solution, recall on 65 known-wrong solutions (`mutants/` in each task).
- `boss resume` cuts an incomplete last ledger line left by a hard kill and says so. Damage
  anywhere else in a ledger is reported by file and line and never altered.
- Documents for the sandbox (`docs/SANDBOX.md`) and for everything skipped or deferred
  (`docs/BACKLOG.md`).
- Hard run limits on spend, slices (60), workers (16) and, with `--max-minutes`, wall clock.
- `--boss-thinking N` to cap or turn off the boss's thinking, which was about half of a run's cost.
- `boss fund --parallel N` works on up to N tasks at once. Each task still has one worker at a
  time, and only one thread writes the ledger.
- `boss fund --profile NAME` adds a worker profile's skills to the builder's prompt. No profile is
  used unless asked for. It is recorded on every hire and kept on `boss resume`.
- `boss roles` prints the organisation: each specialist role and worker profile, its gate, its
  skills and whether it is on by default (none is).
- Versioned skill files under `src/boss/skills/`, with a test that holds each to a size and a
  quality bar.
- Nine specialist roles, each one model call with no tools behind a gate in code (`boss roles`
  lists them). All are off unless you name them, and none is measured yet.
- `boss fund --roles A,B` (or `all`) runs the chosen roles: stories and a staged draft before you
  approve, an opinion on each dispute, a critic's review and a demo after the build. A role only
  advises or proposes.
- A failed role is booked, reported in one line and never read as "no problems found"; the staged
  draft falls back to the boss's own draft.
- The critic's verified findings can become checks and a fix round. You are asked once, and your
  approval is recorded as an amendment: `--review-cycles` and `--fix-budget` set the limits.
- A demo that ran is installed in `product/` with a `USAGE.md` that holds its real output.
- The board report has a Roles section with one line per role call.
- `python -m boss.roles.judge calibrate` compares the judge with a person's scores. Its scores
  stay labelled uncalibrated until they agree closely enough.
- `python -m boss.bench.drafts` can score the product manager, designer and tester in place of the
  boss's one call (`staged`).
- `python -m boss.bench.audit` scores the check auditor's flags against the reference solution.
- A benchmark of 17 tasks with hidden checks (`python -m boss.bench.run`, `.table`, `.replay`): a
  single agent against the firm, with intervals, the visible-against-hidden gap, the number of wrong
  boss checks, and an offline replay of firing policies.
- Benchmark results under `bench/results/` with what they show: three runs of each arm, and the
  boss's draft quality scored without worker runs.
- A refused role or audit answer is kept beside its cell as `rejected_output.json`, so a corrected
  gate can be judged without paying again.
- `boss doctor --live` also asks a worker to write outside its folder and fails if the file lands.
- The run pauses, with its round left open, when a slice reports a plan window 95% used and work
  remains, instead of running into the limit and losing that slice.
- A worker's folder over 200 MB stops the run before the gate copies it, and a slice's log stops
  growing at 50 MB. The slice's cost and outcome are still recorded.
- A worker is shown the code of checks added by an approved amendment, which the critic's fix
  round writes once you agree.
- A threat model in which every control cites a test, and a test that fails if a cited test is gone.
- Continuous integration on Linux and macOS with a coverage floor of 96%.
- Documentation: architecture, roles and skills, ledger schema, command line, decision log,
  security policy and contributing guide, each with a test that fails when it and the code disagree.

### Changed

- The product is now AntStreet: the package is `antstreet`, with an `antstreet` command beside `boss` (the module stays `boss`), new hero art and mascots; licence settled as Apache-2.0 (B39).
- README and EVIDENCE give the blinded 35-task result: firm 64 of 105, single 62 of 105, not shown
  to differ, at 2.4 times the cost per delivered task; the old 69% against 63% is not comparable.
- The test suite runs in parallel with the `pytest-xdist` dev dependency (see CONTRIBUTING.md), and
  pull-request CI fully validates only the benchmark tasks the pull request changes.
- A slice cap now leaves a fixed reserve (default $0.10) of the round unspent, instead of a 25%
  headroom, because a slice overshoots by one whole response.
- A budget too small to fund one slice per round is refused before the boss is called.
- A worker refused a tool call and reporting `blocked` is told why and funded again, not set aside.
- A worker whose only failing checks are ones it disputes is not fired: you are asked. This holds
  only when the dispute is credible (every other check passes, at most half the task's checks
  disputed).
- Ctrl-C after approval exits 130 and names `boss resume`. `--rounds`, `--max-tasks`, `--max-slices`
  and `--stall-slices` must be whole numbers of 1 or more, and `--slice` at least $0.005: usage
  error 2.
- A pause or a stop leaves its round open, so a resume continues it. A round that closed below its
  unlock threshold stays locked on resume.
- Every attempt that is not a proven resume starts a new session id; the CLI refuses one already
  in use.
- The approval is verified before every slice and every gate run, not once at the start.
- The benchmark's task set hash encoding changed: the same 17 task files went from
  `7a212cdcc5f4f466` to `c130282a6eec5fe8`.
- `boss report` lists events with missing data as incomplete instead of failing.
- The result and the exit code are the gate's run of every required check on the assembled
  `product/`, not the sum over each worker's folder. A difference is said aloud, and a status line
  follows every slice.
- A finished run opens no further round when it is run again, and Ctrl-C at the funding question
  is an interruption, not a recorded no.
- A blank idea is refused before a run folder exists.
- Ctrl-C while the boss or a role is being called ends the run with a message and exit 130, instead
  of a traceback; the ledger records that it stopped before approval.

### Fixed

- A worker facing a check that contradicts your idea bent correct code to it instead of disputing
  it. `builder_v5.md` makes the dispute the expected move, and every later brief says how.
- Ctrl-C during a slice could end in `RuntimeError: release unlocked lock` and a traceback instead of `continue with boss resume`: the interrupt was raised inside a lock wait. It now stops the worker first and is raised afterwards, where no lock is held.
- A login whose refresh fails (Claude Code 2.1.292: no retry, no HTTP status) is `login`, not `api_error`: the run stops, and `boss fund` says to run `claude auth login`.
- `python -m boss.bench.run` checks `claude auth status` before any cell, and stops after 3 cells in a row end in the same infrastructure failure instead of running every cell.
- Docs no longer call the benchmark's hidden checks, mutants and labels "hand-written": Claude wrote them, apart from the agents measured. The 29 false passes are now "read and judged real errors", one class debatable.
- The term sheet question takes `y`/`yes` and `n`/`no` like every other question; `y` was
  "Unrecognised answer" and asked again.
- `boss fund` with no terminal to ask on (Claude Code, a pipe) no longer reads end of input as a
  rejection of a paid-for draft: it keeps it waiting for `boss approve` and exits 4.
- `python -m boss.bench.run` refuses a saved cell that ran with another task set, model, budget
  or firm options, instead of counting it as this run's. Two arms of one name (the firm with and
  without `--roles critic`) each need their own results folder.
- The benchmark's spend cap now reserves a staged draft's full cost (its three role calls) before
  starting one; it reserved one call's cost and could start a draft that passed the allowance.
- The mapper pass's spend cap now counts mapper calls saved by an earlier pass, so a resumed pass
  cannot pass the allowance; a saved call with no recorded cost counts at its cap.
- A wording fix in the DECISIONS note on the offline evaluation ("hand-written mutants").
- On macOS, stopping a worker that exits at that same moment no longer fails the slice with
  "Operation not permitted".
- A benchmark cell whose run ended on an infrastructure stop (usage limit, login, isolation) is
  excluded from every count even when its product passed; old results are read the same way (B71).
- A benchmark cell cut off before its result is refused, naming the folder to move aside, instead
  of being run on top of the cut-off run.
- A resumed worker slice books only its own tokens, not the session's running total (B63).
- The ledger writer refuses a file whose last line was cut off and names `boss resume` (B64).
- Round plans use the run's own reserve, so a Sonnet or Opus run never gets an unfundable round (B65).
- The round-funding question includes top-ups made before the round opened (B66).
- A replacement worker inherits the disputes its predecessor raised that you have not ruled on.
- After a refused tool call, the worker's next brief gives the reason the CLI gave.
- A session the CLI lost ("No conversation found") starts a new one instead of failing the worker.
- A lost slice whose session is later resumed is counted once, not at its cap and again.
- `--budget` with `--rounds` is judged against the real round plan, after the draft.
- A slice killed before its result records its input tokens instead of 0.
- Ctrl-C at the critic's fix question no longer loses its findings; a no is recorded as a ruling.
- The critic's fix round takes the place of the first round that never opened.
- The examiner reads interfaces a task brief states in prose, never a visible check's file.
- `redact` no longer masks `task-...` style words or token counts; URL redaction is linear again.
- A slice that did work but reported no cost, or started and never ended, is charged at its cap, so
  a round can no longer fund such slices without end. Its cost stays unknown in the ledger.
- A run interrupted during a worker's first slice can be resumed; before, the retry reused a
  session id the CLI refused.
- A stalled worker can no longer avoid its firing by disputing every failing check.
- A check file deleted mid-run stops the run like an edited one, and a file name that collides with
  another task's is left out of `product/` and named, instead of a traceback.
- A hook event late in a worker's stream fails the slice as an isolation failure; it was counted
  and never checked.
- Replay stops at a finished task as well as at an escalation. A ledger `v` other than the integer
  1 is corrupt; `classify` and retry backoff no longer fail on malformed or huge values.
- A fired worker's passing checks are kept when no replacement can be funded.
- A run killed between two gate results, between two rulings, before a round closed, or part way
  through the product verdict is finished on resume, without paying for a needless slice.
- Your note or ruling is no longer dropped when the worker's next slice starts a new session or a
  replacement takes over.
- A benchmark cell that paused for the plan limit counts as an infrastructure outcome.
- A role's quote from your idea may drop its backticks or quote marks, or elide text with `...`,
  when each piece is word for word; a changed word or number is still refused.
- A draft that fails validation still records the cost of the boss's call.
- A `claude` binary that cannot start ends the run with a message that names it and points to
  `boss doctor`, not a traceback.
- Approving a term sheet re-reads and validates it from disk; a check edited since you last saw it
  is shown again, not approved.
- A rejected term sheet never says approved on disk, and a missing or unreadable one is reported
  during review instead of aborting it.
- A string where a task's paths must be a list, a non-UTF-8 or byte-order-marked check, and a
  check that is a symlink out of the checks folder are reported as problems.
- Ids and file names that end in a newline are refused.
- The stream reader no longer raises on malformed output; unknown cost stays unknown.
- The ledger rejects a line whose run, actor or timestamp has the wrong type.
- Replay stops at an escalation, as the live loop does, so it no longer overstates savings.
- Benchmark commands name a damaged ledger or result file instead of showing a traceback, and
  results with wrongly typed fields are refused on load.

### Security

- Boss and role calls run with stream-json and have their init event checked like a worker's (only
  the structured-output tool, no MCP servers, mode dontAsk, no hook events); a call that fails the
  check is discarded and its spend booked (B21).
- Every investor event (ruling, `resumed`, top-up, stop, round approval) is signed over the whole
  line including `prev`, so it cannot be edited, replayed or moved; a bad one is refused (B23).
- The ledger writer will not append to a ledger the key does not vouch for; older ledgers without a
  chain load unchanged (B23).
- The ledger's last line hash and line count are anchored in `.boss/anchors/<run>`; a dropped tail
  or an edited last line is refused with the line count (B23).
- Every ledger line carries `prev`, the hash of the line before it, and approvals are signed with
  `.boss/investor.key`: a worker without the key cannot forge one (T46).
- The gate needs a plugin-signed proof, so a check cannot fake a pass by rewriting its report or
  exiting 0; code aimed at the plugin itself still can (T12).
- Checks are stored outside the worker's folder and copied fresh into every gate run; a pass needs
  exit code 0 and a test report with at least one test and no failures.
- Workers have no shell, and their tool rules are limited to their own folder.
- A workspace holding `.claude` or `.mcp.json` at any depth is refused before a worker starts.
- A task's files in the product come only from that task's worker; a worker cannot replace a file
  another task's checks passed on.
- A worker's own words are stored with secrets masked, control characters made visible and a fixed
  length limit, so they cannot print terminal escapes in a report.
- The boss's briefs and check descriptions, and the gate's details, are shown as data: one line,
  secrets masked, control characters visible. Check code is shown byte for byte.
- Masking private-key blocks takes linear time (1 MB without an end line took 70 seconds).
- Secrets are masked when glued to other text, in quoted JSON values and in private-key blocks cut
  at either end.
- Only the investor's approval, with hashes matching the term sheet and every check file, lets a
  run spend money.
