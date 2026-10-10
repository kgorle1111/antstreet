# AntStreet: tests your coding agent never saw

**AntStreet checks your AI coding agent's work against tests it never saw, so "all tests pass"
actually means something.**

<img src="https://kgorle1111.github.io/antstreet/assets/og.png" alt="AntStreet: checks your AI coding agent's work against tests it never saw." width="100%">

Your agent writes the code *and* the tests, like a student who writes their own exam. AntStreet is
the answer key the student never sees. The AI drafts the checks; you approve them; plain code, not a
model, decides.

## What we measured

29 of 77 runs (38%, 95% interval 28-49%) passed every check the model had written and still failed a
hidden check it never saw (written by Claude, separately from the agents measured). We read all 29
against the task text and judge each a real error; one class is debatable.

Caveats, kept on purpose: 17 small Python tasks, Haiku writing both the checks and the code, and
runs of one task are not independent (resampling tasks widens the interval to 20-57%). 13 of the 29
failed only on non-ASCII input or a returned type; without those, 16 of 77 (21%). These were
AntStreet's own build runs, not a general agent failure rate.

## Install

Needs macOS or Linux, Python 3.12+ and [Claude Code](https://code.claude.com), logged in.

```bash
uvx antstreet --help
# or
pip install antstreet
```

## Audit in three steps

Run these in the Python repo your agent will change (a clean working tree).

```bash
antstreet audit plan --request req.txt   # drafts checks from your request; you approve; they are sealed
# ... any agent works and commits; it never sees the checks ...
antstreet audit check --claim done       # runs the sealed checks on HEAD in a sandbox, signs a verdict
antstreet audit report                   # every verdict, and the false-pass rate
```

A verdict is `refuted`, `unrefuted`, `inconclusive` or `no_claim`.

## What it does, and what it does not claim

- The agent never sees the checks: they are kept in a store outside the repo.
- Only checks that fail on the base commit are counted.
- pytest runs in an OS sandbox (macOS seatbelt, Linux bwrap); every approval and verdict goes on a
  signed, hash-chained ledger.
- It does not show that code is correct. `unrefuted` means no counted check failed, nothing more.
- It checks Python repos only, with checks a model drafted and you approved; weak checks give weak
  verdicts.
- Pre-release (0.0.1). Its build mode, where a boss model runs a team of agents, has not shown a
  benefit in our fair tests; we published that result too.

## Read more

- [Website](https://kgorle1111.github.io/antstreet/)
- [Technical README](https://github.com/kgorle1111/antstreet/blob/main/README-technical.md)
- [False-pass audit (the 29 of 77)](https://github.com/kgorle1111/antstreet/blob/main/bench/results/2026-10-03-false-pass-audit/README.md)
- [Blind 35-task benchmark](https://github.com/kgorle1111/antstreet/blob/main/bench/results/2026-10-03-blind35/README.md)
- [Critic experiment (E4b)](https://github.com/kgorle1111/antstreet/blob/main/bench/results/2026-10-07-e4b-critic/README.md)
- [CLI reference](https://github.com/kgorle1111/antstreet/blob/main/docs/CLI.md)
- [Source and issues](https://github.com/kgorle1111/antstreet)
