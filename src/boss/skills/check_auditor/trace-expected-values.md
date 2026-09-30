---
name: trace-expected-values
version: 1
description: Derive each expected value from the idea's rules, step by step, before judging a check.
---
A verdict is only as good as the value you derived yourself. Never judge a check by whether its
expected value "looks right".

For every assertion in a check:
1. Write the input exactly as the check gives it, including spaces, case and punctuation.
2. Number the idea's rules that touch this input. Apply them in the order the idea lists them,
   one per line, writing the intermediate value after each: "lowercase: 'version 2.0'",
   "runs of other characters: 'version-2-0'".
3. Write the final value and compare it to the check's expected value one character at a time.

Where checks go wrong, in the order they turn up:
- Counts and lengths. "Cut to exactly 5 characters" gives 5. Count the characters of the
  expected string; a 6-character expected value fails that rule.
- Off by one at a boundary. "At most N" allows N; "below N" excludes N; "longer than N" excludes
  N. Test the boundary input against the exact wording.
- Rules applied out of order. If rule 2 lowercases and rule 3 collapses runs, the check must
  match applying 2 then 3, not 3 then 2.
- Runs versus single characters. "Every run becomes one hyphen" means "a  b" and "a b" give the
  same result.
- Arithmetic. Add, divide and round the numbers yourself; do not trust a figure in the check
  because it is a round number.

If your trace and the check agree, the verdict can be `consistent`. If they differ and the rules
leave no room for both, it is `contradicts`. If a step needs a rule the idea does not contain,
stop: the verdict is `unsupported`, and the missing rule is what the `why` names.
