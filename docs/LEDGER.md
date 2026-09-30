# Ledger

The ledger is the only record of a run: every spend and every decision, one JSON object per line
in `.boss/runs/<id>/ledger.jsonl`. The loop, the report, offline replay and the hard limits all
read state from it and from nothing else.

`tests/test_docs_ledger.py` runs the code (a scripted firm with the real gate, and the real CLI
against a fake `claude`) and fails if it writes an event type, an actor, a `data` key or a value
type that this file does not document. The example line under each event was produced by that
run.

Related: [ARCHITECTURE.md](ARCHITECTURE.md), [CLI.md](CLI.md).

## The file

- Append-only. One writer at a time (exclusive lock; a second writer is refused).
- Each event is validated before it is written, then flushed to disk.
- A line that is not a valid event makes reading fail with the file name and line number.
  A torn last line counts.
- Keys are sorted. Timestamps are UTC ISO 8601.
- `state.py`'s docstring lists the `data` contract for nine event types. This file is the
  complete list; the docstring is a subset of it, and the test checks that.

## Top-level fields

| Field | Type | Meaning |
|---|---|---|
| `v` | int | Always 1. The ledger format version. |
| `run` | str | The run id, for example `20260930T101500Z-3fa9c1`. Never empty. |
| `round` | int | 0 for events before any round (the boss's call, the first approval, a rejection); 1 and up for the round the event belongs to. Money is summed per round. |
| `actor` | str | Who wrote it: `boss`, `gate`, `rule`, `investor`, or `worker:<name>` such as `worker:w1`. Any other value is refused. |
| `event` | str | One of the event types below. |
| `cost_micros` | int or null | Estimated cost in millionths of a dollar. `null` means unknown, which is never the same as 0. Default 0. |
| `tokens_in` | int | Input tokens, cache creation included. Default 0. |
| `tokens_out` | int | Output tokens. Default 0. |
| `tokens_cached` | int | Cache-read tokens. Default 0. |
| `billing` | str | `api`, `subscription` or `unknown`. `unknown` unless the event is a spend. |
| `data` | object | The keys below, by event type. |
| `ts` | str | When the event was written. |

- Counts and costs are non-negative integers. A bool is refused.
- Costs are the CLI's client-side estimates, not a bill.
- Only `boss_call` and `slice_end` carry a cost or tokens. `error` carries a cost of `null`.

## Events

Types are listed in the order of `EventType`. "Type" cells use `str`, `int`, `float`, `bool`,
`list`, `object` and `null`. A key is present in every event of its type unless the meaning says
otherwise.

### `boss_call`

- Actor: `boss`
- Round: 0
- Written by `cli.py` after the boss's drafting call, whether the call worked, failed, timed out or
  returned a draft that does not validate. It is the only event that comes from a model call by
  the boss.
- Cost and tokens: the call's usage. `cost_micros` is `null` if the call did not report one.

| Key | Type | Meaning |
|---|---|---|
| `purpose` | str | Always `term_sheet`. |
| `model` | str | The boss model, from `--boss-model`. |
| `thinking_tokens` | int or null | The thinking budget from `--boss-thinking`; `null` means the CLI's own default. |
| `outcome` | str | How the call ended: an outcome name such as `completed`, `timeout` or `crashed`. `completed` is also used for a paid call whose draft was unusable or invalid. |

Example:

```json
{"actor": "boss", "billing": "subscription", "cost_micros": 4000, "data": {"model": "haiku", "outcome": "completed", "purpose": "term_sheet", "thinking_tokens": null}, "event": "boss_call", "round": 0, "run": "20260930T110134Z-365351", "tokens_cached": 0, "tokens_in": 10, "tokens_out": 5, "ts": "2026-09-30T11:01:35.110818+00:00", "v": 1}
```

### `hired`

- Actor: `boss` (the loop)
- Round: the current round
- Written by `firm.py` when a task needs a worker: its first, or a replacement.

| Key | Type | Meaning |
|---|---|---|
| `worker` | str | The worker's name: `w1`, `w2`, ... in hiring order across the run. |
| `task` | str | The task id. |
| `session` | str | The UUID of the worker's CLI session. |
| `model` | str | The worker model. |
| `prompt` | str | The builder prompt file the worker runs under. |

Example:

```json
{"actor": "boss", "billing": "unknown", "cost_micros": 0, "data": {"model": "haiku", "prompt": "builder_v3.md", "session": "313b164c-0a4a-4078-82fe-758c1de638c7", "task": "t1", "worker": "w1"}, "event": "hired", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:25.685263+00:00", "v": 1}
```

### `slice_start`

- Actor: `worker:<name>`
- Round: the current round
- Written by `firm.py` after the cap is fixed and the approval verified, before the CLI starts.
  The benchmark's single arm writes it with `cap_micros` only.

| Key | Type | Meaning |
|---|---|---|
| `slice` | int | The worker's slice number, from 1. Infrastructure retries count. |
| `task` | str | The task id. |
| `cap_micros` | int | The slice's spend cap in micro-dollars. A target: one response can run past it. |

Example:

```json
{"actor": "worker:w1", "billing": "unknown", "cost_micros": 0, "data": {"cap_micros": 100000, "slice": 1, "task": "t1"}, "event": "slice_start", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:25.685789+00:00", "v": 1}
```

### `slice_end`

- Actor: `worker:<name>`
- Round: the current round
- Written by `firm.py` when the CLI process ends, whatever the outcome.
- Cost and tokens: this slice's own spend, the difference between the CLI's cumulative session
  totals; `null` if unknown. Billing is `api` or `subscription`.
- The benchmark's single arm writes it with `outcome` and `status` only, and `status` there is the
  worker's report as received, not cleaned.

| Key | Type | Meaning |
|---|---|---|
| `slice` | int | The slice number. |
| `task` | str | The task id. |
| `outcome` | str | How the run ended: `completed`, `capped`, `max_turns`, `refusal`, `timeout`, `crashed`, `login`, `rate_limited`, `usage_limit` or `api_error`. |
| `status` | object or null | The worker's own report, cleaned: `status` (`done`, `continuing`, `blocked` or `none`) and `reason` (secrets masked, control characters shown as escapes, at most 500 characters). `null` if it gave none. A note, never a pass. |
| `session_total_micros` | int or null | The CLI's cumulative cost for the session after this slice; `null` if unknown. |
| `exit_code` | int or null | The CLI process's exit code. |
| `denials` | int | How many tool calls the CLI refused. |
| `denied_tools` | list | The distinct names of the refused tools, sorted. |
| `log` | str | Path of the worker's raw stream log. |

Example:

```json
{"actor": "worker:w1", "billing": "subscription", "cost_micros": 10000, "data": {"denials": 1, "denied_tools": ["Write"], "exit_code": 0, "log": ".boss/runs/r1/logs/w1.jsonl", "outcome": "completed", "session_total_micros": 10000, "slice": 1, "status": {"reason": "scripted continuing", "status": "continuing"}, "task": "t1"}, "event": "slice_end", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 10, "tokens_out": 5, "ts": "2026-09-30T11:01:25.686130+00:00", "v": 1}
```

### `check_result`

- Actor: `gate`
- Round: the current round
- Written by `firm.py` after a slice whose outcome is not an infrastructure failure: one event per
  check of the worker's task. Later results supersede earlier ones.
- The gate also runs to build the next brief; those runs are not recorded.

| Key | Type | Meaning |
|---|---|---|
| `check` | str | The check id, such as `c01`. |
| `task` | str | The task id. |
| `status` | str | `passed`, `failed` or `timeout`. The only source of "passed". |
| `detail` | str | Why: the pytest exit code, or the count of passed tests. |
| `worker` | str | The worker whose files were checked. |
| `slice` | int | The slice after which the gate ran. |

Example:

```json
{"actor": "gate", "billing": "unknown", "cost_micros": 0, "data": {"check": "c01", "detail": "pytest exited 1", "slice": 1, "status": "failed", "task": "t1", "worker": "w1"}, "event": "check_result", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:26.170363+00:00", "v": 1}
```

### `blocked`

- Actor: `worker:<name>`
- Round: the current round
- Written by `firm.py` when the rule escalates a worker that reported `blocked` without a refused
  tool call, or whose run ended in a model refusal. `abandoned` follows.

| Key | Type | Meaning |
|---|---|---|
| `task` | str | The task id. |
| `reason` | str or null | The worker's own reason, cleaned; `null` if it gave no report. |

Example:

```json
{"actor": "worker:w1", "billing": "unknown", "cost_micros": 0, "data": {"reason": "scripted blocked", "task": "t1"}, "event": "blocked", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:29.626100+00:00", "v": 1}
```

### `disputed`

- Actor: `worker:<name>`
- Round: the current round
- Written by `firm.py` when a worker's report names a check of its own task that fails now and
  that it has not disputed before. A dispute never counts as passing.

| Key | Type | Meaning |
|---|---|---|
| `task` | str | The task id. |
| `check` | str | The disputed check id. |
| `reason` | str | The worker's reason, cleaned and cut to 300 characters. |
| `worker` | str | The worker's name. |
| `slice` | int | The slice in which it was raised. |

Example:

```json
{"actor": "worker:w1", "billing": "unknown", "cost_micros": 0, "data": {"check": "c01", "reason": "the idea says otherwise", "slice": 1, "task": "t1", "worker": "w1"}, "event": "disputed", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:26.170657+00:00", "v": 1}
```

### `fired`

- Actor: `rule`
- Round: the current round
- Written by `firm.py` when the rule says to stop funding a worker: no progress or the slice limit.
  With `--no-firing`, only the slice limit fires.

| Key | Type | Meaning |
|---|---|---|
| `worker` | str | The worker's name. |
| `task` | str | The task id. |
| `reason` | str | `no progress` or `slice limit`. |
| `evidence` | object | What the rule saw. Keys below. |
| `last_reason` | str or null | The worker's last reason, cleaned; `null` if it gave none. |

Evidence keys:

| Key | Type | Meaning |
|---|---|---|
| `counted_slices` | int | Slices that count (infrastructure ones do not). |
| `stalled_slices` | int | Counted slices in a row that added no passing check. |
| `passing` | list | Checks passing after the latest slice. |
| `best` | list | Every check that passed at some slice. |
| `missing` | list | Checks not passing after the latest slice. |
| `disputed` | list | Checks the worker disputes that still fail. |
| `spent_micros` | int | Known spend of the worker's slices. |
| `unknown_cost_slices` | int | Slices whose cost is unknown. |

Example:

```json
{"actor": "rule", "billing": "unknown", "cost_micros": 0, "data": {"evidence": {"best": [], "counted_slices": 2, "disputed": ["c01"], "missing": ["c01", "c02"], "passing": [], "spent_micros": 20000, "stalled_slices": 2, "unknown_cost_slices": 0}, "last_reason": "scripted continuing", "reason": "no progress", "task": "t1", "worker": "w1"}, "event": "fired", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:27.135282+00:00", "v": 1}
```

### `abandoned`

- Actor: `boss` (the loop)
- Round: the current round
- Written by `firm.py` when a task will get no more work in this run. Nothing later reopens it.

| Key | Type | Meaning |
|---|---|---|
| `task` | str | The task id. |
| `reason` | str | `already reassigned once`, `blocked`, `refusal` or `disputed`. |

Example:

```json
{"actor": "boss", "billing": "unknown", "cost_micros": 0, "data": {"reason": "blocked", "task": "t1"}, "event": "abandoned", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:29.626185+00:00", "v": 1}
```

### `reassigned`

- Actor: `boss` (the loop)
- Round: the current round
- Written by `firm.py` when a fired worker's task gets its one replacement. `hired` follows.

| Key | Type | Meaning |
|---|---|---|
| `task` | str | The task id. |
| `from` | str | The fired worker. |
| `to` | str | The replacement. |

Example:

```json
{"actor": "boss", "billing": "unknown", "cost_micros": 0, "data": {"from": "w1", "task": "t1", "to": "w2"}, "event": "reassigned", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:27.136598+00:00", "v": 1}
```

### `round_closed`

- Actor: `boss` (the loop)
- Round: the round that ended
- Written by `firm.py` whenever a round's loop ends: done, out of money, limit reached, paused or
  stopped.

| Key | Type | Meaning |
|---|---|---|
| `passed` | int | Checks passing across all tasks, taking each task's best worker. |
| `total` | int | Checks in the term sheet. |
| `unlocked` | bool | Whether `passed` reaches this round's unlock threshold. |

Example:

```json
{"actor": "boss", "billing": "unknown", "cost_micros": 0, "data": {"passed": 1, "total": 2, "unlocked": true}, "event": "round_closed", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:28.107862+00:00", "v": 1}
```

### `approved`

- Actor: `investor`
- Two forms, both by the investor:
  - Round 0, by `approval.py` when the investor approves the term sheet. Carries `hashes`.
  - Round N, by `firm.py` when the investor funds a later round. Carries `round`.
- A missing `round` counts as round 1 when the state is rebuilt, so the first approval opens
  round 1.
- `require_approval` accepts only an `approved` event by `investor` whose `hashes` equal the hashes
  of the term sheet and check files now on disk.

| Key | Type | Meaning |
|---|---|---|
| `hashes` | object | SHA-256 hex digests: `term_sheet` for the term sheet without its approval flag, and one entry per check file, named by the file. Present in the first form only. |
| `round` | int | The round funded. Present in the second form only. |

Examples:

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"hashes": {"term_sheet": "c3d23ee4f53f84a5ad36b910b0e4fce13cf4db1c9bcc148db5ef99b939a52c2d", "test_c01.py": "46dcc9df463d18fec190640e9731fb76fd54990602d51e6f562260ee40137215", "test_c02.py": "ef8fdb7658a4589dad9a7e41b8b287e591fb402c96b8b5b3bc1438cbe7fe1173"}}, "event": "approved", "round": 0, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:25.684405+00:00", "v": 1}
```

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"round": 2}, "event": "approved", "round": 2, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:28.108273+00:00", "v": 1}
```

### `topped_up`

- Actor: `investor` (intended)
- No code writes this event. `budget.round_budget` reads it and adds `micros` to a round's budget,
  for events whose `round` is that round.

| Key | Type | Meaning |
|---|---|---|
| `micros` | int | Extra budget for the round, a positive integer. Anything else makes the budget code raise. |

Example, built with the `Event` class to show the shape the budget code accepts:

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"micros": 250000}, "event": "topped_up", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:37.222182+00:00", "v": 1}
```

### `paused`

- Actor: `boss` (the loop)
- Round: the current round
- Written by `firm.py` when the plan's usage limit is reached. The round ends and so does the run.

| Key | Type | Meaning |
|---|---|---|
| `reason` | str | Why it paused. |
| `until_epoch` | float or null | Unix time when the limit resets; `null` if the CLI did not say. |

Example:

```json
{"actor": "boss", "billing": "unknown", "cost_micros": 0, "data": {"reason": "plan usage limit reached", "until_epoch": null}, "event": "paused", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:33.545170+00:00", "v": 1}
```

### `stopped`

- Actor: `boss`, `investor` or `rule`, as listed under Writers
- Round: the round it happened in; 0 before the first round
- Written when the run ends on purpose. Writers:
  - `boss`, by `cli.py`: the boss's call failed or its draft was invalid (round 0).
  - `investor`, by `approval.py`: the term sheet was rejected (round 0).
  - `investor`, by `firm.py`: a later round was not funded.
  - `rule`, by `firm.py`: a hard run limit was reached, or the term sheet or a check no longer
    matches the approval.
  - `boss`, by `firm.py`: the worker did not start isolated, or an infrastructure failure the
    loop will not retry (login lost, or attempts used up).

| Key | Type | Meaning |
|---|---|---|
| `reason` | str | Why the run stopped. |
| `fix` | str | A one-line next step. Present only when an infrastructure failure stopped the run. |

Examples:

```json
{"actor": "boss", "billing": "unknown", "cost_micros": 0, "data": {"fix": "run `claude auth login`, then resume", "reason": "the CLI is not logged in"}, "event": "stopped", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:33.547644+00:00", "v": 1}
```

```json
{"actor": "rule", "billing": "unknown", "cost_micros": 0, "data": {"reason": "1 slices started; the run limit is 1"}, "event": "stopped", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:34.023016+00:00", "v": 1}
```

### `denied`

- Actor: `worker:<name>` (intended)
- No code writes this event. Refused tool calls are counted in `slice_end` (`denials`,
  `denied_tools`). The type is reserved and has no keys.

| Key | Type | Meaning |
|---|---|---|
| none | | |

Example, built with the `Event` class:

```json
{"actor": "worker:w1", "billing": "unknown", "cost_micros": 0, "data": {}, "event": "denied", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:37.222200+00:00", "v": 1}
```

### `error`

- Actor: `worker:<name>`
- Round: the current round
- Cost: `null`, because a worker that never started cannot prove it cost nothing.
- Written by `firm.py` (and by the benchmark's single arm, as `worker:solo`) when the CLI's
  `system/init` shows the worker is not in the configuration that was launched. `stopped`
  follows.

| Key | Type | Meaning |
|---|---|---|
| `isolation` | str | The problems found, joined by `; `. |

Example:

```json
{"actor": "worker:w1", "billing": "unknown", "cost_micros": null, "data": {"isolation": "tools differ"}, "event": "error", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:34.025877+00:00", "v": 1}
```
