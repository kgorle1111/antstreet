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
  must be 2.1.277 or newer. Otherwise the process is killed and the run refused.
- Why: A plain `-p` run inherits the user's setup. Probe P2 showed `--safe-mode` gives no MCP
  servers and no hooks, and still lists plugins (their hooks do not run), so the check counts hook
  events instead of reading the plugin list.
- Rejected: A plain headless run: it exposed 86 tools, 3 connectors, 60 skills, 238 agents and a
  session-start hook, and cost $0.058 for one word against $0.010 with `--safe-mode`. Trusting the
  flags without reading `init`.
- Evidence: `tests/test_worker_isolation.py::test_recorded_unisolated_run_is_refused_for_every_reason`,
  `tests/test_runner.py::test_unisolated_worker_is_stopped_and_refused`;
  `tests/fixtures/stream_safe_mode_ok_2.1.285.jsonl`. The `--bare` mode has not been run against the
  real CLI.

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
- Decision: A worker runs in slices: the first with `--session-id`, later ones with `--resume`,
  each with `--max-budget-usd`. Between slices the gate runs and the rule decides. A slice's spend
  is the session total after it minus the total before. The CLI must be 2.1.277 or newer.
- Why: Spend cannot be read reliably mid-run (output tokens are placeholders until a response
  ends) and a killed process leaves no result. Probe P4: from 2.1.277 a resumed call reports the
  session's cumulative total, and a resume after a capped slice was coherent (one sample).
- Rejected: Killing a worker on a mid-run cost reading. Summing per-call figures.
- Evidence: `tests/test_firm.py::test_second_slice_resumes_the_session_with_gate_feedback_and_costs_are_deltas`;
  `tests/fixtures/stream_resume_after_cap_2.1.285.jsonl`.

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
- Evidence: `src/boss/prompts/builder_v3.md`,
  `tests/test_bench_tasks.py::test_reference_must_be_stdlib_only`.

### D14: The gate runs worker code on the host, with no container

- Status: `in force`
- Decision: The gate limits what it can (allowlisted environment, temporary `HOME`, a copy of the
  workspace, a timeout that kills the process group) and the README says it is not a sandbox.
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
  reserve (default $0.10, `--reserve`). A round that cannot fund a cap of $0.005 is not started, and a
  budget that cannot fund one slice per round is refused before the boss is called.
- Why: The CLI checks a cap only between responses, so a slice overshoots by one whole response.
  Probe P4: cap $0.006 spent $0.0079. Real runs: cap $0.030 spent $0.099 and $0.075. The overshoot is
  an absolute amount, so a percentage cannot cover it.
- Rejected: A percentage headroom (25%): wrong in kind. Very small slices: they tripled a task's
  cost ($0.20 against $0.04 to $0.08 in one go) and never finished a turn.
- Evidence: `tests/test_budget.py::test_a_round_never_exceeds_its_budget_when_each_overshoot_fits_the_reserve`,
  `tests/test_firm.py::test_a_slice_cap_holds_back_the_reserve_so_an_overshoot_stays_inside_the_round`;
  `tests/fixtures/stream_budget_capped_2.1.285.jsonl`. Rerun: no round went over budget; the largest
  cell cost $0.365 of $0.40. One figure serves all models.

### D19: A disputed check goes to the investor instead of getting the worker fired

- Status: `in force`
- Decision: A worker may list a failing check of its own task that it believes contradicts the idea,
  once, with a reason. A dispute never counts as passing. When disputed checks are all that still
  fail, the task is set aside and shown in the report; the worker is not fired.
- Why: In the pilot the boss wrote wrong checks (`slugify("Version 2.0") == "version-20"`, and a typo)
  and correct workers stalled on them until fired. In the rerun 3 disputes were raised, all on
  checks the reference solution also fails; none of those workers was fired and all 3 cells passed
  every hidden check. One wrong check that was not disputed (bigdecimal c07) cost a fired worker.
- Rejected: Firing on any stall, which was the first form. Letting a dispute count as a pass, which
  would let a worker earn a round by complaining. A second boss pass to audit the checks: see D26.
- Evidence: `tests/test_rule.py::test_a_dispute_never_makes_a_check_pass_or_a_task_done`,
  `tests/test_firm.py::test_a_worker_disputing_its_only_failing_check_is_set_aside_not_fired`;
  pilot and rerun. A set-aside task has no way back in this run: the investor's ruling is not built.

### D20: A slice of unknown cost is charged at its cap when the round's money is counted

- Status: `in force`
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
