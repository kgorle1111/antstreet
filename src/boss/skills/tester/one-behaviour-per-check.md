---
name: one-behaviour-per-check
version: 1
description: Keep each check to one behaviour so a failure tells the builder exactly what to fix.
---
A check is the only feedback a builder gets. It sees which checks fail and reads their output, so
a check that tests three behaviours hides two of them behind the first failed assert.

Write each check as:
- One `def test_<behaviour>():` per file, named for the behaviour, not for the function
  (`test_words_joined_by_single_hyphen`, not `test_slugify`).
- Imports at the top of the file, from the module the design names.
- Arrange, one call to the code under test, then assertions about that one result.

Several asserts are fine when they describe one behaviour (the returned type, and the value).
Split the check when the asserts would still make sense if one of them were removed.

`pytest.mark.parametrize` is fine for one rule over many inputs (the same rule, different
words). Every parameter must be a case the idea states or trivially implies, because the check
fails if any one of them does. Never parametrize across different rules.

Tie checks to criteria:
- One check cites one criterion in most cases. Cite two only when the same assertions verify
  both, and say so in the description.
- A criterion with an error rule ("raises ValueError for X") gets its own check per kind of bad
  input the idea lists, not one check that loops over all of them, unless the idea groups them.

No shared state: a check must pass or fail the same way alone, in any order, once the code is
right. No module-level side effects except imports.
