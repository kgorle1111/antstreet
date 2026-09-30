# Security policy

What `boss` protects, what it does not, how to report a problem, and which versions get fixes.
`tests/test_docs_security.py` fails when this file and the code or the threat model disagree.

The full list of threats, controls and the test behind each is in
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## What it protects

- **Checks cannot be edited by a worker.** They live outside every workspace and are copied fresh
  into each gate run.
- **Only the gate says "passed".** A check passes only when pytest exits 0 and its test report shows
  at least one test and no failures. A worker's own "done" is a note.
- **A worker has three tools and one folder.** `Read`, `Write` and `Edit`, each limited to its own
  workspace. No shell. A worker is refused if the CLI reports any other configuration.
- **Secrets stay out of workers, checks and logs.** A worker or boss process gets only `HOME`,
  `PATH`, `USER`, `LANG`, `TMPDIR` and `CLAUDE_CONFIG_DIR` from your environment, plus
  `ANTHROPIC_API_KEY` when you set one. Checks get a smaller set. Known secrets and credential
  shapes are masked in logs, the ledger and reports.
- **Approval is bound to content.** Hashes of the term sheet and every check file are verified
  before each slice and each gate run. Editing either afterwards stops the run.
- **Spend is bounded twice.** A reserve is held back from every slice cap, and hard limits stop a
  run at 60 slices, 16 workers, or spend past its rounds' budgets plus one reserve each.
- **A worker's words are treated as data.** They are stored with control characters made visible
  and a length limit, and quoted, never obeyed, when handed to a replacement.

## What it does not protect

- **`boss` is not a sandbox.** The gate runs the code a worker wrote on your machine, as you, with a
  filtered environment and a timeout. Do not run ideas from sources you do not trust.
- Prompt-injection resistance of the models is not measured. The controls limit what an injected
  instruction can do, not whether the model follows it.
- The `claude` CLI's own behaviour (path rules, `--safe-mode`, the budget cap) was verified by
  recorded probes, not by a test that calls the real CLI. A CLI upgrade can change it.
- Using an API key (`--bare` mode) has not been run against the real CLI.
- Cost figures are the CLI's estimates, not a bill.
- Not in scope: multi-user machines, hosted use, an attacker who can already write to your run
  folder or your environment.

Risks accepted in the threat model, with what would change each:

| Id | Risk | Status |
|---|---|---|
| T12 | Code written to defeat the gate can fake a pass | `accepted` |
| T13 | The gate runs worker-written code on the host | `accepted` |
| T14 | Check code runs during validation, before you have read it | `accepted` |
| T29 | Anyone who can write the ledger can forge an approval | `accepted` |
| T36 | A hostile `claude` binary on `PATH` or in `BOSS_CLAUDE_BIN` | `accepted` |
| T37 | A worker can fill the disk or CPU within the time and money caps | `accepted` |

## Reporting a problem

- Open a private security advisory on this repository (the Security tab, then "Report a
  vulnerability"). Do not put details in a public issue or pull request.
- No email address is published for reports.
- Say what you ran (the commit, the command, the idea if it matters), what you expected, and what
  happened. Remove any API key, token or private path first.
- There is no response-time promise: this is pre-release software.

## Supported versions

| Version | Supported |
|---|---|
| 0.0.1 (not released; the `main` branch) | Fixes land on `main` only |

`boss` needs Python 3.12 or newer and the `claude` CLI 2.1.277 or newer. `boss doctor` and the
check on every worker's start refuse an older CLI.
