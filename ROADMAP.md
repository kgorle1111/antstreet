# AntStreet roadmap

**North star.** An open-source tool that makes AI coding agents prove their work: you approve the
checks before the agent runs, the agent never sees them, and a gate outside the agent decides.
It has to work the first time, be easy to start (two commands, no config), and every claim it makes
has to be checkable by you.

This page says what is shipped, what is being built, what comes after, and what was measured and
dropped. It promises no dates. Item ids (`B..`) point at [docs/BACKLOG.md](docs/BACKLOG.md), which
holds every deferred item with its reason and status.

## Where things stand

Shipped on `main` (pre-release; nothing is on PyPI yet):

- **The gate and the ledger.** Checks you approve run in a sandboxed gate outside the agent (macOS
  seatbelt; Linux `bwrap`, run and required in CI). Every dollar and decision goes on a
  hash-chained ledger; your approvals are signed. See [How it works](README-technical.md#how-it-works)
  and the [threat model](docs/THREAT_MODEL.md).
- **`antstreet fund`**: an LLM boss drafts checks, you approve them, budget-capped workers build,
  the gate grades. Quickstart: [README.md](README.md#-quickstart).
- **`antstreet audit`**: seal checks for a change request before any agent starts, then test the
  agent's commit against them. [Audit an agent's "done"](README-technical.md#audit-an-agents-done).
- **`antstreet verify`**: an offline integrity check of a run's ledger, with no model call
  ([docs/CLI.md](docs/CLI.md)).
- **A Claude Code plugin** (the repository is its own marketplace):
  [Use it from Claude Code](README-technical.md#use-it-from-claude-code).
- **A read-only MCP server** (`antstreet mcp`):
  [Use it from any MCP client](README-technical.md#use-it-from-any-mcp-client).
- **A GitHub Action** that runs `antstreet audit check` on a pull request, with one manual step
  (B78): [Use it in GitHub Actions](README-technical.md#use-it-in-github-actions), [action.yml](action.yml).
- **`--dispatch rules` and `--dispatch cascade`**, both off by default until E6 says otherwise.
- **Six pre-registered experiments** and every result so far, including the negative ones:
  [bench/PREREG.md](bench/PREREG.md), [bench/results/](bench/results/README.md).

## Now

Being built, each in its own pull request.

**Plug-and-play front doors**
- `antstreet approve`: approve a term sheet when there is no terminal, so `fund` works from inside
  Claude Code without losing a paid draft ([#42](https://github.com/kgorle1111/antstreet/pull/42)).
- A plugin guard so the agent can never approve its own checks
  ([#38](https://github.com/kgorle1111/antstreet/pull/38), after #42).
- An approve pane inside Claude Code that times each approval, to measure the slowest step
  ([#46](https://github.com/kgorle1111/antstreet/pull/46), draft).
- A PyPI release, so `uvx antstreet ...` works without a clone (B41).

**Verification core**
- Every ledger line signed, not only your approvals
  ([#40](https://github.com/kgorle1111/antstreet/pull/40)).

**Evidence**
- E4, a fresh-context critic against self-review: runs in progress, no result yet.

## Next

**Verification core**
- Audit runs the checks in the repository's own environment, so a check that imports a
  third-party package is not "blocked" (B77).
- Audit any agent's branch in one command, with the checks shown as plain-English lines.
- A Stop hook that calls `audit check`, so an in-session "done" gets a verdict.
- `audit export`, so the GitHub Action needs no manual step (B78).
- Put the delivered product where you expect it (a copy into the project, refused on a dirty tree).

**Plug-and-play**
- A short `--help` for first runs: advanced `fund` flags and experimental commands hidden.
- A timed fresh-machine run of the two-command path, from PyPI, published in the README.

**Security**
- `antstreet doctor --mods`: warn when an installed Claude Code mod can override the plugin's guard.
- Deny the agent reads of the sealed audit store, and alert on edits to `.boss/`.
- Repository hygiene: Dependabot, and a release workflow with PyPI trusted publishing.

**Evidence**
- A new task-set version that fixes the defects an eval audit found (one wrong check and reference
  in `tokenbucket`, unenforced "must not use" rules, two over-specified checks), as a new version
  so earlier results stay reproducible.
- Grading that holds under load: timeouts reported apart from failures, explicit time budgets for
  scale checks.
- The false-pass audit's scripts and per-cell labels committed next to its write-up.
- An eval of the product's own claim: injected wrong products, and the catch rate of each layer
  (boss checks, held-out checks, a human reading the checks).
- E5 (reliability across runs) and E6 stage 1 (dispatch), as pre-registered.

**Docs and contributors**
- A first-run guide, issue and pull-request templates, and a few good first issues.

## Later

- Dispatch on by default, only if E6 shows a lower cost per delivered task at equal delivery
  (B101).
- Optional roles (critic, tester and others) out of "experimental", only if E4 or a later
  experiment shows a gain (B33, B97).
- Public-key (Ed25519) signatures on seals and verdicts, so anyone can check them without the key
  (B80).
- An audit store another OS user or a container holds, so a same-user agent cannot read it (B84).
- A check that cannot forge its own verdict even with adversarial code (B19; accepted today as T12).
- An external benchmark, NL2Repo-Bench, easy tasks first (B54).
- Renaming the Python module from `boss` to `antstreet` (B100).

## Experiments

Fixed in [bench/PREREG.md](bench/PREREG.md) before any run. "Not shown" means the paired 95%
interval did not clear the bar, whatever the point estimate.

| Id | Question | Status |
|---|---|---|
| E1 | Do held-out checks from a separate examiner lower the false-pass rate? | **Not shown.** They caught 0 of 17 false passes ([write-up](bench/results/2026-10-03-heldout3-and-nl2repo/README.md)) |
| E2 | Is a strong planner with cheap builders cheaper per delivered task? | Pre-registered, not run |
| E3 | Are parallel waves faster on multi-file work? | **Not shown.** 0.80x against a 1.3x bar ([write-up](bench/results/2026-10-05-e3-parallel/README.md)) |
| E4 | Does a fresh-context critic beat self-review? | Running; no result yet |
| E5 | Is the firm more reliable across five runs? | Pre-registered, not run |
| E6 | Does per-task dispatch (and the `cascade` arm) lower cost per delivered task? | Pre-registered, not run |

Also published: the blinded 35-task comparison of the firm against one agent (64 of 105 against
62 of 105, not shown, at about 2.4 times the cost; [write-up](bench/results/2026-10-03-blind35/README.md)),
and the false-pass audit (29 of 77 runs that passed every visible check failed a hidden one; 16 of
77 under a stricter count; [write-up](bench/results/2026-10-03-false-pass-audit/README.md)).

## Not planned, or cut

| Item | Why |
|---|---|
| Selling "a team of agents builds better" | Not shown on the blinded 35-task run, at about 2.4 times the cost. `fund` stays as a way to run the gate, not the pitch |
| Parallel multi-file speed as a feature claim | E3 not shown |
| `--spec` on by default | Its paid draft test missed its pre-registered bar ([write-up](bench/results/2026-10-03-spec-p1/README.md)); it stays off |
| An LLM judge deciding pass or fail | Tests decide. Judges stay advisory and uncalibrated until labelled |
| A model reading the audited agent's own words | It would give the agent a channel to the verdict (B81) |
| Killing a slice mid-stream on an estimated cost | The stream carries no reliable per-message cost (B13) |
| A leaderboard of other vendors' agents | Terms of service and cost per run |
| A web UI, deploying built products, Windows | Out of scope; macOS and Linux only |

## How to contribute

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. Good places to start: a new benchmark task, a sharper
check for an existing one, or an `open` row in [docs/BACKLOG.md](docs/BACKLOG.md) (say which id in
your pull request). To argue with a result, open an issue that names the number and the file it
comes from. Security problems go through [SECURITY.md](SECURITY.md), not a public issue.
