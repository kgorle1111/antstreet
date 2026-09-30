---
name: validate-first
version: 1
description: Check the whole input for malformation before any evaluation, lookup or effect.
---
When the request says malformed input raises, or that input is checked "before" anything happens, work in two phases: validate all of it, then act.

- Phase one reads the whole input (every token of a pointer, every character of an expression, the whole pattern) and raises for any malformation. It looks at no document, returns nothing, and never stops early because the first part was fine.
- Phase two runs only on input that passed phase one.
- The test of this rule: input that is malformed at its end must raise the malformed-input error even when its start would raise a different error if run (`ZeroDivisionError`, `KeyError`). One pass that validates while it executes gets this wrong, because the earlier error fires first.
- Parse into a structure (token list, postfix list, tree) rather than evaluating while reading.
- Check argument types at the top of the function when the request names a type failure. If a wrong type must raise `ValueError`, test with `isinstance` before any other use, and do not let a `TypeError` escape.
