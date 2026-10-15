"""The pytest plugin inside every `gate.run_tree` run: a time limit per test and a progress log.

Not imported by antstreet. `gate.run_tree` copies this file into the run folder under a random
module name with the two placeholders below filled in and loads it with `-p`.

One hanging test must not cost the results of the others. Each phase of a test (setup, call,
teardown) gets `_LIMIT` seconds of wall clock from `SIGALRM`; the handler raises a `BaseException`
(not an `Exception`, which a test's own `except Exception:` would swallow), pytest reports that
test as failed with `MARK` in the message, and the run goes on. `gate._tree_statuses` reads the
mark and reports the test as `timeout`.

The alarm cannot stop what ignores signals (a test that resets the handler, a C extension that
never returns). The suite cap in `gate.run_tree` still kills the process then, and the progress
log tells which tests had finished and which one was running: JUnit is only written at the end.
Like the rest of a tree run it is unsigned: a product written to fake its results can (T12).
"""

import contextlib
import json
import os
import signal
from collections.abc import Generator, Iterator
from types import FrameType

import pytest

_LIMIT = float("@LIMIT@")
_PROGRESS = "@PROGRESS@"
MARK = "boss-test-timeout"

_fd = os.open(
    _PROGRESS, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600
)
_bad: dict[str, bool] = {}
_timed: set[str] = set()


class _TestTimeout(BaseException):
    pass


def _log(tag: str, node: str) -> None:
    os.write(_fd, (json.dumps([tag, node]) + "\n").encode())


def _fire(signum: int, frame: FrameType | None) -> None:
    raise _TestTimeout(f"{MARK}: a test phase exceeded {_LIMIT:g}s")


@contextlib.contextmanager
def _limited() -> Iterator[None]:
    signal.signal(signal.SIGALRM, _fire)
    signal.setitimer(signal.ITIMER_REAL, _LIMIT)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def pytest_runtest_logstart(nodeid: str, location: object) -> None:
    _log("start", nodeid)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None, object, object]:
    with _limited():
        return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, object, object]:
    with _limited():
        return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_teardown(
    item: pytest.Item, nextitem: pytest.Item | None
) -> Generator[None, object, object]:
    with _limited():
        return (yield)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    node = report.nodeid
    if report.outcome != "passed":
        _bad[node] = True
    if MARK in str(report.longrepr):
        _timed.add(node)
    if report.when == "teardown":
        tag = "timeout" if node in _timed else "failed" if _bad.get(node) else "passed"
        _log(tag, node)
