# boss

You fund an idea. An LLM boss turns it into executable checks, you approve them, and a worker
builds against them. Nothing counts as done until an independent gate says the checks pass, and
every cent is written to a ledger.

**Status: working, and not yet better than one agent.** Funding rounds, capped slices, firing,
one reassignment, disputed checks and your rulings on them, held-out checks no worker sees,
`boss resume`, `boss topup`, hard run limits and a hash-chained ledger with signed approvals are
built. Checks run in an OS sandbox on macOS. On the 17-task benchmark (Haiku, $0.40 a task, three
runs per task) the firm passed 35 of 51 (69%) against 32 of 51 (63%) for a single agent given the
same idea; the intervals overlap. It cost about 2.4 times as much ($0.2197 against $0.0925 a task)
and took longer (median 4m04s against 1m28s). See
[bench/results/2026-09-30-final3/table.md](bench/results/2026-09-30-final3/table.md) and
[bench/METHOD.md](bench/METHOD.md). The two arms ran on different commits, and code changed after
those runs is not measured. Raw results are not committed.

## How it works

| Role | Is | Does |
|---|---|---|
| Investor | You | Gives the idea and budget. Approves the term sheet. |
| Boss | One schema-validated model call, no tools | Drafts the term sheet: a task and pytest checks. |
| Worker | A headless `claude` session | Builds the task in funded slices. Can read, write and edit files in its own folder. No shell. |
| Rule | Plain code | After each slice: fund another, fire the worker, or set the task aside for you. Reads only the ledger. |
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
two small paid calls, each capped at $0.05 on Haiku: one to verify the login, because `claude auth
status` can report a login that the API then rejects, and one that asks a worker to write outside
its folder, to check that the installed CLI still refuses it.

## Use

```bash
uv run boss fund "A function is_palindrome(text) that ignores case, spaces and punctuation." --budget 0.40
```

1. The boss drafts a term sheet. You see the task brief and every check's code.
2. You approve, reject, or edit the files and have them re-validated. With `--held-out N`, an
   examiner first writes up to N more checks from your idea and the public names the product must
   expose (never a visible check); you approve them too, no worker ever sees them, and the
   finished product must pass them as well.
3. A worker builds the task in `.boss/runs/<run>/workspaces/w1/`, one capped slice at a time. It
   is given your idea word for word, then the boss's brief and checks.
4. The gate runs the checks after every slice. The worker's next brief shows what failed.
5. A worker that stops making progress is fired and replaced once, with its files and the gate's
   findings handed over. A worker that believes a check contradicts your idea can dispute it. The
   check never counts as passing. If the claim is credible (every other check passes and at most
   half the task's checks are disputed), you are asked: drop the check, keep it, or set the task
   aside. A worker that says it is blocked gets the same choice, with a note from you. Your answer
   is a ledger event; the approved term sheet is not edited.
6. The board report is printed and saved. Built files are in `.boss/runs/<run>/product/`.

Useful options for `boss fund` (every option is in [docs/CLI.md](docs/CLI.md)):

| Option | Meaning | Default |
|---|---|---|
| `--rounds N` | Split the budget into rounds; each later round needs your yes | 1 |
| `--slice D` | Dollars a worker may spend before the gate looks again | 0.10 |
| `--reserve D` | Held back from every slice cap: what one model response can cost | 0.10 for Haiku (set by model) |
| `--stall-slices N`, `--max-slices N` | When the rule fires a worker | 2, 6 |
| `--max-minutes M` | Stop the run after this much wall-clock time | none |
| `--boss-thinking N` | Thinking tokens for the boss's draft; 0 turns thinking off | the CLI's |
| `--worker-thinking N` | Thinking tokens for every worker slice; 0 turns thinking off | the CLI's |
| `--held-out N` | Checks an examiner writes that no worker sees, run on the finished product (0 to 8) | 0 |
| `--max-tasks N` | Let the boss split the work into up to N tasks | 1 |
| `--parallel N` | Work on up to N tasks at once; one worker per task | 1 |
| `--profile NAME` | Add a worker profile's skills to the builder prompt; `boss roles` lists them | none |
| `--roles A,B` | Run specialist roles around the build (stories, staged draft, audit, consultant, critic, demo, judge); `all` turns on every role | none |
| `--review-cycles N`, `--fix-budget D` | Critic reviews of the product that may lead to a fix round you approve; dollars for that round | 1, two slices and a reserve |

```bash
uv run boss resume    # continue the latest run: interrupted, paused or stopped
uv run boss topup --round 1 --amount 0.20   # add money to a round; reopens a locked one
uv run boss report    # the latest run's board report
uv run boss status    # one line: last event, checks passing, spend
uv run boss roles     # the organisation: roles, worker profiles and their skills
uv run boss doctor    # check this machine; --live adds the two paid calls above
uv run boss audit plan --repo . --request req.txt --base main   # seal checks for someone else's change
```

`boss audit` checks a change an agent made in a git repository against checks sealed before it, and
reports `refuted`, `unrefuted` (not proof), `inconclusive` or `no_claim`; see [docs/CLI.md](docs/CLI.md).

`boss resume` reads the run's ledger and the settings it started with. Running it is your decision
to lift a stop, and the approval, the budget and every limit are checked again. A round that closed
below its unlock threshold stays locked until you `boss topup` it.

Exit codes: `0` every check passed; `1` the boss produced no usable term sheet, you rejected it, or
a worker did not start isolated; `2` usage error (including a blank idea and a budget too small to fund one slice);
`3` the run ended with checks not passing, including a run stopped early by a limit, a declined
round, a pause or a lost login; `130` you pressed Ctrl-C (continue with `boss resume`).

## Limits

What `boss` does not do, in plain words. Each links to its row in the [threat model](docs/THREAT_MODEL.md).

- **A determined adversary can forge a pass.** The gate checks a worker's code by running it, and
  code written specifically to attack this gate can fake the result from inside the same process
  ([T12](docs/THREAT_MODEL.md#t12), accepted). Workers are not told to attack it, so ordinary
  gaming (exit codes, edited reports, patched pytest) fails, but do not run ideas or code from
  sources you do not trust.
- **Checks catch only what they test.** A passing gate means the checks passed, not that the
  product is right. The boss writes the checks and can write a weak or wrong one; you reading them
  before you approve is the only control ([T14](docs/THREAT_MODEL.md#t14),
  [T44](docs/THREAT_MODEL.md#t44)).
- **The sandbox is stronger on macOS than on Linux.** macOS denies every read it was not told
  to allow. Linux (`bwrap`) leaves most of the disk readable and hides only `/home`, `/root`,
  `/tmp`, `/run`, the project's `.boss/` and `BOSS_AUDIT_HOME`, and its first real run is CI. With
  no working tool a check has your full access ([T13](docs/THREAT_MODEL.md#t13),
  [T39](docs/THREAT_MODEL.md#t39), [docs/SANDBOX.md](docs/SANDBOX.md)).
- **It trusts one machine and one user.** Anyone who can read your project folder, including
  `.boss/investor.key`, can forge your approvals; there is no multi-user, hosted or synced use
  ([T29](docs/THREAT_MODEL.md#t29)).
- **Python with pytest only.** Checks are pytest files and products are expected to use the
  standard library. Other languages and test runners are out of scope (the scope
  paragraph at the top of the [threat model](docs/THREAT_MODEL.md)).

## What the safeguards are, and are not

- Checks are stored outside the worker's folder and copied fresh for every gate run, so a worker
  cannot edit a check to make it pass.
- Approval is recorded with hashes of the term sheet and each check, and verified again before
  every slice and every gate run. Any later edit stops the run.
- Every ledger line carries the hash of the line before it, and your approvals are signed with a
  key in `.boss/investor.key` that no worker can read, so a forged approval is refused.
- Workers start in an isolated configuration (no hooks, MCP servers or shell) and are refused if
  the CLI reports anything else.
- A pass needs pytest to exit 0, a test report showing at least one test and no failures, errors
  or skips, and a signed proof from a plugin inside the run that every collected test really ran
  and returned.
- Costs are the CLI's client-side estimates, not a bill. Unknown costs are shown as unknown, and
  counted against the budget at the slice's cap.
- A run also stops at hard limits on total spend, slices, workers and (optionally) wall clock.
- Where the platform has a working tool, each check runs in an OS sandbox: no network, writes only
  in its own temp folder. See [docs/SANDBOX.md](docs/SANDBOX.md).
- A worker's own words are cleaned of secrets and control characters before they are stored, and
  the boss's text is shown to you the same way.
- The [threat model](docs/THREAT_MODEL.md) lists each threat, its control, the test that proves it, and what is accepted.

Limits you should know:

- **The tool whitelist is not a sandbox, and the gate's sandbox is partial.** The gate executes the
  code a worker wrote, on your machine, with a filtered environment and a timeout. On macOS that
  runs under a deny-by-default profile; on Linux the `bwrap` version is set up to run in CI but not yet confirmed by a passing run; with no
  working tool, checks run with your full access (`boss doctor` warns; `BOSS_GATE_SANDBOX=require`
  refuses). Do not run ideas from sources you do not trust. Container isolation is not built.
- Code written to target the gate's own process can still fake a pass (T12 in the threat model).
- Built products are meant to use only the Python standard library: the builder prompt says so,
  and nothing installs dependencies for a product.
- `--budget` covers the funding rounds. The boss's own drafting call is charged on top of it (about
  $0.03 to $0.10 on Haiku, most of it thinking; see `--boss-thinking`).
- A task you set aside (or leave unanswered) stays set aside for the run, resumed or not.
- A ledger whose last line was cut by a hard kill is repaired by `boss resume`, which removes
  that line. A ledger damaged anywhere else cannot be resumed.
- A slice cap can be overshot by one model response. The reserve is sized for that; a response
  that costs more than the reserve still overshoots.
- The boss can write a wrong check. You are the filter: read the checks before approving.
- Using an Anthropic API key instead of a Claude login (`--bare` mode) is untested.

## Documentation

| Document | What it holds |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Roles, one line per module, the life of a run, the loop's control flow, the invariants |
| [docs/LEDGER.md](docs/LEDGER.md) | Every event type and the `data` keys it carries, with an example line each |
| [docs/CLI.md](docs/CLI.md) | Every command and option, environment variables, exit codes, the run folder |
| [docs/ROLES.md](docs/ROLES.md) | Roles, worker profiles and skills: what each is, how to add one, and when a role is switched on |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Why it is built this way: what was rejected and the evidence |
| [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) | Each threat, its control, the test that proves it, and what is accepted |
| [docs/SANDBOX.md](docs/SANDBOX.md) | The gate's OS sandbox: what it denies, what it allows, the probes, what is not verified |
| [docs/BACKLOG.md](docs/BACKLOG.md) | Everything skipped or deferred, with a status |
| [bench/METHOD.md](bench/METHOD.md) | What the benchmark measures, the draft evaluation of the boss's checks, and what the numbers can support |
| [CHANGELOG.md](CHANGELOG.md) | What changed |
| [SECURITY.md](SECURITY.md) | What is and is not protected, and how to report a problem |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Setup, tests, the rules, and how to add a benchmark task |

Each of these has a test that fails when the document and the code disagree.

## Development

```bash
uv run pytest                 # unit tests, no model calls
uv run pytest --cov --cov-report=term-missing   # same, with line and branch coverage of src/boss
uv run ruff check . && uv run ruff format --check .
BOSS_LIVE=1 uv run pytest tests/test_end_to_end.py   # one real run, a few cents
```

Tests use recorded CLI output in `tests/fixtures/` and fake `claude` executables, so the whole
flow, including `boss fund` end to end, runs without credentials.

## License

Apache License 2.0. See [LICENSE](LICENSE).
