---
name: smallest-convincing-example
version: 1
description: Pick the fewest calls that show the idea's main promise and one edge it names.
---
A demo is read in under a minute. Choose the smallest set of calls that would convince an
investor the product does what the idea says.

1. Find the idea's main promise, the one sentence it would be described by. Show it first with
   one ordinary, realistic input a customer in the idea's field would actually have. Not "foo",
   "test", "abc" or "hello": a real title, a real amount, a real address.
2. Then show one edge the idea names in so many words (a limit, an error, an empty case). Pick
   it from the idea's text, not from what you guess is hard. If the idea names none, stop after
   the main use.
3. Stop there. Three to six printed lines is right. Do not tour every function, do not loop over
   many inputs, do not build a table.
4. Use each `step` to point at the words that justify the call: one step per printed idea, its
   `quote` copied from the idea.
5. If the idea names a function or a module, import exactly that name. If it names none, use the
   public names in the source files, and only those: a demo that needs a name you are unsure of
   is worse than a smaller demo that runs.
6. Keep the setup to the minimum: build sample data inline in one or two lines, never read a file
   and never take arguments.
