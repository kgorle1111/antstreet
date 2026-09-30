---
name: boundaries-the-idea-names
version: 1
description: Find the exact boundary values the idea names and test each side of them, and nothing beyond what the idea names.
---
Ideas hide their sharpest rules in a comparison word. Read the idea once only for these:

- Numbers and limits: "at most N", "at least N", "below 1", "longer than", "exactly", "up to".
- Empty and edge positions: "empty", "no letters", "first", "last", "leading", "trailing",
  "single", "every run of".
- Defaults and absent values: "if X is given", "when omitted", "None".
- Results that "never" or "always" have a property: "never ends with a hyphen", "always sorted".

For each one, write the boundary and test the values on both sides of it:

    "at most 10 characters"  ->  a result of 10 is allowed, a result of 11 is cut
    "a max_length below 1 raises ValueError"  ->  0 raises, 1 does not
    "if the first word alone is longer than n, cut it to exactly n"  ->  a first word of n + 1

Then compare the boundary with the code's operator: `<` against `<=`, `len(x) > n` against
`>= n`, a slice `[:n]` against `[:n + 1]`, `range(1, n)` against `range(1, n + 1)`. The value
exactly on the boundary is where these differ, so it is the input to trace and to test.

Stay inside the idea. If the idea says "at most 10", then 10 and 11 are in scope. Zero, negative
numbers, huge numbers, `None`, wrong types and non-ASCII input are in scope only when the idea
names them. A behaviour the idea does not state is not a finding, even when the code looks
fragile there: the firm's approved tests cover the stated rules, and yours must not invent new
ones.

A "never" or "always" claim is checked on the outputs the earlier rules produce: apply the cut, the
trim or the sort, then test the property on the result, on an input that makes the rule bite.
