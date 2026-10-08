---
name: quoting-the-idea
version: 1
description: How to quote the idea so every finding survives the exact-match check.
---
Code checks each quote against the idea. A finding whose quote is not in the idea, or is under
8 characters, makes the whole review fail and it is thrown away, so quote carefully.

- Copy from the idea, never from the stories. The stories paraphrase; the idea is the only text
  a quote may come from.
- Copy exactly, including punctuation, inline code marks and quote characters. Only case and
  line breaks are forgiven. Do not fix typos, expand `e.g.`, or swap ' for ".
- Quote one clause: the shortest stretch that carries the rule, at least 8 characters. Do not
  stitch two distant sentences together with "..."; that text is not in the idea.
- Do not include list numbers ("3.") or bullet marks in a quote.
- `criterion` is an id copied from the stories (`S2.1`), never a description of it. An id that
  is not in the stories fails the check; if unsure which criterion is meant, quote the idea in
  a `missing` finding instead.
- `verdict` follows the findings and nothing else: any finding at all means `revise`; none
  means `accept`. Do not answer `accept` with findings "for information", and do not answer
  `revise` for a reason you did not list.
- `why` is one line, and states the gap: what a test would assert that nothing asserts today,
  or how the criterion differs from the idea.
