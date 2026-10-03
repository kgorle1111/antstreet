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
| B06 | `boss topup`: add money to a round; a locked round can be reopened by the investor | Top-up events are read by `budget.py`, nothing writes them | done: `boss topup` (`cli.py`), investor-only top-ups in `budget.py`, a top-up reopens a locked round in `state.py` (T45) |
| B07 | Pause before a plan limit is hit (plan pressure), not only after | `retry.plan_pressure` exists, the loop does not call it | done: feat(firm): pause before the plan limit is hit |
| B08 | A replacement worker inherits its predecessor's disputes | Disputes are per worker today | done: `state.slice_history` adds the unruled disputes of earlier workers of the task; brief, question and rulings in `firm.py`, `briefs.py`, `rulings.py` |
| B09 | The refusal brief names the real reason for each refused tool call | It assumes a path outside the folder; true for every case seen | done: `slice_end` records `denial_reasons`; the continuation brief quotes them (`stream.py`, `rundir.py`, `briefs.py`) |
| B10 | Tolerate a torn final ledger line on resume; `ledger.py` kn: a torn final line after a hard kill also raises | Failing closed was the safe first step | done: fix(cli): resume repairs a torn ledger line |
| B11 | Recover when a session to resume no longer exists ("No conversation found") | Only happens if the CLI's session store is cleared between runs | done: `Outcome.SESSION_LOST`, a new session on the next attempt, a second loss in a row stops the run; which stream carries the CLI's message is unprobed (both are read) |

## Money

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B12 | A reserve per model; `budget.py` kn: one figure for every model; make it per-model when workers run on larger ones | Only Haiku has been measured | done: `budget.reserve_for` by model family; Sonnet and Opus figures are price-ratio estimates, measure them (D18) |
| B13 | A stream-side cost watch that kills a slice in flight when it passes its cap | The CLI checks its cap only between responses | wont: D37. The stream has no per-message cost and its output counts are placeholders; an estimate would need invented prices |
| B14 | No double count when a lost slice's session is resumed; `budget.py` kn: if the lost slice's session is later resumed | Over-counting after an interruption is the safe side | done: `budget._unknown_slice_charges` drops a lost slice's charge once a later slice of its session reports its total |
| B15 | Thinking budget for workers, not only the boss | Would make the benchmark arms unequal until the single arm has it too | done: `FirmConfig.thinking_tokens` and `boss fund --worker-thinking N` (`worker.py`, `runner.py`, `firm.py`, `cli.py`) |
| B16 | `--effort` for models that honour it | No reliable effect on Haiku in 4 drafts | wont: revisit when workers run on a model where it changes cost |
| B17 | Recover input tokens from per-message usage; `stream.py` kn: input tokens could be recovered from per-message usage | The cumulative figure is enough for cost | done: `stream.py` sums per-message input tokens when the result has none; output tokens stay 0, cost stays unknown |

## Safety

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B18 | Run checks inside an OS sandbox (no network, no writes outside a temp folder, no reads of the home folder) | The largest accepted risk (T13) | done: feat(gate): run checks inside the sandbox when the platform has one; run and tested on macOS, never run on Linux (B50) |
| B19 | A check cannot forge its own verdict; `gate.py` kn: in-process verdicts are forgeable by deliberately adversarial code | Needs the report read from outside the process that runs worker code | building: the gate needs a plugin-signed proof (`_gate_plugin.py`), so a report rewrite, an exit 0 or a patched pytest is FAILED; code that reads the nonce from the check's own process can still forge a pass (T12) |
| B20 | `boss doctor` canary: prove at run time that a write outside the workspace is refused | Tests pin the flags only (T18) | done: `src/boss/doctor.py` `_check_path_rules`, run by `boss doctor --live` (one paid call; it reports "inconclusive" when the worker does not try the write) |
| B21 | Re-check isolation after the init event; verify the boss call's isolation | Checked once at init (T21) | done: late hook events fail a slice (runner); the boss and role calls run with stream-json and their init is checked after they end (`boss._call`, `BossIsolationError`), against an init recorded from a real no-tool call (`tests/fixtures/stream_boss_no_tools_2.1.285.jsonl`) |
| B22 | Size caps on a workspace, a log and the gate's copy | Bounded by time and money only (T37) | done: `src/boss/limits.py` `max_workspace_bytes` (200 MB), checked in `src/boss/firm.py` before every gate run and before the product gate, so the gate never copies a larger folder; `src/boss/runner.py` `DEFAULT_MAX_LOG_BYTES` (50 MB) |
| B23 | Hash-chain the ledger and sign approvals | Single-user machine (T29) | done: hash chain (`ledger.py` `prev`); every investor event signed by `LedgerWriter` with `<project>/.boss/investor.key` over the whole line including `prev` (`signing.py`); readers get events through `RunPaths.events`, which refuses a bad signature; the last line's hash and count anchored per run in `.boss/anchors/` (T46). Open: refuse unchained ledgers once no old runs remain; keep the key in a keychain |
| B24 | Probe API-key mode; `worker.py` kn: --bare not yet probed. | Needs an API key | open |
| B25 | A recorded fixture for a plan usage limit; `errors.py` kn: no recorded fixture for a plan usage limit yet | One has not occurred | open |
| B26 | Probe whether `Read(./**)` also confines Glob and Grep | Workers are not given those tools | wont: they are not in the tool list; revisit if they are added |
| B27 | Escape the boss's briefs and check descriptions where a person reads them | Only worker text is cleaned (T35) | done: fix(approval): the boss's text and gate details are shown as data |

## Boss and checks

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B28 | Measure check quality without worker runs: precision on the reference, recall on known-wrong implementations | Nothing measured coverage | done: feat(bench): evaluate boss drafts without running workers, with feat(bench): score a draft's checks for precision and recall |
| B29 | Boss thinking off: measure wrong checks and coverage with it | Costs about $0.50 per 17 drafts | open |
| B30 | A second pass that audits each check against the idea | Needs B28 to be judged | building: the check auditor is built and gated (`src/boss/roles/advisory.py`), `boss fund --roles check_auditor` shows its opinion of each check under the term sheet, and `src/boss/bench/audit.py` scores its flags against the reference; no scored run is recorded |
| B31 | User stories with acceptance criteria, and a check traced to every criterion | Part of the roles work | building: stories, acceptance criteria, `CheckSpec.criteria` and a tester whose checks must cover every criterion are built (`src/boss/roles/stories.py`, `product.py`, `engineering.py`) and `boss fund --roles product_manager,system_designer,tester` builds the term sheet from them; no scored run compares that sheet with the boss's own |

## Roles

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B32 | Role registry: each role's prompt, tools, output schema, gate and budget in one place | New scope | done: `RoleSpec` and `call_role` in `src/boss/roles/base.py`, `registry()` in `src/boss/roles/__init__.py`, `boss roles`; a role's output schema stays in its own module |
| B33 | Product manager (stories), user agent, system designer, tester, critic, judge, demo writer, consultant | New scope; each default-off until it earns its cost | building: all nine are built, each behind a gate and off unless `boss fund --roles` names it (`src/boss/pipeline.py`: before approval, during a dispute, after the build); none has been measured |
| B34 | Skills: versioned prompt modules per role, with tests | New scope | done: `src/boss/skills/` (the loader and 36 skill files), `tests/test_skills_quality.py` |
| B35 | Judge calibration against the investor's labels before its verdicts count | A judge is advisory until calibrated | building: the harness is built (`python -m boss.roles.judge calibrate`, `require_calibrated`) and an unlabelled set of 20 cases per rubric is in `bench/calibration/`; waiting for the owner to score them and run `calibrate`, so no calibration file exists and every judgement is `uncalibrated` |

## Benchmark

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B36 | Three runs per arm on the hardened code | Cost | done: `bench/results/2026-09-30-final3/` (both arms, 3 runs, 51 cells each; single arm at dca56c1, firm arm at a886934) |
| B37 | Replay: stop at DONE like the live loop | The live loop never funds past DONE, so replay's extra walk changes no figure today | done: fix(replay): a worker whose task is done is not walked past that point |
| B38 | More tasks: about 60 paired tasks are needed to see a 20-point difference | 17 exist | done: 59 tasks in `bench/tasks` (hash `0a83fc97a753b08c`; 18 added 2026-10-02, 24 on 2026-10-03) and 8 multi-file tasks in `bench/tasks-multi` |

## Packaging and release

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B39 | Package name and licence | The investor's decision; `boss` is taken on PyPI | open |
| B40 | Static type checking in CI | A new dev dependency needs the investor's yes | done: `mypy --strict` over `src/boss` passes and runs in CI after the format check (`pyproject.toml` `[tool.mypy]`, `.github/workflows/ci.yml`); `tests/` are not type-checked yet |
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
| B48 | `redact` masks some ordinary text (a word containing `sk-` followed by 20 characters; `max_tokens: 1000000`) | done: `redact._mask_bare_sk` and `_mask_assignment`; a hex-only `sk-` key glued after a vowel is not masked (T17) |
| B49 | The early budget check refuses `--budget 0.30 --rounds 3` even when the boss would draft fewer checks than rounds | open |

## Sandbox, added later

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B50 | Run the Linux (`bwrap`) sandbox on a Linux host, then tighten its root to an allowlist; `sandbox.py` kn: root read-only with /home, /root, /tmp and /run hidden; not run on this machine | No `bwrap` on the machine it was written on; `docs/SANDBOX.md` step 1 is the check | building: CI installs bubblewrap, lets it through AppArmor and requires the sandbox on ubuntu; done only when a Linux CI run is green; the root is not yet an allowlist |
| B51 | Show `sandboxed` in `boss report` | The flag is on every check result and in `boss doctor`; the report does not print it yet (T39) | done: the firm records `sandboxed` on every `check_result`; `boss report` prints it and warns on an unconfined check (T39) |

## Measurement and staffing, added later

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B52 | Held-out checks: a tester with no contact with the workers writes checks the workers never see, run only at the final product gate | In the final run 12 of 36 firm cells passed every visible check and failed a hidden one. The visible checks stay the spec; the held-out ones decide the verdict | done: `src/boss/held_out.py` (the folder, its hashes, its gate), `src/boss/roles/examiner.py` (the role and `run_examiner`), `src/boss/approval.py` (review and approval), `src/boss/firm.py` (`_gate_held_out`, `FirmConfig.held_out`), `src/boss/report.py`, `src/boss/bench/run.py`; the command-line option is B56, and whether a held-out failure predicts a hidden one is not measured yet |
| B53 | Staff by need: one worker by default, more only when the design splits into tasks with separate files, or when a worker is fired or stuck | The firm cost 2.4x per cell and took 2.8x the time for 69% against 63%, within the noise. A model's guess at "complexity" is not a signal the gate can check | open: designed; the measured firm arm already runs one task and one worker (final3: every cell had `--max-tasks 1`, `--parallel 1`); its extra cost is the boss call (40% of spend) and the gate-feedback slices, which staffing does not touch, and all 17 tasks are single-module, so a split signal never fires. Plan: a pure `plan_staffing` over check imports versus task paths (fail closed to one worker), behind `--staffing need`. First, with no code: run `--firm-args "--max-tasks 3 --parallel 3"` on multi-file tasks; build nothing unless that beats the firm on cost or time |
| B54 | An external benchmark: NL2Repo-Bench, its easy tasks first (spec in, Python library out, graded by upstream tests the agent never sees) | Needs an adapter and network blocking for the workers; no published cost per task, so one task is measured before any more | building: imported tasks (`gate.run_tree`, `bench/imported.py`); decouple converted and validated locally; the paid run is not done |
| B55 | pass^k and time per cell in the table | Asked for with B54 | done: `bench/table.py` shows the median time per cell and the tasks passed on every run |

## Roles in `boss fund`, added later

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B56 | Offer the critic's findings again after Ctrl-C at the fix question; `pipeline.py` kn: a cycle counts once its critic call is booked, so findings left unanswered by a Ctrl-C are not offered again | The investor's answer is not on the ledger, so a resume cannot tell a no from an interruption | done: a no is an investor `ruled` event (`declined`); a cycle counts only once answered; a resume asks the critic again (one more capped call) |
| B57 | Give the fix round the place of the first round that never opened; `pipeline.py` kn: the fix round goes after every round, so a sheet whose later rounds never opened | The round loop's own rule asks the investor to fund the unopened rounds first, and changing an approved sheet's rounds is the investor's decision | done: the fix round takes the first unopened round's number; later unopened rounds follow it, each still needing your yes |
| B58 | `tests/test_pipeline.py::test_resume_can_offer_the_fix_round_with_its_own_budget` failed once in a full-suite run and passed in 70 reruns, 40 of them with six other test processes running; the cause is not known | The failing output was not kept, and the failure did not come back | open: the next failure's output decides; run the suite with `-rf` and keep it |

## Held-out checks, added later

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B59 | `boss fund --held-out N`: call `run_examiner` between the boss's draft and the investor's review, pass `held_out_dir` to `review_term_sheet`, build `FirmConfig(held_out=N)` | `cli.py` and `pipeline.py` were being changed by other work when the feature was built. The benchmark already passes `--held-out N`, so a benchmark cell that asks for it fails until this is done | done: `boss fund --held-out N` (`cli.py` `_fund`, `Pipeline.examine` in `pipeline.py`); `--roles examiner` is refused and names the option |
| B60 | Give the examiner the design's interfaces, not only backticked names and imports; `roles/examiner.py` kn: names come from code-quoted words in briefs and imports in check files; a brief that | A brief that names an interface in prose only gives the examiner nothing to import, and it then writes checks that fail a correct product on the import | done: call shapes and `*.py` names in briefs are public names; a visible check's file never is |
| B61 | Count the held-out checks the task's reference solution fails, as `wrong_checks` does for the visible ones; `bench/run.py` kn: counts what the product passed, not how many held-out checks are wrong; run the | The investor's review is the control for a wrong held-out check and the benchmark approves automatically, so it cannot yet say how often the examiner is wrong | done: `held_out_wrong` per firm cell (`bench/run.py`, `results.py`, `table.py`) |
| B62 | The usage judge's `accurate` criterion ("matches the code shown") is scored from `USAGE.md` alone: the judge sees the demo and its printed output, never the product's source | Found while building the calibration set; the labelling guide tells the investor to score from the same material, so calibration stays fair | open: decide whether the judge should see the product's public API |
| B63 | Token totals of a resumed session: `rundir.py` books each slice's `modelUsage` tokens, which are cumulative after a resume, so the report may count them twice (cost is differenced, tokens are not) | Found during the B17 work; not traced | done: `slice_end` books each slice's own tokens, the difference of the session's running totals; `session_total_tokens` is carried like cost |
| B64 | A `LedgerWriter` opened on a file whose last line is cut off glues the next line onto the fragment | Pre-existing; `repair_torn_tail` runs first on `resume` and `topup`, but nothing stops another writer | done: `LedgerWriter` refuses a cut-off last line (naming `boss resume`) and ends a complete line that only lost its newline |
| B65 | `plan_rounds_by_priority` floors rounds at the default reserve, ignoring `--reserve` and the per-model figure | Found during B12; the post-draft round check now refuses such a plan, after the roles were paid | done: the run's reserve reaches every round planner; `budget.plan_rounds` takes a `min_round_micros` floor |
| B66 | The round-funding question shows the term sheet's budget, not `budget.round_budget` after a top-up | Found during B06 | done: the funding question shows `budget.round_budget`, top-ups included |
| B67 | Keep the critic's verified findings so a resume after Ctrl-C offers them again without a new call | B56 re-asks the critic (one more capped call); the investor decides | open |
| B68 | Paired comparison of two arms by task (`python -m boss.bench.paired`) | Asked for with the pre-registration (PREREG.md) | done: `bench/paired.py`, task-level bootstrap and a `shown`/`not shown` verdict. Open: a paired test for pass^k; a bias-corrected interval for few tasks; `cost_per_delivery` is the mean cost of a task's runs, not a pooled cost per delivery |
| B69 | A `single-review` arm: the single agent resumes its session once to review its own work (E4's baseline) | Asked for with E4 | done: `bench/run.py`, `prompts/self_review_v1.md`; 75% build, 25% review inside the single arm's cap. No paid run yet, so the split is untested |
| B70 | KPI scorecard follow-ups: record the single arm's final status word in `result.json` (today read from its ledger); count term-sheet edit loops in the ledger so investor questions stop being a lower bound | Found while building `bench/kpi.py` | open |
| B71 | A firm cell whose run hit the usage limit but whose product passed every hidden check is counted as delivered (`heldout3/linediff/firm/rep2`) | Found by the KPI scorecard; deciding whether "delivered" needs the run to finish is a definition change, so it waits for a decision | open |
| B72 | Stream a git command's output instead of holding it in memory; `gitrepo.py` kn: a command's output is held in memory under a cap; stream it if histories grow | A 16 MiB cap bounds it, and a diff of a normal audit is far smaller | open |
| B73 | `gitrepo.is_clean` looks into submodules and reads a split index (today a submodule's contents are not compared, and a split index is refused with git's message) | Neither occurs in the repositories audited so far | open |
