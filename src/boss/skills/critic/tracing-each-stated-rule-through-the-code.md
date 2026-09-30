---
name: tracing-each-stated-rule-through-the-code
version: 1
description: Walk every rule the idea states through the product's code with real values, so a finding rests on a traced result and not a hunch.
---
Work rule by rule, not file by file.

1. List the rules the idea states, one line each: numbered rules, every "must", "never", "at most",
   "if ... then", and every example the idea gives. Ignore what the idea does not say.
2. Beside each rule, write the lines of the product that implement it. A rule with no lines is a
   finding candidate; a rule with lines is not one yet.
3. Pick an input that the passing checks did not use. The descriptions of the passing checks tell
   you which inputs are already covered, and the plain case nearly always is. Start with the
   input where two rules apply at once, or where the idea's own example has a twist.
4. Execute the lines by hand with that input. Write down the value of each variable after each
   line, in order. Do not read the code and decide it looks right: run it in your head with
   numbers and strings.
5. Write down what the idea says the result must be, from the idea's words alone. Compare it with
   what you traced. Only a difference is a finding. If they match, drop the candidate.

Traps to trace on purpose, because plausible code gets these wrong:
- `split(" ")` against `split()`, `strip()` against `strip(" ")`, `replace` that leaves a run.
- `<` against `<=`, `>` against `>=`, `range(n)` against `range(n + 1)`, a slice that is one short.
- An early `return` before a later rule is applied, and rules applied in a different order than
  the idea lists them, when the order changes the result.
- A default argument that is shared or mutated, and input that is modified in place.
- `None` or a wrong type returned where the idea says an empty string, a list, or an exception.
- An exception of a different class than the idea names, or none where the idea demands one.

If you cannot trace the code to a specific input and a specific wrong value, you do not have a
finding. Do not report a suspicion, and do not report a rule you were unable to read the code for.
