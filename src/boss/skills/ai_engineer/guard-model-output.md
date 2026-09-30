---
name: guard-model-output
version: 1
description: Model output is untrusted input: one call, then deterministic parsing, validation and verification in code.
---
The model is called once and its output is untrusted. Deterministic code decides what happens next.

- Put the model behind one function that takes the prompt data and returns text or a dict. The rest of the code receives that function as a parameter, so tests pass a fake with fixed output. No SDK import, subprocess or network call at import time.
- Ask for JSON with named fields and parse with `json.loads` inside a `try`. Not JSON, not an object, a missing field and an extra field are errors, not defaults.
- Validate after parsing, in code: the type of every field, enum members, numeric ranges, list lengths, non-empty strings. Collect every problem into a list and raise one error that names them all.
- Verify each claim you can against what you hold: a quote must occur in the source text, an id must be one you sent, a total must equal what you recompute. What code can check, code checks.
- Never repair silently: no guessed field, no clamped number. On failure raise a typed error a person can read. Retries are a small fixed number written in code, never a loop until it works.
- Nothing irreversible (a write, a send, a delete, spending) happens on model output alone.
