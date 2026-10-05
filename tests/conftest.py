import faulthandler
import hashlib
import os
import signal

import pytest

# Measured 2026-10-04 (`--durations`): each of these spends minutes in subprocesses (gates inside a
# sandbox, benchmark validation, simulated firms). A plain `uv run pytest` leaves them out; CI runs
# them. Whole files by name, single tests by node id. Add a test when it takes over ~8 seconds.
SLOW = (
    "tests/test_bench_tasks.py",
    "tests/test_bench_mutants.py",
    "tests/test_bench_run.py",
    "tests/test_bench_held_out.py",
    "tests/test_bench_drafts_staged.py",
    "tests/test_bench_single_review.py",
    "tests/test_bench_score.py",
    "tests/test_firm.py",
    "tests/test_firm_simulation.py",
    "tests/test_pipeline.py",
    "tests/test_docs_ledger.py",
    "tests/test_audit_check.py",
    "tests/test_audit_report.py",
    "tests/test_docs_contributing.py::test_a_task_built_by_those_steps_validates",
    "tests/test_docs_cli.py::test_a_run_with_roles_holds_the_extra_paths_the_document_lists",
    "tests/test_runner.py::test_a_slice_can_be_stopped_from_another_thread_and_its_cost_is_still_read",
    "tests/test_runner.py::test_worker_ignoring_sigint_and_sigterm_is_still_killed",
)
SHARD_ENV = "BOSS_SHARD"
TIMEOUT_ENV = "BOSS_TEST_TIMEOUT_S"


def pytest_configure(config):
    """Restore SIGINT handling so simulated Ctrl-C works in background test runs."""
    # A shell starts a backgrounded command (`pytest &`) with SIGINT ignored, and Python keeps it
    # ignored, so the fakes' simulated Ctrl-C would be dropped and every interrupt test would fail.
    signal.signal(signal.SIGINT, signal.default_int_handler)


def parse_shard(raw: str) -> tuple[int, int]:
    """`"i/N"` as (i, N), 0 <= i < N; anything else is a usage error, never "run everything"."""
    try:
        index, count = (int(part) for part in raw.split("/"))
    except ValueError:
        index = count = -1
    if not 0 <= index < count:
        raise pytest.UsageError(f"{SHARD_ENV}={raw!r} must look like i/N with 0 <= i < N")
    return index, count


def shard_of(path: str, count: int) -> int:
    """The shard a test file belongs to: a hash of its path, stable across runs and machines."""
    return int(hashlib.sha256(path.encode()).hexdigest(), 16) % count


def pytest_collection_modifyitems(config, items):
    """Mark the known slow tests, then select the configured file shard."""
    for item in items:
        if item.nodeid.startswith(SLOW):
            item.add_marker(pytest.mark.slow)
    _shard(config, items)


def _shard(config, items):
    """`BOSS_SHARD=i/N` keeps the tests of the files that hash to shard i, so a module's shared
    fixtures and xdist groups stay together and the N shards partition the suite exactly."""
    raw = os.environ.get(SHARD_ENV, "").strip()
    if not raw:
        return
    index, count = parse_shard(raw)
    keep, dropped = [], []
    for item in items:
        mine = shard_of(item.nodeid.split("::")[0], count) == index
        (keep if mine else dropped).append(item)
    if dropped:
        config.hook.pytest_deselected(items=dropped)
    items[:] = keep


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """`BOSS_TEST_TIMEOUT_S=N` ends the process, with every thread's stack on stderr, when one test
    takes longer than N seconds. A hung test then fails its CI job in minutes instead of holding it
    to the job's timeout (under xdist the worker dies and the run reports the test it was on).
    Not a pytest-timeout: no per-test failure that lets the rest of that worker continue."""
    limit = float(os.environ.get(TIMEOUT_ENV, "0") or 0)
    if limit > 0:
        faulthandler.dump_traceback_later(limit, exit=True)
    try:
        yield
    finally:
        if limit > 0:
            faulthandler.cancel_dump_traceback_later()
