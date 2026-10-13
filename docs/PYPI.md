# AntStreet: a fund for AI coding agents

**You bring an idea. A boss model drafts a term sheet of checks, you approve it, and a team of agent
workers builds it in budget-capped rounds. Workers that stop making progress are fired. A sandboxed
gate of plain code, not a model, decides what passed, and every step goes on a signed, hash-chained
ledger.**

Early and experimental: in our published benchmark runs a team has not yet shown a benefit over a single agent;
every result, including the misses, is in
[bench/results](https://github.com/kgorle1111/antstreet/tree/main/bench/results).

<img src="https://kgorle1111.github.io/antstreet/assets/og.png" alt="AntStreet: checks your AI coding agent's work against tests it never saw." width="100%">

The AI drafts; you approve; plain code decides.

## Install

Needs macOS or Linux, Python 3.12+ and [Claude Code](https://code.claude.com), logged in.

```bash
uvx antstreet --help
# or
pip install antstreet
```

## Fund an idea in three steps

```bash
antstreet doctor --live      # checks this machine; two paid calls of at most $0.05 each
antstreet fund "A function is_palindrome(text) that ignores case, spaces and punctuation." --budget 0.40
antstreet report             # the board report for the run
```

1. **Fund.** `fund` asks the boss for a term sheet: tasks, the checks each must pass, and the budget
   split into rounds.
2. **Approve.** You read every check and answer at the prompt. With no terminal (a pipe, CI, Claude
   Code's Bash tool) it waits instead and prints the one `antstreet approve RUN --sheet VALUE`
   command that approves exactly the text shown; `antstreet resume` then builds it.
3. **Build.** Workers build in capped slices until the gate says pass or the money runs out.
   `antstreet verify` re-checks the ledger's hashes and signatures without a model call.

## Audit someone else's change

The same sealed-check engine, applied to a change any agent (or person) makes. Run these in the
Python repo the agent will change (a clean working tree).

```bash
antstreet audit plan --request req.txt   # drafts checks from your request; you approve; they are sealed
# ... any agent works and commits; it never sees the checks ...
antstreet audit check --claim done       # runs the sealed checks on HEAD in a sandbox, signs a verdict
antstreet audit report                   # every verdict, and the false-pass rate
```

A verdict is `refuted`, `unrefuted`, `inconclusive` or `no_claim`.

## What we measured

The fund: on a blinded 35-task benchmark (three runs each, $0.40 a task) the team passed 64 of 105
and one agent 62 of 105; paired by task the delivery benefit was not shown, and the team cost about 2.4
times as much. We do not claim a team builds better, faster or cheaper.

Why sealed checks matter: 29 of 77 runs (38%, 95% interval 28-49%) passed every check the model had
written and still failed a hidden check it never saw (written by Claude, separately from the agents
measured). We read all 29 against the task text and judge each a real error; one class is debatable.

Caveats, kept on purpose: 17 small Python tasks, Haiku writing both the checks and the code, and
runs of one task are not independent (resampling tasks widens the interval to 20-57%). 13 of the 29
failed only on non-ASCII input or a returned type; without those, 16 of 77 (21%). These were
AntStreet's own build runs, not a general agent failure rate.

## What it does, and what it does not claim

- In a fund run, held-out checks (`--held-out`) are never shown to a worker. In an audit, the agent
  never sees the checks: they are kept in a store outside the repo.
- In an audit, only checks that fail on the base commit are counted.
- pytest runs in an OS sandbox (macOS seatbelt, Linux bwrap); approvals, top-ups, verdicts and the
  estimated cost of each model call go on a signed, hash-chained ledger.
- It does not show that code is correct. A pass means no counted check failed, nothing more.
- Python with pytest only, with checks a model drafted and you approved; weak checks give weak
  verdicts.
- Pre-release (0.0.1).

## Read more

- [Website](https://kgorle1111.github.io/antstreet/)
- [Technical README](https://github.com/kgorle1111/antstreet/blob/main/README-technical.md)
- [Blind 35-task benchmark](https://github.com/kgorle1111/antstreet/blob/main/bench/results/2026-10-03-blind35/README.md)
- [Critic experiment (E4b)](https://github.com/kgorle1111/antstreet/blob/main/bench/results/2026-10-07-e4b-critic/README.md)
- [False-pass audit (the 29 of 77)](https://github.com/kgorle1111/antstreet/blob/main/bench/results/2026-10-03-false-pass-audit/README.md)
- [CLI reference](https://github.com/kgorle1111/antstreet/blob/main/docs/CLI.md)
- [Source and issues](https://github.com/kgorle1111/antstreet)
