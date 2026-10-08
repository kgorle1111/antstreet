---
name: one-task-by-default
version: 1
description: Split into several tasks only when parts are independent; otherwise use one.
---
Start from one task holding every story. Split only when every test below passes for the split.

A split is safe when all of these hold:
1. The parts live in different files and neither imports the other.
2. The idea would still make sense if one part were deleted.
3. A builder of one part needs nothing from the other part's brief.
4. Each part has stories of its own, and each story sits wholly in one part.

A split is unsafe when:
- A story's acceptance criteria touch two parts ("the CLI prints what the parser returns"): the
  story stays whole, so both parts go in one task.
- One part is a helper of another. A helper is not a task.
- The only reason is size. A long single file is still one task; the cost of two builders
  agreeing on an interface is paid on every run, the cost of one long file is not.

Use as few tasks as the rules allow, and never more than the limit in the user message. If the
limit is 1, put everything in one task without comment.

Story assignment when you do split: read each story's criteria and put the story where the
criteria's behaviour is implemented. Two stories that describe the same function go together.
