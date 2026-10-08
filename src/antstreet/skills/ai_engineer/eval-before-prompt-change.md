---
name: eval-before-prompt-change
version: 1
description: Ship a prompt with its versioned file and a small eval that can fail, and never invent a score.
---
A prompt change without a measurement is an opinion. Deliver the measurement with the prompt, in the files your task owns.

- A prompt is a file with a version in its name (`extract_v1.md`). A changed prompt is a new file with the next number, never an edit in place.
- Write at least 10 eval cases as data (a JSON file or a constant): an `input` and the `expected` output a person would accept. Take them from the request's own examples plus one case per edge it states. Never fill `expected` by calling the code under test.
- Write a runner that loads the cases, calls the pipeline through the same injectable model function, compares with `expected`, prints one line per case and the count passed out of total, and exits non-zero when any case fails.
- Test the runner with a fake model that returns the expected outputs (all pass) and another that returns wrong ones (all fail). A runner that cannot fail measures nothing.
- You cannot run the runner and no real model exists in this build. Never write a score you did not compute: state in your status that the eval is written and not run.
