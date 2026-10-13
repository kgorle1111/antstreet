# Recovery under injected faults

The question: when something dies mid-run, does `antstreet resume` finish the job from the ledger
without paying for any slice twice, and does every dollar spent end up on a ledger line, or at
least flagged as missing?

The answer below is measured, not argued. `tests/fault_support.py` injects each fault into a real
`antstreet fund` and `tests/test_fault_injection.py` checks every trial and regenerates the table,
which must match the one here (a docs test), so it cannot drift from the code's behaviour.

## Setup

- Each `antstreet` command runs in its own process (so a fault can `SIGKILL` it), against a fake
  `claude` that plays the boss and the worker, the real gate, and a signed, anchored ledger.
- The fake keeps a session store like the real CLI and reports a session's cumulative cost, as the
  real one does: $0.004 for the boss's draft, $0.01 per worker call. It writes what a provider
  would bill to a file the moment each call is made, before any fault: the ground truth.
- A clean run is two worker slices (the first product fails the check, the second passes): $0.024
  billed, $0.024 booked, 12 ledger lines.
- Each worker fault is injected in call 1 (a new session) and call 2 (a resumed session). The
  anchor crash is injected after each of the clean run's 12 lines. After a fault, `resume` runs
  until the run ends, then once more (it must write nothing and spend nothing), then `verify`.

## Definitions

- **Recovered**: the last `fund` or `resume` exits 0 with the check passing on the product.
- **Escalated cleanly**: it stops with a non-zero exit, names the command to run next
  (`antstreet resume` or `antstreet fund`), and loses nothing unseen.
- **Double-spend**: a slice booked twice, a slice run again after its end was booked, or more
  booked in total than was billed (a session's cumulative cost counted twice).
- **Silent loss**: billed money on no ledger line with no event of unknown cost in the ledger, so
  the report's total would read as complete when it is not.
- **Billed, not booked**: billed minus the ledger's known costs, per trial. The report shows it as
  "event(s) of unknown cost" next to the total, which is then a lower bound.
- **Wasted**: billed minus the clean run's $0.024 for a recovered trial; everything billed for a
  trial that must start again. The clean run's first slice does not finish the task either, so a
  fault there costs nothing extra; a fault in the slice that would have finished costs one more.

## Results

Measured 2026-10-13 on the fake CLI (no model was called; $0 spent).

| Fault | Trials | Recovered | Escalated cleanly | Double-spends | Silent losses | Unknown-cost events | Billed, not booked, per fault | Wasted per fault |
|---|---|---|---|---|---|---|---|---|
| worker SIGKILLed mid-slice | 2 | 2/2 | 0/2 | 0 | 0 | 2 | $0.0100 | $0.0050 |
| tool call hangs past the slice timeout | 2 | 2/2 | 0/2 | 0 | 0 | 2 | $0.0100 | $0.0050 |
| worker prints gibberish, no result | 2 | 2/2 | 0/2 | 0 | 0 | 2 | $0.0100 | $0.0050 |
| result with an unparseable status | 2 | 2/2 | 0/2 | 0 | 0 | 0 | $0.0000 | $0.0000 |
| Ctrl-C mid-slice (the CLI reports its cost) | 2 | 2/2 | 0/2 | 0 | 0 | 2 | $0.0050 | $0.0050 |
| `antstreet` SIGKILLed mid-slice | 2 | 2/2 | 0/2 | 0 | 0 | 2 | $0.0050 | $0.0050 |
| `antstreet` SIGKILLed mid-slice, its worker left running | 2 | 2/2 | 0/2 | 0 | 0 | 2 | $0.0050 | $0.0050 |
| `antstreet` killed between a ledger write and its anchor | 12 | 10/12 | 2/12 | 0 | 0 | 2 | $0.0000 | $0.0007 |
| a second `resume` while the first runs | 1 | 1/1 | 0/1 | 0 | 0 | 1 | $0.0100 | $0.0000 |

Across 27 faulted trials: 25 recovered, 2 escalated cleanly, 0 double-spends, 0 silent losses,
every ledger verified, and a further `resume` changed nothing in any of them.

## What the table shows

- **No slice was paid twice.** A slice whose `slice_end` is on the ledger is never run again: a
  crash after it is written is resumed by grading that slice, not by repeating it. A resumed
  session books only what its cumulative total grew by, so a killed slice in a resumed session is
  paid once, by the slice after it (Ctrl-C and `antstreet` killed in call 2: $0 unbooked).
- **Worker faults never need a resume.** A killed, hung or garbled worker ends its slice as
  `crashed` or `timeout` with a cost of `null`, the round is charged its cap, and the loop goes on.
- **The report undercounts only where it says so.** A worker killed before it reported anything
  costs $0.01 the ledger cannot know; each such slice is an event of unknown cost. Before R7, an
  `antstreet` process killed mid-slice left only a `slice_start`, and that slice's spend was on no
  line with nothing to say so (G11 in the readiness audit): now `resume` books it as an `error` with
  `interrupted_slice` and a cost of `null` (see [LEDGER.md](LEDGER.md#error)).
- **Two anchor crashes escalate.** Killed after line 1 (the boss's call) or line 2 (the approval),
  the run has nothing to resume: `resume` says to start again with `antstreet fund`, and the
  $0.004 draft is the waste. Two others (after a `slice_start`, before the worker started) are
  booked as unknown cost although nothing was spent: the ledger cannot tell a slice that never
  started from one killed at once, so it says "unknown" rather than "free".
- **A worker left running is stopped before its slice runs again.** The worker runs in a session
  of its own, so a SIGKILL of `antstreet` does not reach it: it can go on writing its workspace.
  The runner records its process group in `logs/<worker>.pgid` (next to its log) before the
  worker CLI starts, and removes it once the slice's group is stopped: the launched child waits
  on a pipe and execs the CLI only after the record, so an `antstreet` killed in between leaves
  no worker running (the child sees the pipe close and exits). `resume` reads the file before
  booking the interrupted slice: a live group whose command line holds the slice's session id
  is stopped (SIGTERM, then SIGKILL) and the booking says so (`stopped_pgid`); a live group that
  cannot be shown to be the worker (its id reused, or only the worker's tool commands left) is
  never signalled, and `resume` refuses, books nothing and says what to do. The trial's fake
  worker records every later worker call made while it still runs: none was.
- **Two resumes cannot run one run at once.** The second is refused (the run is still being
  written by another process) and the ledger is byte for byte unchanged; the first finishes.

## Bugs this found

- G11 / R7, a silent loss: an `antstreet` killed mid-slice left that slice's spend on no ledger
  line. Fixed: booked as unknown cost on resume (`firm.interrupted_slices`).
- A crash between the ledger's first line and its first anchor left a signed line with no anchor,
  which `verify` and every later writer refused as a deleted anchor: an honest run read as
  tampered. Fixed: the writer anchors an empty ledger (0 lines) when it opens it.
- Open: on Ctrl-C the runner reads the CLI's final result, cost included, then raises before the
  slice is booked, so a known cost becomes an unknown one (the Ctrl-C row, call 1: $0.01). It is
  flagged, not lost; booking the slice before re-raising would make it exact.

## Limits

- One task, one check, one slice at a time; parallel waves (`--parallel`) were not faulted.
- The fake's costs are fixed; real slices cost more and vary, so the dollar columns show where
  money goes, not how much a real fault costs.
- `hang` and `gibberish` model a worker that dies without a result. A real CLI stopped at its
  timeout usually prints one with its cost; then the slice is booked exactly.
- The benchmark runner (`bench/run.py`) resumes whole cells, not slices; it was not faulted here.
- A worker left running is found only through `logs/<worker>.pgid`: a run started before this
  file existed resumes as before (the slice is booked, a worker may still run). Stopping needs
  `/bin/ps` (macOS, Linux); without it a live group cannot be verified and `resume` refuses.

Rerun: `uv run pytest -o addopts="" tests/test_fault_injection.py` (about a minute), or print the
table with `uv run python tests/fault_support.py`.
