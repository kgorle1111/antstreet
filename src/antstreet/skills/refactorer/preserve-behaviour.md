---
name: preserve-behaviour
version: 1
description: Change structure and nothing observable: read first, keep the public surface, make the smallest diff.
---
A refactor changes structure and nothing else. Every behaviour a caller can observe stays the same.

1. Read first. Read each file you may change in full, and each file that imports from it. List what callers can observe: return values and their types, exception classes, result order, mutation of arguments, printed output, public names.
2. Keep the public surface: names, signatures, module paths, exception classes, and any message a check matches. When a rename is the point, rename exactly what the request names and update every caller you found.
3. Keep quirks. Behaviour that looks like a bug stays unless the request says to fix it. Mention any you noticed in your status reason.
4. Smallest diff: use Edit on the lines that change; do not Write over the whole file. Leave formatting, comments, blank lines and import order of untouched lines alone. Add no feature, parameter, dependency or test nobody asked for.
5. One structural change at a time: trace it against the checks before starting the next.
6. Where a check pins old behaviour that the request says to change, follow the request and dispute the check.
7. After a rename or move, re-read every file you read in step 1 for the old name. A missed call site is the typical failure.
