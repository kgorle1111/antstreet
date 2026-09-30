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
| B03 | Run every check on `product/` after assembly and report that result | Only matters with several tasks | building |
| B04 | Parallel workers for tasks that own disjoint paths | Sequential was enough for one task | open |
| B05 | One-line status after every slice (spend against budget, checks passing, worker) | Not needed for correctness | open |
| B06 | `boss topup`: add money to a round; a locked round can be reopened by the investor | Top-up events are read by `budget.py`, nothing writes them | open |
| B07 | Pause before a plan limit is hit (plan pressure), not only after | `retry.plan_pressure` exists, the loop does not call it | open |
| B08 | A replacement worker inherits its predecessor's disputes | Disputes are per worker today | open |
| B09 | The refusal brief names the real reason for each refused tool call | It assumes a path outside the folder; true for every case seen | open |
| B10 | Tolerate a torn final ledger line on resume; `ledger.py` kn: a torn final line after a hard kill also raises | Failing closed was the safe first step | done: feat(ledger): repair a torn final line |
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
| B18 | Run checks inside an OS sandbox (no network, no writes outside a temp folder, no reads of the home folder) | The largest accepted risk (T13) | building |
| B19 | A check cannot forge its own verdict; `gate.py` kn: in-process verdicts are forgeable by deliberately adversarial code | Needs the report read from outside the process that runs worker code | open |
| B20 | `boss doctor` canary: prove at run time that a write outside the workspace is refused | Tests pin the flags only (T18) | open |
| B21 | Re-check isolation after the init event; verify the boss call's isolation | Checked once at init (T21) | done: fix(runner): a late hook event fails the slice as an isolation failure; the boss call's isolation is still unverified (no init event) |
| B22 | Size caps on a workspace, a log and the gate's copy | Bounded by time and money only (T37) | open |
| B23 | Hash-chain the ledger and sign approvals | Single-user machine (T29) | open |
| B24 | Probe API-key mode; `worker.py` kn: --bare not yet probed. | Needs an API key | open |
| B25 | A recorded fixture for a plan usage limit; `errors.py` kn: no recorded fixture for a plan usage limit yet | One has not occurred | open |
| B26 | Probe whether `Read(./**)` also confines Glob and Grep | Workers are not given those tools | wont: they are not in the tool list; revisit if they are added |
| B27 | Escape the boss's briefs and check descriptions where a person reads them | Only worker text is cleaned (T35) | done: fix(approval): the boss's text and gate details are shown as data |

## Boss and checks

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B28 | Measure check quality without worker runs: precision on the reference, recall on known-wrong implementations | Nothing measured coverage | building |
| B29 | Boss thinking off: measure wrong checks and coverage with it | Costs about $0.50 per 17 drafts | open |
| B30 | A second pass that audits each check against the idea | Needs B28 to be judged | open |
| B31 | User stories with acceptance criteria, and a check traced to every criterion | Part of the roles work | open |

## Roles

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B32 | Role registry: each role's prompt, tools, output schema, gate and budget in one place | New scope | open |
| B33 | Product manager (stories), user agent, system designer, tester, critic, judge, demo writer, consultant | New scope; each default-off until it earns its cost | open |
| B34 | Skills: versioned prompt modules per role, with tests | New scope | open |
| B35 | Judge calibration against the investor's labels before its verdicts count | A judge is advisory until calibrated | open |

## Benchmark

| Id | Item | Why it was deferred | Status |
|---|---|---|---|
| B36 | Three runs per arm on the hardened code | Cost | building |
| B37 | Replay: stop at DONE like the live loop | The live loop never funds past DONE, so replay's extra walk changes no figure today | open |
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
| B42 | `state.slice_history` raises on an outcome it does not know (a ledger from a newer version) | open |
| B43 | `ledger.Event.from_json` accepts `"v": true` as version 1 | done: fix(ledger): a version must be the integer 1 |
| B44 | `errors.classify`: an `errors` field that is an int raises TypeError | done: fix(errors): classify never raises on malformed signals |
| B45 | `retry.infra_action` overflows for an attempt number over about 1000 | done: fix(retry): backoff and plan pressure hold for any input |
| B46 | `retry.plan_pressure` assumes utilisation is a fraction, not a percentage | done: fix(retry): backoff and plan pressure hold for any input |
| B47 | `FiringPolicy` accepts bool and float | open |
| B48 | `redact` masks some ordinary text (a word containing `sk-` followed by 20 characters; `max_tokens: 1000000`) | open |
| B49 | The early budget check refuses `--budget 0.30 --rounds 3` even when the boss would draft fewer checks than rounds | open |
