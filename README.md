# boss

You fund an idea. An LLM boss turns it into executable checks, you approve them, and a worker
builds against them. Nothing counts as done until an independent gate says the checks pass, and
every cent is written to a ledger.

**Status: stage 0.** One approved round, one worker, one slice. Funding rounds, firing and
reassignment are the next stage and are not built yet.

## How it works

| Role | Is | Does |
|---|---|---|
| Investor | You | Gives the idea and budget. Approves the term sheet. |
| Boss | One schema-validated model call, no tools | Drafts the term sheet: a task and pytest checks. |
| Worker | A headless `claude` session | Builds the task. Can read, write and edit files in its own folder. No shell. |
| Gate | Plain code | Runs the checks in isolated pytest processes. The only thing that can say "passed". |
| Ledger | Append-only JSONL | Every spend, decision and check result. The report is generated from it. |

The model drafts; code and the investor decide. Check ids, file names, the budget split, pass or
fail, and totals are never taken from a model.

## Requirements

- macOS or Linux, Python 3.12+, [uv](https://docs.astral.sh/uv/)
- [Claude Code](https://code.claude.com) 2.1.277 or newer, logged in (`claude auth login`)

## Install

```bash
git clone https://github.com/kgorle1111/boss-agent.git
cd boss-agent
uv sync
uv run boss doctor --live
```

`doctor` checks everything a run needs and prints a fix line for anything missing. `--live` makes
one small real call, because `claude auth status` can report a login that the API then rejects.

## Use

```bash
uv run boss fund "A function is_palindrome(text) that ignores case, spaces and punctuation." --budget 0.40
```

1. The boss drafts a term sheet. You see the task brief and every check's code.
2. You approve, reject, or edit the files and have them re-validated.
3. A worker builds the task in `.boss/runs/<run>/workspaces/w1/`.
4. The gate runs every check and the board report is printed and saved.

```bash
uv run boss report    # the latest run's board report
uv run boss status    # one line: last event, checks passing, spend
```

Exit codes: `0` every check passed, `1` stopped or failed, `2` usage error, `3` the round closed
with failing checks.

## What the safeguards are, and are not

- Checks are stored outside the worker's folder and copied fresh for every gate run, so a worker
  cannot edit a check to make it pass.
- Approval is recorded with hashes of the term sheet and each check. Any later edit voids it.
- Workers start in an isolated configuration (no hooks, MCP servers or shell) and are refused if
  the CLI reports anything else.
- A pass needs pytest to exit 0 and a test report showing at least one test and no failures.
- Costs are the CLI's client-side estimates, not a bill. Unknown costs are shown as unknown.
- The [threat model](docs/THREAT_MODEL.md) lists each threat, its control, the test that proves it, and what is accepted.

Limits you should know:

- **The tool whitelist is not a sandbox.** The gate executes the code a worker wrote, on your
  machine, with a filtered environment and a timeout. Do not run ideas from sources you do not
  trust. Container isolation is not built.
- Code written specifically to defeat the gate can still fake a pass.
- Built products are limited to the Python standard library.
- A budget cap can be overshot by one model response.
- Using an Anthropic API key instead of a Claude login (`--bare` mode) is untested.

## Development

```bash
uv run pytest                 # unit tests, no model calls
uv run ruff check . && uv run ruff format --check .
BOSS_LIVE=1 uv run pytest tests/test_end_to_end.py   # one real run, a few cents
```

Tests use recorded CLI output in `tests/fixtures/` and fake `claude` executables, so the whole
flow, including `boss fund` end to end, runs without credentials.
