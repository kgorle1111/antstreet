# Ledger

The ledger is the only record of a run: every spend and every decision, one JSON object per line
in `.boss/runs/<id>/ledger.jsonl`. The loop, the report, offline replay and the hard limits all
read state from it and from nothing else.

`tests/test_docs_ledger.py` runs the code (a scripted firm with the real gate, and the real CLI
against a fake `claude`) and fails if it writes an event type, an actor, a `data` key or a value
type that this file does not document. The example line under each event was produced by that
run, except for the type that no code writes (`denied`): its example is built with the code that
would write it.

Related: [ARCHITECTURE.md](ARCHITECTURE.md), [CLI.md](CLI.md).

## The file

- Append-only. One writer at a time (exclusive lock; a second writer is refused).
- Each event is validated before it is written, then flushed to disk.
- A line that is not a valid event makes reading fail with the file name and line number.
  A torn last line counts. `boss resume` calls `ledger.repair_torn_tail` before it reads the file:
  it cuts an incomplete last line (only when every earlier line is valid) and says what it removed.
  No other command repairs: `boss report` and `boss status` report a torn ledger as damaged.
- `LedgerWriter` never appends to a cut-off last line, because the next line would be glued onto
  it and the file could no longer be repaired. Opening a file whose last line has no newline and
  does not parse as an event raises `LedgerCorruptError` naming `boss resume`, and changes nothing.
  A last line that is a complete event and only lost its newline gets the newline, under the
  writer's lock; the next `prev` is the same either way.
- The version `v` must be the integer 1: `true` and `1.0` make the line corrupt. Adding `prev`
  (below) did not change the version: it is an optional key, a reader older than the chain refuses
  a line that has it (its fields differ from the schema), and a reader that knows the chain reads
  every older line unchanged.
- Hash chain. Each line written by `LedgerWriter` carries `prev`, the SHA-256 (lower-case hex) of
  the previous line's exact bytes, without its newline. The first line of a file carries the
  genesis value, 64 zeros. The writer takes the link from the file's real last line when it opens
  the file, under the exclusive lock, so a ledger resumed later (including one written before the
  chain existed) continues from what is on disk.
- `read_events` checks the chain. A line whose `prev` is not the hash of the line before it, or
  a line without `prev` after a line that has one, raises `LedgerCorruptError` naming the first
  such line. A ledger in which no line has `prev` was written before the chain and loads as it
  always did; a ledger that begins that way and goes on with chained lines is checked from its
  first chained line, which must hash the last older line. After `repair_torn_tail` cuts a torn
  last line the next line chains from the new last line.
- What the chain proves. It is unkeyed, so it catches any edit that does not also recompute every
  later line: a changed byte, a deleted, inserted or reordered line, a line from another ledger.
  It does not stop a forger who recomputes it; that is what the line signatures are for (below). It also cannot see the end of the file: dropping the last lines leaves a valid
  chain, and the last line is not covered until another line follows it; that is what the anchor
  is for (below). A ledger with every `prev` removed reads as an older one.
  `docs/THREAT_MODEL.md` T46 states the limits.
- Signatures. When a run is in a project (`<project>/.boss/runs/<id>`), `LedgerWriter` signs every
  event whose actor is `investor` as it writes it: `data.sig` is `v2:` and the HMAC-SHA-256 (hex)
  with `<project>/.boss/investor.key` of every field of the line (run, round, actor, event, cost,
  tokens, billing, time, `data` without `sig`, and `prev`). So an investor event cannot be edited,
  moved to another run or place, replayed, or kept when any line before it is edited, even by a
  forger who recomputes the chain. The events are `approved`, `ruled`, `resumed`, `topped_up` and
  the investor's `stopped`, and the gate's `audited` verdict (`ledger.is_signed_kind`: the audit
  verdict is a record other people are shown); no other event is signed. An approval written by the first
  version of signing has a bare hex `sig` over its run, round and data; it still verifies, on an
  `approved` event only.
- Line signatures. When a run is in a project, `LedgerWriter` loads the project's key when it opens
  (creating it if the project has none) and ends every line it appends with
  `, "mac": "<hex>"}`: the HMAC-SHA-256 with the investor key of `boss ledger line v1`, the run id
  (the run folder's name) and the SHA-256 of the line without its `mac` (the same line with that
  suffix replaced by `}`). `mac` is not an event field: `Event.from_json` drops it, and a `mac`
  anywhere but the end of the line makes the line corrupt. With the key path, `read_events`
  refuses, naming the line, a signed line whose `mac` does not verify (edited, forged, copied from
  another run, or the key was replaced) and an unsigned line after a signed one (appended without
  the key). Lines before the first signed line are covered by its `prev`. Signed lines with the key
  missing are refused with the path of the key to restore. Checking costs about 1 µs of HMAC per
  line.
- What the line signatures and the anchor prove together. Someone without the key who can write
  the run folder cannot edit, insert or append a line in a run that has its anchor, even by
  recomputing the whole chain, and the writer never re-anchors such a line, because it runs the
  same check when it opens. They can still (a) put back an earlier genuine ledger together with its
  earlier genuine anchor (a rollback is not seen), (b) cut the one line a crash left between its
  append and its anchor, and (c) strip every signature, rewrite the ledger and delete the anchor,
  which makes the run look like one older than line signing: that is refused (below) until the
  investor adopts it, and the investor cannot tell the two apart. The full fix is a trust root
  outside the run folder that the investor key signs (not built).
- Unsigned runs. With the key path and no anchor, a ledger with any unsigned line is refused by
  every reader and by the writer (which also refuses when the key file is gone, so a new key never
  signs on top of it), naming `boss verify RUN --adopt-unsigned`. That command
  (`ledger.adopt_unsigned`) is the investor's decision: it makes every other check (chain, every
  `mac`, every investor signature), refuses to create a key over signed lines whose key is lost,
  then writes the anchor for the ledger as it is now; later reads and appends work as for any
  signed run. It changes nothing for a run that has an anchor. `boss report` then says
  `Ledger: N of M lines are unsigned: either older than line signing or rewritten without the
  key`. A signed line's `prev` covers the chained lines before it, and nothing covers lines older
  than the chain.
- `read_events(path, key_path)` with the project's key path (`RunPaths.events`, which every
  command, the loop and the pipeline use) refuses the ledger with `LedgerUnverifiedError` (a
  `LedgerCorruptError`) naming the first line when an investor or `audited` event does not verify. When the key
  exists, an unsigned investor event is accepted only on a line without `prev` (older than the
  chain); a signed one is refused when the key is missing. With no key file, nothing can be
  verified and an unsigned event is accepted as it always was. The readers that act on an investor
  event (`rulings.ruled`, `budget.is_top_up`, `state.run_state`, the round-funding check, the
  pipeline's `_settled`, `require_approval`) only ever see events that passed this.
  `LedgerWriter` runs the same check when it opens, so it never appends to a ledger the key does
  not vouch for.
- Anchor. After every append, once the project has a key, `LedgerWriter` replaces (atomically:
  temporary file, `fsync`, rename, `fsync` of the folder) `<project>/.boss/anchors/<run id>`, a JSON
  object `{"lines": N, "last": "<SHA-256 of line N>", "mac": "<HMAC with the investor key over the
  run id, N and that hash>"}`. A reader that passes the key path refuses a ledger with fewer than
  `lines` lines (naming how many were dropped), whose line `lines` is not the recorded one (an edit
  of the last line), or whose anchor does not verify. Lines past `lines` must be signed like any
  other; the anchor is written after the line, so a crash between the two, or a reader racing the
  writer, sees one, and only such a line, never anchored, can be cut unseen. A missing anchor is
  refused when the ledger holds a signed line or a `v2:` signed event (it was written by code that
  anchors, so the file was deleted), and when it holds an unsigned line until the investor adopts
  the run (above); only an empty ledger needs none. An anchor with the key missing is refused.
- The benchmark tools (`bench.kpi`, `bench.replay`, `bench.run`) read a firm cell's
  `.boss/runs/<id>/ledger.jsonl` through `RunPaths`, so with that cell's key: a keyless append is
  refused, not counted. The single arm's `ledger.jsonl` has no project and no key, and raw results
  whose `.boss/investor.key` was not kept are read unchecked; nothing in them is vouched for.
- Keys are sorted, except `mac`, which is always last. Timestamps are UTC ISO 8601.
- `state.py`'s docstring lists the `data` contract for thirteen event types. This file is the
  complete list; the docstring is a subset of it, and the test checks that.

## Top-level fields

| Field | Type | Meaning |
|---|---|---|
| `v` | int | Always 1. The ledger format version. |
| `run` | str | The run id, for example `20260930T101500Z-3fa9c1`. Never empty. |
| `round` | int | 0 for events before any round (the boss's call, the first approval, a rejection, `started`); 1 and up for the round the event belongs to. Money is summed per round, across every actor. |
| `actor` | str | Who wrote it: `boss`, `gate`, `rule`, `investor`, `worker:<name>` such as `worker:w1`, or `role:<name>` such as `role:critic` (lower case letters and `_`, starting with a letter). Any other value is refused. |
| `event` | str | One of the event types below. |
| `cost_micros` | int or null | Estimated cost in millionths of a dollar. `null` means unknown, which is never the same as 0. Default 0. |
| `tokens_in` | int | Input tokens, cache creation included. Default 0. |
| `tokens_out` | int | Output tokens. Default 0. |
| `tokens_cached` | int | Cache-read tokens. Default 0. |
| `billing` | str | `api`, `subscription` or `unknown`. `unknown` unless the event is a spend. |
| `data` | object | The keys below, by event type. |
| `ts` | str | When the event was written. |
| `prev` | str | The chain link: SHA-256 hex of the previous line's bytes, or 64 zeros on a file's first line. Set by `LedgerWriter` (it overwrites any value on the event), so it is on every line the code writes now. Absent from lines written before the chain; once one line has it, every later line must. |

- Counts and costs are non-negative integers. A bool is refused.
- Costs are the CLI's client-side estimates, not a bill.
- Only `boss_call`, `role_call` and `slice_end` carry a cost or tokens. `error` carries a cost of
  `null`.

## Events

Types are listed in the order of `EventType`. "Type" cells use `str`, `int`, `float`, `bool`,
`list`, `object` and `null`. A key is present in every event of its type unless the meaning says
otherwise.

### `boss_call`

- Actor: `boss`
- Round: 0
- Written by `cli.py` after the boss's drafting call, and by `audit.py` after the audit's, whether
  the call worked, failed, timed out or returned a draft that does not validate. It is the only
  event that comes from a model call by the boss.
- Cost and tokens: the call's usage. `cost_micros` is `null` if the call did not report one.

| Key | Type | Meaning |
|---|---|---|
| `purpose` | str | `term_sheet` for `boss fund`, `audit_checks` for `boss audit plan`. |
| `model` | str | The boss model, from `--boss-model`. |
| `thinking_tokens` | int or null | The thinking budget from `--boss-thinking`; `null` means the CLI's own default. |
| `outcome` | str | How the call ended: an outcome name such as `completed`, `timeout` or `crashed`. `completed` is also used for a paid call whose draft was unusable or invalid. |
| `prompt` | str | Only with `--spec`: `term_sheet_v3.md`, the prompt that asks for rule citations. |
| `rules` | int | Only with `--spec`: how many scored rules of the idea the boss was given. |

Example:

```json
{"actor": "boss", "billing": "subscription", "cost_micros": 4000, "data": {"model": "haiku", "outcome": "completed", "purpose": "term_sheet", "thinking_tokens": null}, "event": "boss_call", "round": 0, "run": "20260930T110134Z-365351", "tokens_cached": 0, "tokens_in": 10, "tokens_out": 5, "ts": "2026-09-30T11:01:35.110818+00:00", "v": 1}
```

### `role_call`

- Actor: `role:<name>`; one of `role:product_manager`, `role:user_agent`, `role:system_designer`, `role:tester`, `role:check_auditor`, `role:spec_mapper`, `role:consultant`, `role:critic`, `role:demo_writer`, `role:judge`, `role:examiner`
- Two writers, both building the cost, tokens, billing and first keys with `ledger_fields` from
  `roles/base.py`, which books the spend whether the call worked or not:
  - `Pipeline._book` in `pipeline.py`, for every call a role chosen with `--roles` makes, whether
    it worked, failed or was refused before it was made. Round 0, so the call is outside every
    round's budget and outside the run's spend ceiling, like `boss_call`. It adds `result` and
    `detail`.
  - `run_examiner` in `roles/examiner.py`, for the examiner. Round 1, before the investor
    approves, so the call counts in that round's spend and against its budget; it is skipped
    (cost 0, outcome `skipped`) when round 1 could not then fund a worker slice. It adds
    `requested`, `kept` and `problems`. `boss fund --held-out N` calls it through
    `Pipeline.examine`.
- `boss report` reads these events for its Roles section.
- Cost and tokens: the call's usage. `cost_micros` is `null` if the call did not report one, and 0
  for a call that was not made (`outcome` `not_called` or `skipped`). Billing is `api` or
  `subscription`. The report's spend line for the actor comes from these events.

| Key | Type | Meaning |
|---|---|---|
| `role` | str | The role's name, the part of the actor after `role:`. |
| `model` | str | The model the call used. |
| `prompt` | str | The prompt file the role runs under. |
| `skills` | list | The skill ids appended to that prompt, in order. Empty if none. |
| `outcome` | str | How the call ended: an outcome name such as `completed`, `api_error`, `timeout` or `crashed`; `not_called` when the pipeline refused it before any call (an unusable request, for example a file that already exists); `skipped` when the examiner was not called because round 1 could not then fund a worker slice. `completed` is also used for a paid call whose output failed the role's gate. `completed` is also used for a paid call whose output failed the role's gate. |
| `result` | str | What became of the output: `ok` (used), `failed` (the call failed or its output failed the gate; nothing was used) or `unused` (a good output thrown away because a later stage of the staged draft failed). |
| `detail` | str | One line, made safe to show. The reason for a failure or an `unused` result; for `ok`, a short count such as `1 verified, 0 rejected`. |
| `check` | str | The disputed check's id. Only on a consultant's call. |
| `verified` | int | Findings the gate confirmed. Only on a critic's call that worked. |
| `rejected` | int | Findings that were malformed, not reproduced or not grounded. Only on a critic's call that worked. |
| `cycle` | int | Which review this was, from 1. Only on a critic's call that worked. |
| `rubric` | str | The rubric id, `stories` or `usage`. Only on a judge's call. |
| `calibrated` | bool | Whether a calibration covered the judge. Only on a judge call that worked. |
| `requested` | int | The examiner's events only: how many held-out checks were asked for (`FirmConfig.held_out`). |
| `kept` | int | The examiner's events only: how many passed its gate and were stored in `held_out/`. 0 means the run goes on without held-out checks, and the report says so. |
| `problems` | list | The examiner's events only: why nothing was kept, one line each, at most 10 lines of 300 characters. Empty when checks were kept. A refused output is saved whole in the run folder as `examiner_refused.json`. |

`requested`, `kept` and `problems` are on the examiner's events only; `result` and `detail` on
the pipeline's only.

`pipeline.py` counts these events to decide what a resumed run still owes: one critic call per
review cycle (a cycle with verified findings counts once the investor's answer follows it: an
amendment's `approved` event, or a `ruled` event with ruling `declined`), one demo call per build of the product (after the last `slice_end`), and one judge
call per rubric and build.

Example, a critic's call written by a run with every role:

```json
{"actor": "role:critic", "billing": "subscription", "cost_micros": 4000, "data": {"cycle": 1, "detail": "1 verified, 0 rejected", "model": "haiku", "outcome": "completed", "prompt": "critic_v1.md", "rejected": 0, "result": "ok", "role": "critic", "skills": ["critic/tracing-each-stated-rule-through-the-code", "critic/writing-a-minimal-failing-test", "critic/boundaries-the-idea-names"], "verified": 1}, "event": "role_call", "round": 0, "run": "20260930T184138Z-128493", "tokens_cached": 0, "tokens_in": 10, "tokens_out": 5, "ts": "2026-09-30T18:41:40.854167+00:00", "v": 1}
```

### `started`

- Actor: `boss` (the loop)
- Round: 0
- Written once, before the first round, holding the configuration the run was started with.
  `run_firm` writes it. When roles were chosen `pipeline.py` writes it first (`record_start`) with
  the same `config` and adds `roles`, and `run_firm` then writes none. `boss resume` reads it back,
  so a run continues with its own settings and roles, not the defaults. A run without this event
  never hired anyone and cannot be resumed.

| Key | Type | Meaning |
|---|---|---|
| `config` | object | The run's `FirmConfig`. Keys below. |
| `roles` | object | The roles the investor chose; only when `--roles` named some. Keys `names` (list: the sorted role names), `model` (str: the model every role call uses, from `--boss-model`) and `thinking_tokens` (int or null: `--boss-thinking`). |

Config keys:

| Key | Type | Meaning |
|---|---|---|
| `model` | str | The worker model. |
| `slice_micros` | int | The default slice cap. |
| `reserve_micros` | int | Held back from every cap. |
| `firing` | bool | `false` with `--no-firing`. |
| `policy.stall_slices` | int | Counted slices in a row with no new passing check before firing. |
| `policy.max_slices` | int | Counted slices before firing. |
| `limits.max_slices` | int | Slices started in the whole run. |
| `limits.max_workers` | int | Workers hired in the whole run. |
| `limits.max_seconds` | float or null | Wall clock of one invocation, in seconds; `null` means no limit. |
| `limits.max_workspace_bytes` | int | Most bytes a worker's folder or the assembled product may hold. The gate copies the folder for every check, so a larger one is not gated. |
| `parallel` | int | Tasks worked on at once (`--parallel`). Each task still has one worker at a time. |
| `profile` | str or null | The worker profile: skills added to the builder prompt. `null` is the bare prompt. |
| `held_out` | int | How many held-out checks the examiner was asked for, 0 to 8; 0 (the default) is off. Set by `boss fund --held-out N`. A run started before the key existed loads with 0. |
| `thinking_tokens` | int or null | The thinking budget of every worker slice (`MAX_THINKING_TOKENS`); 0 turns thinking off, `null` is the CLI's own default. Set by `boss fund --worker-thinking N`. A run started before the key existed loads with `null`. |
| `dispatch` | bool | `true` when the run uses `--dispatch rules`. Written only then; a run without it has neither this key nor `max_tier`. |
| `max_tier` | str | The dearest tier dispatch may use (`--max-tier`, default `sonnet`). Written only with `dispatch`. |
| `plan_pause_at` | float or null | A fraction of a plan window. The run pauses once a slice reports a window this full and work is left; `null` turns the pause off. `boss fund` has no option for it, so it is 0.95. |

Example, a run without roles:

```json
{"actor": "boss", "billing": "unknown", "cost_micros": 0, "data": {"config": {"firing": true, "held_out": 0, "limits": {"max_seconds": null, "max_slices": 60, "max_workers": 16, "max_workspace_bytes": 209715200}, "model": "haiku", "parallel": 1, "plan_pause_at": 0.95, "policy": {"max_slices": 6, "stall_slices": 2}, "profile": null, "reserve_micros": 100000, "slice_micros": 100000, "thinking_tokens": null}}, "event": "started", "round": 0, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T17:20:48.680074+00:00", "v": 1}
```

The same, in a run that named roles:

```json
{"actor": "boss", "billing": "unknown", "cost_micros": 0, "data": {"config": {"firing": true, "limits": {"max_seconds": null, "max_slices": 60, "max_workers": 16, "max_workspace_bytes": 209715200}, "model": "haiku", "parallel": 1, "plan_pause_at": 0.95, "policy": {"max_slices": 6, "stall_slices": 2}, "profile": null, "reserve_micros": 100000, "slice_micros": 100000, "thinking_tokens": null}, "roles": {"model": "haiku", "names": ["check_auditor", "consultant", "critic", "demo_writer", "judge", "product_manager", "system_designer", "tester", "user_agent"], "thinking_tokens": null}}, "event": "started", "round": 0, "run": "20260930T184138Z-128493", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T18:41:39.880351+00:00", "v": 1}
```

### `resumed`

- Actor: `investor`
- Round: the round of the last event in the ledger
- Written by `cli.py` when `boss resume` finds the run stopped. It lifts the stop: a stop holds
  until a later `resumed`, and a later stop holds again. Nothing else writes it. Its only key is
  the signature: an unsigned or forged one is refused when the ledger is read, so it cannot lift a
  stop.
- Lifting a stop does not skip a check: the approval, the budget and every hard limit are verified
  again before the next slice.

| Key | Type | Meaning |
|---|---|---|
| `sig` | str | `v2:` and the HMAC-SHA-256 (hex) of the line with the project's investor key (see Signatures above). Present when the run is in a project (`<project>/.boss/runs/<id>`); absent otherwise and from lines written before signing. |

Example:

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"sig": "v2:02fd5ae8cb08ff5f593615717f871b34d6d8aff11a6c3dfda28fe59cec9e7e98"}, "event": "resumed", "prev": "f05dd6f39d389e5a81a1273664ea0392abaeae922862036e01b844bb8e129b47", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-10-02T11:53:40.133254+00:00", "v": 1}
```

### `hired`

- Actor: `boss` (the loop)
- Round: the current round
- Written by `firm.py` when a task needs a worker: its first, or a replacement.
- The profile is recorded by name, not its skills: the prompt file is the builder prompt either way.
- `hired` carries no session id. Ledgers written before the `session` key moved to `slice_start`
  had one here; a resume falls back to it.

| Key | Type | Meaning |
|---|---|---|
| `worker` | str | The worker's name: `w1`, `w2`, ... in hiring order across the run. |
| `task` | str | The task id. |
| `model` | str | The worker model: the run's `--model`, or, under `--dispatch rules`, the tier the term sheet gave this worker (a step up included). A resume runs the worker on this one, not on the config's. |
| `prompt` | str | The builder prompt file the worker runs under. |
| `profile` | str or null | The worker profile in force (`started`'s `config.profile`, or the task's `dispatch.profile`); `null` for none. |
| `dispatch` | object | Why this worker is on this model. Only under `--dispatch rules`. Keys below. |

Dispatch keys:

| Key | Type | Meaning |
|---|---|---|
| `tier` | str | `haiku`, `sonnet` or `opus`; the same as `model`. |
| `effort` | str | `off` (thinking 0), `default` (the run's own) or `high` (`dispatch.HIGH_THINKING_TOKENS`). |
| `why` | str | `term sheet` for a task's first worker; for a replacement, `predecessor fired: ` and the gate's reason (`no progress` or `slice limit`) and its stalled slices. |
| `from_tier` | str | The fired predecessor's tier. Only on a replacement. Equal to `tier` when the replacement was not stepped up in tier. |
| `refused` | str | Why the step the task allowed was not taken (the round could not fund the next tier, or stepping up is off for the task). Only on a replacement. |

Example:

```json
{"actor": "boss", "billing": "unknown", "cost_micros": 0, "data": {"model": "haiku", "profile": null, "prompt": "builder_v3.md", "task": "t1", "worker": "w1"}, "event": "hired", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T17:20:48.680759+00:00", "v": 1}
```

A replacement, stepped up one tier by `--dispatch rules`:

```json
{"actor": "boss", "billing": "unknown", "cost_micros": 0, "data": {"dispatch": {"effort": "default", "from_tier": "haiku", "tier": "sonnet", "why": "predecessor fired: no progress, 2 stalled slices"}, "model": "sonnet", "profile": null, "prompt": "builder_v4.md", "task": "t1", "worker": "w2"}, "event": "hired", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-10-04T11:10:11.003149+00:00", "v": 1}
```

### `slice_start`

- Actor: `worker:<name>`
- Round: the current round
- Written by `firm.py` after the cap is fixed and the approval verified, before the CLI starts.
  The benchmark's single arm (`bench/run.py`, actor `worker:solo`) writes it with `slice`,
  `cap_micros` and `session` only, and no `task`.
- A `slice_start` with no `slice_end` after it (the run was killed) is charged to its round at its
  `cap_micros`. The same slice number started again means the first was lost, and is charged too.

| Key | Type | Meaning |
|---|---|---|
| `slice` | int | The worker's slice number, from 1. Infrastructure retries count. |
| `task` | str | The task id. |
| `cap_micros` | int | The slice's spend cap in micro-dollars. A target: one response can run past it. |
| `session` | str | The UUID of the CLI session this attempt uses. A new one for every attempt that is not a proven resume (a session is resumed only after a slice in it got past infrastructure); the CLI refuses an id that is already in use. |
| `context_sha256` | str | SHA-256 (hex) of the worker's system prompt, a NUL byte, then its user prompt: the bytes of `logs/<worker>-s<slice>.prompt.txt`, which `boss report` rehashes. Only under `--dispatch rules`. |
| `context_chars` | int | Characters in the user prompt, at most `context.MAX_BUNDLE_CHARS` (30,000). Only under `--dispatch rules`. |
| `context_parts` | object | Characters of each part of the user prompt that is in it: `task`, `interfaces`, `handoff`, `notes` for a first slice; `gate` for a resumed one. Only under `--dispatch rules`. |

Example:

```json
{"actor": "worker:w1", "billing": "unknown", "cost_micros": 0, "data": {"cap_micros": 100000, "session": "9a5c8b55-eb42-490d-a75b-9d9fad2c7eba", "slice": 1, "task": "t1"}, "event": "slice_start", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:25.685789+00:00", "v": 1}
```

The same under `--dispatch rules`, the first slice of a replacement:

```json
{"actor": "worker:w2", "billing": "unknown", "cost_micros": 0, "data": {"cap_micros": 100000, "context_chars": 2867, "context_parts": {"handoff": 2292, "task": 573}, "context_sha256": "994021c28d0cf77cdf645ff4953c476e0ea488d914dc8ee3b8b48b944e1d8856", "session": "0a2f333c-1e08-4941-8d2d-d61c512fbcd5", "slice": 1, "task": "t1"}, "event": "slice_start", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-10-04T11:10:12.335965+00:00", "v": 1}
```

### `slice_end`

- Actor: `worker:<name>`
- Round: the current round
- Written by `firm.py` when the CLI process ends, whatever the outcome.
- Cost and tokens: this slice's own spend, the difference between the CLI's cumulative session
  totals (never below zero); cost is `null` if unknown. A slice that got no totals (it was
  killed, or the CLI zeroed them) books the input-side tokens of its own messages and no output
  tokens; the next slice's difference includes its real spend. Billing is `api` or
  `subscription`.
- The benchmark's single arm writes it with `slice`, `outcome` and `status` only. `status` there
  is cleaned the same way.

| Key | Type | Meaning |
|---|---|---|
| `slice` | int | The slice number. |
| `task` | str | The task id. |
| `outcome` | str | How the run ended: `completed`, `capped`, `max_turns`, `refusal`, `timeout`, `crashed`, `login`, `rate_limited`, `usage_limit`, `api_error` or `session_lost` (the CLI no longer had the session to resume; the next attempt starts a new one). |
| `status` | object or null | The worker's own report, cleaned: `status` (`done`, `continuing`, `blocked` or `none`) and `reason` (secrets masked, control characters shown as escapes, at most 500 characters). `null` if it gave none. A note, never a pass. |
| `session_total_micros` | int or null | The CLI's cumulative cost for the session after this slice; `null` if unknown. |
| `session_total_tokens` | list or null | The CLI's cumulative tokens for the session after this slice, as `[in, out, cached]`; `null` if the slice got no totals. The next slice of the session is booked against it. Ledgers from before this key carry none. |
| `exit_code` | int or null | The CLI process's exit code. |
| `denials` | int | How many tool calls the CLI refused. |
| `denied_tools` | list | The distinct names of the refused tools, sorted. |
| `denial_reasons` | list | One `{tool, reason}` object per distinct refused call the CLI gave a message for, at most 5: `reason` is the first sentence of that message, secrets masked and at most 160 characters. The next brief quotes them. Empty when the CLI gave no message. |
| `log` | str | Path of the worker's raw stream log. |
| `model_id` | str or null | The model the CLI's `system/init` event says it started with (for example `claude-haiku-4-5-20251001`); `null` when no init arrived. Only under `--dispatch rules`, where a launched tier that does not appear in it stops the run (T69). |

Example:

```json
{"actor": "worker:w1", "billing": "subscription", "cost_micros": 10000, "data": {"denial_reasons": [], "denials": 1, "denied_tools": ["Write"], "exit_code": 0, "log": ".boss/runs/r1/logs/w1.jsonl", "outcome": "completed", "session_total_micros": 10000, "session_total_tokens": [10, 5, 0], "slice": 1, "status": {"reason": "scripted continuing", "status": "continuing"}, "task": "t1"}, "event": "slice_end", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 10, "tokens_out": 5, "ts": "2026-09-30T11:01:25.686130+00:00", "v": 1}
```

The same under `--dispatch rules`:

```json
{"actor": "worker:w2", "billing": "subscription", "cost_micros": 10000, "data": {"denial_reasons": [], "denials": 0, "denied_tools": [], "exit_code": 0, "log": ".boss/runs/r1/logs/w2.jsonl", "model_id": "claude-sonnet-4-5-20251001", "outcome": "completed", "session_total_micros": 10000, "session_total_tokens": null, "slice": 1, "status": {"reason": "scripted done", "status": "done"}, "task": "t1"}, "event": "slice_end", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 10, "tokens_out": 5, "ts": "2026-10-04T11:10:12.336468+00:00", "v": 1}
```

### `check_result`

- Actor: `gate`
- Round: the current round
- Written by `firm.py` after a slice whose outcome is not an infrastructure failure: one event per
  check of the worker's task that still counts (a check the investor dropped is no longer run).
  Later results supersede earlier ones.
- If the run was killed after a slice ended and before its results were written, the loop gates
  that slice on resume and writes them then.
- The gate also runs to build the next brief; those runs are not recorded.
- Three scopes. A result of a worker's slice carries `worker` and `slice`. A result with
  `scope` `product` is the verdict on the assembled `product/` folder, where the tasks' files
  meet. `firm.py` writes it whenever `run_firm` ends after at least one slice (a finished run, a
  stop or a pause), for each required check that has no product verdict after the last
  `slice_end`; running a finished run again adds nothing. It is not written when the product
  folder is over the size limit or the approval no longer matches. It carries no `worker` and no
  `slice`, and its round is that of the last `slice_end`. The state rebuild ignores it (it reads
  only results with a `worker` and a `slice`); the report lets it supersede the earlier result of
  the same check, so the report shows the product's figure.
- A result with `scope` `held_out` is a held-out check (ids `h01`..) graded on the assembled
  product, which no worker ever saw. It is written in the same place and on the same terms as the
  product verdict, for each held-out check with no held-out result after the last `slice_end`, so a
  run cut short between two of them finishes the grading on resume. It carries no `task`, no
  `worker` and no `slice`. The state rebuild skips every result with this scope, so no firing,
  dispute or unlock decision rests on it. The report shows these results apart from the visible
  checks, and a run counts as passed only when they pass too.

| Key | Type | Meaning |
|---|---|---|
| `check` | str | The check id, such as `c01`. |
| `task` | str | The task id. Absent when `scope` is `held_out`. |
| `status` | str | `passed`, `failed` or `timeout`. The only source of "passed". |
| `detail` | str | Why: the pytest exit code, or the count of passed tests. |
| `worker` | str | The worker whose files were checked. Absent when `scope` is `product`. |
| `slice` | int | The slice after which the gate ran. Absent when `scope` is `product`. |
| `scope` | str | `product` for a visible check's verdict on the assembled product, `held_out` for a held-out check's. Absent on a worker's result. |
| `sandboxed` | bool | The gate ran this check inside an OS sandbox. `false` also means the sandbox was off or none worked (T39). Absent in ledgers written before it was recorded; the report says "not recorded" for those. |

Examples:

```json
{"actor": "gate", "billing": "unknown", "cost_micros": 0, "data": {"check": "c01", "detail": "pytest exited 1", "sandboxed": true, "slice": 1, "status": "failed", "task": "t1", "worker": "w1"}, "event": "check_result", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:26.170363+00:00", "v": 1}
```

```json
{"actor": "gate", "billing": "unknown", "cost_micros": 0, "data": {"check": "c01", "detail": "1 passed", "sandboxed": true, "scope": "product", "status": "passed", "task": "t1"}, "event": "check_result", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T17:20:50.832951+00:00", "v": 1}
```

```json
{"actor": "gate", "billing": "unknown", "cost_micros": 0, "data": {"check": "h01", "detail": "1 passed", "sandboxed": true, "scope": "held_out", "status": "passed"}, "event": "check_result", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T18:17:34.333908+00:00", "v": 1}
```

### `blocked`

- Actor: `worker:<name>`
- Round: the current round
- Written by `firm.py` when the rule escalates a worker that reported `blocked` without a refused
  tool call, or whose run ended in a model refusal. The investor is then asked: `ruled`
  (`unblocked`) or `abandoned` follows.

| Key | Type | Meaning |
|---|---|---|
| `task` | str | The task id. |
| `reason` | str or null | The worker's own reason, cleaned; `null` if it gave no report. |

Example:

```json
{"actor": "worker:w1", "billing": "unknown", "cost_micros": 0, "data": {"reason": "scripted blocked", "task": "t1"}, "event": "blocked", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:29.626100+00:00", "v": 1}
```

### `ruled`

- Actor: `investor`
- Round: the current round; 0 for `declined`
- Written by `firm.py` after the investor answers a question the worker could not settle, and by
  `pipeline.py` for `declined`. Only an `investor` event counts as a ruling. The term sheet and its
  approval are not touched: a dropped check is skipped because the ledger says so.
- Four rulings:
  - `dropped`: the check is no longer run, counted or required. Unlock thresholds are capped at
    what is left.
  - `kept`: the dispute is settled and the worker is told to satisfy the check.
  - `unblocked`: a blocked worker is funded again; the note is in its next brief.
  - `declined`: round 0, written by `pipeline.py` when the critic's findings end with no fix round:
    the investor said no (or input ended), or none was offered (`--review-cycles 0`, the run ended
    early, no finding could be proposed). It is how a resume tells that from a Ctrl-C at the
    question, which writes nothing and so leaves the findings to be offered again.
- Anything but a clear answer (or the end of input) writes `abandoned` instead.

| Key | Type | Meaning |
|---|---|---|
| `task` | str | The task id. Absent for `declined`. |
| `worker` | str | The worker that raised the dispute or the block. Absent for `declined`. |
| `ruling` | str | `dropped`, `kept`, `unblocked` or `declined`. |
| `check` | str | The check ruled on. Present for `dropped` and `kept` only. |
| `note` | str | The investor's note, on one line, secrets masked, at most 1000 characters. Present for `unblocked` only. |
| `sig` | str | `v2:` and the HMAC-SHA-256 (hex) of the line with the project's investor key (see Signatures above). Present when the run is in a project (`<project>/.boss/runs/<id>`); absent otherwise and from lines written before signing. |

Examples:

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"check": "c01", "ruling": "dropped", "task": "t1", "worker": "w1"}, "event": "ruled", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:53:37.767131+00:00", "v": 1}
```

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"note": "use the standard library", "ruling": "unblocked", "task": "t1", "worker": "w1"}, "event": "ruled", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:53:36.246239+00:00", "v": 1}
```

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"ruling": "declined", "sig": "v2:583ded96c7a685332ecf92bc442d56c2a69824e475803ac896eb46bad9e15a7a"}, "event": "ruled", "prev": "615362e7cf3d7296fd55fe95617522e00d3774a098d0a3848838c4e693621d23", "round": 0, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-10-02T11:53:36.246239+00:00", "v": 1}
```

### `disputed`

- Actor: `worker:<name>`
- Round: the current round
- Written by `firm.py` when a worker's report names a check of its own task that fails now, that it
  has not disputed before and that the investor has not ruled `kept`. A dispute never counts as
  passing. It changes the rule's decision only when it is credible: every other check passes and
  at most half of the task's checks are disputed. Otherwise the worker is judged as if it had
  disputed nothing; the event stays on record. A dispute is about the check, not the worker: a
  worker hired later for the same task inherits the disputes the investor has not ruled on, in the
  rule's view and in its brief, and a question about one names the worker who raised it.

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
| `disputed` | list | Checks the worker disputes, or an earlier worker of its task disputed and nobody has ruled on, that still fail. |
| `spent_micros` | int | Known spend of the worker's slices. |
| `unknown_cost_slices` | int | Slices whose cost is unknown. |

Example:

```json
{"actor": "rule", "billing": "unknown", "cost_micros": 0, "data": {"evidence": {"best": [], "counted_slices": 2, "disputed": ["c01"], "missing": ["c01", "c02"], "passing": [], "spent_micros": 20000, "stalled_slices": 2, "unknown_cost_slices": 0}, "last_reason": "scripted continuing", "reason": "no progress", "task": "t1", "worker": "w1"}, "event": "fired", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:27.135282+00:00", "v": 1}
```

### `abandoned`

- Actor: `boss` (the loop)
- Round: the current round
- Written by `firm.py` when a task will get no more work in this run: two workers used, or the
  investor set it aside (or gave no clear answer). Nothing later reopens it, a resume included.

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
- Written by `firm.py` when a round runs to its end: every task done or set aside, or the round
  cannot fund another slice. A pause or a stop leaves the round open, so a resume continues it.
- A round closed with `unlocked` false stays locked: a resume does not fund the next round. Only
  an investor `topped_up` event for that round, recorded after this one, reopens it.

| Key | Type | Meaning |
|---|---|---|
| `passed` | int | Checks passing across all tasks, taking each task's best worker. |
| `total` | int | Checks in the term sheet, less the ones the investor dropped. |
| `unlocked` | bool | Whether `passed` reaches this round's unlock threshold. |

Example:

```json
{"actor": "boss", "billing": "unknown", "cost_micros": 0, "data": {"passed": 1, "total": 2, "unlocked": true}, "event": "round_closed", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:28.107862+00:00", "v": 1}
```

### `approved`

- Actor: `investor`
- Three forms, all by the investor:
  - Round 0, by `approval.py` when the investor approves the term sheet. Carries `hashes`,
    `held_out_hashes` when the run has held-out checks, `route` when the run uses
    `--dispatch rules`, `rules.json` among its `hashes` and a `spec` coverage summary (rule and
    anchor counts, the uncovered and waived rule ids, the digest of the rule list) when the run
    was started with `--spec`. The summary is inside the signed data.
  - Round N, by `firm.py` when the investor funds a later round. Carries `round`.
  - An amendment: the investor approves more checks and a round added to an approved term sheet.
    It carries `hashes` of the amended term sheet and its check files, `round` (the round the
    amendment added) and `added_checks`. `pipeline.py` writes it, only after the investor says yes
    to the critic's fix round, and before it rewrites `term_sheet.json`. `firm.py` reads it: a
    worker is told about an added check of its own task, and only an `investor` event counts.
- A missing `round` counts as round 1 when the state is rebuilt, so the first approval opens
  round 1.
- `require_approval` accepts only an `approved` event by `investor` whose `hashes` equal the hashes
  of the term sheet and check files now on disk, and whose `held_out_hashes` (absent means none)
  equal the hashes of every file now in the run's `held_out/` folder. A held-out file edited, added
  or removed after approval, or a `held_out/` folder that appears after an approval that recorded
  none, voids the approval exactly as an edited check does. An amendment must carry the current
  `held_out_hashes` as well as its `hashes`, or it does not match. After an amendment, the
  amendment's hashes are the ones that match.
- Signature. The investor's key is 32 random bytes in `<project>/.boss/investor.key` (hex, mode
  0600, created when a ledger writer of the project first opens, inside the project's ignored `.boss/`).
  `LedgerWriter` signs every investor event with it, the three forms of `approved` included (see
  Signatures above), and `require_approval` verifies with it and never prints it. When the key file
  exists, a signed approval counts only if its `sig` verifies (an edited approval, one moved to
  another run or place, or one signed with another key does not), and an unsigned approval counts
  only if its line has no `prev`, that is, it was written before the chain: every line the code
  writes now is chained and signed. When the key file is missing, a signed approval cannot be
  verified and is refused, and an unsigned one is accepted (as it always was). A key file that is
  unreadable, readable by others, a symlink or not 32 bytes of hex stops the check with an error
  that does not quote it. Losing the key voids the signed events of the project's runs.

| Key | Type | Meaning |
|---|---|---|
| `hashes` | object | SHA-256 hex digests: `term_sheet` for the term sheet without its approval flag, and one entry per check file, named by the file, and `rules.json` for a run started with `--spec`. Present in the first form, and in an amendment. |
| `held_out_hashes` | object | SHA-256 hex digests of every file in the run's `held_out/` folder, named by the file (`manifest.json` and one `test_h01.py` per held-out check). Present only when the run has held-out checks. |
| `route` | str | `one_agent` or `firm`: the route the investor approved (`dispatch.route_of` chose it from the sheet, or the investor edited it). Only in the first form, and only when the run uses `--dispatch rules`. The term sheet carries it too, and `hashes` covers that. |
| `spec` | object | Only with `--spec`, in the first form: `rules_sha256` (digest of the rule list), `rules` (scored rules), `anchored`, `unanchored`, `anchor_missing`, `unscored_missing` (counts), `uncovered` and `waived` (rule ids) and `waived_reasons` (id to the boss's one-line reason). Inside the signed data. |
| `round` | int | The round funded. Present in the second form, and in an amendment. |
| `added_checks` | list | The ids of the checks an amendment added, in order. Only in an amendment. |
| `sig` | str | On every form. `v2:` and the HMAC-SHA-256 (hex) of the line with the project's investor key (see Signatures above). Present when the run is in a project (`<project>/.boss/runs/<id>`). Approvals written by the first version of signing carry a bare hex `sig` over their run, round and data; approvals older than signing have none. |

Examples:

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"hashes": {"term_sheet": "c3d23ee4f53f84a5ad36b910b0e4fce13cf4db1c9bcc148db5ef99b939a52c2d", "test_c01.py": "46dcc9df463d18fec190640e9731fb76fd54990602d51e6f562260ee40137215", "test_c02.py": "ef8fdb7658a4589dad9a7e41b8b287e591fb402c96b8b5b3bc1438cbe7fe1173"}}, "event": "approved", "round": 0, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:25.684405+00:00", "v": 1}
```

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"round": 2}, "event": "approved", "round": 2, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:28.108273+00:00", "v": 1}
```

The first two examples are unsigned and unchained: the first is older than signing, the second
was written outside a project (a test's run folder). In a project every investor event carries
`prev` and `sig`, as in the next two (the key that signed them was thrown away). A signed approval,
as `boss fund` writes it:

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"hashes": {"term_sheet": "aa0ce180f53592efa47a651dc9e0b62d750b5817cec5f2dce48f585f158c7f5b", "test_c01.py": "46dcc9df463d18fec190640e9731fb76fd54990602d51e6f562260ee40137215", "test_c02.py": "ef8fdb7658a4589dad9a7e41b8b287e591fb402c96b8b5b3bc1438cbe7fe1173"}, "sig": "v2:641b282b994350128b7ed8524b68500a73dad5f1e5eee113e5cae602a6949211"}, "event": "approved", "prev": "b87dac9056fcb0aa1702b8b8a51f98408b164689f7f17e3f753bf1feea4e03ff", "round": 0, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-10-02T20:52:27.361484+00:00", "v": 1}
```

An amendment (signed like the first form, in round 2):

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"added_checks": ["c03"], "hashes": {"term_sheet": "3358c4b8c732606c083e7f794881519b229ba89c5d388c2be6f7e79448cae768", "test_c01.py": "1d8375400c8f62ba12608933211da7dade2459fb89df181c1f23150d29b89b56", "test_c02.py": "8be209cefbc72a3ceb2b34f55206827c0a0efd55aa9e6d45b66b1fe3fba83f63", "test_c03.py": "65ba46c76ea3d12622b3ae82f9715b4baf58c84be286d8cb03645894e00ca6a1"}, "round": 2, "sig": "v2:adcb9a85d6fe9daf6134391aca9dc6e8c6c5c5388807e66f6120d1cbb073d7d2"}, "event": "approved", "prev": "0da687d01ba1bbfb554ea25d742c468035b9909c9471e81e6dfa307197b812e6", "round": 2, "run": "20260930T184138Z-128493", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T18:41:41.920211+00:00", "v": 1}
```

The first form of an approval under `--dispatch rules`:

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"hashes": {"term_sheet": "af46755ef33933fbd23a67c7c103ae22c005f6003649687a474b55bc00a4a0ff", "test_c01.py": "46dcc9df463d18fec190640e9731fb76fd54990602d51e6f562260ee40137215"}, "route": "one_agent", "sig": "v2:200390a2b3a67984b41409a39d86e414c986d067adb01bf11437798b74e0e6ef"}, "event": "approved", "round": 0, "run": "20261004T111014Z-298163", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-10-04T11:10:16.704558+00:00", "v": 1}
```

### `topped_up`

- Actor: `investor`
- Round: the round that gets the money
- Written by `cli.py` when `boss topup` adds money to a round. Only an `investor` event counts:
  `budget.round_budget` adds `micros` to the budget of the round of each such event, and
  `state.run_state` takes the round out of `locked_rounds` and `closed_rounds` when the event comes
  after the `round_closed` that locked it, so the loop funds that round again and writes another
  `round_closed` when it ends. The same event raises the run's spend ceiling. The same event from
  any other actor adds nothing and reopens nothing.
- `boss topup` writes it only for a round of the term sheet, and not for one that closed unlocked.

| Key | Type | Meaning |
|---|---|---|
| `micros` | int | Extra budget for the round, a positive integer. Anything else makes the budget code raise. |
| `sig` | str | `v2:` and the HMAC-SHA-256 (hex) of the line with the project's investor key (see Signatures above). Present when the run is in a project (`<project>/.boss/runs/<id>`); absent otherwise and from lines written before signing. |

Example, `boss topup --round 1 --amount 0.25` on a round that had run out of money:

```json
{"actor": "investor", "billing": "unknown", "cost_micros": 0, "data": {"micros": 250000, "sig": "v2:dfda8844d673948b2b77d479b4464dee1fb77733da6912a495f97c3388a47f63"}, "event": "topped_up", "prev": "4be3ea985fb0bd3310654b880a2858826e97e546af41463965caa7373a4f68b1", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-10-02T20:48:19.193786+00:00", "v": 1}
```

### `paused`

- Actor: `boss` (the loop)
- Round: the current round
- Written by `firm.py` in two cases. A slice ended because the plan's usage limit was reached
  (`reason` `plan usage limit reached`), or a slice reported a plan window at or over
  `config.plan_pause_at` while work is left (`reason` names the window and its percentage), so the
  next slice is not lost to the limit. The run ends; the round stays open and `boss resume`
  continues it.

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
- Written when the run ends on purpose. A stop holds until a `resumed` event; a later stop holds
  again. Writers:
  - `boss`, by `cli.py`: the boss's call failed or its draft was invalid (round 0).
  - `investor`, by `approval.py`: the term sheet was rejected (round 0).
  - `investor`, by `firm.py`: a later round was not funded.
  - `rule`, by `firm.py`: a hard run limit was reached, or the term sheet or a check no longer
    matches the approval, or a worker's folder is over the size limit (the gate would copy it for
    every check).
  - `boss`, by `firm.py`: the worker did not start isolated, or an infrastructure failure the
    loop will not retry (login lost, or attempts used up).

| Key | Type | Meaning |
|---|---|---|
| `reason` | str | Why the run stopped. |
| `fix` | str | A one-line next step. Present only when an infrastructure failure stopped the run. |
| `sig` | str | On the investor's stops only. `v2:` and the HMAC-SHA-256 (hex) of the line with the project's investor key (see Signatures above). Present when the run is in a project (`<project>/.boss/runs/<id>`); absent otherwise and from lines written before signing. |

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
  `system/init` shows the worker is not in the configuration that was launched, or when a hook
  event appears anywhere later in the stream. `stopped` follows.

| Key | Type | Meaning |
|---|---|---|
| `isolation` | str | The problems found, joined by `; `. Written for an isolation failure. |
| `model` | str | The launched tier and the model the CLI reported, when they differ (T69), or that it reported none. Written under `--dispatch rules` instead of `isolation`, after the slice's `slice_end`; `stopped` follows. |

Example:

```json
{"actor": "worker:w1", "billing": "unknown", "cost_micros": null, "data": {"isolation": "tools differ"}, "event": "error", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-09-30T11:01:34.025877+00:00", "v": 1}
```

A model that is not the one launched, under `--dispatch rules`:

```json
{"actor": "worker:w1", "billing": "unknown", "cost_micros": null, "data": {"model": "launched 'haiku', but the CLI ran 'claude-sonnet-4-5-20250929'"}, "event": "error", "round": 1, "run": "r1", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-10-04T11:10:14.869643+00:00", "v": 1}
```

### `audited`

- Actor: `gate`
- Round: 0. Cost: 0. It records a verdict on a change made outside this run; it is not a spend.
- Written by `audit_check.check` (`boss audit check`), once everything it verifies has held: the
  ledger, the signed approval, every check file, and that the head descends from the base. One run
  has one per audited head; a later one for the same head and agent replaces an earlier one in
  `boss audit report`.
- Signed like an investor event: `sig` is `v2:` and the HMAC-SHA-256 of the line with the audit
  store's key. A reader that passes the key path (`RunPaths.events`, which `check` and `report` use)
  refuses a ledger holding an `audited` line that does not verify, whoever the actor says it is.
  `ledger.audited` returns only the ones whose actor is `gate`.

| Key | Type | Meaning |
|---|---|---|
| `base` | str | The commit the checks were sealed against, as a full hash. |
| `head` | str | The commit that was audited, as a full hash. |
| `seal` | str | SHA-256 over the approved term sheet, every check file and every held-out file, as `boss audit plan` printed it. |
| `verdict` | str | `refuted`, `unrefuted`, `inconclusive` or `no_claim`. |
| `claim` | str | `done` or `none`: what the audited agent said about its own work, as `--claim` gave it. |
| `claim_mode` | str | `pre_registered` (at least one commit, every one dated after the seal) or `post_hoc`. The dates are the committer's own and can be forged. |
| `counted` | int | How many sealed checks failed on `base`: the ones a verdict rests on. |
| `failed` | list | The ids of the counted checks that failed on `head`. At most 50. |
| `blocked` | list | The ids of counted checks that could not be run on `head` (timeout, or a module that is not installed). At most 50. |
| `leaks` | list | Where the change quotes the sealed checks, as `<check id> test name` or `<check id> string literal`. At most 50. |
| `tests_deleted` | list | Test files of the base's `tests/` folder that `head` does not have. Not part of the verdict. At most 50. |
| `regressions` | list | Tests of the base that pass on the base and fail when run over `head`'s code. Not part of the verdict. At most 50. |
| `agent` | str or null | A label the investor gave the audited agent, if any. |
| `claim_text_sha256` | str or null | SHA-256 of the file given as `--claim-text`, if any. The text itself is not stored. |
| `sig` | str | `v2:` and the HMAC-SHA-256 (hex) of the line with the audit store's investor key (see Signatures above). |

Example, as `boss audit check` wrote it:

```json
{"actor": "gate", "billing": "unknown", "cost_micros": 0, "data": {"agent": null, "base": "450109a66507cb2312db91fceb657edcd4d879cf", "blocked": [], "claim": "done", "claim_mode": "pre_registered", "claim_text_sha256": null, "counted": 2, "failed": [], "head": "ac5fface67ba4175f03134261b26d1e3c1b55c54", "leaks": [], "regressions": [], "seal": "ed5a83020bc8e7c814acc2b64bf69be69db78fdb731235283f725efb8c6e24e2", "sig": "v2:11f3f5c7765a68856569245a2258e4c9a63fecd56ad831dc35c813371b91a782", "tests_deleted": [], "verdict": "unrefuted"}, "event": "audited", "prev": "08f885e9ad713d74176d4dc5b9dffb45510c7b440dae6ec7c2ece46984f894f8", "round": 0, "run": "20261004T033508Z-051c5a", "tokens_cached": 0, "tokens_in": 0, "tokens_out": 0, "ts": "2026-10-04T03:35:15.210999+00:00", "v": 1}
```
