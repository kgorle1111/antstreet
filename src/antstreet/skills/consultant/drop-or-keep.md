---
name: drop-or-keep
version: 1
description: Choose drop or keep and a calibrated confidence for a disputed check.
---
Both errors cost the investor. Dropping a right check weakens the gate: a wrong build can pass.
Keeping a wrong check makes a correct worker fail and be replaced. Decide on the idea, not on
which error feels safer.

Recommend `drop` when either holds:
- the idea's rules give a different value than the check expects (typo, invented rule, wrong
  order of rules); quote the rule that gives the different value;
- the idea does not state what the check demands at all (an error message, a format, a default),
  so a correct build could not know it; quote the nearest fragment.

Recommend `keep` when the idea states what the check demands and the check's expected value is
what the rules give. If a reading of the idea makes the check pass and another does not, and the
idea does not choose, that is not `keep`: the check demands something unstated, so `drop` with
`low` confidence.

Confidence
- `high`: you derived the expected value from a quoted rule, there is one fair reading, and your
  trace and the check disagree (or agree) on a specific character or number.
- `medium`: the derivation is sound but rests on a reading of one ambiguous phrase, or the
  check asserts several things and only some were traced.
- `low`: the idea is vague on this point, you cannot derive the value, or the dispute reason is
  the only evidence.

Do not report `high` for a `drop` that rests on "the idea does not mention it" unless the idea
is short enough that you have read every sentence for it.
