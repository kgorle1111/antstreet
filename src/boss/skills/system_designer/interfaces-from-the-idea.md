---
name: interfaces-from-the-idea
version: 1
description: Copy public signatures from the idea word for word, and fix the ones it leaves open.
---
The tester writes checks against the names you list, and the builder writes code against the same
names. A name that differs by one character between them fails a correct build.

Copy, do not paraphrase:
- If the idea gives `evaluate(expression: str) -> int | float`, the interface entry is exactly
  that text, with the module: `calc.py: evaluate(expression: str) -> int | float`.
- Keep default values, keyword-only markers and return types as written. Do not add type hints
  the idea did not give, and do not drop ones it did.
- Keep the exact exception types the idea names in the brief (`raises ValueError`), because the
  checks will assert on them. Do not name a type the idea does not name.

Fill the gaps the idea leaves:
- If the idea names a behaviour but no function ("a command that prints the total"), choose the
  simplest public name and full signature yourself, and put it in `interfaces`. Do not leave it
  for the builder to guess: the tester would then guess differently.
- Choose plain function signatures over classes unless the idea asks for a class.
- Never invent extra public names. Every entry must be needed by a story. Helpers stay internal
  and are not listed.

One entry per public name. Put each name in the task whose file will define it, so the tester can
tell which task a check belongs to from the name alone.
