---
name: request-first
version: 1
description: Read the investor's request before the brief, and write code for every rule in it, checked or not.
---
Your task opens with the investor's request. Read all of it before the boss's brief or any check.

1. List every rule the request states: each name, each behaviour, each "must" and "must not", each size or time limit, each banned import or call. A numbered request is the list already.
2. Read the brief and the checks second. They are one reading of the request. Where the brief drops a rule the request states, or changes it, follow the request.
3. The checks you see exercise some of the request's rules and skip others. The request is what is judged: in benchmark runs about half the cells that passed every visible check still broke a rule no visible check touched. Write code for every rule, including those.
4. Before you stop, walk the list from step 1 and point at the line of code that handles each rule. A rule with no line is unfinished work.
5. Do not add a rule the request does not state. Where a sentence reads two ways, take the reading its own examples use.
