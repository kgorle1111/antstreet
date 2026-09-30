---
name: file-ownership
version: 1
description: Assign every file to exactly one task so builders never overwrite each other.
---
Builders work in parallel in one workspace. A file written by two builders is a bug that no check
will name, so ownership is decided here and is checked by code.

Rules for `paths`:
- A path is a file relative to the workspace root: `slug.py`, `pkg/parse.py`. Never absolute, never
  containing `..`.
- One owner per file. If two stories both need `util.py`, the helper belongs to one task and the
  other task gets its behaviour through that task's public interface, or the two stories merge
  into one task.
- Do not give a task a directory (`pkg`) if any other task owns a file under it (`pkg/a.py`).
  Prefer listing files. A task that owns a whole package lists the package once and nobody else
  lists anything inside it.
- Do not use `.`: it claims the whole workspace, which is only right when there is one task.
- Do not list test files. The checks are written by someone else and live elsewhere.

Signs the split is wrong:
- Task B's brief has to say "call the function from task A": B depends on A's file, so B cannot
  be checked until A is done. Merge them.
- Two tasks each need to change the same data structure. Merge them.
- A task exists only to hold a constants file or a `__init__.py`. Give that file to the task that
  uses it.

Example: an idea asks for `parse.py` (parse a date string) and `fmt.py` (format a date), and says
`fmt.py` does not use `parse.py`. Two tasks: t1 owns `["parse.py"]`, t2 owns `["fmt.py"]`. If
`fmt.py` imported `parse.py`, it would be one task owning both files.
