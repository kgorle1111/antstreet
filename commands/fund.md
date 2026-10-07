---
description: Draft an AntStreet term sheet for an idea, have you approve it yourself with `!`, then build it
argument-hint: <idea in plain words> [--budget 0.40]
allowed-tools: Bash(uvx antstreet doctor) Bash(uvx antstreet fund *) Bash(uvx antstreet resume *)
disable-model-invocation: true
---

The user wants AntStreet to build this idea: $ARGUMENTS

This needs the `antstreet` version with the `approve` command. Approving the term sheet is the
user's act, never yours: do not run `antstreet approve` (or `boss approve`) in any form. A hook in
this plugin denies it; do not try to get around it.

1. Run `uvx antstreet doctor` exactly as written (no `--live`: that flag makes two paid calls). It
   makes no model call. Show its output. If a line failed, give its fix line and stop here.
2. Run `uvx antstreet fund '<idea>' --budget <dollars>` in the project folder, with a Bash timeout
   of 10 minutes.
   - The idea goes in single quotes; write each `'` inside it as `'\''`. An idea that starts with
     `-` is refused by the CLI, so put a word in front of it.
   - Use the `--budget` the user gave. If they gave none, use `0.40` and say that it is real money,
     spent only after they approve the term sheet. The boss's drafting call (a few cents) is spent
     now.
   - Pass through any other `antstreet fund` options the user wrote, unchanged.
3. With no terminal to ask on, `fund` keeps the drafted term sheet unapproved, prints it with every
   check, and exits 4. That is the expected result, not a failure. Show the user the term sheet and
   checks as printed, then the line for them to type at this prompt themselves, with the run id and
   value `fund` printed:
   `! uvx antstreet approve RUN --sheet VALUE`
   The `!` runs it as the user, outside you. A changed sheet or a mistyped value is refused and
   nothing is written. If they do not approve, nothing more is spent. Stop and wait.
4. When the user says they approved, run `uvx antstreet resume RUN` in the background: a build can
   take longer than a Bash timeout. Questions the run asks later (a fix round, a disputed check)
   read end of input here, which is no. If the user wants to answer them, they run
   `uvx antstreet resume RUN` in their own terminal instead.
5. When the run ends, `/antstreet:report` reads the verdict back from the ledger.

Any exit other than 0 or 4 from `fund` means it stopped: show what it printed and stop. Do not edit
anything under `.boss/`: it is the run's signed, hash-chained ledger.
