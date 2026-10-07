"""The pytest plugin inside every gate run: it writes the proof a clean session leaves behind.

Not imported by boss. `boss.gate` copies this file into the run folder under a random module name
with the two placeholders below filled in, loads it with `-p`, and the plugin deletes its own file
on import, so the nonce is on disk only until pytest has started and worker code can never be
imported before it. At the end of the session it writes `<collected> <passed> <mac>` to a file only
it can create; `gate._proof_count` checks the mac and that every collected test passed.

"Really passed" is not read from pytest's reports, which a hook or a patch can rewrite. It is
read from the interpreter: `sys.monitoring` reports each test function starting and returning
without an exception leaving it, whatever pytest was told, plus setup and teardown finishing.
A product value must not decide its own comparison either: an object whose `__eq__` always says
True passes `assert reverse("ab") == "ba"`. Every comparison in the check file (`== != < <= > >=
in not in`, in an assert or not) has each operand passed through `_guard` after pytest rewrites
the file. A value built only from builtin and a few stdlib value types (`_honest`) passes through
unchanged, so Python compares it as it always would (`1 == 1.0` holds). Anything else is wrapped
in `_Opaque`, which compares by its own rules only against another wrapped value and is never
equal to an honest one. So two product objects still use the product's `__eq__` (or a product's
`__contains__` for `"ab" in trie`), but a product object never equals a plain expected value.
A `pytest.approx` object counts as honest only if the check file built it. Coverage and gaps:
`docs/SANDBOX.md`, comparisons.

What this cannot stop is code that targets this process: reading the nonce out of this module
(gc, sys.modules), replacing `_guard`, or switching the monitoring off. All need a verdict read
from outside the process (T12).
"""

import ast
import collections
import contextlib
import datetime
import decimal
import fractions
import hashlib
import hmac
import os
import sys
import weakref
from collections import defaultdict
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from _pytest.assertion import rewrite as _rewrite
from _pytest.python_api import ApproxBase

_NONCE = "@NONCE@"
_PROOF = "@PROOF@"
_PHASES = frozenset({"setup", "call", "teardown"})
_EVENTS = sys.monitoring.events
_TOOL = sys.monitoring.PROFILER_ID
_CHECKS = Path(__file__).resolve().parent.parent / "checks"  # the gate's own layout of a run
_GUARD = "@boss_guard"  # not an identifier: no source code can name or shadow it

_collected: list[str] = []
_ok: dict[str, set[str]] = defaultdict(set)
_body: dict[str, list[str]] = defaultdict(list)  # per test: "start", then "return" if it returned
_current: list[str] = []  # the test whose call phase is running
_unguarded: set[str] = set()  # tests whose module was not rewritten with `_guard`: never a pass

with contextlib.suppress(OSError):
    os.unlink(__file__)

# Compared natively when both sides are honest. Exact types only: a subclass of `int` or `str`
# can carry its own `__eq__`, and a scalar subclass can fake `numerator` for `Fraction.__eq__`.
_SCALARS = frozenset(
    {type(None), bool, int, float, complex, str, bytes, bytearray, range, type, decimal.Decimal}
    | {datetime.date, datetime.datetime, datetime.time, datetime.timedelta, datetime.timezone}
)
_VIEWS = frozenset({type({}.keys()), type({}.values()), type({}.items())})
_STDLIB_CONTAINERS = frozenset(
    {collections.deque, collections.OrderedDict, collections.defaultdict, collections.Counter}
)
# A subclass of one of these (a namedtuple) is honest if it keeps every comparison of its base;
# their comparisons read the object's own storage, which a subclass cannot redirect.
_CONTAINERS = (list, tuple, dict, set, frozenset)
_COMPARISONS = ("__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__", "__contains__")
_GUARDED_OPS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn)


# `pytest.approx` objects the check file built. One the product built is not trusted: it can hold
# a value that equals everything, or an infinite tolerance.
_matchers: dict[int, weakref.ref[ApproxBase]] = {}  # by id; an approx object is unhashable
# kn: entries for dead matchers are never pruned and `_honest` walks a whole value per comparison;
# both are bounded by one check's size. Prune on a weakref callback if a check ever builds millions.
_pytest_approx = pytest.approx


def _approx(*args: Any, **kwargs: Any) -> ApproxBase:
    matcher = _pytest_approx(*args, **kwargs)
    if Path(sys._getframe(1).f_code.co_filename).resolve().parent == _CHECKS:
        _matchers[id(matcher)] = weakref.ref(matcher)
    return matcher


pytest.approx = _approx  # the check imports pytest after this plugin


def _built_by_the_check(item: object) -> bool:
    ref = _matchers.get(id(item))
    return ref is not None and ref() is item  # a dead entry's id may be reused


def _container_base(cls: type) -> type | None:
    if cls in _STDLIB_CONTAINERS:
        return cls
    for base in _CONTAINERS:
        if issubclass(cls, base) and all(
            getattr(cls, name, None) is getattr(base, name, None) for name in _COMPARISONS
        ):
            return base
    return None


def _honest(value: object) -> bool:
    """True when nothing reachable from `value` can run product code in a comparison. Walks
    containers with their base type's iterator, so an overridden `__iter__` hides nothing."""
    stack: list[Any] = [value]
    seen: set[int] = set()
    while stack:
        item = stack.pop()
        cls = type(item)
        if cls in _SCALARS or _built_by_the_check(item):
            continue
        if cls is fractions.Fraction:
            if type(item._numerator) is int and type(item._denominator) is int:
                continue
            return False
        if id(item) in seen:
            continue
        seen.add(id(item))
        if cls in _VIEWS:
            stack.extend(item)
        elif (base := _container_base(cls)) is None:
            return False
        elif issubclass(base, dict):
            stack.extend(part for pair in dict.items(item) for part in pair)
        else:
            stack.extend(base.__iter__(item))  # type: ignore[attr-defined]
    return True


class _Opaque:
    """A value the product made, as it enters a comparison in the check. Against another wrapped
    value it compares as the product says; against an honest value it is unequal and unordered."""

    __slots__ = ("inner",)

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def __eq__(self, other: object) -> Any:
        return self.inner == other.inner if type(other) is _Opaque else False

    def __ne__(self, other: object) -> Any:
        return self.inner != other.inner if type(other) is _Opaque else True

    def __lt__(self, other: object) -> Any:
        return self.inner < other.inner if type(other) is _Opaque else NotImplemented

    def __le__(self, other: object) -> Any:
        return self.inner <= other.inner if type(other) is _Opaque else NotImplemented

    def __gt__(self, other: object) -> Any:
        return self.inner > other.inner if type(other) is _Opaque else NotImplemented

    def __ge__(self, other: object) -> Any:
        return self.inner >= other.inner if type(other) is _Opaque else NotImplemented

    def __contains__(self, item: object) -> bool:
        return (item.inner if type(item) is _Opaque else item) in self.inner

    def __hash__(self) -> int:
        return hash(self.inner)

    def __repr__(self) -> str:
        return repr(self.inner)


def _guard(value: object) -> object:
    return value if _honest(value) else _Opaque(value)


class _Guard(ast.NodeTransformer):
    def visit_Compare(self, node: ast.Compare) -> ast.Compare:
        self.generic_visit(node)
        if not all(isinstance(op, _GUARDED_OPS) for op in node.ops) or _names_a_local(node):
            return node  # `is` keeps identity; pytest's own `"x" in locals()` needs no guard
        node.left = _call(node.left)
        node.comparators = [_call(operand) for operand in node.comparators]
        return node


def _call(operand: ast.expr) -> ast.expr:
    name = ast.copy_location(ast.Name(_GUARD, ast.Load()), operand)
    return ast.copy_location(ast.Call(name, [operand], []), operand)


def _names_a_local(node: ast.Compare) -> bool:
    match node.comparators:
        case [ast.Call(func=ast.Attribute(value=ast.Name(id="@py_builtins"), attr="locals"))]:
            return True
    return False


def _guard_module(mod: ast.Module) -> None:
    _Guard().visit(mod)
    pos = 0  # after the docstring and `from __future__` imports, where pytest puts its own
    for stmt in mod.body:
        match stmt:
            case ast.Expr(value=ast.Constant(value=str())) if pos == 0:
                pos += 1
            case ast.ImportFrom(module="__future__"):
                pos += 1
            case _:
                break
    # Not `ast.fix_missing_locations`: it would stamp end lines onto pytest's own nodes.
    line = mod.body[pos].lineno if pos < len(mod.body) else 1
    place = {"lineno": line, "col_offset": 0, "end_lineno": line, "end_col_offset": 0}
    alias = ast.alias("_guard", _GUARD, **place)
    mod.body.insert(pos, ast.ImportFrom(__name__, [alias], 0, **place))


_pytest_rewrite_asserts = _rewrite.rewrite_asserts


def _rewrite_asserts(mod: ast.Module, source: bytes, module_path: str | None = None, config=None):  # type: ignore[no-untyped-def]
    _pytest_rewrite_asserts(mod, source, module_path, config)
    if module_path is not None and Path(module_path).resolve().parent == _CHECKS:
        _guard_module(mod)


_rewrite.rewrite_asserts = _rewrite_asserts  # looked up at call time by pytest's import hook


def _on(event: str) -> Callable[..., None]:
    def record(*_: object) -> None:
        if _current:
            _body[_current[0]].append(event)

    return record


_LOCAL = _EVENTS.PY_START | _EVENTS.PY_RETURN  # an exception unwinding the frame fires neither
sys.monitoring.use_tool_id(_TOOL, "boss-gate")  # taken: pytest cannot start, which is a FAILED
sys.monitoring.register_callback(_TOOL, _EVENTS.PY_START, _on("start"))
sys.monitoring.register_callback(_TOOL, _EVENTS.PY_RETURN, _on("return"))


def pytest_itemcollected(item: pytest.Function) -> None:
    _collected.append(item.nodeid)
    if not hasattr(item.module, _GUARD):  # pytest did not rewrite the check: fail closed
        _unguarded.add(item.nodeid)
    code = getattr(item.obj, "__func__", item.obj).__code__
    sys.monitoring.set_local_events(_TOOL, code, _LOCAL)


def _phase(item: pytest.Item, name: str, result: object) -> object:
    _ok[item.nodeid].add(name)
    return result


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None, object, object]:
    return _phase(item, "setup", (yield))


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, object, object]:
    _current[:] = [item.nodeid]
    try:
        result = yield
    finally:
        _current.clear()
    return _phase(item, "call", result)


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_runtest_teardown(
    item: pytest.Item, nextitem: pytest.Item | None
) -> Generator[None, object, object]:
    return _phase(item, "teardown", (yield))


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish() -> None:
    total = len(_collected)
    passed = {
        node
        for node in _collected
        if _ok[node] == _PHASES and _body[node] == ["start", "return"] and node not in _unguarded
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
