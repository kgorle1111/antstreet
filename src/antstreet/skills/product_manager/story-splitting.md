---
name: story-splitting
version: 1
description: How to cut an idea into few stories, order them, and spend the criteria budget.
---
Stories exist so a tester can cover the idea in order and so the investor can cut scope by
priority. Cut along what a caller can do, not along code layers.

How many
- A one-function idea is usually one to three stories: the main behaviour, a story for its
  options or limits, a story for its errors. Do not pad to reach a number; eight is a ceiling.
- Two stories that share one `as_a` and one `i_want` are one story with more criteria.

Where to cut
- Cut on independent capabilities: "parse a line" and "format a line" are two stories, because
  one can work while the other fails.
- Cut on options: the plain behaviour first (`must`), then each optional parameter or mode
  (`should`), because the investor may fund the first without the second.
- Keep error handling with the capability it guards when the idea states it inline; give it its
  own story only when the idea has a separate list of error rules.
- Do not cut on "happy path" versus "edge cases" alone: an edge case the idea states is part of
  the behaviour it modifies.

Order and priority
- S1 is the story the idea cannot work without. Later stories build on it.
- Priority follows the idea's wording: "must", "always", "never" and the first numbered rule
  are `must`; "if ... is given", "optionally", "may" are `should` or `could`.

Spend the 16 criteria on the idea's rules
- Count the rules the idea states (numbered items, sentences with "must", "never", "raises").
  Give each its criterion before adding a second criterion to any rule.
- If the idea has more rules than 16 criteria allow, keep the most testable and list the rest
  in `open_questions` as "not covered: <rule>", so the investor sees the gap instead of a
  silent cut.
