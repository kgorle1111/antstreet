---
name: import-public-names-only
version: 1
description: Reach the product only through the files and names you were given, so a check can run.
---
A held-out check runs once, on the finished product. If it imports a name the product does not
have, it fails a correct product for a reason the idea never gave. The names you are given are the
whole contract; everything else is the builder's choice.

- Import only the modules, functions and classes in the list. Call them with the signatures the
  idea and the list show, nothing more.
- Do not import a helper, a constant or a submodule the list does not name, even if it seems the
  obvious way to write the product. Do not reach into private names (a leading underscore).
- Put every import at the top of the file, unguarded. The gate runs each check on an empty
  workspace and refuses one that passes there; an import at the top is what makes it fail.
- If the idea needs a rule tested that the listed names cannot reach, leave that rule out. A check
  that needs a name you invented is a wrong check.
- Take expected values from the idea's own examples first, copied exactly. Work out others by hand
  from the stated rules, step by step; if you are not certain, leave that case out.
