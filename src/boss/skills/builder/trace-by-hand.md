---
name: trace-by-hand
version: 1
description: You cannot run code, so trace every check against your code by hand before you stop.
---
You cannot run code. A check you have not traced is a check you have not tested. Before you stop, for each check shown in your task, in order:

1. Take its literal inputs, unchanged.
2. Follow your code line by line with them, tracking each variable's value as you go. Do this in your reasoning; do not write scratch or notes files, because your task owns only its named files.
3. Follow the branch that runs, not the one you meant. Note the exact result with its type (`2` and `2.0` differ) or the exact exception class.
4. Compare it with what the check asserts.
5. Trace its import line too, so a wrong file or function name shows up.

When a step diverges, fix the code, then re-trace the checks you traced before: one fix often breaks another. Also trace one input for each rule of the request that no check covers.

When a later brief shows the gate's output for a check you traced as passing, the gate is right and your trace was wrong. Find the step where the real output first differs from your trace. Do not resubmit the same code.
