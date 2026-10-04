import faulthandler
import hashlib
import os
import signal

import pytest

SHARD_ENV = "BOSS_SHARD"
TIMEOUT_ENV = "BOSS_TEST_TIMEOUT_S"


def pytest_configure(config):
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
    """`BOSS_SHARD=i/N` keeps the tests of the files that hash to shard i, so a module's shared
    fixtures and xdist groups stay together and the N shards partition the suite exactly."""
    raw = os.environ.get(SHARD_ENV, "").strip()
    if not raw:
        return
    index, count = parse_shard(raw)
    keep = [i for i in items if shard_of(i.nodeid.split("::")[0], count) == index]
    dropped = [i for i in items if i not in keep]
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
