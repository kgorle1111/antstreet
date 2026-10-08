---
name: dispute-wrong-checks
version: 1
description: Dispute a check only when it contradicts the request, with proof; never bend the code to it.
---
A check is wrong only when it contradicts a sentence of the request. Dispute exactly those.

Before disputing a check:
1. Work out the correct result from the request's sentence alone, then trace the check's input against code that follows the request.
2. If the request's result differs from the check's expected value, the check is wrong. If they match, your code is wrong: fix the code. A check your code fails is not evidence that the check is wrong.

To dispute, add an entry to `disputed_checks` with the check's id and a reason under 300 characters that quotes the rule, the input, the value the check expects and the value the request requires. Example: `c04: rule 6 says 0 * 1.5 is 0.0, the check expects 0`.

Keep the code following the request. Never special-case a check's input to make it pass, and never edit a check file. A dispute is never counted as a pass, and a claim that most of a task's checks are wrong is not believed: dispute only what you can prove, and finish every other check.
