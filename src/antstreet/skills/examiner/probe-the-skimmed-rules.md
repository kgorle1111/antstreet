---
name: probe-the-skimmed-rules
version: 1
description: Aim each check at a different stated rule, favouring the ones builders skim past.
---
Builders read the idea once and build to its first example. The held-out checks exist to catch
what that reading drops, so they must not repeat what a visible check most likely covers.

Before writing, list every rule the idea states, one per line. Then pick rules, not examples:
- One check per rule, spread across as many different rules as the count allows.
- Rank the rules by how easily a skim loses them: a rule in the middle of the list, a rule that
  only applies when two other rules meet, a stated limit (test both sides of it), a named
  exception type, a rule about what must not change (the input, the order, the type returned).
- Skip the rule that opens the idea and its headline example unless the idea has only one rule.
- For a stated limit L, test L and the value just past it, never a limit the idea does not state.
- For an error rule, assert the exception type the idea names, and no message text unless the idea
  quotes the message.

Each check is one behaviour: one test function, plain asserts on one call's result. Several
asserts are fine when they describe that one behaviour. A check that mixes two rules hides one of
them behind the other's failure.
