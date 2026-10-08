---
name: stated-edges
version: 1
description: Handle each edge case the request states, and add no behaviour it does not state.
---
The request decides the edge cases. Handle every one it states and invent none.

- Scan the request for each edge it names: empty input, wrong type, zero, the largest size, a boundary value, every "even when" and "regardless of" clause, and every example with a result. Each gets its own branch or line, and its example is one input you trace.
- A sentence with "never", "must not", "exactly", "shares no" or "even when" states an edge. "Never modifies the document and shares no list with it" needs a deep rebuild: `copy.copy` or a slice leaves nested containers shared.
- Order rules are behaviour. If the request says which error wins when two apply, or that input is checked before anything runs, implement that order.
- Do not add what is not stated: no extra validation that rejects input the request allows, no extra exception types, no stripping or lower-casing, no logging or printing, no extra parameters. Where the request is silent, do the plain Python thing.
- Where a check asserts something the request is silent on, meet it unless it contradicts a rule of the request.
