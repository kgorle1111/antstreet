---
name: show-dont-assert
version: 1
description: Print what the product returns instead of asserting or restating an expected answer.
---
The investor is shown what your script really printed. A script that decides for itself what is
right ("assert x == 'hello-world'", "print('OK')", "print('works!')") shows them nothing: if the
product is wrong, the demo either crashes or lies.

- Print the value the product returns, with a label saying what was asked:
  `print("slugify('Crème Brûlée') ->", slugify("Crème Brûlée"))`.
- Do not `assert`. Do not print "success", "passed", "OK" or a hard-coded expected value beside
  the real one. The reader compares the label with the value.
- Never type the result you expect into the script as a string to print. If a number or string in
  your script is the answer, you have shown your own claim, not the product.
- Do not catch broad exceptions to hide a failure. Catch one named exception only where the idea
  says the product raises it, and print its type and message: `except ValueError as exc:`
  then `print("raises ValueError:", exc)`.
- Print objects in a form a reader can compare: `print(repr(value))` for text with spaces or
  empty results, so an empty string shows as `''` and not as a blank line.
- One `print` per fact, one line each. No banners, no blank-line decoration, no colour codes.
- Sort anything whose order is not defined (sets, dict views from a set) before printing, so the
  output is the same on every run.
