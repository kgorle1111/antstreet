---
name: honest-status
version: 1
description: Give the status done, continuing or blocked only when it is true, with a reason that names files and checks.
---
Your status is read by the loop and by the investor. Make it true.

- `done`: you traced every check of your task and each passes (a disputed check excepted), and every rule of the request has code. A failed or skipped trace means `done` is false: use `continuing`.
- `continuing`: you made progress and know what is left. The reason names the check ids and what each still needs.
- `blocked`: the request cannot be met as written, for example two of its rules contradict. The reason quotes both. Nothing else is `blocked`. A refused Read, Write or Edit means the path was outside your folder: name the file relatively (`module.py`) and do the work again. A failing check is not `blocked`.
- The reason is under 500 characters of plain sentences: files written, checks traced as passing, checks disputed. No praise and no promise about the next slice.
- The gate runs the checks whatever your status says. A `done` that is not true only hides which check you were unsure of.
