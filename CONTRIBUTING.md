# Contributing

How to set up, run the tests, what a change must include, and how to add a benchmark task.
`tests/test_docs_contributing.py` fails when the commands, versions and figures here differ from
the repository.

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) first: it says what each module owns and must
never do. [docs/DECISIONS.md](docs/DECISIONS.md) says why. For a security problem, see
[SECURITY.md](SECURITY.md) and do not open a public issue.

## Set up

You need Python 3.12 and [uv](https://docs.astral.sh/uv/). You do not need the `claude` CLI or an
account to run the tests.

```bash
git clone https://github.com/kgorle1111/antstreet.git
cd antstreet
uv sync
```

## Run the tests

```bash
uv run pytest                      # the quick run: no model calls, one worker per core, no `slow` tests
uv run pytest -m "slow or not slow"   # everything except the serial `sigint` tests (what CI runs)
uv run pytest -n 0 -m sigint       # the Ctrl-C tests, one process
uv run pytest tests/test_rule.py   # one file
uv run pytest --cov --cov-report=term-missing   # with line and branch coverage of src/antstreet
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

- Tests use recorded CLI output in `tests/fixtures/` and fake `claude` executables, so `boss fund`
  runs end to end without credentials.
- One test makes a real model call and costs a few cents. It is skipped unless you set
  `BOSS_LIVE=1`: `BOSS_LIVE=1 uv run pytest tests/test_end_to_end.py`.
- A plain `uv run pytest` runs in parallel (`-n auto --dist loadgroup` is in `addopts`) and leaves
  out the tests marked `slow` and `sigint`: about 1.5 minutes on a 16-core Mac, against 4 minutes
  for the whole suite there. `loadgroup` keeps the tests marked `xdist_group` on one worker (the
  ledger document's tests share a fixture that takes minutes to build). A `-m` on the command
  line replaces the one in `addopts`, which is how CI selects everything. Coverage works the same
  way: pytest-cov merges the workers' data. A test must not rely
  on running first, on a fixed path or port, or on another test's leftovers: CI runs the suite in
  parallel, so a test that only fails in parallel is a bug in the test.
- Benchmark task validation is the slowest part of the suite (many short pytest runs per task).
  `BOSS_VALIDATE_TASKS_SINCE=<git ref>` makes `test_every_shipped_task_is_valid` and
  `test_every_multi_file_task_is_valid_and_needs_more_than_one_module` run the gate only on the
  tasks whose files differ from that ref (`git diff --name-only <ref>...HEAD -- bench/tasks
  bench/tasks-multi`), for example `BOSS_VALIDATE_TASKS_SINCE=origin/main uv run pytest -n auto
  tests/test_bench_tasks.py`. Every task is still loaded, and the count and set-hash pins are still
  checked. Unset, or when the ref or the history is unavailable, every task is validated.
  Pull-request CI sets it to the base branch; a push to main leaves it unset.
- Tests marked `sigint` make a fake worker send a real SIGINT (Ctrl-C) to the pytest process. On a
  busy machine with coverage on, that has hung a parallel worker, so CI runs them last, serially,
  with `-m sigint`; the parallel run leaves them out with `-m "not sigint"`. Mark a new test that
  does this the same way.
- Tests marked `slow` spend minutes in subprocesses: gates inside the sandbox, benchmark task
  validation, simulated firms. `tests/conftest.py` lists them (`SLOW`, whole files or single node
  ids, from `--durations`); add a test there when it takes over about 8 seconds, and run all of
  them with `-m "slow or not slow"`. CI never relies on the default: it passes its own `-m`.
- The benchmark validation tests skip a task that already passed under the same files and the same
  validator and gate code, when `BOSS_TASK_CACHE=<folder>` names a cache folder (CI keeps it with
  `actions/cache`; the nightly run leaves it unset). Only a pass is stored.
- `BOSS_SHARD=i/N` (for example `BOSS_SHARD=0/3`) runs only the test files whose path hashes to
  shard `i`, so a file's fixtures stay together and the shards add up to the whole suite
  (`tests/test_ci_selection.py` proves it). `BOSS_TEST_TIMEOUT_S=N` ends the process, with every
  thread's stack on stderr, when a single test runs longer than N seconds.
- CI runs `uv sync --locked`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy` (strict, over `src/antstreet`) and two pytest runs:
  `uv run pytest -n auto --dist loadgroup -m "not sigint" --cov --cov-report= --durations=30`, then
  `uv run pytest -n 0 -m sigint --cov --cov-append --cov-report= || [ $? -eq 5 ]` (5 is "nothing collected", normal for a shard with no such test), which adds to the first run's
  coverage data. Both pass their own `-m`, so the `slow` tests run. On Linux the suite is split
  into three jobs by test file (`BOSS_SHARD`) because every gate runs inside `bwrap` there; each
  uploads its coverage data and a final job runs `coverage combine` and
  `uv run coverage report --show-missing --fail-under=96` over all three. macOS runs the whole
  suite in one job and enforces the same floor itself, but only on a push to main and the nightly
  run, not on a pull request (the Linux shards and the combined coverage floor still do). The coverage floor is 96; it only ever goes
  up. A pull request validates only the benchmark tasks it changes; a push to main and the
  nightly run (03:17 UTC) validate every task, the nightly one without the cache. On Linux CI first
  installs `bubblewrap` and runs the tests with
  `BOSS_GATE_SANDBOX=require`, so the sandbox tests fail instead of skipping when `bwrap` cannot
  start (docs/SANDBOX.md).

## Mutation testing

Coverage shows a line ran, not that a test would notice it being wrong. `mutmut` (a dev
dependency, not part of CI: a module takes minutes to an hour) changes one thing in a source line at
a time and reruns the tests; a "survivor" is a change no test caught.

- Run one module at a time: `uv run python scripts/mutate.py errors` (also `rule`, `budget`, `gate`,
  `ledger`, `signing`, `firm`, `judge`, `table`, `kpi`, `paired`). The script gives mutmut only that
  module's test files; mutmut's own full-suite pass is about 5000 tests and fails on the docs tests.
- List what survived: `uv run python scripts/mutate.py errors --results`; show one change with
  `uv run mutmut show antstreet.errors.x_classify__mutmut_16`.
- Classify each survivor: a real test gap (add the smallest test that kills it), an equivalent
  change (no behaviour differs), or defensive code that cannot be reached. A timeout means the change
  made the code hang, which counts as caught.
- Do not run two modules at once: they share the `mutants/` folder, which version control ignores.
  Add a module by adding its focused test files to `TARGETS` in `scripts/mutate.py`.

## Rules

- **Small commits, one concern each.** The subject is a conventional commit: `type(scope): what`,
  in the imperative. Types in use: `feat`, `fix`, `test`, `docs`, `refactor`, `build`, `ci`,
  `chore`, `style`. The body says why. Work on a branch and open a pull request; CI must be green.
- **Tests that can fail.** New logic comes with a test that fails when the logic is wrong. Then
  mutation-check what you changed: make the smallest change to the code that should break the test,
  run it, see it fail, and restore the code. A test you have not seen fail proves nothing.
- **Documents are tested.** If you change behaviour a document describes, change the document. The
  tests `tests/test_docs_*.py` and `tests/test_threat_model.py` tell you what drifted.
- **No new dependency without discussion.** The only runtime dependency is `pytest`, because the
  gate runs checks with it. Use the standard library first.
- **Prompts are versioned files** under `src/antstreet/prompts/`, named `<name>_v<N>.md`. A change to
  what a prompt says is a new file with the next number and a change to the constant that names it,
  so a ledger's `hired` events always say which prompt ran. Measure a prompt change with the
  benchmark before claiming it helps.
- **Python 3.12, type hints, ruff line length 100.** Match the neighbouring code.
- **Mark a deliberate shortcut** with a `# kn:` comment that names its ceiling and the upgrade
  path, for example
  `# kn: global lock; per-account if throughput matters`. Then list it in
  [docs/BACKLOG.md](docs/BACKLOG.md): `tests/test_backlog.py` fails while a `kn:` comment is missing
  there.
- **Never commit secrets.** `.gitignore` already excludes `.env`, `.env.*`, `*.pem`, `*.key`, `.boss/` (run
  state) and `bench/results/raw/` (raw benchmark output).
- **Say what is not built** as plainly as what is, in code comments and in documents.

## Add a benchmark task

A task is a folder `bench/tasks/<id>/`. The rules are enforced by `antstreet.bench.tasks`, and
`tests/test_bench_tasks.py::test_every_shipped_task_is_valid` checks every task in the folder.

1. Choose an `<id>`: lowercase letters, digits and dashes, and the same as the folder name.
2. `meta.json`: exactly the keys `id`, `title` and `difficulty`, all strings. Difficulty is
   `easy`, `medium` or `hard`.
3. `idea.md`: the idea, stating the module and function names exactly and every behaviour the
   hidden checks test. No hidden requirements. It must not start with `-` and must not contain test
   code.
4. `hidden_checks/test_<name>.py`: at least 5 files, each a complete pytest file that defines a
   test. They score the arms and are never shown to either.
5. `reference/`: a solution in standard-library-only Python that passes every hidden check.
6. `mutants/<name>/`: at least 3 known-wrong solutions, one folder each, laid out like `reference/`
   (the same module files). Each is standard-library-only, imports, and fails at least one hidden
   check (a wrong solution that passes them all is not wrong). Name it for its bug: lowercase
   letters, digits and underscores. The first line of each file is a comment saying what is wrong.
   Mutants score the boss's checks (`python -m antstreet.bench.drafts`); no arm ever sees one, and they
   are not in the task set hash.
7. Every hidden check must fail on an empty workspace and pass on the reference, and every mutant
   must fail one. Check that with `uv run pytest tests/test_bench_tasks.py` and
   `uv run pytest tests/test_bench_mutants.py`.
8. A task set is identified by a hash of every task file, and the task count appears in the
   README and other documents. Adding a task changes both; the docs tests tell you which numbers
   to update. Results recorded against another task set are not comparable, and the results table
   warns when they are mixed.

Real runs are described in [bench/METHOD.md](bench/METHOD.md) and cost money:
`uv run python -m antstreet.bench.run --dry-run --out /tmp/bench --budget 0.40` lists the cells without
running any.

## Release

Owner only; nothing here runs in CI.

1. Bump `version` in `pyproject.toml` and move the `CHANGELOG.md` entries under it.
2. `uv build` writes the sdist and wheel to `dist/`. The wheel must hold `antstreet/prompts/*.md`
   and no top-level `boss` package (`tests/test_packaging.py` checks both) and the sdist only
   `src/antstreet`, `README.md`, `LICENSE` and `pyproject.toml`.
3. Check the wheel in a clean place, from the repository root:
   `wheel="$PWD/$(ls dist/*.whl)"; cd "$(mktemp -d)" && uv venv && uv pip install "$wheel" &&
   .venv/bin/antstreet --version`, or `uvx --from dist/*.whl antstreet --help`.
4. `uv publish` (a PyPI token in `UV_PUBLISH_TOKEN`; never commit it). A published version cannot
   be replaced, so try `uv publish --publish-url https://test.pypi.org/legacy/` first if the metadata changed.

PyPI shows `README.md` as the project page, and its relative image links (`docs/assets/...`) do
not resolve there; the project page links to GitHub instead.
