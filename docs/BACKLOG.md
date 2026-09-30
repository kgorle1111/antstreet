# Backlog

Everything that was skipped, deferred, or left as a known limit, in one place. Nothing here is
hidden in a comment: `tests/test_backlog.py` fails if a `kn:` shortcut in the source is not listed,
or if an entry has no status.

Status: `open` (not started), `building` (in progress), `done` (say where), `wont` (say why).

## Loop and investor

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B01 | The investor rules on a disputed check inside a run (drop it, keep it, set the task aside) | Needed the interactive prompt | done: feat(firm): the investor rules on disputed checks and blocked tasks |
| B02 | The investor unblocks a blocked task with a note, inside a run | Same prompt as B01 | done: feat(firm): the investor rules on disputed checks and blocked tasks |
| B03 | Run every check on `product/` after assembly and report that result | Only matters with several tasks | done: feat(firm): the final verdict is the gate's result on the assembled product |
| B04 | Parallel workers for tasks that own disjoint paths | Sequential was enough for one task | done: feat(firm): work on several tasks at once |
| B05 | One-line status after every slice (spend against budget, checks passing, worker) | Not needed for correctness | done: feat(firm): the final verdict is the gate's result on the assembled product (status line) |
| B06 | `boss topup`: add money to a round; a locked round can be reopened by the investor | Top-up events are read by `budget.py`, nothing writes them | open |
| B07 | Pause before a plan limit is hit (plan pressure), not only after | `retry.plan_pressure` exists, the loop does not call it | done: feat(firm): pause before the plan limit is hit |
| B08 | A replacement worker inherits its predecessor's disputes | Disputes are per worker today | open |
| B09 | The refusal brief names the real reason for each refused tool call | It assumes a path outside the folder; true for every case seen | open |
| B10 | Tolerate a torn final ledger line on resume; `ledger.py` kn: a torn final line after a hard kill also raises | Failing closed was the safe first step | done: fix(cli): resume repairs a torn ledger line |
| B11 | Recover when a session to resume no longer exists ("No conversation found") | Only happens if the CLI's session store is cleared between runs | open |

## Money

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B12 | A reserve per model; `budget.py` kn: one figure for every model; make it per-model when workers run on larger ones | Only Haiku has been measured | open |
| B13 | A stream-side cost watch that kills a slice in flight when it passes its cap | The CLI checks its cap only between responses | open |
| B14 | No double count when a lost slice's session is resumed; `budget.py` kn: if the lost slice's session is later resumed | Over-counting after an interruption is the safe side | open |
| B15 | Thinking budget for workers, not only the boss | Would make the benchmark arms unequal until the single arm has it too | open |
| B16 | `--effort` for models that honour it | No reliable effect on Haiku in 4 drafts | wont: revisit when workers run on a model where it changes cost |
| B17 | Recover input tokens from per-message usage; `stream.py` kn: input tokens could be recovered from per-message usage | The cumulative figure is enough for cost | open |

## Safety

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B18 | Run checks inside an OS sandbox (no network, no writes outside a temp folder, no reads of the home folder) | The largest accepted risk (T13) | done: feat(gate): run checks inside the sandbox when the platform has one; run and tested on macOS, never run on Linux (B50) |
| B19 | A check cannot forge its own verdict; `gate.py` kn: in-process verdicts are forgeable by deliberately adversarial code | Needs the report read from outside the process that runs worker code | open |
| B20 | `boss doctor` canary: prove at run time that a write outside the workspace is refused | Tests pin the flags only (T18) | done: `src/boss/doctor.py` `_check_path_rules`, run by `boss doctor --live` (one paid call; it reports "inconclusive" when the worker does not try the write) |
| B21 | Re-check isolation after the init event; verify the boss call's isolation | Checked once at init (T21) | building: half done. fix(runner): a late hook event fails the slice as an isolation failure. The boss call's isolation is still unverified (its output has no init event) |
| B22 | Size caps on a workspace, a log and the gate's copy | Bounded by time and money only (T37) | done: `src/boss/limits.py` `max_workspace_bytes` (200 MB), checked in `src/boss/firm.py` before every gate run and before the product gate, so the gate never copies a larger folder; `src/boss/runner.py` `DEFAULT_MAX_LOG_BYTES` (50 MB) |
| B23 | Hash-chain the ledger and sign approvals | Single-user machine (T29) | open |
| B24 | Probe API-key mode; `worker.py` kn: --bare not yet probed. | Needs an API key | open |
| B25 | A recorded fixture for a plan usage limit; `errors.py` kn: no recorded fixture for a plan usage limit yet | One has not occurred | open |
| B26 | Probe whether `Read(./**)` also confines Glob and Grep | Workers are not given those tools | wont: they are not in the tool list; revisit if they are added |
| B27 | Escape the boss's briefs and check descriptions where a person reads them | Only worker text is cleaned (T35) | done: fix(approval): the boss's text and gate details are shown as data |

## Boss and checks

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B28 | Measure check quality without worker runs: precision on the reference, recall on known-wrong implementations | Nothing measured coverage | done: feat(bench): evaluate boss drafts without running workers, with feat(bench): score a draft's checks for precision and recall |
| B29 | Boss thinking off: measure wrong checks and coverage with it | Costs about $0.50 per 17 drafts | open |
| B30 | A second pass that audits each check against the idea | Needs B28 to be judged | building: the check auditor is built and gated (`src/boss/roles/advisory.py`) and `src/boss/bench/audit.py` scores its flags against the reference; `boss fund` does not call it and no scored run is recorded |
| B31 | User stories with acceptance criteria, and a check traced to every criterion | Part of the roles work | building: stories, acceptance criteria, `CheckSpec.criteria` and a tester whose checks must cover every criterion are built (`src/boss/roles/stories.py`, `product.py`, `engineering.py`); `boss fund` does not call them |

## Roles

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B32 | Role registry: each role's prompt, tools, output schema, gate and budget in one place | New scope | done: `RoleSpec` and `call_role` in `src/boss/roles/base.py`, `registry()` in `src/boss/roles/__init__.py`, `boss roles`; a role's output schema stays in its own module |
| B33 | Product manager (stories), user agent, system designer, tester, critic, judge, demo writer, consultant | New scope; each default-off until it earns its cost | building: all eight are built, each behind a gate and off by default (`src/boss/roles/`); `boss fund` calls none and none has been measured |
| B34 | Skills: versioned prompt modules per role, with tests | New scope | done: `src/boss/skills/` (the loader and 36 skill files), `tests/test_skills_quality.py` |
| B35 | Judge calibration against the investor's labels before its verdicts count | A judge is advisory until calibrated | building: the harness is built (`python -m boss.roles.judge calibrate`, `require_calibrated`); no calibration file exists, so every judgement is `uncalibrated` |

## Benchmark

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B36 | Three runs per arm on the hardened code | Cost | done: `bench/results/2026-09-30-final3/` (both arms, 3 runs, 51 cells each; single arm at dca56c1, firm arm at a886934) |
| B37 | Replay: stop at DONE like the live loop | The live loop never funds past DONE, so replay's extra walk changes no figure today | done: fix(replay): a worker whose task is done is not walked past that point |
| B38 | More tasks: about 60 paired tasks are needed to see a 20-point difference | 17 exist | open |

## Packaging and release

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B39 | Package name and licence | The investor's decision; `boss` is taken on PyPI | open |
| B40 | Static type checking in CI | A new dev dependency needs the investor's yes | open |
| B41 | Release workflow, versioning, install from a package index | After B39 | open |

## Small findings not yet fixed

| Id | Item | Status |
|---|---|---|
| B42 | `state.slice_history` raises on an outcome it does not know (a ledger from a newer version) | done: fix(state): an unknown slice outcome is refused by name |
| B43 | `ledger.Event.from_json` accepts `"v": true` as version 1 | done: fix(ledger): a version must be the integer 1 |
| B44 | `errors.classify`: an `errors` field that is an int raises TypeError | done: fix(errors): classify never raises on malformed signals |
| B45 | `retry.infra_action` overflows for an attempt number over about 1000 | done: fix(retry): backoff and plan pressure hold for any input |
| B46 | `retry.plan_pressure` assumes utilisation is a fraction, not a percentage | done: fix(retry): backoff and plan pressure hold for any input |
| B47 | `FiringPolicy` accepts bool and float | done: fix(rule): the firing policy's counts must be whole numbers |
| B48 | `redact` masks some ordinary text (a word containing `sk-` followed by 20 characters; `max_tokens: 1000000`) | open |
| B49 | The early budget check refuses `--budget 0.30 --rounds 3` even when the boss would draft fewer checks than rounds | open |

## Sandbox, added later

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B50 | Run the Linux (`bwrap`) sandbox on a Linux host, then tighten its root to an allowlist; `sandbox.py` kn: root read-only with /home, /root, /tmp and /run hidden; not run on this machine | No `bwrap` on the machine it was written on; `docs/SANDBOX.md` step 1 is the check | open |
| B51 | Show `sandboxed` in `boss report` | The flag is on every check result and in `boss doctor`; the report does not print it yet (T39) | open |

## Measurement and staffing, added later

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B52 | Held-out checks: a tester with no contact with the workers writes checks the workers never see, run only at the final product gate | In the final run 12 of 36 firm cells passed every visible check and failed a hidden one. The visible checks stay the spec; the held-out ones decide the verdict | open |
| B53 | Staff by need: one worker by default, more only when the design splits into tasks with separate files, or when a worker is fired or stuck | The firm cost 2.4x per cell and took 2.8x the time for 69% against 63%, within the noise. A model's guess at "complexity" is not a signal the gate can check | open: measure as a third arm before it becomes the default |
| B54 | An external benchmark: NL2Repo-Bench, its easy tasks first (spec in, Python library out, graded by upstream tests the agent never sees) | Needs an adapter and network blocking for the workers; no published cost per task, so one task is measured before any more | open |
| B55 | pass^k and time per cell in the table | Asked for with B54 | done: `bench/table.py` shows the median time per cell and the tasks passed on every run |
