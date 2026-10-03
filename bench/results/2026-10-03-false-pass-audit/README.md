# 2026-10-03-false-pass-audit

Is the false-pass rate real? This audit read every false-pass cell in two saved runs and judged it
against the task text. No model call was made and nothing was spent. The raw cells stay under
`bench/results/raw/` (git-ignored); nothing from them is copied here except short quotes.

A **false pass** is a firm cell where every visible check (the boss's checks the worker saw) passed,
but a hidden check (written by hand, never shown to any agent) failed.

## Result

- 29 false-pass cells: 17 of 41 visible-pass cells in `heldout3`, 12 of 36 in `final3`. Both counts
  match the published figures.
- Every one is a real departure from the task text: **29 (A), 0 (B), 0 (C), 0 (D)**. No hidden check
  was over-strict, and no failure was the harness's.
- So the corrected rate equals the raw rate: 29 of 77 (37.7%, Wilson 95% [28-49%]). The upper bound
  with (B) is the same, since there are no (B) cases.
- The failures are not equally serious. 9 of the 29 fail only on non-ASCII input and 4 only on an
  `int` returned where the text says `float`. Without those 13, the rate is 16 of 77 (20.8%, [13-31%]).
- The boss's own held-out checks (3 per cell in `heldout3`) passed in all 17 false-pass cells there.
  They caught none of them.

## Method

1. Listed every firm cell whose `visible_passed` equals `visible_total` and whose `hidden` map has a
   non-passing check. Both folders hold 51 cells (17 tasks, 3 reps).
2. Confirmed the task files are the ones the cells ran on: the 17 original tasks hash to
   `c130282a6eec5fe8`, the `set_hash` in every cell.
3. Re-ran every hidden check of all 29 cells against that cell's saved product, in a temporary copy,
   with plain `pytest -q` (the product on the path, the check file beside it). That is 221 check runs.
   All 221 gave the status recorded in `result.json`. Nothing timed out and nothing was flaky, so no
   case is a harness failure.
4. Listed every failing test id, then probed the product by hand to see the actual output.
5. Read the failing assertion against `idea.md`, as `METHOD.md` requires: a hidden check may only
   test behaviour the idea states. Quotes below are under 15 words.
6. Searched the cell's boss checks (and held-out checks) for the behaviour that failed.
7. Re-ran the three boss checks that the reference solution fails (the cells with `wrong_checks` = 1)
   against the reference to confirm they are wrong.

Verdicts: (A) real error, the idea clearly states it; (B) ambiguous; (C) over-strict check;
(D) harness. Confidence in the verdicts: high. The least clear-cut are the four `tokenbucket` cells
(a type, not a value); the idea states the type, so they stay (A).

Cell names: H = `heldout3`, F = `final3`, then task and rep.

## Cases

| # | Cell | Failing hidden check and exact failure | Idea says | V | Did a boss check touch it? |
|---|---|---|---|---|---|
| 1 | H bigdecimal r3 | `invalid_input`: 24 of 369 subtests, all non-ASCII digits (`５`, `١٢٣`, `1.٥`): `DID NOT RAISE ValueError`. Product tests digits with `str.isdigit` | "digits that are not ASCII 0-9 (such as Arabic-Indic digits)" | A | No |
| 2 | H calc r2 | `malformed_tokens`: `"١ + ١"` returns 2. `precedence`: `(((1 + 2) * 3) - 4) * 5` raises `ValueError: Unbalanced parentheses`. `result_types`: `(8 / 4) + 1` raises `ValueError: Unexpected tokens after expression` | "Parentheses group subexpressions and can be nested at least 50 levels deep"; "no non-ASCII digits" | A | Partly. c03 tries `(2 + 3) * 4` and 50 nested levels, never a group followed by another operator. Worker was capped in both slices |
| 3 | H duration r1 | `parse_decimals`: `parse_duration("٣s")` returns 3.0; 5 non-ASCII subtests `DID NOT RAISE ValueError` | "and non-ASCII digits are not" (valid) | A | No |
| 4 | H jsonpointer r3 | `list_indexes`: tokens `"1 "`, `"1_0"`, `"١"`, `"１"`, `"१"` accepted as list indexes, `DID NOT RAISE KeyError`. `set_value_errors`: `"١"` | "Signs, spaces, underscores, decimal points, leading zeros (`01`) and non-ASCII digits are not indexes" | A | Partly. c04 tries `/01`, `/00`, `/-1`; no space, underscore or non-ASCII |
| 5 | H justify r1 | `last_line`: `justify("hello there world", 30)` returns `'hello        there       world'`; expected single spaces padded to 30 | "If the whole text fits on one line, that line is the last line" | A | Yes, and it was wrong. c06 asserts the stretched form (`'a   b   c  d  e'` for `'a b c d e'`, 15); the reference fails it. The product matched the wrong check |
| 6 | H semver r1 | `parse_invalid_input`: `١.٢.٣`, `1.2.३`, `１.２.３` parse without error (3 subtests) | "Any other character is invalid, including spaces, underscores and every non-ASCII character" | A | No |
| 7 | H semver r2 | As #6, plus `1.2.3-é`, `1.2.3+é`, `1.2.3-α`, `1.2.3-٣`, `1.2.3+٣` (8 subtests) | same | A | No |
| 8 | H semver r3 | As #6 (3 subtests) | same | A | No |
| 9 | H slugify r1 | `max_length_long_word`: `slugify("abc", max_length=1)` returns `''`; `assert '' == 'a'` | "cut that word to exactly `max_length` characters" | A | Yes, and it was wrong. c06 asserts `slugify("a-b-c-d-e", max_length=1) == ""`; the reference returns `"a"`. The product matched the wrong check |
| 10 | H tokenbucket r1 | `basic`: `assert isinstance(bucket.available(), float)` fails; `available()` returns the int `5` for capacity 5 | "`available()` returns the current number of tokens as a `float`" | A | Value yes, type no. Boss checks write `available() == 5.0`, which an int satisfies |
| 11 | H tokenbucket r2 | as #10 | same | A | as #10 |
| 12 | H tokenbucket r3 | as #10 | same | A | as #10 |
| 13 | H toposort r1 | `dependency_only_nodes`: `layers` with generator values returns `[['a','b','c']]`, expected `[['a'],['b'],['c']]` | "Each value is consumed at most once" | A | No. No boss check passes a generator |
| 14 | H toposort r2 | As #13, plus `random_graphs`: `IndexError`. `CycleError.cycle` is `[]` for `{0:[2], 1:[3,3,3], 2:[], 3:[3,2,5]}` | "`CycleError.cycle` is a list of nodes forming one cycle" | A | Partly. Boss checks test `["a","a"]` and first == last; never that every cyclic graph yields a cycle |
| 15 | H toposort r3 | As #13, plus `cycle_error`: for `a->b->c->a` it reports `['a','c','b','a']` (`assert 'c' in ['b']`); `random_graphs`: `assert 3 in [2, 4, 6]` | "each item depends directly on the item after it" | A | Partly. Boss checks test first == last and `["a","a"]`; direction is never checked |
| 16 | H wildcard r1 | `escapes`: `match('[\\]-a]', '^')` is False; `[\a-c]` does not match `b` | "Either end of a range may be an escaped character" | A | No |
| 17 | H workdays r3 | `add_months`: `add_months(date(2024,2,29), 1)` returns 2024-03-31, expected 03-29; `date(2023,2,28)` + 1 gives 03-31, expected 03-28 | "The day of the month is kept, except that it is clamped" | A | Yes, and it was wrong. c02 asserts Apr 30 + 1 month is May 31; the reference gives May 30. The product matched the wrong check |
| 18 | F bigdecimal r1 | `compare`: `compare('0.5','0.25')` returns -1 (expected 1); `('0.09','0.1')` returns 1 (expected -1); 4 subtests | "`compare` compares numeric values, not text" | A | Partly. c04 compares integers and equal-value decimals only |
| 19 | F bigdecimal r2 | `invalid_input`: 24 subtests, non-ASCII digits, as #1 | as #1 | A | No |
| 20 | F calc r2 | `associativity`: `RecursionError` on a 2000-operand `+` chain. `malformed_tokens`: 5 non-ASCII subtests | "an expression of 2000 operands joined by `+` is valid"; "no non-ASCII digits" | A | Partly. c06 uses 100 operands; no non-ASCII |
| 21 | F calc r3 | `malformed_tokens`: 5 non-ASCII subtests, no `ValueError` | "no non-ASCII digits" | A | No |
| 22 | F duration r1 | `parse_negative`: `"- 1s"` and `"-\t1s"` return -1.0 | "between a leading minus sign and the first number" (never allowed) | A | No |
| 23 | F duration r2 | `parse_decimals`: 5 non-ASCII subtests; `parse_negative`: `"- 1s"`, `"-\t1s"` | as #3 and #22 | A | No |
| 24 | F jsonpointer r2 | `list_indexes`: `١`, `１`, `²`, `१` accepted or, for `²`, `ValueError` instead of `KeyError`; `set_value_errors`: `١`; `set_value_isolation`: `assert [[1], [2]] is not [[1], [2]]`, untouched branches shared with the input (4 of 7 tests) | "shares no dict or list with `document`" | A | Partly. Boss checks test copies on the edited path only, never a branch the edit does not touch |
| 25 | F jsonpointer r3 | `list_indexes` (4) and `set_value_errors` (1): non-ASCII digits accepted | as #4 | A | No |
| 26 | F semver r1 | `parse_invalid_input`: non-ASCII digits (3). `sort_versions`: `sort_versions(["not a version"])` returns the list, no `ValueError` | "If any element is invalid, `ValueError` is raised" | A | Partly. c08 sorts valid lists only |
| 27 | F semver r3 | `parse_invalid_input`: non-ASCII digits (3) | as #6 | A | No |
| 28 | F tokenbucket r3 | `basic`: `isinstance(bucket.available(), float)` fails, as #10 | as #10 | A | as #10 |
| 29 | F toposort r2 | `dependency_only_nodes`: `layers` with generator values raises `KeyError: 'a'` | "Each value is consumed at most once" | A | No |

Reasoning for the table as a whole: in every row the idea has a rule that names the behaviour, and
the product's output contradicts that rule. No row needed a reading of the idea that the product's
output could also satisfy.

Verdict counts: **A 29, B 0, C 0, D 0.**

Boss-check coverage (item 4):

- 14 cells: no boss check touched the behaviour (#1, 3, 6, 7, 8, 13, 16, 19, 21, 22, 23, 25, 27, 29).
- 12 cells: a boss check touched the area but not the failing case (#2, 4, 14, 15, 18, 20, 24, 26,
  and the four `tokenbucket` cells, which compare the value but not the type).
- 3 cells: a boss check demanded the wrong behaviour (#5, 9, 17).
- None of the boss or held-out checks in any rep of the five tasks with non-ASCII failures (`bigdecimal`,
  `calc`, `duration`, `jsonpointer`, `semver`) contains a non-ASCII character.

## Corrected rates

Rates are over visible-pass cells. Intervals are Wilson 95% and treat cells as independent, which they
are not (see Limits).

| Count | H (n=41) | F (n=36) | Pooled (n=77) |
|---|---|---|---|
| Raw false pass | 17, 41.5% [28-57%] | 12, 33.3% [20-50%] | 29, 37.7% [28-49%] |
| (A) only, the corrected rate | 17, 41.5% [28-57%] | 12, 33.3% [20-50%] | 29, 37.7% [28-49%] |
| (A)+(B), upper bound | 17, 41.5% [28-57%] | 12, 33.3% [20-50%] | 29, 37.7% [28-49%] |
| (A) without the 9 non-ASCII-only cells | 12, 29.3% [18-44%] | 8, 22.2% [12-38%] | 20, 26.0% [17-37%] |
| (A) without those and the 4 type-only cells | 9, 22.0% [12-37%] | 7, 19.4% [10-35%] | 16, 20.8% [13-31%] |
| (A) without the 3 cells a wrong boss check pushed | 14, 34.1% [22-49%] | 12, 33.3% [20-50%] | 26, 33.8% [24-45%] |

The last three rows are sensitivity checks, not corrections. The audit found no reason to drop any
case. They show how much of the rate comes from small, exotic or type-only failures.

Cells cluster by task: 3 reps of the same 17 tasks. Resampling whole tasks (20,000 draws, fixed
seed) gives pooled 37.7% [20-57%], and [10-33%] for the rate without non-ASCII-only and type-only
cells. Use these wider intervals if the claim is about tasks rather than runs.

## Patterns by task

Each entry is false-pass cells over visible-pass cells (H / F).

| Task | H | F | What failed |
|---|---|---|---|
| semver | 3/3 | 2/3 | non-ASCII characters accepted; single-item sort not validated |
| tokenbucket | 3/3 | 1/1 | `available()` returns an `int` |
| calc | 1/1 | 2/2 | non-ASCII digits; `(a) + b` mis-parsed; 2000-term chain overflows the stack |
| duration | 1/2 | 2/2 | non-ASCII digits; space after the minus sign |
| jsonpointer | 1/2 | 2/2 | non-ASCII and padded list indexes; shallow copy in `set_value` |
| toposort | 3/3 | 1/3 | generators read twice in `layers`; wrong or empty cycle |
| bigdecimal | 1/2 | 2/3 | non-ASCII digits; `compare` on unequal scales |
| justify | 1/3 | 0/2 | single line stretched (wrong boss check) |
| slugify | 1/3 | 0/1 | `max_length=1` (wrong boss check) |
| workdays | 1/2 | 0/1 | month-end snapping (wrong boss check) |
| wildcard | 1/1 | 0/1 | escaped range ends |
| csvline, intervals, linediff, lrucache, matrixops, roman | 0 | 0 | none |

- 11 of 17 tasks produce a false pass. The other six had 2 or 3 visible-pass cells in each run and no
  false pass.
- The one failure shared by the most cells is non-ASCII input: 15 of 29 cells contain it, 9 contain
  nothing else. The boss's drafts never tested it, although each idea states it. A boss prompt
  that asked for one non-ASCII case per input rule would reach it; that is a prompt change and needs an
  eval, not a guess.
- Three cells (#5, #9, #17) were pushed by a boss check that the reference solution fails. In the real
  flow a human reviews checks. The benchmark auto-approves them. These three show the worker obeying a
  wrong visible check over the idea.
- Hidden checks that fail most often: `parse_invalid_input` (semver, 5 cells), `malformed_tokens`
  (calc, 3), `list_indexes` (jsonpointer, 3), `invalid_input` (bigdecimal, 2), `basic` (tokenbucket, 4),
  `dependency_only_nodes` (toposort, 4). All test a rule the idea names.
- Over-strict hidden checks: none found. No hidden check tested a message, an exception attribute
  beyond the idea, or an unstated type.

## Recommended fixes to hidden checks or the harness

None are required: there are no (C) and no (D) cases.

Optional, and not recommended while results are being compared: `tokenbucket/hidden_checks/test_basic.py`
checks the value and the type in `test_new_bucket_is_full`. Moving the `isinstance(..., float)` line
into its own test file would make a type-only failure show up as its own check. That changes the
task-set hash and invalidates every earlier result, and the idea does state the type, so the
current check is within the method.

Process findings, not fixes to checks:

- Wrong boss checks leak into false passes (3 of 29). `wrong_checks` already counts them per cell.
  A false-pass report should list them separately, as this audit does.
- The headline should be computed from `hidden` and `visible_*` only. One cell here (#2) ended both worker slices at its cap and
  never finished on its own; the "done" signal in the firm arm is the gate, not the worker.

## Limits

- The 29 cells come from 17 tasks, 3 reps each. Reps of one task fail alike (the four `tokenbucket`
  cells share one bug; five `semver` cells share one gap). The cell-level intervals are too narrow.
- The tasks are small standard-library modules with strict, many-rule ideas, and the hidden checks
  probe every rule, including exotic input. The rate is for that kind of task and that kind of check.
  It does not estimate how often a user would hit a bug.
- Both runs use Haiku as boss and worker, with no shell: the worker cannot run code. A coding agent
  that runs its own tests is a different setup.
- The rate is conditional on all visible checks passing. It is not a rate over all cells.
- I judged each case from the idea text. A different reader may move a case from (A) to (B),
  most likely the four `tokenbucket` cells. Moving all four changes the pooled rate from 29 to 25 of 77
  (32.5%) and nothing else in the conclusion.
- The audit scripts are not committed. They only copy a saved product, run `pytest`, and read
  `result.json`.

## What may be published

> On 17 small Python tasks (3 runs each, Haiku writing both the checks and the code), 29 of 77 runs
> (38%, 95% Wilson interval 28-49%) passed every check the model wrote and still failed a
> human-written check the model never saw; we read all 29 against the task text and each is a real
> error, 13 of them only on non-ASCII input or a returned type.

What this does not support: any rate for "coding agents" in general, any other model, agents that can
run code, or the phrase "says done" for the worker (the done signal is the boss's checks). The runs of
one task are not independent: resampling tasks widens the 38% interval to 20-57%.
