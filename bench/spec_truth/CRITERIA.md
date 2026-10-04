# Offline evaluation of the spec layer: criteria fixed before the run

Written and committed before `python -m boss.bench.spec_eval` was run on any saved cell. The
splitter and the anchor extraction are frozen at the commit that adds `src/boss/spec.py`
(`SPLITTER = "v1"`). If either is changed after the numbers are seen, the result is for a new
splitter version and is reported as such, not as a pass of these criteria.

No model call is made. Nothing here is a paid run.

## What is measured

- **Drafts**: every saved draft of the 17 original tasks (task set hash `c130282a6eec5fe8`) in
  `final3`, `heldout3`, `pilot`, `rerun1`, `drafts-single` and `drafts-single-think0` under
  `bench/results/raw/`: a folder named `checks` holding `test_*.py`. Not `superseded-*`, not the
  staged drafts, not the 18 later tasks (no labels yet).
- **Flagged rule** (union form, because old drafts carry no claims): a scored rule that has at least
  one anchor, where at least one anchor appears in no check of the draft.
- **Labels**: `bench/spec_truth/<task>.json` maps each hidden check to the rules it tests, by hand.
  A mutant's violated rules are the rules of the hidden checks that fail on it.
- **Mutants**: the hand-written ones only. Mutants harvested from earlier runs (names starting
  `pilot`, `rerun`, `final`, `heldout`) were built against these drafts and are excluded.
- **Known omissions**: the 15 `final3` firm cells with a failing hidden check, except `wildcard`
  rep 1 (class b in `2026-10-02-why-the-firm-loses`, a wrong boss check).

## Criteria

| Step | Question | Pass when |
|---|---|---|
| O1 | Is the splitter sound? | Every property holds on 100% of the 59 ideas and of their numbering-stripped copies (offsets reproduce the text, rules ordered and disjoint, no empty rule), and the sentence count is at most 40 in at least 95% of the ideas |
| O2 | Are the labels trustworthy? | Reported: the automatic proposer's top-1 agreement with the final hand labels. If under 70%, every file was hand-labelled (it was) and the proposer is not used |
| O3 recall | Does the free verifier find the known omissions? | At least 60% of the 15 known-omission cells (9 of 15) have at least one flagged rule that is a rule of one of their failing hidden checks |
| O3 burden | Is the list short enough to read? | Median flagged rules per draft is at most 4 |
| O4 | Is anchor-present predictive of killing? | Over (draft, rule, mutant) triples where the rule has an anchor and the mutant violates the rule: kill rate with all anchors present minus kill rate with an anchor missing is at least 25 points, with at least 40 triples on each side |
| O5 | How noisy are flags? | Reported only: the share of flags on rules whose hidden checks every saved product of the task passes |

## Reading the result

- O3 recall and O4 both pass: the deterministic part is worth building into `boss fund` (branch B).
- O3 passes and O4 fails: anchors find omissions but do not predict kills; keep the structural
  checks, drop the anchors from the headline.
- O3 recall fails: the design needs another idea before any prompt work.
- O3 burden fails: tighten what counts as an anchor before showing flags to a person.

Priors, recorded before running (to be scored in the calibration log): O3 recall passes, 65%;
O3 burden passes, 60%; O4 passes, 50%.

## Limits stated in advance

- Union form: a draft gets credit for an anchor present in any of its checks, even one that does not
  test that rule. It understates what claim-level checking would flag.
- O4 counts a mutant as killed by any check of the draft, not by a check that claims the rule.
- Triples share drafts, rules and tasks, so the sample is not independent; the intervals are
  Wilson intervals over triples and are too narrow.
- The benchmark ideas have numbered rule lists and strict wording; a vaguer request splits worse.
