---
name: only-what-the-idea-states
version: 1
description: Assert only what the idea states; a wrong check fires a correct worker.
---
A check that fails a correct implementation is worse than no check: the worker is blamed, retried
and paid again. Before each assert, ask: which words of the idea say this must be true?

Things the idea usually leaves open, and so you must not assert:
- Exact wording of error messages. Assert the exception type only when the idea names it, and use
  `pytest.raises(ValueError)` without `match=` unless the message is quoted in the idea.
- Which of several valid answers is returned (ordering of equal items, which duplicate is kept),
  unless the idea says.
- Exact container types: `list` versus `tuple`, `set` versus `frozenset`. Compare with the type
  the idea gives, and compare contents, not identity.
- Float results to full precision. Use `pytest.approx` unless the idea gives an exact value.
- Whitespace, case and punctuation of text results, unless the idea states the format.
- Behaviour on inputs the idea never mentions: None, negative numbers, non-ASCII text.
- Performance, memory, and the internal names or files the builder chose.

Where to get expected values:
1. The idea's own examples, copied exactly, are the safest assertions.
2. A value computed by hand from a stated rule. Compute it twice. If the two results differ, or
   the rule has two readings, drop that case.
3. Never a value computed by running a reference solution you imagined.

If a criterion can only be checked by assuming something the idea does not state, list it in
`untestable` with the assumption as the reason instead of writing a guess.

When the idea gives an example that seems to contradict your reading of a rule, the example wins.
