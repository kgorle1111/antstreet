"""The pytest plugin inside every gate run: it writes the proof a clean session leaves behind.

Not imported by boss. `boss.gate` copies this file into the run folder under a random module name
with the two placeholders below filled in, loads it with `-p`, and the plugin deletes its own file
on import, so the nonce is on disk only until pytest has started and worker code can never be
imported before it. At the end of the session it writes `<collected> <passed> <mac>` to a file only
it can create; `gate._proof_count` checks the mac and that every collected test passed.

"Really passed" is not read from pytest's reports, which a hook or a patch can rewrite. It is
read from the interpreter: `sys.monitoring` reports each test function starting and returning
without an exception leaving it, whatever pytest was told, plus setup and teardown finishing.
What this cannot stop is code that targets this process: reading the nonce out of this module
(gc, sys.modules), or switching the monitoring off. Both need a verdict read from outside the
process (T12).
"""

import contextlib
import hashlib
import hmac
import os
import sys
from collections import defaultdict

import pytest

_NONCE = "@NONCE@"
_PROOF = "@PROOF@"
_PHASES = frozenset({"setup", "call", "teardown"})
_EVENTS = sys.monitoring.events
_TOOL = sys.monitoring.PROFILER_ID

_collected: list[str] = []
_ok: dict[str, set[str]] = defaultdict(set)
_body: dict[str, list[str]] = defaultdict(list)  # per test: "start", then "return" if it returned
_current: list[str] = []  # the test whose call phase is running

with contextlib.suppress(OSError):
    os.unlink(__file__)


def _on(event):
    def record(*_):
        if _current:
            _body[_current[0]].append(event)

    return record


_LOCAL = _EVENTS.PY_START | _EVENTS.PY_RETURN  # an exception unwinding the frame fires neither
sys.monitoring.use_tool_id(_TOOL, "boss-gate")  # taken: pytest cannot start, which is a FAILED
sys.monitoring.register_callback(_TOOL, _EVENTS.PY_START, _on("start"))
sys.monitoring.register_callback(_TOOL, _EVENTS.PY_RETURN, _on("return"))


def pytest_itemcollected(item):
    _collected.append(item.nodeid)
    code = getattr(item.obj, "__func__", item.obj).__code__
    sys.monitoring.set_local_events(_TOOL, code, _LOCAL)


def _phase(item, name, result):
    _ok[item.nodeid].add(name)
    return result


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_runtest_setup(item):
    return _phase(item, "setup", (yield))


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_runtest_call(item):
    _current[:] = [item.nodeid]
    try:
        result = yield
    finally:
        _current.clear()
    return _phase(item, "call", result)


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_runtest_teardown(item, nextitem):
    return _phase(item, "teardown", (yield))


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish():
    total = len(_collected)
    passed = {
        node for node in _collected if _ok[node] == _PHASES and _body[node] == ["start", "return"]
    }
    if total == 0:
        return
    mac = hmac.new(_NONCE.encode(), f"{total}:{len(passed)}".encode(), hashlib.sha256)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(_PROOF, flags, 0o600)
    except OSError:
        return  # a file already there is not ours: no proof, so the gate says FAILED
    with os.fdopen(fd, "w") as fh:
        fh.write(f"{total} {len(passed)} {mac.hexdigest()}")
