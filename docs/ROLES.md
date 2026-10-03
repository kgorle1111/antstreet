# Roles, worker profiles and skills

What each is, how to add one, and when a role is switched on. `tests/test_docs_roles.py` fails
when a profile or builder skill is missing here, when a file named here does not exist, and when a
step below stops working. The table in "How `boss fund --roles` reaches each role" is checked
against the registry; what each role is for is in code, and `render_org` prints it (see "See the
whole organisation").

## Three different things

| | Role | Worker profile | Skill |
|---|---|---|---|
| What it is | One structured model call | A builder: the same worker with a chosen list of skills | A versioned Markdown file |
| Defined in | `src/boss/roles/<name>.py`, as `SPECS` | `src/boss/roles/builders.py`, as `PROFILES` | `src/boss/skills/<owner>/<name>.md` |
| Tools | None | `Read`, `Write`, `Edit` in its own folder; no shell | Not applicable |
| Produces | Data that must pass its gate | Files that the gate's checks run against | Text appended to a system prompt |
| Paid for | A capped call, booked as a `role_call` event | Capped slices, like any worker | Its characters, on every call that loads it |
| On by default | No: `boss fund --roles` turns it on | No: the builder prompt runs alone unless `boss fund --profile` names one | Loaded by whatever names it |

## What a role is

- **One structured call.** `call_role` runs the CLI with no tools, the role's system prompt and a
  JSON schema. A role that needs to touch files is a worker, not a role.
- **A gate.** `RoleSpec.gate` is one line naming the deterministic check its output must pass
  before anything uses it. A role drafts; code decides.
- **Metered.** A call's spend is booked by whoever calls the role (`src/boss/pipeline.py`), as a
  `role_call` event under the actor `role:<name>` (`ledger_fields` builds the fields). The call has a cap of `cap_micros`
  (150,000 micro-dollars, $0.15, unless the spec says otherwise).
- **Off by default.** `default_on` is `False` until a measurement says the role earns its cost.
  A role runs only when `boss fund --roles` names it.
- **Placed by two fields.** `department` is one of `product`, `engineering`, `quality`,
  `delivery` or `advisory`. `reports_to` is `boss` or the name of another role.

## A role is switched on by a measurement, not by an opinion

- `default_on=True` needs a benchmark or draft-evaluation result that shows the role moves a number
  the investor cares about (wrong checks, gamed cells, cost per passing cell) by more than the noise,
  at a cost the change repays. "It should help" is not a result.
- What counts as more than the noise is not fixed here. At 17 tasks a difference in pass rate is
  descriptive only ([DECISIONS.md](DECISIONS.md), D29), so a role is judged on the measures a small
  set can support.
- The check auditor is the worked example (D26). It exists as a role and is off, because nobody has
  measured that it pays for one more model call in every run.
- The tools that measure a role are in the repository and cost money to run, so each has a dry run:
  `src/boss/bench/drafts.py` (`python -m boss.bench.drafts`) scores the checks the boss drafts, and
  with `--prompt staged` it scores the product manager, designer and tester in place of the
  boss's one call; `src/boss/bench/audit.py` (`python -m boss.bench.audit`) scores the
  check auditor's flags against the reference solution; `src/boss/roles/judge.py`
  (`python -m boss.roles.judge calibrate`) compares the judge's scores with a person's on about
  twenty artifacts.
- A judge's scores are labelled `uncalibrated` until that comparison meets its bar, and
  `require_calibrated` refuses to hand an uncalibrated one to code that would act on it.

## Held-out checks and the examiner

Workers see the checks they are graded on. In the last benchmark 12 of 36 firm runs passed every
visible check and then failed a hidden one a person wrote (B52 in [BACKLOG.md](BACKLOG.md)). The
examiner is the role that closes that gap: a separate call that writes checks the workers never
see, which are run once, on the assembled `product/`. It is off by default; `FirmConfig.held_out`
says how many to ask for (0 is off, up to 8), and `boss fund` has no option for it yet.

- **What it sees.** The investor's idea, and the public names the product must expose: the paths
  each task owns, the modules and names the visible check files import, and the names the task
  briefs state: in backticks, or in prose as a call shape (`reverse(s)`) or a `*.py` file name
  (`public_names` in `src/boss/roles/examiner.py`). Names only; a test file named in a brief is
  left out.
- **What it never sees.** A visible check's body, description or file name. Independence from the
  checks the workers are graded on is the point, so `tests/test_roles_examiner.py::test_no_visible_check_body_description_or_file_name_reaches_the_examiner`
  pins it.
- **Its gate**, all in code (`examine`, then `held_out.problems`): exactly the asked number of
  checks; every `source` quote a fragment of the idea of at least 8 characters (the rule
  `roles/advisory.py` uses, `is_fragment`); ids `h01`.. unique and not a visible check's; every
  file parses and defines a `test_` function; every check fails on an empty workspace (the same
  run `termsheet.validate` makes for the visible checks, `empty_checks_problems`). A refused
  output raises `RoleOutputError` carrying the output, and `run_examiner` saves it as
  `examiner_refused.json` in the run folder.
- **Where they live.** The run folder's `held_out/`, with a `manifest.json`: beside `checks/`, never
  in a workspace, a brief, a prompt or `product/`.
- **The one human gate.** The investor reads every held-out check with the term sheet, and their
  content hashes go into the `approved` event as `held_out_hashes`. A check that is wrong fails a
  correct product, and boss-written checks were wrong 3 to 5 percent of the time, so nothing
  unreviewed may decide a verdict. Editing a held-out file after approval stops the run like
  editing a visible check.
- **The verdict.** `_gate_product` also runs them on `product/` and records `check_result` events
  with `scope: held_out`. The report shows the two results apart, and a run passes only when both
  do. They never enter a per-worker decision: the firing rule does not see them.
- **When it fails.** `run_examiner` is called once, after the boss drafts and before the investor
  approves. If its call fails, its output is refused, or round 1 could not then fund a worker
  slice, the investor is told, the ledger says so (`role_call` with `kept` 0 and the `problems`),
  the report says so, and the run goes on without held-out checks. Its spend is booked in round 1
  like any role's and counts against that round's budget.

## What a worker profile is

- The same worker, the same three tools, the same base prompt (`builder_v3.md`), the same gate.
  Only the list of skills after the base prompt differs. A profile cannot grant a permission.
- `builder_system_prompt(name)` is the base prompt, a blank line, then the profile's skills in
  order. With no skills it is the base prompt byte for byte.
- `boss fund --profile NAME` chooses one profile for the whole run. It is stored in the `started`
  event's configuration, so `boss resume` uses the same one, and in every `hired` event. Without
  the option the loop sends the base prompt alone: no profile is on by default.
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

## How `boss fund --roles` reaches each role

`boss fund --roles a,b,c` (or `--roles all`) names the roles to run. With no `--roles` nothing
below happens, and the run, its ledger and its output are what they were before roles existed.
`src/boss/pipeline.py` is the one module that calls a role's function. Every role call uses the
boss's model (`--boss-model`) and thinking setting (`--boss-thinking`), and they are recorded on
the `started` event, so `boss resume` calls roles the same way.

| Role | Runs | You see | The code uses it for |
|---|---|---|---|
| `product_manager` | before approval | The stories, saved as `stories.json`, and "parts of your idea no acceptance criterion quotes" | The staged draft |
| `user_agent` | before approval | A note marked as an opinion: what the stories miss or misread | Nothing |
| `system_designer` | before approval | The tasks in the term sheet, with the tester's checks | The term sheet's tasks |
| `tester` | before approval | The checks, each with the criteria it covers, and a coverage matrix | The term sheet's checks |
| `check_auditor` | before approval | A note with one opinion per check | Nothing |
| `judge` | before approval and after the build | A score of the stories, and a score of `USAGE.md`, each labelled uncalibrated unless a calibration covers it | Nothing |
| `consultant` | while a dispute is open | One line, marked as an opinion, before the question on a disputed check | Nothing |
| `critic` | after the build | Each verified finding and how many were rejected; if any, one question: add these checks and fund a fix round | Proposed checks, only if you say yes |
| `demo_writer` | after the build | `demo.py` and `USAGE.md` in `product/`, only when every required check passes | Files added to the product |
| `examiner` | before approval, with `--held-out N` | Its checks in full, marked as never shown to a worker, with the term sheet you approve | The final verdict: the product must pass them too |

- **Nothing is decided by a role.** A note under the term sheet binds nothing: approval is of the
  sheet and its check files, and their hashes are the same with or without the notes. A proposal
  (the critic's checks) changes the run only when you answer yes, and your answer is an `approved`
  event with `added_checks`.
- **Roles that need another.** `user_agent` needs `product_manager`. `tester` needs
  `product_manager` and `system_designer`, and `system_designer` needs `tester`, because a design
  alone produces no checks. Anything else is a usage error that names what to change, before
  anything is spent. `judge` with no stories or no demo has nothing to score and makes no call.
- **Staged draft.** With `product_manager`, `system_designer` and `tester`, the term sheet comes
  from `draft_staged` and the boss's own draft call is not made, so it is not paid for. With
  `--rounds` above 1 the rounds are planned by story priority.
- **A role that fails.** Its spend is booked whatever happened, you are told in one line, and the
  run goes on without that role's output. A failed advisory role is a note that says it failed; it
  is never shown as "no problems found". Two steps cannot go on without a role's output, so they
  fall back to the boss's own draft and say so: a failed `product_manager` (there are no
  stories), and a failed staged draft (the designer, the tester, or assembling the sheet). Every
  paid call of a failed staged draft is booked under its own role, and a good output that was
  thrown away is booked as `unused`.
- **Fix round.** After the build the critic's findings are run by the gate on the product, and
  each one that fails there is verified. Each is proposed as a check for the task that owns the
  module its test imports (the only task, if there is one). A check that would pass on an empty
  workspace is dropped with a line saying so. You are shown each check's code and asked once:
  `--review-cycles` limits how many reviews there are, `--fix-budget` sets the new round's money,
  and no question is asked when the run ended early. On yes, the amended sheet is validated,
  approved in the ledger and written to `term_sheet.json`, and the loop runs again so a worker
  fixes what was found.
- **Demo.** Only for a product that passes every required check. The demo script is screened by
  code, run inside the gate against a copy of the product, and `USAGE.md` holds what that run
  printed, not what the model said it would.
- **Resume.** A resumed run reads its roles from the ledger, does not repeat the stage before
  approval, and does not repeat a critic review, a demo or a usage score the ledger already shows.
- **What you can read afterwards.** `stories.json`, `critic-N/` (the tests the critic wrote),
  `demo/` (the installed files, kept because `product/` is rebuilt on every run) and `demo_scratch/`
  in the run folder; one line per role call in the report's Roles section; every call in the
  ledger as `role_call`. Text a model wrote is made safe before you read it: control characters
  visible, secrets masked, one line where a line is expected.
- **Tests.** `tests/test_pipeline.py` runs all of this against one fake `claude` that plays the
  boss, the worker and every role. For example
  `tests/test_pipeline.py::test_every_role_end_to_end_and_the_ledger_adds_up`.

## Not built

- No role is on unless `--roles` names it. The roles return data and usage to their caller and write
  nothing, except the examiner's `run_examiner`, which books its own call and stores its checks;
  for every other role, `src/boss/pipeline.py` books their spend. The examiner is chosen with
  `--held-out N`, not with `--roles` (`--roles examiner` is refused and names the option).
  `src/boss/firm.py` and `src/boss/cli.py` import only `registry`, `PROFILES`, `org_chart`,
  `render_org` and `builder_system_prompt` from the roles package.
- Nothing assigns a profile to a task. The investor picks one for the run; the boss does not pick
  one, and a task has no profile field.
- No role has been measured to pay for its call, so none is on unless you name it. No judge
  calibration file is in the repository.
- The fix round takes the place of the first round that never opened, so a sheet whose later
  rounds were never needed does not ask you to fund them first. Those rounds follow it, one number
  higher, with their money unchanged and each still asking for your yes; the last one now unlocks
  only when every check passes, which a sheet requires. You are told this before you answer.
- A Ctrl-C at the fix question is not an answer. The critic is called again on `resume` (one more
  call, its own cap) and its findings, which may differ, are offered again; its first review stays
  in `critic-N/`. A no, or a cycle that offered nothing, is recorded as an investor `ruled` event
  and is not asked again.
- No measurement shows that any skill changes a worker's output. No benchmark cell has used a
  profile. Each skill answers a failure seen in the pilot and rerun or reasoned from a worker with no
  shell; none has been tested by an A/B run.
- No token cost has been measured for a skill set. The 10,000-character cap is a bound, not a
  measurement.
- The ledger records a role's skill ids, not their versions.
- The table above says where each role runs, not what it is worth: run the command above for each
  role's purpose and gate.
