---
name: boundary-values
version: 1
description: Turn every limit, range and threshold the idea states into edge checks.
---
Wrong implementations fail at edges. When a criterion states a limit, a range, a count or a
category boundary, test both sides of it, with values the idea itself lets you compute.

For each stated limit L:
- Exactly L: the value the rule names, the one most often off by one.
- One step inside and one step outside (L-1 and L+1 for integers).
- Only when the idea states a limit. If it says "at most 5 items", test 5 and 6; if it says
  "long lists", there is no boundary to test, so do not invent one.

Emptiness and singletons, when the idea says the function takes a collection or text:
- The empty input, but only if the idea says what it gives (a result, or a named exception).
  If it says nothing, do not test it.
- One element. Then two. Most loop and separator bugs show at one and two.

Type and shape edges, when the idea lists them: negative numbers, zero, whitespace-only text,
duplicated inputs, input that is already in the wanted form (idempotence: `f(f(x)) == f(x)` when
the idea implies it).

Keep each boundary its own check, or one parametrized check per rule. When a boundary check
fails, the failure name must say which limit broke.

Example: "a discount of 10% applies to orders of 100 or more". Checks: 99 gets no discount, 100
gets it, 101 gets it. Not: 0, negative totals, or a million, because the idea says nothing about
them.
