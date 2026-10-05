---
description: Check this machine for AntStreet, then hand you the exact `antstreet fund` command to run in your own terminal
argument-hint: <idea in plain words> [--budget 0.40]
allowed-tools: Bash(uvx antstreet doctor)
disable-model-invocation: true
---

The user wants AntStreet to build this idea: $ARGUMENTS

AntStreet's engine must run outside this session: the user approves the term sheet and its checks at
their own keyboard, and `antstreet fund` reads that answer from a terminal. Run from here, the
approval question gets end of input, which counts as reject, after the boss's draft is already paid
for. So do not run `antstreet fund` yourself, by any route.

1. Run `uvx antstreet doctor` exactly as written (no `--live`: that flag makes two paid calls). It
   makes no model call. Show its output. If a line failed, give its fix line and stop here.
2. Write out the one command for the user to paste into a terminal in this project folder:
   `uvx antstreet fund '<idea>' --budget <dollars>`.
   - The idea goes in single quotes; write each `'` inside it as `'\''`. An idea that starts with
     `-` is refused by the CLI, so put a word in front of it.
   - Use the `--budget` the user gave. If they gave none, use `0.40` and say that it is real money,
     spent only after they approve the term sheet, plus the boss's own drafting call (a few cents).
   - Pass through any other `antstreet fund` options the user wrote, unchanged.
3. Tell the user, in two lines: they will be shown the term sheet and every check and asked
   `[a]pprove, [r]eject, or [e]dit`; when the run ends, `/antstreet:report` reads the verdict
   back from the ledger here.

Do not edit anything under `.boss/`: it is the run's signed, hash-chained ledger.
