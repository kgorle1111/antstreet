---
name: acceptance-criteria
version: 1
description: What makes an acceptance criterion checkable by one automated test.
---
A criterion is good when a tester can turn it into one pytest function without asking you
anything. Test yourself: could two testers write checks that disagree about pass or fail? Then
the criterion is vague; rewrite it.

One observable outcome
- `then` names something a test can assert: a return value, a raised exception type, a message,
  a file's content, an exit code. "Works correctly", "handles errors gracefully", "is fast" and
  "is user friendly" are not outcomes.
- One `then` per criterion. "Returns the slug and never ends with a hyphen" is two criteria.

Concrete values
- Put real inputs in `given` and real outputs in `then`: `'  Hello,  World '` gives
  `'hello-world'`, not "a string with extra spaces gives a cleaned string".
- Copy every example, limit, default and exception type the idea states. If the idea gives a
  number, the criterion carries that number (a `max_length` of 5, a range of 1 to 12).
- When the idea states a rule but no example, write the smallest input that separates the rule
  from its absence: the rule "never cut a word in half" needs an input where a cut would fall
  inside a word.

Boundaries the idea names
- If the idea says "at most N", "below 1", "empty", "the last", "no more than", the boundary is
  a criterion of its own: one at the edge, and the state just past it.
- Errors are criteria: "raises ValueError" is checkable; "rejects bad input" is not, unless the
  idea says what happens to it.

What is not a criterion
- Anything you cannot quote a source for. Implementation choices (which algorithm, which
  library) and code quality are not behaviour and stay out.
- A guess about what the investor probably meant belongs in `open_questions`, phrased as a
  question the investor can answer in one line.
