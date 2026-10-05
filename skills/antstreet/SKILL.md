---
name: antstreet
description: Read the state, board report or ledger check of an AntStreet run in this project (a `.boss/runs/` folder), or explain how to fund an idea with AntStreet. Use when the user asks whether an AntStreet or `boss` run passed, what it cost, or whether its ledger verifies.
allowed-tools: Bash(uvx antstreet status *) Bash(uvx antstreet report *) Bash(uvx antstreet doctor)
---

AntStreet is a CLI (`antstreet`, alias `boss`). The human investor approves a term sheet and its
pytest checks, headless Claude workers build in budget-capped slices, a sandboxed gate decides what
passed, and every decision lands on a signed, hash-chained ledger under `.boss/runs/<id>/`.

The engine runs outside this session; this skill only reads what it recorded.

- `uvx antstreet status [RUN]`: one line, last event, checks passing, spend. Verifies the ledger.
- `uvx antstreet report [RUN]`: the board report. Exit 1 when the run cannot be vouched for.
- `uvx antstreet doctor`: checks this machine can run AntStreet. No model call.

Never run `antstreet fund`, `resume`, `topup`, `audit` or `doctor --live` yourself: they spend the
user's money or need the user's own approval at a terminal. To start a run, tell the user to use
`/antstreet:fund <idea>`, which hands them the command to paste. Never edit anything under `.boss/`:
the ledger is the record the gate and the investor's signature vouch for. If a command fails
because `uvx` is missing, the fix is `curl -LsSf https://astral.sh/uv/install.sh | sh`; tell the
user, do not run it.
