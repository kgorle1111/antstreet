---
name: tests-that-can-fail
version: 1
description: When tests are the product, take expected values from the request and make each test able to fail.
---
When the tests are the product, the request is the specification, and each test must fail if the code is wrong.

- Take each expected value from a sentence or example of the request and work it out by hand. Never copy it from the code under test: you cannot run that code, and a value read from it proves the code equals itself.
- One rule per test, named for it (`test_a_range_whose_start_is_above_its_end_matches_nothing`). Cover every numbered rule, both sides of each boundary (n-1, n, n+1), and each stated exception with `pytest.raises(Class, match=...)`.
- Assert the exact value, and the exact type when the type is a rule: `2 == 2.0` passes, so add `isinstance`. Never assert only "not None" or "does not raise".
- Where the request orders two errors, give an input that triggers both and assert which one wins.
- For each test, name one wrong line in a plausible implementation that this test would fail on. If you cannot, strengthen the test or delete it.
- Tests are independent: no shared mutable state, no order dependence, no network, no clock, no unseeded randomness, files only under `tmp_path`. Prefer inline literals to fixture files.
- Import the module under test by the name the request gives.
