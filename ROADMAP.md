# AntStreet roadmap: tests your coding agent never saw

AntStreet checks your AI coding agent's work against tests it never saw, so "all tests pass"
actually means something. You seal checks before the agent starts; a sandboxed gate outside the
agent tests its "done" afterwards; every verdict lands on a ledger you can verify. The AI drafts;
you and plain code decide.

## Why it matters

- Agents say "done" and mean "I stopped". In our false-pass audit, **29 of 77 runs (38%)** passed
  every check the model wrote and still failed a hidden check it never saw.
- The caveat, kept on purpose: 17 small Python tasks, one model writing both checks and code, and
  under a stricter count it is 16 of 77 (21%). [Read the audit](bench/results/2026-10-03-false-pass-audit/README.md).
- Either way, "the agent's own tests pass" says little. Checks it never saw, which you approved,
  say more.

This page lists what works today, what is being built, and what we measured and dropped. No dates.
Item ids (`B..`) point at [docs/BACKLOG.md](docs/BACKLOG.md), where every item has its reason and
status.

## Shipped

On `main`, pre-release (not on PyPI yet). Each item links the pull request that landed it.

**Audit any agent's "done"**
- **`antstreet audit`**: seal checks for a change request before any agent starts, then test its
  commit against them, with a signed verdict ([#9](https://github.com/kgorle1111/antstreet/pull/9)).
  [Audit an agent's "done"](README-technical.md#audit-an-agents-done).
- **Audits in your repo's own environment**: the checks import your `.venv` packages, read-only
  inside the sandbox, and `audit plan --request FILE` then `audit check --claim done` is all it
  takes inside the repo ([#64](https://github.com/kgorle1111/antstreet/pull/64)).

**A gate and a ledger you can trust**
- **A gate the agent can't talk its way past**: checks run in an OS sandbox outside the agent
  (macOS seatbelt; Linux `bwrap`, required in CI), and a product's own value, such as a forged
  `__eq__`, can no longer decide a check's comparison ([#51](https://github.com/kgorle1111/antstreet/pull/51)).
- **Every ledger line signed**, not only your approvals ([#40](https://github.com/kgorle1111/antstreet/pull/40)),
  and an automatic decision is never signed in your name ([#61](https://github.com/kgorle1111/antstreet/pull/61)).
- **`antstreet verify`**: check a run's chain, signatures and saved prompts offline, with no model
  call ([#33](https://github.com/kgorle1111/antstreet/pull/33)).
- **You stay the one who approves**: `antstreet approve` for runs with no terminal
  ([#42](https://github.com/kgorle1111/antstreet/pull/42)), a plugin guard so the agent can never
  approve its own checks ([#38](https://github.com/kgorle1111/antstreet/pull/38)), an approve pane
  inside Claude Code ([#46](https://github.com/kgorle1111/antstreet/pull/46)), and disputes that
  wait for your ruling when there is no terminal ([#63](https://github.com/kgorle1111/antstreet/pull/63)).

**Front doors**
- A [Claude Code plugin](README-technical.md#use-it-from-claude-code)
  ([#27](https://github.com/kgorle1111/antstreet/pull/27)), a read-only
  [MCP server](README-technical.md#use-it-from-any-mcp-client)
  ([#36](https://github.com/kgorle1111/antstreet/pull/36)), and a
  [GitHub Action](README-technical.md#use-it-in-github-actions)
  ([#39](https://github.com/kgorle1111/antstreet/pull/39); one manual step today, B78).

**The build mode (experimental)**
- **`antstreet fund`**: the boss drafts checks, you approve them, and budget-capped worker agents
  build until the gate says pass. Not shown to build better than one agent (see Experiments).
- **Model dispatch**, opt-in: per-task routes ([#11](https://github.com/kgorle1111/antstreet/pull/11)),
  a cascade that climbs a model tier per verified failure ([#30](https://github.com/kgorle1111/antstreet/pull/30)),
  and a start tier picked from your own past runs ([#49](https://github.com/kgorle1111/antstreet/pull/49)).
- **Optional roles out of beta**: all stay off unless `--roles` names them; the critic is the one
  we suggest, and the judge is advisory and decides nothing
  ([#60](https://github.com/kgorle1111/antstreet/pull/60)).

**Evidence**
- A threat model with a test per row ([docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)), pre-registered
  experiments ([bench/PREREG.md](bench/PREREG.md)), and every result published, negative ones
  included ([bench/results/](bench/results/README.md)): blind35
  ([#16](https://github.com/kgorle1111/antstreet/pull/16)), E3
  ([#29](https://github.com/kgorle1111/antstreet/pull/29)), E4
  ([#53](https://github.com/kgorle1111/antstreet/pull/53)) and E4b
  ([#58](https://github.com/kgorle1111/antstreet/pull/58)).

## Now

In progress or up next, each in its own pull request.

- **The Python module renamed** from `boss` to `antstreet` (B100). The `boss` command, `.boss/`
  run folders and existing ledgers keep working.
- **`antstreet` on PyPI**, so nothing needs a clone (B41).
- **Check strength**: shows which checks would catch a broken change. Each sealed check is run
  against deliberately broken copies of the changed code (mutation testing); a check that passes
  them all is flagged as weak before you spend time on it.
- **Approval as a few yes/no questions**: instead of reading test code, you answer the questions
  where the request is ambiguous ("Should an empty string raise?"). Your answers become checks or
  waivers, signed like any approval.

## Next

- **A one-command, zero-install audit**: `uvx antstreet audit` in any Python repo, once the
  package is on PyPI.
- **A Claude Code Stop hook** that runs `audit check` when the agent says it is done, so an
  in-session "done" gets a verdict from checks it never saw.
- **CI export** (`audit export`, B78): carry a sealed run to CI so the GitHub Action needs no
  manual step.
- **First run**: a short `--help`, a timed fresh-machine run published in the README, a first-run
  guide, and a few good first issues.
- **Evidence**: a new task-set version that fixes the defects an eval audit found, keeping old
  results reproducible, and the false-pass audit's scripts committed.

## Later

- **The Agent Honesty Report (PLANNED).** A pre-registered public measurement of how often coding
  agents pass their own tests while hidden checks fail: same tasks, same prompt, hidden checks
  validated against a reference, every cell published with intervals. No numbers exist yet, and
  none will be quoted before the run.
- **A PR bot for agent pull requests**: a verdict and check strength as a comment on pull requests
  that coding agents open.
- **TypeScript** (vitest or jest), if there is demand for it.
- **Cascade dispatch as the default, after launch and only with the numbers.** Today it is opt-in
  (`--dispatch cascade`). It becomes the default only once E6 shows it lowers the cost per
  delivered task at no loss of delivery (B101).
- **Autopilot mode** (opt-in): an LLM judge reviews the drafted checks in your place. It unlocks
  only after the judge agrees with human labels on a calibration set; the ledger then says
  "approved by autopilot" (never by you), and the gate still decides pass or fail with plain code.
- **E7: does `audit` catch false "done" claims?** Recall against hidden checks, pre-registered
  before it runs.
- **Back on the bench**: `--spec` mode (B85) and parallel building (B04, B53), each improved and
  re-measured before it becomes more than an option.
- **An external benchmark**, NL2Repo-Bench, easy tasks first (B54).
- **A live cost kill-switch** that stops a slice mid-stream at its cap (B13), once the stream
  reports a reliable per-message cost; we won't ship one built on guessed prices.
- Public-key (Ed25519) signatures on seals and verdicts, so anyone can verify them without the key
  (B80).
- An audit store held by another OS user or a container (B84), and a gate that adversarial code
  can't forge (B19).

## Experiments: we publish the no

Each rule is fixed in [bench/PREREG.md](bench/PREREG.md) before the run. "Not shown" means the
paired 95% interval did not clear the bar.

| Id | Question | Status |
|---|---|---|
| E1 | Do held-out checks from a separate examiner cut false passes? | **Not shown.** Caught 0 of 17 ([write-up](bench/results/2026-10-03-heldout3-and-nl2repo/README.md)) |
| E2 | Strong planner, cheap builders: cheaper per delivered task? | Pre-registered, not run |
| E3 | Are parallel waves faster on multi-file work? | **Not shown.** 0.80x against a 1.3x bar ([write-up](bench/results/2026-10-05-e3-parallel/README.md)). Re-run planned after the planner learns to split |
| E4 | Does a fresh-context critic beat self-review? | **Not shown** (positive trend; see [write-up](bench/results/2026-10-07-e4-critic/README.md)) |
| E4b | The same critic with room to finish: does it beat self-review? | **Not shown, by the slimmest margin; strongest positive trend so far** (+0.0952 [-0.0000, +0.1905]; 70% delivered against 61%, about 1.56x the cost per delivered task; see [write-up](bench/results/2026-10-07-e4b-critic/README.md)) |
| E5 | Is the firm more reliable across five runs? | Pre-registered, not run |
| E6 | Does dispatch lower cost per delivered task? | Pre-registered, not run |
| E7 | Does `audit` catch false "done" claims? | Planned, not yet pre-registered |
| Honesty Report | How often do coding agents pass their own tests while hidden checks fail? | Planned, not yet pre-registered |
| Spec | Does `--spec` make the boss write stronger checks? | **First test missed its bar** ([write-up](bench/results/2026-10-03-spec-p1/README.md)); the larger run waits on a better draft |

The result we lead with is a loss. On a blinded 35-task run, a team of agents delivered 64 of 105
against one agent's 62 of 105, at about 2.4 times the cost, and the difference is not shown. So we
don't claim a team builds better. What AntStreet adds is verification and control, which is why
the audit is the front door. [Write-up](bench/results/2026-10-03-blind35/README.md).

## Not doing

- **Selling "a team of agents builds better."** We measured it and it didn't.
- **An LLM judge deciding pass or fail.** Tests decide.
- **A model reading the audited agent's own words.** That's a channel to the verdict (B81).
- **Quoting a catch rate** before one is measured on real repositories.
- **Turning the Honesty Report into a vendor attack**: it reports cells and intervals, not verdicts
  on companies.
- **Multi-user, SSO or hosted use for now**, deploying built products, or native Windows.

## Help build it

- **Try it**: run the [quickstart](README.md#-quickstart) on a repo of yours and tell us where it
  broke.
- **Contribute**: read [CONTRIBUTING.md](CONTRIBUTING.md), then pick a benchmark task, a sharper
  check, or an `open` row in [docs/BACKLOG.md](docs/BACKLOG.md).
- **Argue with a number**: open an issue naming the number and the file it comes from.
- **Star the repo** if you want agents that show their work. It helps other people find it.

Security problems go through [SECURITY.md](SECURITY.md), not a public issue.
