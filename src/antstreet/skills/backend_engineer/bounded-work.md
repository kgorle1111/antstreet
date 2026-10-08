---
name: bounded-work
version: 1
description: When the request states a size or time limit, code for the worst input it names.
---
Treat every limit in the request as a test input, and trace your code's cost on it: "2000 operands", "nested 50 levels deep", "100 unary operators in a row", "texts of 10,000 characters", "about a second".

- Python's default recursion limit is about 1000 frames. A function that recurses once per operand, per character or per list item fails on 2,000 of them with `RecursionError`: use a loop with an explicit list as a stack. Recursion once per nesting level is fine when the stated depth is far below 1000, allowing several frames per level.
- Backtracking that retries the rest of the input at every wildcard is exponential. Use a table over (pattern position, text position), or the two-pointer method that remembers only the last `*`. Cost is at most pattern length times text length.
- Do not repeat a linear scan inside a loop over the same input when one pass with a dictionary or an index would do.
- Where the request names a worst case (`"a" * 10000` against `a*a*a*a*a*b`), work that exact case through your code and count steps.
