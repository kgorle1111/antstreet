# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Version 0.0.1 has not been released, so every change so far is under Unreleased. Each line says
what changed for someone using the tool, not which commit did it.

## [Unreleased]

### Added

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
