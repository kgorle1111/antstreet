---
name: antstreet
description: Read the state, board report or ledger check of an AntStreet run in this project (a `.boss/runs/` folder), or explain how to fund an idea with AntStreet. Use when the user asks whether an AntStreet or `boss` run passed, what it cost, or whether its ledger verifies.
allowed-tools: Bash(uvx antstreet status *) Bash(uvx antstreet report *) Bash(uvx antstreet doctor)
---

AntStreet is a CLI (`antstreet`, alias `boss`). The human investor approves a term sheet and its
pytest checks, headless Claude workers build in budget-capped slices, a sandboxed gate decides what
passed, and every decision lands on a signed, hash-chained ledger under `.boss/runs/<id>/`.

This skill only reads what a run recorded:

- `uvx antstreet status [RUN]`: one line, last event, checks passing, spend. Verifies the ledger.
- `uvx antstreet report [RUN]`: the board report. Exit 1 when the run cannot be vouched for.
- `uvx antstreet doctor`: checks this machine can run AntStreet. No model call.

To start a run, tell the user to use `/antstreet:fund <idea>`: it drafts the term sheet, the user
approves it themselves, and then it builds. Never run `antstreet approve` (or `boss approve`) in
any form: approval is the investor's act, and this plugin's hook denies it. When a run is waiting
for approval, tell the user to type `! uvx antstreet approve RUN --sheet VALUE` with the values
`fund` printed. Do not run `fund`, `resume`, `topup`, `audit` or `doctor --live` from this skill:
they spend the user's money. Never edit anything under `.boss/`: the ledger is the record the gate
and the investor's signature vouch for. If a command fails because `uvx` is missing, the fix is
`curl -LsSf https://astral.sh/uv/install.sh | sh`; tell the user, do not run it.
