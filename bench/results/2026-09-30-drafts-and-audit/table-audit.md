# Check auditor (Haiku) on 34 saved drafts: the re-run

Drafts from the `pilot` and `rerun1` runs (`bench/results/raw/audit-haiku`). 19 of the 34 cells were re-run on 2026-09-30 after the quote-matching gate fix, and the 7 of those that ended on the usage limit were retried on 2026-10-02. No model call was made to produce this page.

Task set: c130282a6eec5fe8 | Prompt: a54b2db9bd68 | Model: haiku | Thinking tokens: None

| calls | audited | rejected | failed | checks/audit | mean cost/audit | unknown-cost |
| --- | --- | --- | --- | --- | --- | --- |
| 34 | 27 | 7 | 0 | 7.9 | $0.0812 | 0 |

Truth: a check is wrong when the task's reference solution fails it. A flag is a verdict of contradicts or unsupported.
- checks: 214, wrong (truth): 12 (6%)
- flagged: 9 (0.3 per audit)
- true positives 9, false positives 0, false negatives 3
- precision (flag is a wrong check): 9/9 = 100% [70-100%]
- recall (wrong check is flagged): 9/12 = 75% [47-91%]

| verdict | checks | of which wrong | share wrong | share of all wrong |
| --- | --- | --- | --- | --- |
| consistent | 205 | 3 | 1% | 25% |
| contradicts | 9 | 9 | 100% | 75% |
| unsupported | 0 | 0 | n/a | 0% |

| source | audits | checks | wrong | flagged | TP | FP | FN | excluded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pilot | 14 | 111 | 9 | 7 | 7 | 0 | 2 | 3 |
| rerun1 | 13 | 103 | 3 | 2 | 2 | 0 | 1 | 4 |

What these numbers can support:
- Recall rests on 12 wrong checks and precision on 9 flags. The intervals treat every check as independent; the checks of one draft share an idea and a boss, so the real uncertainty is wider.
- With only 12 wrong checks, recall is a rough figure: its 95% interval is 44 points wide, and one more or fewer wrong check found moves it by 8 points. It cannot rank two prompts or models that differ by less than that.
- Base rate: 6% of checks are wrong, which is the precision of flagging at random. The investor reads every check anyway, so an opinion earns its cost only if its flags are far likelier to be wrong than that base rate, at a number of flags per draft (now 0.3) the investor will read.
- A false positive is a flag on a check the reference passes. Such a check can still demand something the idea does not state (the reference may happen to do it), which this ground truth cannot see, so precision here is a lower bound on how often a flag is right.
- 7 rejected (paid for, failed the gate) and 0 failed audits are excluded from every rate; a high rejection rate means those drafts got no opinion.
- These numbers cannot support letting the auditor decide anything: it stays advisory.
