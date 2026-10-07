# AntStreet roadmap: make AI coding agents prove their work

You approve the checks before the agent writes a line. The agent never sees them. A sandboxed gate
outside the agent decides what passed, and every decision lands on a ledger you can verify. The AI
drafts; you and plain code decide.

## Why it matters

- Agents say "done" and mean "I stopped". In our false-pass audit, **29 of 77 runs (38%)** passed
  every check the model wrote and still failed a hidden check it never saw.
- The caveat, kept on purpose: 17 small Python tasks, one model writing both checks and code, and
  under a stricter count it is 16 of 77 (21%). [Read the audit](bench/results/2026-10-03-false-pass-audit/README.md).
- Either way, "the agent's own tests pass" proves little. Checks it never saw, which you approved,
  prove more.

This page lists what works today, what is being built, and what we measured and dropped. No dates.
Item ids (`B..`) point at [docs/BACKLOG.md](docs/BACKLOG.md), where every item has its reason and
status.

## Shipped

On `main`, pre-release (not on PyPI yet).

- **A gate the agent can't talk its way past.** Your checks run in a sandbox outside the agent
  (macOS seatbelt; Linux `bwrap`, required in CI). [How it works](README-technical.md#how-it-works).
- **A ledger you can check.** Every dollar and decision is hash-chained; your approvals are signed.
  `antstreet verify` checks a run offline, with no model call ([docs/CLI.md](docs/CLI.md)).
- **`antstreet audit`.** Seal checks for a change before any agent starts, then test its commit
  against them. [Audit an agent's "done"](README-technical.md#audit-an-agents-done).
- **`antstreet fund`.** The bull (the boss model) drafts checks, you, the pig, approve them, and
  budget-capped ants build until the gate says pass. [Quickstart](README.md#-quickstart).
- **Three front doors:** a [Claude Code plugin](README-technical.md#use-it-from-claude-code), a
  read-only [MCP server](README-technical.md#use-it-from-any-mcp-client), and a
  [GitHub Action](README-technical.md#use-it-in-github-actions) ([action.yml](action.yml); one
  manual step today, B78).
- **Model dispatch** (`--dispatch rules`, `--dispatch cascade`): start each task on the cheapest
  model that fits, escalate when it stalls.
- **A threat model with a test per row** ([docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)) and
  **pre-registered experiments**, negative results included ([bench/PREREG.md](bench/PREREG.md),
  [bench/results/](bench/results/README.md)).

## Now

Being built, each in its own pull request.

- **Approve from anywhere.** `antstreet approve` for runs with no terminal, so `fund` works inside
  Claude Code without losing a paid draft ([#42](https://github.com/kgorle1111/antstreet/pull/42)).
- **The agent can never approve its own checks.** A plugin guard
  ([#38](https://github.com/kgorle1111/antstreet/pull/38)).
- **Every ledger line signed**, not only your approvals
  ([#40](https://github.com/kgorle1111/antstreet/pull/40)).
- **An approve pane inside Claude Code** that times each approval, so we can fix the slowest step
  ([#46](https://github.com/kgorle1111/antstreet/pull/46), draft).
- **`uvx antstreet` from PyPI**, no clone needed (B41).
- **Cascade dispatch becoming the default** (Haiku, then Sonnet, then Opus when a task stalls). E6
  checks the cost: if the default raises the cost per delivered task, it goes back to opt-in (B101).
- **Optional roles out of "experimental"**: the critic, the tester and the rest (B33). The judge
  stays out of pass/fail until it is calibrated against human labels; tests decide. E4 is measuring
  the critic right now.
- **The Python module renamed** from `boss` to `antstreet`, with `boss` kept as an alias so
  nothing breaks (B100).

## Next

**Audit, sharper**
- Run the checks in your repository's own environment, so a check that imports a third-party
  package isn't blocked (B77).
- Audit any agent's branch in one command, with the checks shown as plain-English lines.
- A Stop hook that calls `audit check`, so an in-session "done" gets a verdict.
- `audit export`, so the GitHub Action needs no manual step (B78).

**Back on the bench: features we cut, now being improved and re-measured**
- **`--spec` mode**: write a rule list before the checks, so each rule gets a check (B85). Its
  first test missed its bar; we are improving the draft, then running the larger firm experiment
  before it becomes more than an option.
- **Parallel building**: several ants on independent files at once (B04, B53). The first test came
  in at 0.80x, mostly because the boss rarely split the work. Next: a planner that splits
  independent modules, then E3 again. No speed claim until that number says so.

**See it, prove it**
- **A web dashboard**: fund, approve and watch runs in a browser. It reads through the same
  read-only paths as the CLI and MCP server, and approving stays a human act.
- **Audit reports for regulated teams**: an exportable, signed record of who approved which checks
  and what the gate decided, to hand to your auditors. AntStreet holds no certification and
  doesn't claim one.

**First run**
- A short `--help`, a timed fresh-machine run published in the README, a first-run guide, and a
  few good first issues.
- `antstreet doctor --mods`, which warns when an installed Claude Code mod can override the guard.

**Evidence**
- A new task-set version that fixes the defects an eval audit found, keeping old results
  reproducible; grading that holds under load; the false-pass audit's scripts committed.
- A catch-rate eval of the product's own claim: plant wrong products, measure what each layer
  catches.
- E5 (reliability across runs) and E6 stage 1 (dispatch cost).

## Later

- **E7: does `audit` catch false "done" claims?** Recall against hidden checks, pre-registered
  before it runs.
- **An external benchmark**, NL2Repo-Bench, easy tasks first (B54).
- **A live cost kill-switch** that stops a slice mid-stream at its cap (B13). Blocked today on a
  reliable per-message cost from the stream; we won't ship one built on guessed prices.
- Public-key (Ed25519) signatures on seals and verdicts, so anyone can verify them without the key
  (B80).
- An audit store held by another OS user or a container (B84), and a gate that adversarial code
  can't forge (B19).
- SSO for the dashboard, if teams ask for it.

## Experiments: we publish the no

Each rule is fixed in [bench/PREREG.md](bench/PREREG.md) before the run. "Not shown" means the
paired 95% interval did not clear the bar.

| Id | Question | Status |
|---|---|---|
| E1 | Do held-out checks from a separate examiner cut false passes? | **Not shown.** Caught 0 of 17 ([write-up](bench/results/2026-10-03-heldout3-and-nl2repo/README.md)) |
| E2 | Strong planner, cheap builders: cheaper per delivered task? | Pre-registered, not run |
| E3 | Are parallel waves faster on multi-file work? | **Not shown.** 0.80x against a 1.3x bar ([write-up](bench/results/2026-10-05-e3-parallel/README.md)). Re-run planned after the planner learns to split |
| E4 | Does a fresh-context critic beat self-review? | Running, no result yet |
| E5 | Is the firm more reliable across five runs? | Pre-registered, not run |
| E6 | Does dispatch lower cost per delivered task? | Pre-registered; stage 1 next |
| E7 | Does `audit` catch false "done" claims? | Planned, not yet pre-registered |
| Spec | Does `--spec` make the boss write stronger checks? | **First test missed its bar** ([write-up](bench/results/2026-10-03-spec-p1/README.md)); the larger run waits on a better draft |

The result we lead with is a loss. On a blinded 35-task run, a team of ants delivered 64 of 105 against one agent's
62 of 105, at about 2.4 times the cost, and the difference is not shown. So we don't claim a team
builds better. What AntStreet adds is verification and control. [Write-up](bench/results/2026-10-03-blind35/README.md).

## Not doing

- **Selling "a team of agents builds better."** We measured it and it didn't.
- **An LLM judge deciding pass or fail.** Tests decide.
- **A model reading the audited agent's own words.** That's a channel to the verdict (B81).
- **A leaderboard of other vendors' agents**, deploying built products, or native Windows.

## Help build it

- **Try it**: run the [quickstart](README.md#-quickstart) and tell us where it broke.
- **Contribute**: read [CONTRIBUTING.md](CONTRIBUTING.md), then pick a benchmark task, a sharper
  check, or an `open` row in [docs/BACKLOG.md](docs/BACKLOG.md).
- **Argue with a number**: open an issue naming the number and the file it comes from.
- **Star the repo** if you want agents that show their work. It helps other people find it.

Security problems go through [SECURITY.md](SECURITY.md), not a public issue.
