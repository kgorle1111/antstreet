---
description: One-line state of an AntStreet run in this project (last event, checks passing, spend), read from its verified ledger
argument-hint: [run id, default the latest]
allowed-tools: Bash(uvx antstreet status *)
---

Run `uvx antstreet status $ARGUMENTS` in the project folder. If no run id was given, run
`uvx antstreet status` with no argument; it reads the latest run. A run id is a single word: if the
argument is anything else, do not run the command, say why and stop.

Show the line it prints. Exit 1 means there is no run, or the run's ledger is damaged or does not
verify against the project's investor key: quote the reason and do not touch `.boss/`.
