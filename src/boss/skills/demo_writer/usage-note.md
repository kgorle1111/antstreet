---
name: usage-note
version: 1
description: Write the usage note as instructions for the reader, with no claim about output.
---
The usage note tells a reader how to call the product. The system prints the real output next to
it, so anything the note says about output can only be redundant or wrong.

- Say what to import, what to call, what each argument means, what is optional. Use the names
  from the source files exactly.
- Write in the imperative or present tense about inputs: "Pass the title as text." Not about
  results: never "returns 'hello-world'", "prints", "you will see", "gives", "outputs".
- The exception is a documented failure the idea states in words, e.g. "A max_length below 1
  raises ValueError". Say it in the idea's words; give no example value.
- No code fences, no `>>>` prompts, no line starting with "Output:" or "Result:", no example
  results at all. A call may be shown inline as `slugify(text, max_length=None)`, a signature
  and never a call with its answer.
- Three to six short lines. No headings, no marketing, no install steps: the product is a folder
  of Python files next to demo.py.
