---
name: invented-rules
version: 1
description: Tell a rule the idea states from one the check quietly adds.
---
The boss's most common wrong check is a right-looking one that demands something the idea never
said. Ask of every assertion: which sentence of the idea makes this true?

Things a check adds without saying so:
- An exact error message or wording ("match='must be positive'"). If the idea says only that an
  error or exception is raised, the message is `unsupported`. The exception type counts only if
  the idea names it.
- A type or format of the result the idea does not fix: a tuple where the idea says "pair", a
  string where it says "value", a trailing newline, a list ordering the idea leaves open.
- A default: what happens on empty input, None, negative numbers, or a repeated argument, when
  no rule covers it.
- A tie-break or ordering: which item wins when two are equal, if the idea is silent.
- A normalisation the idea does not list: dropping punctuation, trimming, case folding, Unicode
  handling beyond what is stated.
- An extra public name: a function, a class or an attribute the idea does not name.

Deciding between `contradicts` and `unsupported`:
- `contradicts` needs a rule that rules the check out: a sentence that gives another value or
  forbids the behaviour. Quote that sentence.
- `unsupported` is when you cannot point to such a sentence and cannot derive the expected value
  from the rules either. Common sense that the value is "reasonable" is not support.
- An example in the idea is a rule for that input. If the idea's example gives the value, the
  check is `consistent` even if the general rule alone is ambiguous.

A check that asserts several things is judged by its weakest assertion: one invented rule makes
the whole check `unsupported` or `contradicts`, however sound the other lines are.
