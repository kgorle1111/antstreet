---
name: writing-a-minimal-failing-test
version: 1
description: Write the smallest pytest file that fails on the product for the traced reason and would pass on any correct implementation.
---
The gate keeps your finding only if this test fails on the product with an assertion failure. The
investor rejects it if it would also fail on a correct product. Both come from the same habit:
make the test say exactly one thing the idea says.

Shape of the file:

    from rev import reverse_words


    def test_a_run_of_spaces_becomes_one():
        assert reverse_words("a  b") == "b a"

- Import at the top with the exact module and function names the idea gives. A wrong name makes an
  import error, and an import error is dropped as "proves nothing".
- Call the function with the argument order and keyword names the idea gives.
- Take the expected value from the idea's words, worked out by hand. Never obtain it by calling
  the product, and never copy what the product returns: the product is what is being judged.
- Use the smallest input that shows the traced difference. Short strings, small numbers.
- For an error the idea demands, use `with pytest.raises(ExactClass):` naming the class the idea
  gives. Do not assert on message text unless the idea quotes it.
- One behaviour per file. Two assertions are fine only when they are the same rule on two inputs.
- No fixtures, files, clocks, randomness, network or helpers that could fail for another reason.
  A test that fails for the wrong reason is worse than no test.
- Compare floats with `pytest.approx` only when the idea talks about rounding; otherwise avoid
  inputs that give floats.
- Do not assert on anything the idea leaves open: ordering of equal items, the type of a
  container when the idea says "a list of", exact whitespace inside error messages.

Before you output it, run the test in your head against the product and write down the failing
assertion, then against a correct implementation and write down that it passes.
