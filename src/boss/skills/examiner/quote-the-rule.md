---
name: quote-the-rule
version: 1
description: Copy the source quote from the idea exactly, so the gate keeps the check.
---
Code compares each `source` with the idea. One quote that is not a fragment of it makes the gate
refuse the whole output, and every check you wrote is thrown away.

- One contiguous fragment, copied character for character: same words, same order, same
  backticks and punctuation. Case and line breaks do not matter.
- Pick the clause the check's assertion rests on, not the sentence that introduces the feature.
  The investor reads the quote beside the check to see what it verifies.
- Between 8 and about 150 characters. Shorter matches by accident; longer is hard to read.
- Do not join two rules with "..." or "&". If two rules both matter, quote the one that decides
  the expected value.
- Do not fix the idea's typos or tidy its markdown, and do not add quotation marks inside the
  quote. Quote the idea, not the names list or an example of your own.
- Ids run `h01`, `h02`, ... with no gaps and no repeats.
