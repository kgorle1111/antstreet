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
git clone https://github.com/kgorle1111/boss-agent.git
cd boss-agent
uv sync
```

## Run the tests

```bash
uv run pytest                      # the whole suite, no model calls; takes several minutes
uv run pytest tests/test_rule.py   # one file
uv run pytest --cov --cov-report=term-missing   # with line and branch coverage of src/boss
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

- Tests use recorded CLI output in `tests/fixtures/` and fake `claude` executables, so `boss fund`
  runs end to end without credentials.
- One test makes a real model call and costs a few cents. It is skipped unless you set
  `BOSS_LIVE=1`: `BOSS_LIVE=1 uv run pytest tests/test_end_to_end.py`.
- CI runs, on Linux and macOS: `uv sync --locked`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy` (strict, over `src/boss`) and
  `uv run pytest --cov --cov-report=term-missing --cov-fail-under=96 --durations=30`. The coverage floor is 96;
  it only ever goes up. On Linux it first installs `bubblewrap` and runs the tests with
  `BOSS_GATE_SANDBOX=require`, so the sandbox tests fail instead of skipping when `bwrap` cannot
  start (docs/SANDBOX.md).

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
- **Prompts are versioned files** under `src/boss/prompts/`, named `<name>_v<N>.md`. A change to
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

A task is a folder `bench/tasks/<id>/`. The rules are enforced by `boss.bench.tasks`, and
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
   Mutants score the boss's checks (`python -m boss.bench.drafts`); no arm ever sees one, and they
   are not in the task set hash.
7. Every hidden check must fail on an empty workspace and pass on the reference, and every mutant
   must fail one. Check that with `uv run pytest tests/test_bench_tasks.py` and
   `uv run pytest tests/test_bench_mutants.py`.
8. A task set is identified by a hash of every task file, and the task count appears in the
   README and other documents. Adding a task changes both; the docs tests tell you which numbers
   to update. Results recorded against another task set are not comparable, and the results table
   warns when they are mixed.

Real runs are described in [bench/METHOD.md](bench/METHOD.md) and cost money:
`uv run python -m boss.bench.run --dry-run --out /tmp/bench --budget 0.40` lists the cells without
running any.
