---
name: exact-names
version: 1
description: Use the module, function, parameter and exception names the request gives, character for character.
---
Take every name from the request and spell it exactly.

- The module file has the name the request gives (`calc.py`), in your folder, at the top level unless the request gives a path.
- Functions, classes, parameters and constants keep the request's spelling, parameter order and defaults. Do not rename for style, hide a function inside a class, or add required parameters.
- Raise the exception class the request names, not a relative: `ValueError` is not `TypeError`, `KeyError` is not `IndexError`. Where it names none, raise the plain Python one for that failure.
- Return the type the request states: a `list`, not a generator; an `int`, not a `float`; a new `dict`, not the input.
- Every check starts with an import. Read that line first: each module and name it imports must exist in your files with that spelling. A name only the brief or a check mentions, and the request does not contradict, you provide too.
- If the request bans an import or call (`eval`, `re`, `fnmatch`), keep it out of every file, helpers and lazy imports included.
