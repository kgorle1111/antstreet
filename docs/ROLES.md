# Roles, worker profiles and skills

What each is, how to add one, and when a role is switched on. `tests/test_docs_roles.py` fails
when a profile or builder skill is missing here, when a file named here does not exist, and when a
step below stops working. This document does not list the specialist roles: they are defined in
code, and `render_org` prints them (see "See the whole organisation").

## Three different things

| | Role | Worker profile | Skill |
|---|---|---|---|
| What it is | One structured model call | A builder: the same worker with a chosen list of skills | A versioned Markdown file |
| Defined in | `src/boss/roles/<name>.py`, as `SPECS` | `src/boss/roles/builders.py`, as `PROFILES` | `src/boss/skills/<owner>/<name>.md` |
| Tools | None | `Read`, `Write`, `Edit` in its own folder; no shell | Not applicable |
| Produces | Data that must pass its gate | Files that the gate's checks run against | Text appended to a system prompt |
| Paid for | A capped call, booked as a `role_call` event | Capped slices, like any worker | Its characters, on every call that loads it |
| On by default | No | `generalist` only | Loaded by whatever names it |

## What a role is

- **One structured call.** `call_role` runs the CLI with no tools, the role's system prompt and a
  JSON schema. A role that needs to touch files is a worker, not a role.
- **A gate.** `RoleSpec.gate` is one line naming the deterministic check its output must pass
  before anything uses it. A role drafts; code decides.
- **Metered.** Every call is a `role_call` event under the actor `role:<name>`, with a cap of
  `cap_micros` (150,000 micro-dollars, $0.15, unless the spec says otherwise).
- **Off by default.** `default_on` is `False` until a measurement says the role earns its cost.
- **Placed by two fields.** `department` is one of `product`, `engineering`, `quality`,
  `delivery` or `advisory`. `reports_to` is `boss` or the name of another role.

## A role is switched on by a measurement, not by an opinion

- `default_on=True` needs a benchmark or draft-evaluation result that shows the role moves a number
  the investor cares about (wrong checks, gamed cells, cost per passing cell) by more than the noise,
  at a cost the change repays. "It should help" is not a result.
- What counts as more than the noise is not fixed here. At 17 tasks a difference in pass rate is
  descriptive only ([DECISIONS.md](DECISIONS.md), D29), so a role is judged on the measures a small
  set can support.
- The second boss pass (D26) is the worked example: not built, because nobody has measured that it
  pays for one more model call in every run.

## What a worker profile is

- The same worker, the same three tools, the same base prompt (`builder_v3.md`), the same gate.
  Only the list of skills after the base prompt differs. A profile cannot grant a permission.
- `builder_system_prompt(name)` is the base prompt, a blank line, then the profile's skills in
  order. With no skills it is the base prompt byte for byte, so switching the live loop to this
  function changes nothing until a profile says so.
- Every specialist carries the six `builder/` skills the generalist does, then its own.

| Profile | Purpose |
|---|---|
| `generalist` | The default builder: the base prompt and the skills every builder needs. |
| `backend_engineer` | Data structures, parsing, state and error handling at the edges of a module. |
| `ai_engineer` | Code that calls or evaluates a model: guards around one call, and an eval first. |
| `test_engineer` | Test suites and fixtures as the product, with expected values taken from the request. |
| `refactorer` | Changes existing code without changing behaviour, in the smallest diff. |

`ai_engineer` cannot be exercised by the benchmark yet: its products are standard-library only, so
no task calls a model.

## What a skill is

- A Markdown file with a header of exactly `name`, `version` and `description`, then a body. The
  body is plain text appended to a system prompt. Workers and roles run with the CLI's own skills
  and plugins switched off, so these files are the only skills they have.
- One idea, imperative, specific, under 4,000 characters, built from a failure seen in this project
  or plainly relevant to a worker that cannot run code.
- The bar, enforced for every shipped skill by `tests/test_skills_quality.py`: the header parses;
  the body is under the size limit; no two skills share a body or a description; every skill is used
  by a role or a profile and every skill they name exists; no filler phrase (`please`,
  `be accurate`, `be careful`, `you are an expert`, `as an AI`, `do your best`); the skills of one
  role or profile total at most 10,000 characters, about 2,500 tokens, on every call. The largest
  set shipped today is about 8,400 characters.

| Skill | The failure it answers |
|---|---|
| `builder/request-first` | Workers followed the boss's brief where it dropped a rule of the request (D17); about half the cells that passed every visible check broke a rule no check touched. |
| `builder/exact-names` | A wrong module or function name fails every check at once; a wrong exception class fails every error check. |
| `builder/stated-edges` | Stated edges left out (a shallow copy where the request says nothing is shared), and unstated behaviour added. |
| `builder/trace-by-hand` | A worker with no shell stops without having tested anything; a gate failure repeated unchanged. |
| `builder/dispute-wrong-checks` | Correct code bent to a wrong check, or a right check disputed without proof (D19, D34). |
| `builder/honest-status` | `done` reported on unchecked code; a refused path reported as `blocked` (D23). |
| `backend_engineer/validate-first` | Input validated lazily, so an earlier error beat the malformed-input error the request asks for. |
| `backend_engineer/bounded-work` | Recursion per operand and backtracking that break on the sizes the request names. |
| `ai_engineer/guard-model-output` | Model output used without parsing, validation or verification in code. |
| `ai_engineer/eval-before-prompt-change` | A prompt shipped with no measurement, or a score written that was never computed. |
| `test_engineer/tests-that-can-fail` | Expected values copied from the code under test; assertions that pass on wrong code. |
| `refactorer/preserve-behaviour` | Behaviour, names or quirks changed by a change that was meant to change structure only. |

## Add a skill

1. Pick the owner folder: `builder` when every profile should carry it, otherwise the folder named
   for the one profile or role that uses it. The file is `src/boss/skills/<owner>/<name>.md`; the
   name is lowercase letters, digits and dashes, and the skill id is `<owner>/<name>`.
2. Start the file with a header between `---` lines holding exactly `name` (the file's name),
   `version` (a whole number, 1 or more) and `description`.
3. Write the body: one idea, imperative, under 4,000 characters, no filler phrase. Name the failure
   it answers in the table above.
4. Name the id in the `skills` of a profile in `src/boss/roles/builders.py` or of a role. A skill
   nobody names fails `tests/test_skills_quality.py::test_every_shipped_skill_is_used_and_every_skill_named_exists`.
5. Keep that profile's skills at 10,000 characters or fewer in total:
   `tests/test_skills_quality.py::test_the_skills_of_any_one_role_or_profile_stay_under_the_combined_limit`.
6. Run `uv run pytest tests/test_skills_quality.py tests/test_roles_builders.py`.

A skill's ledger trace is its id, not its version (not built), so a rewrite that must be told apart
from the old text in a ledger gets a new name.

## Add a worker profile

1. Add a `WorkerProfile(name, purpose, skills, suited_to)` to `PROFILES` in
   `src/boss/roles/builders.py`. The name is lower_snake_case; `purpose` and `suited_to` are one line
   each, and `suited_to` says what has not been measured.
2. Start `skills` with the generalist's six, then the profile's own, which live in
   `src/boss/skills/<profile name>/`.
3. Add a row to the profile table above and to the skill table for each new skill.
4. Run `uv run pytest tests/test_roles_builders.py tests/test_docs_roles.py`.
   `tests/test_roles_builders.py::test_a_skill_in_a_profiles_own_folder_belongs_to_that_profile_alone`
   fails when a skill in a profile's folder is used elsewhere.

An unknown profile name is an error that lists the known ones:
`tests/test_roles_builders.py::test_an_unknown_profile_is_an_error_that_lists_the_known_ones`.

## Add a role

1. Create `src/boss/roles/<name>.py` that defines `SPECS`, a tuple of `RoleSpec`. `registry()` in
   `src/boss/roles/__init__.py` collects every module there: nothing else is registered.
2. Fill the spec: `name` lower_snake_case; `department` and `reports_to` as above; a one-line
   `purpose`; a one-line `gate`; `prompt`, a versioned file in `src/boss/prompts/`; `skills`;
   `cap_micros`; and `default_on=False`.
3. Write the gate as code, and a test that it rejects bad output. A role whose gate has never been
   seen to fail is not finished.
4. Run `uv run pytest tests/test_roles_org.py tests/test_roles_base.py`: the roles must form a tree
   under the boss (`org_problems`), and skills the role names must exist.
5. Look at it with `uv run python -m boss.roles.org`.
6. Leave `default_on` `False` until a measurement says otherwise.

## See the whole organisation

- `uv run python -m boss.roles.org` prints the firm as it is defined now: the investor, the boss,
  the departments, each role and each profile, with its purpose, gate, skills and whether it is on
  by default.
- The code is in `src/boss/roles/org.py`: `org_chart(registry, profiles)` builds the tree,
  `org_problems(registry)` lists a missing parent, a cycle, a self-report or a reserved name, and
  `render_org` draws it. A role that reports to another role hangs under it; every other role hangs
  under its department.
- A department with no role is left out of the chart and is not a problem.

## Not built

- The live loop does not choose a profile: `src/boss/firm.py` still appends the base prompt alone.
  `builder_system_prompt` is the function it would call.
- Nothing assigns a profile to a task. The boss does not pick one; `hired` events do not name one.
- No measurement shows that any skill changes a worker's output. No benchmark cell has used a
  profile. Each skill answers a failure seen in the pilot and rerun or reasoned from a worker with no
  shell; none has been tested by an A/B run.
- No token cost has been measured for a skill set. The 10,000-character cap is a bound, not a
  measurement.
- The ledger records a role's skill ids, not their versions.
- This document does not say which specialist roles exist or whether any is on: run the command
  above.
