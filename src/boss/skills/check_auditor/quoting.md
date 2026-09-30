---
name: quoting
version: 1
description: Copy quotes from the idea exactly, so the gate accepts them and the investor can trust them.
---
Code compares your quote with the idea. A quote that is not a verbatim fragment is rejected and
the whole audit is thrown away, so copy; never paraphrase.

- One fragment, contiguous, copied character for character: same words, same order, same
  backticks and punctuation. Case and line breaks do not matter.
- Do not join two rules with "..." or "&". Pick the one sentence or clause your verdict rests
  on. If two rules both matter, quote the one that decides the expected value.
- Do not correct the idea's typos or tidy its markdown. Do not add quotation marks inside the
  quote; leave off the numbering ("3.") and the trailing full stop if in doubt.
- Between 8 and about 150 characters. Too short matches by accident; too long is unreadable.
- For `unsupported`, the quote is the nearest fragment that a reader might think covers the
  check. If nothing is near, use "" (an empty string). Never quote a fragment just to fill the
  field.
- Quote the idea, not the check, the description or another check.

`why` is one line, plain words, no line breaks. For `contradicts` write what the rules give and
what the check expects: "the rules give version-2-0, the check expects version-20". Do not
repeat the quote in `why`.
