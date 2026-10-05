# Decisions

One entry per design decision, newest last. Each says what was decided, why, what was rejected and
why, and the evidence. `tests/test_docs_decisions.py` checks that ids are unique and consecutive,
that every entry has all its fields, that `superseded by` points at a real entry, and that every
file and test an entry cites exists.

Related: [ARCHITECTURE.md](ARCHITECTURE.md), [THREAT_MODEL.md](THREAT_MODEL.md),
[../bench/METHOD.md](../bench/METHOD.md).

Statuses: `in force` (the code does this), `superseded by Dxx`, `under evaluation` (in the code or
proposed, effect not yet measured).

## Kinds of evidence

| Name | What it is | Where |
|---|---|---|
| Probe P1 to P6 | One small paid call to the `claude` CLI (2.1.285, Haiku, subscription login) that answered one question. About $0.20 in all. Output saved as a fixture where it matters. | `tests/fixtures/` |
| Pilot | The benchmark's 17 tasks, one run per task and arm, $0.40 per cell, before the fixes below. | Run notes; raw results are not committed |
| Rerun | The firm arm alone on the same 17 tasks after the fixes, `--slice 0.20`, reserve $0.10. | Run notes; raw results are not committed |
| Session probe | Small calls to CLI 2.1.285 made after P1 to P6. Starting a session with an id that was already in use failed with "Session ID ... is already in use"; resuming an id that was never created failed with "No conversation found". The output was not saved as a fixture. | D32 |
| Review | An independent read of the code that reproduced a defect. The fix has a test that fails without it. | D34 |
| Sandbox probes | macOS 26.6.2, 2026-09-30: the gate's own command run under candidate profiles, with attack scripts run with and without the sandbox. | [SANDBOX.md](SANDBOX.md) |
| Draft baseline | The boss's saved drafts of the pilot and the rerun, scored with `python -m boss.bench.drafts --score-existing`. No spend. | D36 |
| Test | A test in this repository, named with its path. | `tests/` |

- Numbers marked pilot or rerun cannot be reproduced from this repository alone. The commands that
  produce them are in [../bench/METHOD.md](../bench/METHOD.md).
- Costs are the CLI's client-side estimates, not a bill.

Probes: P1 a failed login (no model reached); P2 the same call with `--safe-mode`; P3 a boss-style
call with no tools and a JSON schema; P4 a tiny task with a very low budget cap, then a resume; P5
`dontAsk` with tool rules, trying writes and commands outside the folder; P6 stream output together
with a JSON schema.

## Entries

### D01: Checks are written by the boss and approved by the investor before any work is funded

- Status: `in force`
- Decision: The boss drafts pytest checks. Nothing is funded until the investor has read every
  check and approved. A check is never written after approval.
- Why: The boss must not grade its own work, and spend must follow evidence the investor agreed to.
- Rejected: Letting the worker write its own checks, because it would pass its own tests. Checks
  the investor never sees, because the boss can be wrong: in the pilot 10 of 134 boss checks were
  wrong (a check that the reference solution fails), 4 of 134 in the rerun.
- Evidence: `tests/test_approval.py::test_only_the_investor_can_approve`,
  `tests/test_approval.py::test_render_shows_the_brief_and_every_check_in_full`; pilot and rerun.

### D02: The boss drafts; code computes ids, file names and money

- Status: `in force`
- Decision: The boss returns tasks and check code. Check ids (`c01`), file names
  (`test_c01.py`), the budget and the round plan come from code.
- Why: A model can be wrong, or hostile through the idea's text. Anything that moves money or
  names a file is not left to it.
- Rejected: Taking ids, paths or a budget split from the model's output.
- Evidence: `tests/test_safety.py::test_the_boss_cannot_choose_ids_file_names_or_money`,
  `tests/test_termsheet.py::test_task_paths_must_stay_inside_the_workspace`.

### D03: Only the gate produces "passed", and never from an exit code alone

- Status: `in force`
- Decision: Each check runs in its own pytest process on a fresh copy of the workspace. A pass needs
  exit code 0 and a JUnit report showing at least one test and no failures, errors or skips. The
  worker's own `done` is a note.
- Why: Worker code can execute during a check (`os._exit(0)`, a planted `conftest.py`), so an exit
  code proves nothing by itself.
- Rejected: Trusting the exit code. Trusting the worker's report. Asking a model to judge.
- Evidence: `tests/test_gate.py::test_hard_exit_zero_during_import_is_not_a_pass`,
  `tests/test_safety.py::test_a_worker_saying_done_is_not_a_pass`,
  `tests/test_rule.py::test_worker_saying_done_means_nothing_without_the_checks`.

### D04: Money is integer micro-dollars

- Status: `in force`
- Decision: Costs and caps are integers in millionths of a dollar. One formatter turns them into
  the CLI's dollar string.
- Why: Real events cost fractions of a cent: a boss call about $0.004, a small slice about $0.005.
  Cents would round most events to zero.
- Rejected: Integer cents, which was the first form and would understate every total. Floats, which
  drift and cannot be summed exactly.
- Evidence: Probe P3 (boss-style call, $0.0036, `tests/fixtures/json_boss_schema_call_2.1.285.json`);
  `tests/test_ledger.py::test_totals_equal_the_sum_of_events_and_keep_unknown_separate`.

### D05: Unknown cost is None, never zero

- Status: `in force`
- Decision: A missing, negative, non-finite or crash-zeroed cost is `None` in the ledger and is
  counted apart in totals and in the report.
- Why: The CLI documents that after a crash its cost fields may be zeroed, so zero can mean
  unknown. Treating unknown as free understates spend and lets a round fund work forever. Probe P1
  showed the opposite case is real too: a failed login reports a true 0.
- Rejected: Defaulting a missing cost to 0. Guessing a cost from token counts.
- Evidence: `tests/test_stream.py::test_zeroed_totals_after_a_crash_are_unknown_not_free`,
  `tests/test_stream.py::test_missing_or_invalid_cost_is_unknown`;
  `tests/fixtures/stream_auth_expired_2.1.285.jsonl`.

### D06: The ledger is the only state

- Status: `in force`
- Decision: The loop keeps nothing in memory between decisions. Before each one it rebuilds the run
  from the ledger. The report, replay and hard limits read the same file.
- Why: One source of truth for every cent and decision. A run can be continued by calling the loop
  again, and offline replay uses exactly what the live loop saw.
- Rejected: In-process state, which is lost on a crash and can drift from the record. A database,
  parked until several runs need to be reported together.
- Evidence: `tests/test_state.py::test_run_state_is_rebuilt_from_events_alone`,
  `tests/test_firm.py::test_an_interrupted_run_resumes_from_the_ledger_without_double_spending`.

### D07: Workers start isolated with `--safe-mode`, and the init event is checked

- Status: `in force`
- Decision: A worker runs with `--safe-mode` (`--bare` when an API key is set). On the CLI's
  `system/init` event the tool list must equal `Read`, `Write`, `Edit` plus the structured-output
  tool, there must be no MCP servers, the mode must be `dontAsk`, no hook may have run, and the CLI
  must be 2.1.277 or newer. Otherwise the process is killed and the run refused. The boss's draft
  call and every role call use the same check: they run with `--output-format stream-json
  --verbose --permission-mode dontAsk` (the answer is still the final `result` event), and `init`
  must list only the structured-output tool, with no MCP servers, mode `dontAsk` and no hook
  event anywhere in the output. The check runs once the process has ended, so it cannot stop a
  call, but a violation discards the output, books the spend and fails the call as `crashed`.
- Why: A plain `-p` run inherits the user's setup. Probe P2 showed `--safe-mode` gives no MCP
  servers and no hooks, and still lists plugins (their hooks do not run), so the check counts hook
  events instead of reading the plugin list.
- Rejected: A plain headless run: it exposed 86 tools, 3 connectors, 60 skills, 238 agents and a
  session-start hook, and cost $0.058 for one word against $0.010 with `--safe-mode`. Trusting the
  flags without reading `init`. Keeping `--output-format json` for the boss and roles: its single
  result (`tests/fixtures/json_boss_schema_call_2.1.285.json`) has no tools, MCP or permission
  field, so those calls could not be verified.
- Evidence: `tests/test_boss_isolation.py`, `tests/test_worker_isolation.py::test_recorded_unisolated_run_is_refused_for_every_reason`,
  `tests/test_runner.py::test_unisolated_worker_is_stopped_and_refused`;
  `tests/fixtures/stream_safe_mode_ok_2.1.285.jsonl`. The `--bare` mode has not been run against the
  real CLI. No `init` from a real no-tool call has been recorded: the tool list a boss call is
  expected to show (only the structured-output tool) and `--permission-mode dontAsk` with
  `--tools ""` are inferred from the worker recordings, and `tests/boss_init.py` builds the fake
  `init` the same way.

### D08: Workers get no shell

- Status: `in force`
- Decision: The tool list is `Read`, `Write`, `Edit`. Workers never run tests; the gate runs them
  and its output goes into the next brief.
- Why: Probe P5 allowed `Bash(python3 -m pytest *)` and it blocked `ls /` and `curl`, but a worker
  can write a test file or `conftest.py` and pytest then runs any code it wrote.
- Rejected: A shell limited to pytest, for that reason. A wider shell, for the obvious one.
- Evidence: `tests/test_worker_command.py::test_no_shell_tool_is_ever_offered`,
  `tests/test_worker_isolation.py::test_a_shell_tool_is_refused`.

### D09: Tool rules are path-scoped, and the worker starts in the canonical path

- Status: `in force`
- Decision: `--allowedTools "Read(./**) Write(./**) Edit(./**)"` with `--permission-mode dontAsk`,
  and the process starts in the workspace's real path.
- Why: In probe P5 a bare `Write` wrote outside the workspace; scoped rules blocked writes and reads
  outside it and a planted canary file was not leaked. One in-workspace write was denied once, with
  a non-canonical working directory, and did not recur with a canonical one.
- Rejected: Bare tool names. A deny list, because a whitelist keeps working when the CLI gains
  tools.
- Evidence: `tests/test_worker_command.py::test_first_slice_with_subscription_login`,
  `tests/test_worker_command.py::test_resumed_slice_with_api_key_and_role_prompt`;
  `tests/fixtures/stream_permission_denials_2.1.285.jsonl`. Whether `Glob` and `Grep` obey the
  rule was not tested, so they are not offered.

### D10: A slice is the checkpoint, and spend is the difference of cumulative totals

- Status: `in force`
- Decision: A worker runs in slices: one that starts a session uses `--session-id` with a new id
  (D32), later ones `--resume` it, each with `--max-budget-usd`. Between slices the gate runs and the rule decides. A slice's spend
  and tokens are the session totals after it minus the totals before. The CLI must be 2.1.277 or newer.
- Why: Spend cannot be read reliably mid-run (output tokens are placeholders until a response
  ends) and a killed process leaves no result. Probe P4: from 2.1.277 a resumed call reports the
  session's cumulative total, and a resume after a capped slice was coherent (one sample).
- Rejected: Killing a worker on a mid-run cost reading. Summing per-call figures.
- Evidence: `tests/test_firm.py::test_second_slice_resumes_the_session_with_gate_feedback_and_costs_are_deltas`,
  `tests/test_slice_tokens.py`; `tests/fixtures/stream_resume_after_cap_2.1.285.jsonl`.

### D11: Outcomes are classified from structured signals, and provider failures never count against a worker

- Status: `in force`
- Decision: `errors.classify` reads `is_error`, then `terminal_reason`, then `api_error_status`,
  then `subtype`. Login, rate limit, plan usage limit and API errors are infrastructure: they are
  retried with backoff, paused, or stop the run with a fix line, and are never counted toward firing.
- Why: Probe P1: an expired login ended as `subtype: "success"` with `is_error: true` and status
  401, and `claude auth status` said `loggedIn: true` at the same time.
- Rejected: Classifying from `subtype` alone. Trusting `auth status` (`boss doctor --live` makes one
  real call instead).
- Evidence: `tests/test_errors.py::test_failed_login_is_not_trusted_as_success_despite_its_subtype`,
  `tests/test_rule.py::test_infrastructure_slices_do_not_consume_the_stall_count`;
  `tests/fixtures/stream_auth_expired_2.1.285.jsonl`.

### D12: A worker process is stopped with SIGINT, then SIGTERM, then SIGKILL, to its process group

- Status: `in force`
- Decision: Five seconds of grace between signals, sent to the whole group.
- Why: SIGINT ends the turn cleanly so the CLI still prints the slice's cost; SIGTERM alone leaves
  no result. The group is killed so no child outlives the slice.
- Rejected: SIGTERM first, which turns a known cost into an unknown one.
- Evidence: `tests/test_runner.py::test_timeout_interrupts_first_so_the_slice_cost_is_still_recorded`,
  `tests/test_runner.py::test_timeout_stops_the_worker_and_its_children`.

### D13: Built products use only the Python standard library

- Status: `in force`
- Decision: The builder prompt requires it, and the benchmark's reference solutions are checked for
  it. Nothing installs dependencies for a product.
- Why: The gate runs checks with the interpreter that runs `boss`, so an install step per run would
  need its own environment and a network.
- Rejected: Third-party dependencies in built products, for now. Whether they come in is open.
- Evidence: `src/boss/prompts/builder_v4.md` (the same lines as `builder_v3.md`),
  `tests/test_bench_tasks.py::test_reference_must_be_stdlib_only`.

### D14: The gate runs worker code on the host, with no container

- Status: `in force`
- Decision: The gate limits what it can (allowlisted environment, temporary `HOME`, a copy of the
  workspace, a timeout that kills the process group) and the README says it is not a container.
  Since D35 an OS sandbox narrows this where the platform has one; there is still no container.
- Why: Isolating the gate against code written to defeat it needs a container or VM; that is
  parked until ideas from untrusted sources are supported.
- Rejected: Claiming the tool whitelist protects the machine. It limits the worker, not the code the
  worker writes.
- Evidence: `tests/test_safety.py::test_accepted_risk_worker_code_run_by_the_gate_has_host_access`,
  `tests/test_safety.py::test_accepted_risk_code_aimed_at_the_gate_can_forge_a_pass`;
  [THREAT_MODEL.md](THREAT_MODEL.md) T12 and T13.

### D15: The firing rule is a pure function of a worker's slice history, and it can be replayed offline

- Status: `in force`
- Decision: `rule.decide` sees only what each slice cost, how it ended, and which checks passed
  after it. It fires on no progress (default 2 counted slices in a row) or at a slice limit
  (default 6). The same function runs live and in replay over recorded ledgers, which reports
  workers fired, false firings (a later slice passed a new check) and money saved.
- Why: A rule that reads no model output is explainable and testable, and thresholds can be
  compared without paying twice. Published early-stopping work reports savings of about 15 to 20%
  of tokens for a few points of success (figures as read in the planning notes: arXiv 2608.03222,
  2606.00198, 2605.15206; not re-checked here), but those use learned predictors and give no
  tool.
- Rejected: A learned stopping predictor. Letting a model decide who to fire. Live-only tuning.
- Evidence: `tests/test_rule.py::test_infrastructure_slices_do_not_consume_the_stall_count`,
  `tests/test_replay_integration.py::test_two_ledgers_and_three_policies_give_the_hand_worked_totals`,
  `src/boss/bench/replay.py`. The defaults 2 and 6 have not been checked against replayed
  benchmark ledgers in this repository.

### D16: One reassignment per task; the old files are offered, not imposed

- Status: `in force`
- Decision: A task gets at most two workers. The replacement starts a fresh session with the
  gate's findings and the old worker's files under `previous_attempt/`, which it may ignore. No
  model writes the notes. When no replacement can be funded, the fired worker's progress is kept.
- Why: Bounded spend. Published restart work found that offering the old diff as an optional
  overlay did better than a cold restart (71.8% against 66.8%; figure as read in the planning
  notes, not re-checked). A model summary would cost money and add an injection surface.
- Rejected: Unlimited reassignment. A cold restart. A model-written handoff.
- Evidence: `tests/test_firm.py::test_a_task_is_reassigned_only_once_then_abandoned`,
  `tests/test_firm.py::test_a_fired_workers_progress_survives_when_nothing_is_left_for_a_replacement`,
  `tests/test_handoff.py::test_reassignment_prompt_never_starts_with_a_dash`.

### D17: The investor's idea is quoted word for word at the top of every worker's brief

- Status: `in force`
- Decision: Every first brief starts with the idea, quoted line by line and named the source of
  truth, then the boss's brief and checks.
- Why: In the pilot workers saw only the boss's paraphrase and followed it where it dropped a rule.
- Rejected: Brief and checks only, which was the first form.
- Evidence: Pilot against rerun on hidden checks passed: calc 3 of 8 to 7 of 8, duration 2 of 8 to
  7 of 8, wildcard 6 of 8 to 8 of 8, jsonpointer 4 of 8 to 6 of 8 (a single agent scored 7 of 8 on
  calc and duration). `tests/test_firm.py::test_every_worker_is_given_the_investors_idea_word_for_word`,
  `tests/test_briefs.py::test_the_idea_is_quoted_word_for_word_above_the_boss_brief`.

### D18: A fixed reserve is held back from every slice cap, replacing a 25% headroom

- Status: `in force`
- Decision: A slice's cap is the smaller of the slice size and what is left in the round minus a
  reserve (default $0.10, `--reserve`, larger for Sonnet and Opus). A round that cannot fund a cap
  of $0.005 is not started. A budget that cannot fund one slice at all is refused before the boss is
  called; the round plan is checked again after the draft, when the number of rounds is known.
- Why: The CLI checks a cap only between responses, so a slice overshoots by one whole response.
  Probe P4: cap $0.006 spent $0.0079. Real runs: cap $0.030 spent $0.099 and $0.075. The overshoot is
  an absolute amount, so a percentage cannot cover it.
- Rejected: A percentage headroom (25%): wrong in kind. Very small slices: they tripled a task's
  cost ($0.20 against $0.04 to $0.08 in one go) and never finished a turn.
- Evidence: `tests/test_budget.py::test_a_round_never_exceeds_its_budget_when_each_overshoot_fits_the_reserve`,
  `tests/test_firm.py::test_a_slice_cap_holds_back_the_reserve_so_an_overshoot_stays_inside_the_round`;
  `tests/fixtures/stream_budget_capped_2.1.285.jsonl`. Rerun: no round went over budget; the largest
  cell cost $0.365 of $0.40. The reserve is still one absolute figure per model, never a share of the
  cap: Haiku, the only model measured, keeps $0.10, and Sonnet and Opus scale it by output price
  (3x, 5x) until they are measured (`budget.reserve_for`).

### D19: A disputed check goes to the investor instead of getting the worker fired

- Status: `in force`
- Decision: A worker may list a failing check of its own task that it believes contradicts the idea,
  once, with a reason. A dispute never counts as passing. When disputed checks are all that still
  fail and the dispute is credible (D34), the worker is not fired: the investor is asked what to do
  (D30).
- Why: In the pilot the boss wrote wrong checks (`slugify("Version 2.0") == "version-20"`, and a typo)
  and correct workers stalled on them until fired. In the rerun 3 disputes were raised, all on
  checks the reference solution also fails; none of those workers was fired and all 3 cells passed
  every hidden check. One wrong check that was not disputed (bigdecimal c07) cost a fired worker.
- Rejected: Firing on any stall, which was the first form. Letting a dispute count as a pass, which
  would let a worker earn a round by complaining. A second boss pass to audit the checks: see D26.
- Evidence: `tests/test_rule.py::test_a_dispute_never_makes_a_check_pass_or_a_task_done`,
  `tests/test_firm.py::test_a_worker_disputing_its_only_failing_check_is_set_aside_not_fired`;
  pilot and rerun. The investor's ruling is D30; a task that is set aside stays set aside for the
  run.

### D20: A slice of unknown cost is charged at its cap when the round's money is counted

- Status: `superseded by D33`
- Decision: The ledger keeps the cost as unknown. The budget arithmetic counts a slice that did work
  and reported no cost (a crash, a kill at the timeout) as spent at its cap. An infrastructure
  failure did no work and is not charged.
- Why: Ignoring such slices let a round fund them without the money ever running out: four were
  funded against a $0.12 round.
- Rejected: Charging nothing. Charging the round's whole remainder.
- Evidence: `tests/test_budget.py::test_a_slice_of_unknown_cost_is_charged_at_its_cap`,
  `tests/test_budget.py::test_unknown_cost_slices_cannot_be_funded_without_end`.

### D21: The approval is re-verified before every slice and every gate run

- Status: `in force`
- Decision: The hashes of the term sheet and each check file are verified at run start, before a
  slice is paid for, and before each gate run. A mismatch records `stopped` and ends the run. The
  term sheet is also reloaded and validated from disk at the moment of approval.
- Why: Check files are read from disk on every gate run and quoted into briefs, so a check edited
  after approval would have been used, and its result recorded as a pass.
- Rejected: Verifying once at the start.
- Evidence: `tests/test_firm.py::test_a_check_edited_mid_run_stops_the_run_and_its_result_is_never_recorded`,
  `tests/test_approval.py::test_changing_a_check_after_approval_voids_it`.

### D22: Hard run limits are a second layer under the round budget and the firing rule

- Status: `in force`
- Decision: Before every slice the loop also checks total spend against the rounds' budgets plus one
  reserve each, slices started (60), workers hired (16, counting the hire the next slice would
  need) and, with `--max-minutes`, wall clock.
- Why: The budget and the firing rule are logic that can have bugs. Limits that read only the ledger
  hold even if both fail.
- Rejected: Relying on the budget and the rule alone.
- Evidence: `tests/test_limits.py::test_precedence_spend_then_slices_then_workers_then_clock`,
  `tests/test_firm.py::test_the_spend_ceiling_stops_a_run_whose_slice_ran_far_past_its_cap`,
  `tests/test_firm.py::test_a_run_stopped_by_a_limit_stays_stopped_when_resumed`.

### D23: A refused tool call is explained to the worker instead of being escalated

- Status: `under evaluation`
- Decision: When a worker reports `blocked` after the CLI refused one of its tool calls, the task is
  not set aside. The next brief names the refused tools, says the folder is the whole workspace and
  to use relative paths. The stall rule still applies. Builder prompt v3 states the path rule up
  front.
- Why: In the rerun, csvline scored 0 of 7: the worker named an absolute path, the path rule
  refused it, the worker said `blocked`, and the task was set aside with nothing built. The refusal
  was the control working; giving up was the defect.
- Rejected: Escalating every `blocked`, which was the first form. Widening the path rule.
- Evidence: `tests/test_firm.py::test_a_worker_blocked_by_a_refused_tool_call_is_told_why_and_funded_again`,
  `tests/test_briefs.py::test_continuation_tells_a_worker_why_its_tool_calls_were_refused_and_what_to_do`.
  The fix was written after the rerun and has not been measured in a benchmark run.

### D24: The boss's cost is tuned with a thinking budget, not `--effort`

- Status: `in force`
- Decision: `--boss-thinking N` sets the CLI's thinking budget for the boss's call only (0 turns it
  off). An inherited `MAX_THINKING_TOKENS` never reaches a call.
- Why: The boss's draft was about half a run's cost in the pilot (51%; 44% in the rerun), mostly
  thinking: up to 18,000 to 20,000 output tokens for a few short checks. Four drafts: `--effort low`
  averaged $0.070 against $0.086 by default, and one draft cost more. Thinking off averaged $0.031, all
  four lower and all valid.
- Rejected: `--effort` for the boss and worker, which showed no reliable effect on Haiku.
- Evidence: `tests/test_boss_draft.py::test_thinking_budget_reaches_the_call_and_is_off_limits_to_the_callers_environment`,
  `tests/test_worker_command.py::test_an_inherited_thinking_budget_is_dropped_by_the_allowlist`.

### D25: The boss's default thinking budget stays the CLI's own

- Status: `under evaluation`
- Decision: Without `--boss-thinking`, the boss thinks as much as the CLI allows.
- Why: Thinking off cut a draft's cost to a third, but whether it raises the wrong-check rate is not
  measured. Wrong checks are the failure the investor cannot always see.
- Rejected: Making thinking off the default before that measurement.
- Evidence: The 4-draft probe in D24. What would change this: 17 drafts scored against the reference
  solutions with thinking off (`python -m boss.bench.run` reports wrong checks per draft).

### D26: A second boss pass that audits each check against the idea is not built

- Status: `under evaluation`
- Decision: Not built. Wrong checks are handled by the investor reading them (D01) and by dispute
  (D19).
- Why: In the rerun 6 of 12 firm cells that passed every visible check failed a hidden one, so the
  boss's checks do not cover the idea; a second pass might catch missing rules and wrong ones.
- Rejected: Adding it before it is measured: it is one more model call in every run, and the
  benchmark has to show that it lowers the wrong-check count and the gamed cells enough to pay for it.
- Evidence: Rerun; the wrong-check count is measured by `src/boss/bench/run.py`.

### D27: The benchmark compares a single agent with the firm on the same idea, model, tools and budget

- Status: `in force`
- Decision: Two arms. The single arm is one worker given the idea, one slice capped at 80% of the
  cell budget. The firm arm is `boss fund` with the term sheet approved automatically. Both use the
  same model and tools (`Read`, `Write`, `Edit`, no shell). The boss's drafting call is extra and
  counted apart.
- Why: The question is whether the firm beats one agent at the same price. Approving automatically
  is the only automated investor decision and is recorded with every result.
- Rejected: Public benchmarks (Commit0, NL2Repo-Bench): they need third-party dependencies and heavy
  environments that the standard-library gate does not support. Baselines with more tools or budget.
- Evidence: [../bench/METHOD.md](../bench/METHOD.md),
  `tests/test_bench_run.py::test_both_arms_get_the_same_idea_model_tools_and_total_budget`,
  `tests/test_bench_tasks.py::test_every_shipped_task_is_valid`.

### D28: Hidden checks score the cells, and a firm cell that passed its own checks but failed a hidden one is "gamed"

- Status: `in force`
- Decision: Each task has hidden checks written by the benchmark's author, never shown to either arm,
  and a reference solution. A task is valid only if every hidden check fails on an empty workspace
  and passes on the reference. A cell passes only if every hidden check passes. A firm cell whose
  visible checks all passed but a hidden one failed is counted as gamed. A boss check the reference
  fails is a wrong check, counted per draft outside the pass rate.
- Why: The gap between visible and hidden passes measures how far the boss's checks fall short of
  the idea. In the pilot 5 of 11 firm cells that passed every visible check failed a hidden one; in
  the rerun 6 of 12.
- Rejected: Scoring with the boss's own checks, which grades the firm on its own homework.
- Evidence: `tests/test_bench_run.py::test_hidden_checks_and_reference_never_reach_a_prompt_or_a_workspace`,
  `tests/test_bench_table.py::test_visible_and_gamed_for_firm_only`,
  `tests/test_bench_run.py::test_a_boss_check_the_reference_fails_is_counted_as_wrong`.

### D29: Pass-rate differences on 17 tasks are reported as descriptive only

- Status: `in force`
- Decision: Every rate carries its sample size and a Wilson 95% interval, and the table ends with a
  line saying a difference from fewer than about 60 paired tasks is descriptive. What a small set
  can support is reported instead: cost per passing cell, the boss's share of cost, the visible
  against hidden gap, and false firings.
- Why: At 70% and 45 cells the interval is about 13 points either way. Detecting a 10-point
  difference needs roughly 155 to 234 paired tasks and a 20-point one roughly 57 to 77.
- Rejected: Claiming a pass-rate gain or loss from 17 tasks with one run each. Rerun result:
  single 10 of 17 (59%, interval 36 to 78%), firm 9 of 17 (53%, interval 31 to 74%) at a mean cost
  per cell of $0.091 against $0.206. The firm did not beat one agent; the difference is inside the noise.
- Evidence: `tests/test_bench_table.py::test_closing_line_always_present`,
  `tests/test_bench_table.py::test_wilson_known_values`, [../bench/METHOD.md](../bench/METHOD.md).

### D30: The investor's rulings are ledger events; the approved term sheet is never edited

- Status: `in force`
- Decision: When a worker disputes a check or says it is blocked, the loop asks the investor. The
  answer is a `ruled` event (actor `investor`): `dropped`, `kept` or `unblocked` with a note.
  A dropped check is no longer run or counted, and unlock thresholds cap at what is left. A kept
  check stands and the worker is told to satisfy it. A note goes into the worker's next brief.
  Anything but a clear answer, or end of input, sets the task aside. `term_sheet.json` and the
  check files stay as approved.
- Why: The approval is bound to content hashes (D21). Editing the sheet to drop a check would void
  the approval or need a second one, and it would erase who decided what. State is rebuilt from the
  ledger anyway (D06), so the ruling is read the same way by the loop, the report and replay.
  Only an `investor` event counts: a worker or the rule cannot rule.
- Rejected: Editing the term sheet and approving again. Letting the rule or the worker drop a check.
  Setting every escalated task aside for the run, which was the first form (D19).
- Evidence: `tests/test_firm.py::test_the_investor_drops_a_disputed_check_and_the_task_is_done_without_it`,
  `tests/test_firm.py::test_a_dropped_check_is_never_run_or_counted_again`,
  `tests/test_firm.py::test_only_the_investors_ruling_counts`,
  `tests/test_firm.py::test_anything_but_a_clear_ruling_sets_the_task_aside`,
  `tests/test_state.py::test_a_dropped_check_counts_for_nothing_and_a_ruled_dispute_is_settled`.
  Not measured: how often the investor's ruling is right. A task already set aside is not reopened.

### D31: Resuming is an investor act that lifts a stop; approval, budget and limits are checked again

- Status: `in force`
- Decision: `boss resume` writes a `resumed` event (actor `investor`) when the run is stopped, then
  calls the loop. A stop holds until such an event, and a later stop holds again. The configuration
  comes from the run's `started` event, with no options to change it. An interrupted round stays
  open and continues; a round closed below its unlock threshold stays locked. The approval, the
  round's money and every hard limit are verified again as the loop goes.
- Why: A stop used to be final, so a login that lapsed or a plan limit ended the run for good.
  Lifting it is a decision about money, so it belongs to the investor and is on the record. Nothing
  the loop does can lift its own limit. A resumed run that breaks a rule stops at once.
- Rejected: Lifting stops inside the loop. Options on `resume` that loosen the run's own settings.
  Treating a paused or interrupted round as closed, which was the first form: a resume then skipped
  the unfinished task and asked to fund the next round.
- Evidence: `tests/test_state.py::test_a_stop_holds_until_the_investor_resumes_and_a_later_stop_holds_again`,
  `tests/test_cli.py::test_resume_continues_a_run_that_was_stopped_and_records_who_lifted_the_stop`,
  `tests/test_cli.py::test_resume_uses_the_configuration_the_run_started_with`,
  `tests/test_cli.py::test_resume_refuses_a_run_whose_checks_changed_and_spends_nothing`,
  `tests/test_firm.py::test_a_paused_round_stays_open_and_a_resume_finishes_it`,
  `tests/test_firm.py::test_a_round_that_closed_below_its_threshold_stays_locked_on_resume`.
  A ledger whose last line was cut by a hard kill is repaired when `boss resume` and `boss topup`
  call `ledger.repair_torn_tail` before writing, which tells the investor what was removed;
  `LedgerWriter.__enter__` refuses such a file via `_end_last_line` (B64).

### D32: Every attempt that is not a proven resume starts a new session id

- Status: `in force`
- Decision: A worker's session id is chosen for each attempt and recorded on `slice_start`. A
  session is resumed only after a slice in it got past infrastructure, which shows it exists. Any
  other attempt gets a new id and the first brief again. `hired` carries no session.
- Why: The id used to be fixed at hiring and reused until a slice worked. The session probe shows
  the CLI refuses to start a session whose id is in use ("Session ID ... is already in use") and to
  resume one that was never created ("No conversation found"). A run killed during a worker's
  first slice could not be resumed: the retry failed before any output and the run stopped as not
  isolated. After a kill the ledger cannot say whether the CLI created the session.
- Rejected: Reusing the hired id. Always resuming, which fails when the session was never created.
  Always starting anew, which drops a session's context after every slice.
- Evidence: Session probe (CLI 2.1.285),
  `tests/test_firm.py::test_an_attempt_interrupted_before_it_finished_is_started_again_under_a_new_session`,
  `tests/test_firm.py::test_a_resumed_slice_that_was_interrupted_resumes_the_same_session_and_recovers_its_cost`,
  `tests/test_state.py::test_a_session_is_resumable_only_after_a_slice_in_it_got_past_infrastructure`,
  `tests/test_state.py::test_ledgers_from_before_per_slice_sessions_fall_back_to_the_hired_session`.
  A session that was resumable and is gone ends the slice `session_lost`, an infrastructure outcome:
  never counted toward firing, retried at once under a new session id and the first brief, and a
  second loss in a row stops the run with a fix (B11; `tests/test_session_lost.py`,
  `tests/test_firm.py::test_a_session_the_cli_lost_is_replaced_by_a_new_one_and_never_counts_against_the_worker`).
  Which stream carries the CLI's "No conversation found" was not recorded, so both are read.

### D33: A slice that reported no cost, or never ended, is charged at its cap

- Status: `in force`
- Decision: The ledger keeps an unknown cost as unknown. The budget arithmetic counts as spent, at
  its cap: a slice that did work and reported no cost (a crash, a kill at the timeout), and a
  slice with a `slice_start` and no `slice_end` (the run was killed). A slice number started again
  charges the first start as well. An infrastructure failure did no work and is not charged.
- Why: Treating either as free lets a round fund such slices without the money running out: four
  were funded against a $0.12 round. After a kill the real cost is unknown, and the cap is the most
  the slice was allowed to spend before the one response the reserve covers.
- Rejected: Charging nothing. Charging the round's whole remainder.
- Evidence: `tests/test_budget.py::test_a_slice_of_unknown_cost_is_charged_at_its_cap`,
  `tests/test_budget.py::test_unknown_cost_slices_cannot_be_funded_without_end`,
  `tests/test_budget.py::test_a_slice_that_started_and_never_ended_is_charged_at_its_cap`,
  `tests/test_budget.py::test_a_lost_slice_is_still_charged_after_the_same_slice_number_runs_again`,
  `tests/test_firm.py::test_a_lost_slice_is_charged_to_the_round_at_its_cap`. If the lost slice's
  session is resumed later, its cost is recovered and the cap is counted as well: too much, on
  purpose (B14).

### D34: A dispute protects a worker only when it is credible

- Status: `in force`
- Decision: `rule.decide` sets a task aside for the investor (instead of firing the worker) only
  when every failing check is disputed and the disputed checks are at most half of the task's
  checks. Otherwise the worker is judged as if it had disputed nothing. The disputes stay on the
  ledger. A replacement inherits the disputes of workers hired before it on its task that the
  investor has not ruled on (B08): same test, and its brief quotes them as unverified claims.
- Why: Disputing costs a worker nothing (D19). An independent review reproduced a stalled worker
  that dodged its firing by disputing every failing check. The boss's drafts had at most 3 wrong
  checks in 8, so a claim that most of a task is wrong is not believed.
- Rejected: Letting any dispute protect a worker, which was the first form (D19). Refusing
  disputes, which would bring back the pilot's fired workers with correct code.
- Evidence: `tests/test_rule.py::test_disputing_more_than_half_of_a_tasks_checks_protects_nothing`,
  `tests/test_rule.py::test_exactly_half_of_a_tasks_checks_can_be_disputed`,
  `tests/test_rule.py::test_a_dispute_does_not_excuse_the_other_failing_checks`,
  `tests/test_firm.py::test_a_worker_that_disputes_everything_is_fired_and_replaced_like_any_stalled_worker`;
  the review. The one-half line is a judgement from that count of 3 in 8, not a tuned value.

### D35: The gate runs each check in an OS sandbox that denies by default

- Status: `in force`
- Decision: Where the platform has a working tool (`sandbox-exec` on macOS, `bwrap` on Linux), each
  check runs under a profile that allows nothing but what an honest pytest run needs: no network,
  writes only in the check's own temp folder, reads only that folder, the Python installation, and
  time-zone and locale data. Paths are passed as parameters, never as profile text. A tool counts
  as usable only if a probe of the real command (`python -I -B -c "import pytest"` under the real
  profile) succeeds. `BOSS_GATE_SANDBOX` is `auto` (default), `require` or `off`; every result
  says whether it ran sandboxed.
- Why: The gate runs code a model wrote (D14). A deny-by-default profile is a list of what is
  allowed, and that list can be complete; a list of what to deny cannot. Running the gate's own
  command under `(deny default)` and adding rules until an honest check passed found the whole list
  (SANDBOX.md). The probe of the real command catches a tool that exists but cannot start Python,
  a nested sandbox, or a profile that an OS update made too tight. Overhead: about 9 ms (4%) a check.
- Rejected: `(allow default)` plus denies, which leaves every Mach service reachable (the keychain
  daemon answered, the clipboard was read, `open` and `osascript` ran). Trusting `--version` to
  detect the tool. A container or VM, parked until ideas from untrusted sources are supported (D14).
- Evidence: Sandbox probes; `tests/test_sandbox.py::test_a_tool_that_exists_but_fails_is_not_usable`,
  `tests/test_gate_sandbox.py::test_a_tcp_connection_to_a_local_listener_is_denied_and_never_arrives`,
  `tests/test_gate_sandbox.py::test_a_secret_outside_the_allowed_paths_cannot_be_read`,
  `tests/test_gate_sandbox.py::test_a_hostile_directory_name_grants_that_directory_and_nothing_else`,
  `tests/test_gate_sandbox.py::test_accepted_risk_code_aimed_at_the_gate_still_forges_a_pass_inside_the_sandbox`.
  Limits: verified on macOS only; the `bwrap` argv has never been run (B50). A forged verdict is not
  prevented (T12). The default `auto` runs unsandboxed when no tool works (T39).

### D36: Boss checks are scored by precision on the reference and recall on known-wrong implementations

- Status: `in force`
- Decision: A draft's checks are scored without running a worker. Precision: the task's reference
  must pass every check, and a check it fails is wrong. Recall: each known-wrong implementation (a
  mutant) must fail a check the reference passes; a mutant that fails only wrong checks is not
  counted as caught. `python -m boss.bench.drafts` drafts and scores; `--score-existing` scores
  saved drafts for free.
- Why: Wrong checks and checks that miss the idea were the pilot's failures, and a full worker run
  costs too much to iterate a prompt on. Only the boss's call is paid: about $0.09 a draft.
  Baseline on two past runs (17 drafts each): precision 93% and 97% of checks (10 and 4 of 134
  wrong), recall 58% and 60% of mutants killed (38 and 39 of 65).
- Rejected: Scoring only through worker runs: slow, costly, and it mixes in the worker's skill.
  Counting a mutant as killed by a wrong check, which rejects everything and so detects nothing.
- Evidence: `tests/test_bench_score.py::test_one_wrong_check_one_sound_killer_and_a_mutant_only_the_wrong_check_kills`,
  `tests/test_bench_score.py::test_a_mutant_that_passes_every_check_survives_even_the_wrong_one`,
  `tests/test_bench_mutants.py::test_a_mutant_that_passes_every_hidden_check_is_rejected`,
  `tests/test_bench_drafts.py::test_hidden_checks_reference_and_mutants_never_reach_the_boss`;
  Draft baseline; [../bench/METHOD.md](../bench/METHOD.md). Limits: 65 mutants, 23 taken from Haiku
  runs; the baseline recall is biased down because 16 of those 23 were built against the drafts
  being scored. Whether a better prompt raises these figures is not yet measured.

### D37: No stream-side cost watch: the stream carries no per-message cost or output count

- Status: `in force`
- Decision: A slice is capped only by the CLI's `--max-budget-usd` plus the reserve (D18). The runner
  does not estimate spend from the stream to stop a slice early (B13, closed as `wont`).
- Why: In the recorded streams (CLI 2.1.285) the only cost anywhere is the
  `result` event's `total_cost_usd`; no assistant event, and no other event, carries one. Input
  tokens are exact per message (they sum to the final totals), but output is not: each assistant
  event's `output_tokens` is its count when the response began, 4 summed over the capped stream
  against 775 billed, and 9 against 2,957 on the resumed one. Output was about half of the capped
  slice's cost at Haiku list prices, so a running total built from the stream would miss the larger part. The only
  other signal, `system/thinking_tokens`, is the CLI's own estimate of thinking alone (172 against
  149 reported at the end). The rest would be invented: a price table per model, which neither the
  stream nor this repository holds, and output counted from text length. An estimate that is wrong
  by half cannot be set against a cap without either stopping slices that were fine or missing
  the one that overshoots, and each assistant event arrives after its block is complete, so the
  response that crosses the cap is mostly spent before it is seen.
- Rejected: A price table with output estimated from content length: made-up figures deciding when
  a worker is cut off. Stopping on the input-side cost alone: it undercounts by the output share and
  would stop on a bound that is not the cap.
- Evidence: `tests/fixtures/stream_budget_capped_2.1.285.jsonl`,
  `tests/test_stream_messages.py::test_per_message_output_tokens_are_a_small_fraction_of_the_billed_output`,
  `tests/test_stream_messages.py::test_summed_messages_equal_the_recorded_final_totals`. Reopen when
  the CLI streams a per-message cost or the final output count of each response (check
  `--include-partial-messages` first: it was not probed).

### D38: Audit checks are sealed from the base commit alone, outside the repository, and every claim about a head is computed

- Status: `in force`
- Decision: `boss audit plan` writes the checks from the request and the base commit's public
  surface (paths, names and signatures, no bodies, no tests), in one boss call that has no tools,
  and keeps them in `~/.boss-audit` (or `$BOSS_AUDIT_HOME`), never in the repository. The investor
  approves them, signed, with the base commit and the request's hash inside the approved term sheet.
  `boss audit check` then verifies the ledger, the approval and the check files, requires the head to
  descend from the base, exports both trees from git objects, and counts only the checks that fail on
  the base. The verdict is the gate's, written as a signed `audited` event; the investor states the
  claim (`--claim done|none`) and the agent's words are kept as a hash.
- Why: A check written after the change is seen is fitted to it, and a check an agent can read can be
  copied. Writing from the base alone means no change need exist, so none can be shown; keeping the
  text outside the repository, the prompt and the working folder removes the ways an agent in the
  repo meets it. A check that passes on the base cannot tell a finished change from an unfinished
  one, so it is shown to the investor and not counted. Statuses are recomputed by running the checks
  on the base at every `check` so that a stored status is not another thing to forge, and the base and
  request go in the task brief because that text is already inside the hash the signature covers.
  The ledger, signature, anchor and gate are reused, so a verdict is as hard to forge as an approval
  (T46, T54).
- Rejected: Reading the agent's own words with a model to find its claim: it lets the audited agent
  talk to the verdict, and a wrong parse is a false accusation. Checks stored in the repository, or
  in a hidden folder of it: a worker in the repo can read them. Checks written from the change: they
  would test what was done, not what was asked. Stored base statuses: one more value to protect, and
  a flaky base would be frozen in. Counting a check that passes on the base: it measures nothing
  about the change. Public-key signatures (B80): a new dependency, asked for separately.
- Evidence: `tests/test_audit_plan.py::test_no_check_text_is_anywhere_under_the_repo_and_the_store_is_outside_it`,
  `tests/test_audit_plan.py::test_a_change_that_already_exists_is_never_shown_to_the_boss`,
  `tests/test_audit_plan.py::test_the_base_and_the_request_are_inside_the_signed_term_sheet`,
  `tests/test_audit_check.py::test_a_wrong_implementation_claimed_done_is_refuted`,
  `tests/test_audit_check.py::test_a_changed_base_commit_in_the_term_sheet_voids_the_approval`,
  `tests/test_audit_check.py::test_a_passing_check_on_the_base_is_not_counted_even_when_the_head_breaks_it`.
  This does not make the checks unreadable to an agent running as the same operating-system user
  (T51, B84). No audited run has been measured yet: the false-pass rate and the share of wrong
  implementations the checks catch are the design's working figures until one is.

### D39: A verdict is a refutation or the lack of one, a leak only ever downgrades it, and the two claim modes are never pooled

- Status: `in force`
- Decision: The verdicts are `refuted` (claimed done and a counted check fails on the head),
  `unrefuted` (claimed done and none does, with at least one counted check, every one run, and no
  leak), `inconclusive` and `no_claim`. Text of the sealed checks in the change, a counted check that
  cannot run on the head, or no check that fails on the base make an otherwise passing verdict
  `inconclusive`; none of them can make a failing one anything but `refuted`. The base's own tests
  run over the head's code are listed beside the verdict and not part of it. The false-pass rate is
  `refuted` / (claimed done and not `inconclusive`) with a Wilson interval, per agent label and per
  claim mode (`pre_registered` only when every commit is dated after the seal, else `post_hoc`), and
  is reported as a floor.
- Why: A pass by checks that catch only some wrong implementations is no proof, so the word for it is
  `unrefuted`, and the rate built on it can only understate. A leak means the checks may have been
  seen, which makes a pass doubtful but a failure no less real, so it is allowed to remove trust
  and never to add blame. Commit dates are chosen by the committer, so a post-hoc audit may have
  been written after the work was read; adding it to pre-registered ones would let the weaker kind
  borrow the stronger's credit. Old tests broken by a change that was asked to change behaviour are
  not wrong, so listing them is safer than counting them.
- Rejected: A `passed` verdict: it claims what the checks cannot show. Counting base-test
  regressions as refutations: a request that changes behaviour would be refuted for doing its job
  (B82). One pooled rate: it would hide the difference between a claim made before the checks were
  sealed and one made after. A leak that refutes: a name collision would accuse an honest change.
- Evidence: `tests/test_audit_check.py::test_the_verdict_logic`,
  `tests/test_audit_check.py::test_a_head_that_quotes_a_sealed_test_name_is_flagged_and_a_pass_is_not_trusted`,
  `tests/test_audit_check.py::test_deleted_and_broken_base_tests_are_caught_though_the_sealed_checks_pass`,
  `tests/test_audit_check.py::test_claim_mode_needs_a_commit_and_every_commit_after_the_seal`,
  `tests/test_audit_report.py::test_pre_registered_and_post_hoc_are_never_pooled`,
  `tests/test_audit_report.py::test_wilson_matches_the_published_score_interval`. Reopen when an
  audited run measures how many wrong implementations the checks miss.
### D40: The rule layer's headline counts four anchor types; literals and list items are shown apart

- Status: `under evaluation`
- Decision: `boss.spec` extracts six kinds of anchor from a rule (a literal, a list item, an exception
  name, a type, a size, "non-ASCII"). A rule's state and the headline score (anchored rules over
  scored rules) use only the last four. A missing literal or list item is shown in its own section of
  the approval view, labelled as not scored.
- Why: The offline evaluation on 17 tasks and 169 saved drafts (15 known omissions, 61 of 273 scored
  rules belonging to a failing hidden check, a 22% base rate) found a missing `non_ascii` anchor right
  in 15 of 21 flags (71%), `exception` 5 of 5, `magnitude` 1 of 1, `type` 2 of 7 (29%), and a missing
  list item in 11 of 39 (28%, the base rate) and a literal in 1 of 22 (5%). Flagging as many rules at
  random would have hit 11.0 of the 15 cells, the verifier 12. Scoring the two noisy types would
  count a rule as uncovered on evidence no better than chance. Pre-registered O1 and O4 failed (94.9%
  against 95%; a 4.5-point kill-rate gap against 25 on hand-written mutants that are killed 88% of the time
  whatever the draft holds), so this is a reduction, not a pass.
- Rejected: Counting every anchor, as pre-registered: the evaluation's own numbers say two types are
  noise. Dropping literals and list items altogether: they are cheap to show and a person can judge
  them; only the score is withheld. Re-tuning the extraction on the same 17 tasks: the tasks are used
  up, and a held-out set of 18 more is being labelled separately.
- Evidence: `bench/results/2026-10-03-spec-offline/README.md`,
  `tests/test_spec_verify.py::test_a_missing_literal_does_not_decide_the_state_or_the_headline_but_is_still_reported`,
  `tests/test_spec_verify.py::test_only_the_four_types_with_evidence_are_in_the_headline`. Reopen
  when the 18 held-out tasks are labelled and the same measurements are run on them.

### D41: `--spec` stays off: the rules prompt did not clear its pre-registered bar

- Status: `under evaluation`
- Decision: `boss fund --spec` exists and is off by default. P2, the 51-cell firm run it was to
  unlock, is not run. The coverage view and the signed coverage summary are the part that earns
  its place so far; the prompt is not.
- Why: P1 (17 drafts, $2.3187) met two of five criteria: (a) kill rate on the failing products 35%
  against 45% (baseline 31%), (b) on the non-ASCII subset 31% against 40% (baseline 8%), (c) wrong
  checks 6.1% against 5% (baseline 1.6%); met (d) 1 invalid draft of 17 and (e) 11.2 checks, which
  cannot fail under a ceiling of 12. Only 2 of the 5 tasks that name non-ASCII input got a
  non-ASCII test. After the numbers were committed: for 16 of 16 failing products in that subset, a
  rule the failing check tests was shown as uncovered or anchor-missing to the investor by the
  verifier.
- Rejected: Running P2 anyway: the bar was set to decide exactly this, and a benchmark that
  approves every term sheet cannot measure what the view does. Raising the check ceiling or
  loosening (c) after seeing the numbers: a new prompt version, not a pass.
- Evidence: `bench/results/2026-10-03-spec-p1/README.md`, `bench/spec_truth/P1_CRITERIA.md`,
  `tests/test_bench_spec_p1.py::test_each_criterion_is_decided_at_its_boundary_and_all_five_must_hold`,
  `tests/test_boss_spec.py::test_the_v3_prompt_names_no_benchmark_task_and_no_special_character_class`.
  Reopen with a repair call, or when the held-out 18 are measured.

### D42: Roles and the core never import the CLI or the benchmark

- Status: `in force`
- Decision: Nothing under `src/boss/roles/` and none of `rule`, `gate`, `ledger`, `signing`,
  `sandbox`, `runner`, `worker`, `budget`, `firm`, `pipeline` imports `boss.cli` or `boss.bench`.
  Shared pieces sit below both: `worker.EXECUTABLE_VAR` and `stats` (interval, rate, Markdown table).
- Why: `roles.judge` imported `boss.cli` and `boss.bench.table`, so `pipeline` had to import the
  judge inside a method to avoid the cycle `pipeline -> cli -> roles.judge`. The lazy import hid
  the inversion instead of fixing it.
- Rejected: Keeping the lazy import: it works until the next import moves to module level.
- Evidence: `tests/test_layering.py`.
