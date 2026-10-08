---
name: reading-the-idea
version: 1
description: How to find every requirement in an idea's layout and quote it exactly.
---
Ideas arrive as prose, numbered rules, code signatures and worked examples, often mixed. Each
shape hides requirements in a different place.

Where requirements hide
- Numbered or bulleted rules: each item is at least one requirement; an item with "and", "or",
  "unless" or "if" is several. Read to the end of the item: the exception is usually last.
- Signatures such as `f(text, max_length=None) -> str`: names, parameters, defaults and return
  types are requirements. A default is a criterion ("when max_length is not given ...").
- Worked examples: `'a,,b'` parses to `["a", "", "b"]` is a requirement stated by example. Give
  each distinct example its own criterion and quote the line that contains it.
- Words such as "never", "always", "exactly", "at most", "raises": they mark a hard rule, and
  hard rules are what wrong implementations break. Never skip one.
- Negatives ("must not use eval", "no other operators"): a criterion whose outcome is a raised
  error or an absent behaviour, with the forbidden input as `given`.

Quoting
- Copy from the idea, including punctuation and inline code marks, then trim to the clause that
  carries the rule. Do not fix typos, expand abbreviations or change quote styles.
- Quote one rule per `source`. A quote that runs across two rules is legal but hides which one
  the criterion tests; use two criteria.
- Do not quote list numbers or markdown markers as part of the words ("1." adds nothing) and do
  not quote a fragment shorter than 8 characters: quote the whole clause instead.
- The same fragment may be the source of several criteria (one rule, several inputs), but
  every sentence of the idea that states a behaviour needs at least one criterion of its own.

What the idea does not say
- Silence is not permission. Do not fill gaps with what such software usually does; ask in
  `open_questions`.
