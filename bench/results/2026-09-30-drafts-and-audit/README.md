# 2026-09-30-drafts-and-audit

Three tools scored on the saved cells of one day's runs: the boss's one-call draft (thinking at the
default and thinking off), the staged draft, and the check auditor. No worker ran. This write-up made
no model call and spent nothing: every number below comes from the tools' own report code
(`boss.bench.drafts.render_table`, `boss.bench.audit.render_report`) run on cells already saved under
`bench/results/raw/`, which is git-ignored. The reports, unchanged, are in the `table-*.md` files here.

`--dry-run` on all four sets of cells showed 0 drafts or audits "to do" before anything was read.

## What was measured

- **Precision** (drafts): a check the task's reference solution fails is wrong. Wrong checks over checks,
  and drafts with any.
- **Recall** (drafts): a known-wrong implementation (a mutant) must fail a sound check. A mutant that fails
  only wrong checks is not killed. Mutants killed over mutants, and drafts that kill every mutant.
- **Auditor precision / recall**: the auditor flags a check (`contradicts` or `unsupported`). A flag is right
  when the reference fails that check. Precision = right flags over flags; recall = wrong checks flagged over
  wrong checks.
- **Task set**: `c130282a6eec5fe8` in every cell, the same as `bench/tasks` at 7db2f78. 17 tasks, 1 draft each.
- **Models**: Haiku for every call (boss, the three staged roles, the auditor).
- **Thinking**: CLI default for the single draft, the staged draft and the auditor; `--boss-thinking 0` for
  the `think0` arm.
- **Prompts** (recorded hashes, the same in both attempts): `term_sheet_v1.md` `feb1d5a65005`, staged
  `90ee5c34a822`, auditor `a54b2db9bd68`. All three match the prompts at 7db2f78.
- **Code that ran**: not recorded in the cells; unknown. What is known: the first attempt of the staged draft and
  the auditor ran before abd6f99 (quote-gate fix). The re-run files are dated 11:49-12:02 local and carry
  `rejected_output.json`, which 4a2b93c added, so the re-run ran at 4a2b93c or later.
- Costs are the CLI's client-side estimates.

## Single-call drafts: thinking default against off

`table-single.md`, `table-single-think0.md`. One draft per task, scored against the reference and the mutants.

| | default | thinking off |
|---|---|---|
| Scored / invalid / failed | 16 / 1 / 0 | 16 / 0 / 1 |
| Mean cost per draft | $0.1009 | $0.0322 |
| Checks per draft | 7.8 | 8.0 |
| Wrong checks | 2 of 124 (1.6%) | 7 of 128 (5.5%) |
| Drafts with a wrong check [95% CI] | 2/16 = 12% [3-36%] | 5/16 = 31% [14-56%] |
| Mutants killed | 40 of 61 (66%) | 36 of 61 (59%) |
| Mutants failing only wrong checks | 2 | 10 |
| Drafts that kill every mutant [95% CI] | 5/16 = 31% [14-56%] | 5/16 = 31% [14-56%] |

- Thinking costs 3.1 times as much per draft. The wrong-check intervals overlap, so this does not show it
  writes fewer wrong checks.
- The tool prints no interval for the check or mutant counts; none is invented here.
- The two arms did not score the same 16 tasks. Default lost `wildcard` (one check had a syntax error, line 14
  `expected ':'`). Thinking off lost `workdays` (the call crashed; its $0.085 is counted). This is not a paired
  comparison.

## Staged drafts (product manager, system designer, tester)

`table-staged.md`. 17 cells: **4 scored, 12 invalid, 1 failed.** Mean cost $0.1570 per call over the 16 calls
of known cost; the 1 unknown-cost call is the `lrucache` timeout.

- Cost per scored draft: the 4 scored cells cost $0.20 each. Counting the refused calls too, the 16 measured
  calls cost $2.51, which is $0.63 per scored draft. The single-call draft costs $0.107 per scored draft.
- The 4 scored drafts: 1 wrong check of 48, 13 of 16 mutants killed, 2 of 4 kill every mutant
  [15-85%]. Four drafts say nothing about whether staged checks are better than one-call checks.
- The 1 failed cell is `lrucache`: the product manager call hit the 300 s timeout. Cost unknown.
- **Why the 12 invalid were refused.** Every one was refused by the product manager's own gate, so the system
  designer and the tester never ran for these 12. Read from each cell's `detail` and its
  `rejected_output.json` (32 problems in 12 cells), each quote compared with the task's `idea.md` by hand:

| Reason | Problems | Cells | Example quote |
|---|---|---|---|
| Quote trims a sentence (drops a parenthetical or its tail) or re-joins its parts | 7 | calc, intervals, matrixops, semver | "the part `0` alone is fine (`0.0.0` is valid)" (the idea goes on: ", 01.2.3 is not)") |
| Quote stitches separate parts of the idea together without `...` | 7 | csvline, jsonpointer, semver, toposort, workdays | "`01.2.3` is not" valid and "must not have leading zeros" |
| Quote has words that are not in the idea, or reorders them | 5 | csvline, jsonpointer, linediff | "an empty list [raises ValueError]" |
| Quote rewrites one item of a list sentence | 8 | tokenbucket, semver | "rate must be greater than 0, otherwise ValueError is raised" (the idea: "rate, capacity and cost must be...") |
| Gate length rule on a short or elided quote | 2 | csvline | a quote of 5 characters; an elision piece of 1 character |
| **Gate refuses a verbatim quote** | 1 | wildcard | "`[...]` is a set." |
| More than 16 criteria (18 and 17) | 2 | duration, toposort | "at most 16 criteria in all, has 18" |

- A cell can have several problems, so the cell column does not sum to 12. Of the 32 problems, 29 are "not a
  fragment of the idea", 1 is a quote under 8 characters and 2 are criteria counts.
- The `wildcard` refusal is a gate bug, not a model error: the quote is word for word in the idea, but its literal
  `...` inside `[...]` is read as an elision, and the piece `[` is under 4 characters. It was that cell's only
  problem; the designer and tester never ran, so what would have followed is unknown.
- The other 31 problems are the model's output or a gate rule working as written.
- **Usable today: no.** 4 of 17 tasks get a staged draft (24%). 12 of 17 are paid for and refused ($1.71 spent
  on them). The staged draft stays off.

## Check auditor (Haiku)

`table-audit.md`. 34 saved drafts (pilot 17, rerun1 17). **24 audited, 3 rejected, 7 failed.**

| | |
|---|---|
| Checks audited | 191, of which 11 are wrong (6% base rate) |
| Flags | 8 (0.3 per audit), all `contradicts`, none `unsupported` |
| True / false positives, false negatives | 8 / 0 / 3 |
| Precision [95% CI] | 8/8 = 100% [68-100%] |
| Recall [95% CI] | 8/11 = 73% [43-90%] |
| Mean cost per audit (tool) | $0.0672 over 34 calls |
| Cost per call that ran | $0.0846 over the 27 audited or rejected calls |

- The 7 failed cells (rerun1: intervals, jsonpointer, justify, linediff, semver, tokenbucket, workdays) ended as
  `usage_limit`. They are saved with cost 0, never retried, and not the auditor's fault. They pull the tool's mean
  down; the $0.0846 leaves them out.
- The 3 rejected cells (pilot: bigdecimal, duration, workdays) failed the quote gate again after the fix.
- What the tool says these numbers can support (printed in `table-audit.md`): recall rests on 11 wrong checks and
  is a rough figure, 47 points wide; the intervals treat checks as independent and the real uncertainty is wider;
  precision is a lower bound; the numbers cannot support letting the auditor decide anything, so it stays advisory.
- The 11 wrong checks are 9 from pilot drafts and 2 from rerun1 drafts; only 10 of rerun1's 17 drafts were audited.

## The first attempt against the re-run

Both fixes landed in abd6f99: the quote comparison ignores backticks and quote marks and accepts `...`, and the
product manager's cap went from $0.15 to $0.30. The first attempt's cells are kept in
`bench/results/raw/superseded-2026-09-30-quote-gate/`.

| | First attempt | Re-run |
|---|---|---|
| Staged scored (of 17) | 2 (roman, slugify) | 4 (adds bigdecimal, justify) |
| Staged, 15 cells re-run | 9 invalid, 6 capped | 2 scored, 12 invalid, 1 timeout |
| Auditor audited (of 34) | 15 | 24 |
| Auditor, 19 cells re-run | 19 rejected | 9 audited, 3 rejected, 7 failed (`usage_limit`) |

- Rescued: 2 of the 15 staged cells (13%) and 9 of the 19 auditor cells (47%).
- The 5 staged cells that were capped at $0.15 now run to the end and are refused by the gate instead: the cap
  change moved them from "failed" to "invalid". The cap change and the quote fix cannot be told apart in
  this data for the staged draft.
- The auditor has no cap change and the same prompt hash in both attempts, so its 9 rescued cells are the quote
  fix's, as far as the recorded settings show.

## Spend

Sum of `cost_micros` of every saved cell. Unknown cost is counted separately, never as 0.

| Arm | Attempt | Cells | Measured cost | Unknown-cost cells |
|---|---|---|---|---|
| Single, default thinking | one | 17 | $1.7146 | 0 |
| Single, thinking off | one | 17 | $0.5467 | 0 |
| Staged | first (17 cells: 15 superseded + roman, slugify kept) | 17 | $2.6284 | 0 |
| Staged | re-run (15 cells) | 15 | $2.0648 | 1 (`lrucache`, timeout) |
| Auditor | first (34 cells: 19 superseded + 15 kept) | 34 | $2.6316 | 0 |
| Auditor | re-run (19 cells) | 19 | $1.0332 | 0 (7 recorded as 0: `usage_limit`) |
| **All** | | **119** | **$10.6193** | **1** |

In the staged re-run folder, the 12 invalid cells cost $1.71 and the failed cell's cost is unknown. In the auditor
re-run folder, the 3 rejected cells cost $0.17 and the 24 audited cells $2.11.

## What this decides

- **Thinking stays at the default for the boss's draft.** It costs 3.1 times as much ($0.101 against $0.032) and
  2 of 16 drafts had a wrong check with it on against 5 of 16 with it off, but the intervals overlap ([3-36%] and [14-56%])
  and the two arms lost different tasks. Not supported: a claim that thinking writes better checks.
- **The auditor can ship as an advisory note, not as a decision-maker.** 8 of 8 flags were wrong checks against a
  6% base rate, at 0.3 flags a draft and about $0.085 a call. Not supported: its recall (8 of 11, [43-90%]); 7 of 34
  drafts were never audited; and nothing here lets it overrule a person.
- **The staged draft stays off.** 4 of 17 tasks scored; 12 were refused at the first role for a quote the gate
  would not take (29 of 32 problems); $0.63 per scored draft against $0.107. Not supported: whether its checks
  are better, from 4 drafts.
- **Fix the quote handling before another staged run.** One of 32 refusals is a gate bug (`[...]`); the rest are the
  model re-writing the idea. A re-run at the mean cost of the last one would be about $2.1 and would make model calls.
