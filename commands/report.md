---
description: Print the board report of an AntStreet run in this project, computed from its signed ledger
argument-hint: [run id, default the latest]
allowed-tools: Bash(uvx antstreet report *)
---

Run `uvx antstreet report $ARGUMENTS` in the project folder. If no run id was given, run
`uvx antstreet report` with no argument; it reads the latest run. A run id is a single word: if the
argument is anything else, do not run the command, say why and stop.

Show the report as printed. Then, in at most three lines, say whether every check passed
(`Delivered`), what was spent, and anything marked WARNING or `CONTEXT CHECK FAILED`.

Exit 1 means the report could not vouch for the run (no runs, a damaged or unverified ledger, or a
saved prompt that does not match its hash). Say so plainly, quote the line that says why, and do not
try to repair anything under `.boss/`: the ledger is the record, and editing it is what the check
exists to catch.
