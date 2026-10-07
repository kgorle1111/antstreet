# AntStreet

`antstreet` and `boss` are the same command; `boss` is the bull you talk to. The Python package
is still named `boss`.

**Coding agents say "done" when it is not. AntStreet makes "done" something you can verify.**

You give it an idea and a budget. An LLM boss drafts pytest acceptance checks, and you approve
them before any code exists. Headless Claude Code agents then build in budget-capped slices. A
sandboxed gate, not the agents, decides what passed, and every dollar and decision goes on a signed,
hash-chained ledger.

Why: in our benchmark, 29 of 77 runs (38%, 95% interval 28-49%) passed every check the model had
written and still failed a hidden check it never saw (written by Claude, separately from the agents
measured). We read all 29 against the task text and judge each a real error; one class (tokenbucket's
int-vs-float return) is debatable. Caveats: 17 small Python tasks, Haiku writing both checks and code, and runs
of one task are not independent (resampling tasks widens the interval to 20-57%). These were firm
runs, and the gate passed them: it runs the checks it is given, so the stat measures weak
model-written checks, not the gate or agents in general. Details in the
[false-pass audit](bench/results/2026-10-03-false-pass-audit/README.md).

## Quickstart

You need macOS or Linux, Python 3.12+, [uv](https://docs.astral.sh/uv/) and
[Claude Code](https://code.claude.com), logged in (`claude auth login`).

```bash
git clone https://github.com/kgorle1111/antstreet.git
cd antstreet
uv sync
uv run boss doctor --live        # checks this machine; two paid calls of at most $0.05 each
uv run boss fund "A function is_palindrome(text) that ignores case, spaces and punctuation." --budget 0.40
```

`boss fund` first shows you the term sheet and waits for your yes. This is the real shape of it,
abridged, from the test suite's run with a fake model (so the check is a toy one):

```text
TERM SHEET
Idea: Reverse a string.
Budget: $0.5 (estimated cost, not a bill)
Round 1: $0.5, next unlocks at 1 passing checks

Task t1 (owns rev.py):
  Create rev.py with reverse(s).

Check c01 [t1] reverses a word
--- .boss/runs/<run>/checks/test_c01.py
from rev import reverse

def test_word():
    assert reverse('ab') == 'ba'
```

After you approve, the worker builds, the gate runs the checks, and you get a board report from the
ledger (`Delivered: yes (1 of 1 checks pass on the product)`, spend per role, tokens). Built files
land in `.boss/runs/<run>/product/`.

## What we measured

**Status: working, and not yet better than one agent at building.** Funding rounds, capped slices,
firing, one reassignment, disputed checks and your rulings on them, held-out checks no worker sees,
`boss resume`, `boss topup`, hard run limits and a hash-chained ledger with signed approvals are
built. Checks run in an OS sandbox on macOS. On the 35-task benchmark (Haiku, $0.40 a task, three
runs per task, both arms given the same instruction and neither told about hidden checks) the firm
passed 64 of 105 (61%) against 62 of 105 (59%) for a single agent given the same idea; paired by
task the difference is not shown. It cost about 2.4 times as much ($0.2149 against $0.0883 a task)
and took longer (median 3m34s against 1m25s). See
[bench/results/2026-10-03-blind35/table.md](bench/results/2026-10-03-blind35/table.md) and
[bench/METHOD.md](bench/METHOD.md). Both arms ran on one commit, and code changed after that run is
not measured. An earlier run on 17 of these tasks (firm 35 of 51, 69%; single 32 of 51, 63%) is not
comparable: the single arm was told its work would be judged by hidden checks and the firm's workers
were not, and the two arms ran on different commits. Raw results are not committed.

What that means: the value of AntStreet is verification and control, not "more agents build better".
We do not claim a team of agents beats one agent on small tasks, because we measured it and it did
not. We publish negative results like this one on purpose; the earlier headline did not survive a
fair re-run, and the write-up says so
([blind35 notes](bench/results/2026-10-03-blind35/README.md),
[evidence review](bench/EVIDENCE.md)).

On the false passes: 13 of the 29 failed only on non-ASCII input or a returned type; without those,
16 of 77 (21%, 13-31%). The model's own held-out checks caught none of the 17 false passes in the
run that had them.

## How it works

```text
 idea + budget
      |
      v
 boss drafts pytest checks ---> you read and approve (signed, hashed)
                                      |
                                      v
        agents build in budget-capped slices <--+  fired / replaced / set aside
                                      |         |  by a plain-code rule
                                      v         |
        sandboxed gate runs the checks ---------+
                                      |
                                      v
      signed, hash-chained ledger  ->  board report
```

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

Why it is different:

- **Checks before code.** You approve the checks first. Workers cannot edit them: they live outside
  the worker's folder and are copied fresh for every gate run.
- **The gate decides, not the agent.** A pass needs pytest to exit 0, a report with no failures,
  errors or skips, and a signed proof from a plugin that every test really ran.
- **Budget caps and firing.** Money is released in rounds against passing checks. A worker that
  stops making progress is fired and replaced once. Hard limits stop the run.
- **A signed ledger.** Every line carries the hash of the one before it; your approvals are signed
  with a key no worker can read. Costs are the CLI's estimates, and unknown costs are shown as unknown.
- **Blind measurement.** The benchmark's hidden checks are written separately from the agents being
  measured (by Claude, in a different session), validated against a reference solution and planted wrong
  solutions, and never shown to any agent, and neither arm is told it is measured.
- **Dispatch (optional).** `--dispatch rules` has the term sheet name, per task, the agent route,
  model and effort. You can edit it, it is hashed into your approval, and every choice is on the
  ledger. We have not shown that it saves money without losing delivery, so it is off by default
  (see [docs/CLI.md](docs/CLI.md) and `D43` to `D45` in [docs/DECISIONS.md](docs/DECISIONS.md)).

## Audit an agent's "done"

`boss audit` is the same idea pointed at someone else's work. Before a coding agent starts, you seal
checks for the change request; afterwards you test the agent's commit against them.

```bash
uv run boss audit plan --repo . --request req.txt --base main    # draft, run on base, you approve, seal
uv run boss audit check RUN --head agent-branch --claim done     # RUN is the id `plan` printed
uv run boss audit report                                         # verdicts and the false-pass rate
```

The verdict is `refuted`, `unrefuted`, `inconclusive` or `no_claim`. `unrefuted` is not proof: the
sealed checks catch only what they test. The agent never sees the checks, and the verdict is
signed. Full rules: [docs/CLI.md](docs/CLI.md).

## Use it from any MCP client

`boss mcp` is a read-only MCP server on stdio: `list_runs`, `status`, `report`, `verify_ledger`
and `doctor` (never `--live`). No tool funds, resumes, tops up or approves; those stay yours, at a
terminal. Put this in a project's `.mcp.json`. It works once the package is on PyPI; until then
use `"args": ["--from", "/path/to/your/antstreet/checkout", "antstreet", "mcp"]`.

```json
{
  "mcpServers": {
    "antstreet": { "command": "uvx", "args": ["antstreet", "mcp"] }
  }
}
```

Details: [docs/CLI.md](docs/CLI.md#boss-mcp).

## Use it in GitHub Actions

The repository root holds a composite action, `action.yml`. It runs `antstreet audit check
--claim done` on a pull request's head commit and fails the job on `refuted` or `inconclusive`
(exit 3) or on any refusal (exit 1). It runs nothing else: no `plan`, no `fund`, no model call, no
spend. It writes the verdict table and the check's own output to the job summary.

What it cannot do alone: `audit check` needs the **audit store** that `audit plan` wrote on your
machine (`~/.boss-audit`, see [docs/CLI.md](docs/CLI.md)): the sealed checks, the signed ledger and
`.boss/investor.key`. The store must not be in the repository, or the pull request's author can read
the checks and forge the verdict. So you seal on your machine, pack the one run you want, store it as
an encrypted repository secret, and a step before the action unpacks it. The action refuses a store
that the repository tracks.

```bash
# on your machine, once per sealed run (RUN is the id `plan` printed)
tar -C ~/.boss-audit -czf - .boss/runs/RUN .boss/investor.key .boss/anchors | base64 | gh secret set ANTSTREET_STORE
# a secret holds up to 48 KB: a few small checks fit; the store has one run's files, nothing else
```

```yaml
# .github/workflows/antstreet.yml
name: AntStreet audit
on: pull_request
permissions:
  contents: read          # all the action needs; it never writes to the repository
jobs:
  audit:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # the sealed base commit must be in the history
      - name: Restore the audit store
        env:
          STORE_B64: ${{ secrets.ANTSTREET_STORE }}
        run: |
          mkdir -p "$RUNNER_TEMP/audit-store"
          printf '%s' "$STORE_B64" | base64 -d | tar -xzf - -C "$RUNNER_TEMP/audit-store"
      - uses: kgorle1111/antstreet@main   # pin a commit in real use
        with:
          store: ${{ runner.temp }}/audit-store
          run: 20261005T154252Z-b68e86     # the id `antstreet audit plan` printed
```

| Input | Default | Meaning |
|---|---|---|
| `store` | required | The restored audit store (the folder that holds `.boss/`). |
| `run` | required | The audit run id. |
| `head` | the PR head, else the pushed commit | The commit to audit. |
| `repo` | the workspace | The checkout that holds the head and the base. |
| `python-version` | `3.12` | Python the checks run under. |
| `antstreet-version` | empty | A PyPI version. Empty runs the copy that ships with the action (`uvx --from <action path> antstreet`), so it works before the PyPI release. |

The output `verdict` is `refuted`, `unrefuted`, `inconclusive` or `refused`.

- **Sandbox required.** On Linux the step installs `bubblewrap` and sets `BOSS_GATE_SANDBOX=require`,
  so a runner that cannot start it fails the job instead of running checks unsandboxed.
  `setup-uv` is pinned by commit.
- **Secrets.** A pull request from a fork gets no secrets, so the audit refuses with "No audit
  store" there. A pull request from the same repository can edit the workflow and print the secret:
  keep the secret in an [environment](https://docs.github.com/en/actions/deployment/targeting-different-environments)
  with required reviewers, or run the audit from a ruleset-required workflow the author cannot edit.
  This is the same single-key trust as [T29](docs/THREAT_MODEL.md#t29); the verdict is as strong as
  who can read that secret.
- **One run per pull request.** The run id names one request's sealed checks. A repository that
  audits several requests needs one workflow per run id (or a matrix over them).
- **`unrefuted` is not proof**, and `inconclusive` (no check failed on the base, a check could not
  run, or the change quotes the sealed checks) fails the job on purpose: a "done" the checks could
  not test is not a pass. See [docs/CLI.md](docs/CLI.md) for the verdict rules.

## Requirements

- macOS or Linux, Python 3.12+, [uv](https://docs.astral.sh/uv/)
- [Claude Code](https://code.claude.com) 2.1.277 or newer, logged in (`claude auth login`)

## Install

The [quickstart](#quickstart) commands are the whole install. `boss doctor` checks everything a run
needs and prints a fix line for anything missing. `--live` makes two small paid calls, each capped at
$0.05 on Haiku: one to verify the login, because `claude auth status` can report a login that the
API then rejects, and one that asks a worker to write outside its folder, to check that the
installed CLI still refuses it.

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
| `--dispatch MODE` | `off`, or `rules`: choose each task's agent, model and effort, shown in the term sheet | off |
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
uv run boss routing   # the start tier `--dispatch cascade` would pick per task kind, from past runs
uv run boss verify    # offline integrity check: ledger chain, signatures, saved prompts
uv run boss roles     # the organisation: roles, worker profiles and their skills
uv run boss doctor    # check this machine; --live adds the two paid calls above
uv run boss audit plan --repo . --request req.txt --base main   # seal checks for someone else's change
```

`boss audit` checks a change an agent made in a git repository against checks sealed before it, and
reports `refuted`, `unrefuted` (not proof), `inconclusive` or `no_claim`; see [docs/CLI.md](docs/CLI.md).

With no terminal to ask on (Claude Code's Bash tool, a pipe), `boss fund` does not ask: it prints
the term sheet and every check, keeps the paid-for draft, and exits `4` with the one command that
approves exactly that text. You run it yourself (in Claude Code, with the `!` prefix), then build:

```bash
boss approve <run>                  # read the term sheet again, with its --sheet value
boss approve <run> --sheet <value>  # your approval, refused if anything changed since it was shown
boss resume <run>                   # builds it; an agent may run this, never `approve`
```

`boss resume` reads the run's ledger and the settings it started with. Running it is your decision
to lift a stop, and the approval, the budget and every limit are checked again. A round that closed
below its unlock threshold stays locked until you `boss topup` it.

Exit codes: `0` every check passed; `1` the boss produced no usable term sheet, you rejected it, or
a worker did not start isolated; `2` usage error (including a blank idea and a budget too small to fund one slice);
`3` the run ended with checks not passing, including a run stopped early by a limit, a declined
round, a pause or a lost login; `4` no terminal to ask on, the term sheet waits for `boss approve`; `130` you pressed Ctrl-C (continue with `boss resume`).

## Use it from Claude Code

This repository is also a Claude Code plugin marketplace. In a Claude Code session:

```text
/plugin marketplace add kgorle1111/antstreet
/plugin install antstreet@antstreet
```

| Command | What it does |
|---|---|
| `/antstreet:fund <idea> [--budget 0.40]` | Runs `antstreet doctor` (no model call), then gives you the `uvx antstreet fund ...` line to paste into your own terminal. |
| `/antstreet:report [run]` | Prints the board report from the run's ledger. |
| `/antstreet:status [run]` | One line: last event, checks passing, spend. |

The plugin is a thin front door; the engine runs outside the agent it checks. `fund` is never run
from inside the session: approval reads your answer from a terminal, and from Claude Code it would
read end of input, which is a reject after the draft is paid for. The plugin's commands may run
only `status`, `report` and `doctor` (without `--live`) without asking you.

Two hooks run as you. At session start, if `uvx` is missing, one prints the one command that
installs uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`); it installs nothing. When the
agent stops, in a project with runs under `.boss/runs/`, the other runs `uvx antstreet status`,
which checks the latest ledger's hash chain and signatures offline. A failure is shown to you; it
never blocks the agent. In any other project both are silent.

Running `antstreet` (or the benchmark) from a shell inside a Claude Code session is safe for the
`claude` processes it starts: each gets only `HOME`, `PATH`, `USER`, `LANG`, `TMPDIR`,
`CLAUDE_CONFIG_DIR` and, if set, `ANTHROPIC_API_KEY` (`worker_env` in `src/boss/worker.py`). The
session's own variables (`CLAUDECODE`, `CLAUDE_CODE_*`, `CLAUDE_AGENT_SDK_*`, its
`ANTHROPIC_BASE_URL`) never reach them. They use the login stored for your user by
`claude auth login`, not the session's. If that login has expired, every call fails at once;
`boss fund` and the benchmark then say to run `claude auth login`, and the benchmark stops after
3 such cells.

Until `antstreet` is on PyPI and this repository is public, `uvx antstreet` does not resolve, so
the plugin cannot run yet. To try the CLI the same way before then, with access to the repository:
`uvx --from git+https://github.com/kgorle1111/antstreet antstreet doctor`. The plugin files are
not in the wheel or the sdist.

## Limits

What AntStreet does not do, in plain words. Each links to its row in the [threat model](docs/THREAT_MODEL.md).

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
  runs under a deny-by-default profile; on Linux the `bwrap` version runs, and is required (`BOSS_GATE_SANDBOX=require`), in CI; with no
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

## Status

Early. It works end to end and the tests are deep, but it is pre-release.

- Python with pytest only; workers are Claude Code sessions.
- The macOS sandbox is stronger than the Linux one (see Limits).
- Single machine, single user.
- Built, not yet installable: a Claude Code plugin (it needs the repository public and the PyPI
  release, see [Use it from Claude Code](#use-it-from-claude-code)).
- Planned, not built: a PyPI release (the name is `antstreet`; nothing is published yet).
- Built, with a manual step: a GitHub Action that runs `boss audit check` on a pull request
  ([Use it in GitHub Actions](#use-it-in-github-actions)); you carry the sealed store to the
  runner yourself (see [docs/BACKLOG.md](docs/BACKLOG.md), B78).

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

## Contributing

Bug reports, new benchmark tasks and sharper checks are welcome. Setup, the rules and how to add a
task are in [CONTRIBUTING.md](CONTRIBUTING.md). To report a security problem, see
[SECURITY.md](SECURITY.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
