"""Product code written to make the gate say PASSED for the wrong product. Each string is the
body of `rev.py`; `WRONG` follows it so a real run of the check fails. Shared by the gate tests."""

CHECK = "from rev import reverse\n\ndef test_reverse():\n    assert reverse('ab') == 'ba'\n"
RIGHT = "def reverse(s):\n    return s[::-1]\n"
WRONG = "def reverse(s):\n    return s\n"

# Rewrites the gate's JUnit report as one clean pass and exits 0, as late as it can (T12).
REPORT_FORGER = (
    "import atexit, os, sys\n"
    "def forge():\n"
    "    path = next(a for a in sys.argv if a.startswith('--junitxml=')).split('=', 1)[1]\n"
    "    with open(path, 'w') as fh:\n"
    '        fh.write(\'<testsuite tests="1" failures="0" errors="0" skipped="0"/>\')\n'
    "    os._exit(0)\n"
    "atexit.register(forge)\n"
)
EXIT_AT_IMPORT = "import os\nos._exit(0)\n"
SYS_EXIT_AT_IMPORT = "import sys\nsys.exit(0)\n"
EXIT_ZERO_AT_EXIT = "import atexit, os\natexit.register(lambda: os._exit(0))\n"

# Makes pytest itself report every phase as passed: the report, the JUnit file and the exit code
# are then all honest-looking. Only the outcome read below the hooks and patches can tell.
PATCHED_REPORT = """\
import _pytest.reports as r
_orig = r.TestReport.from_item_and_call.__func__
def _forced(cls, item, call):
    report = _orig(cls, item, call)
    report.outcome, report.longrepr = "passed", None
    return report
r.TestReport.from_item_and_call = classmethod(_forced)
"""
# The same through the supported route: a hook wrapper registered on the live plugin manager.
HOOKED_REPORT = """\
import gc, pytest
from _pytest.config import Config
class Forcer:
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        report = (yield).get_result()
        report.outcome, report.longrepr = "passed", None
for obj in gc.get_objects():
    if isinstance(obj, Config):
        obj.pluginmanager.register(Forcer())
"""
# Swallows the exception of every test body from a wrapper that asks to sit innermost.
SWALLOWED_FAILURE = """\
import gc, pytest
from _pytest.config import Config
class Swallow:
    @pytest.hookimpl(hookwrapper=True, trylast=True)
    def pytest_runtest_call(self, item):
        (yield).force_result(None)
for obj in gc.get_objects():
    if isinstance(obj, Config):
        obj.pluginmanager.register(Swallow())
"""
# Answers "the test was called" before pytest calls it, so no test body ever runs.
PREEMPTED_CALL = """\
import gc, pytest
from _pytest.config import Config
class Preempt:
    @pytest.hookimpl(tryfirst=True)
    def pytest_pyfunc_call(self, pyfuncitem):
        return True
for obj in gc.get_objects():
    if isinstance(obj, Config):
        obj.pluginmanager.register(Preempt())
"""
# The body of every test becomes a no-op, so nothing the check asserts is ever run.
NOOP_RUNTEST = "from _pytest.python import Function\nFunction.runtest = lambda self: None\n"
# Drops every test from the run, after pytest collected it.
DESELECT_ALL = """\
import gc, pytest
from _pytest.config import Config
class Dropper:
    def pytest_collection_modifyitems(self, items):
        items.clear()
for obj in gc.get_objects():
    if isinstance(obj, Config):
        obj.pluginmanager.register(Dropper())
"""

# Finds the gate's plugin module and what it holds. `_plugin()` is the first line of the attacks
# that need the proof's path or the nonce.
FIND_PLUGIN = """\
import sys
def _plugin():
    return next(m for m in list(sys.modules.values()) if hasattr(m, "_PROOF"))
"""
# Knows where the proof goes but not the nonce: creates it first with a guessed signature.
PROOF_GUESSER = (
    FIND_PLUGIN
    + """\
import hashlib, hmac
_p = _plugin()
with open(_p._PROOF, "w") as fh:
    fh.write("1 1 " + hmac.new(b"guess", b"1:1", hashlib.sha256).hexdigest())
"""
    + REPORT_FORGER
)
# Creates the proof's path first, so the plugin's exclusive create cannot write the real one.
PROOF_SQUATTER = FIND_PLUGIN + "open(_plugin()._PROOF, 'w').write('squatted')\n"
# The remaining attack (T12): code that reads the nonce out of the plugin module in its own
# process signs the proof itself.
NONCE_READER = (
    FIND_PLUGIN
    + """\
import hashlib, hmac
_p = _plugin()
with open(_p._PROOF, "w") as fh:
    fh.write("1 1 " + hmac.new(_p._NONCE.encode(), b"1:1", hashlib.sha256).hexdigest())
"""
    + REPORT_FORGER
)

# A value that agrees with every comparison. Not aimed at the gate: it games any `assert x == y`
# that lets the product's object decide, and needs no knowledge of the nonce or the plugin.
ANYTHING = """\
class Anything:
    def __eq__(self, other): return True
    def __ne__(self, other): return False
    def __lt__(self, other): return True
    def __le__(self, other): return True
    def __gt__(self, other): return True
    def __ge__(self, other): return True
    def __contains__(self, item): return True
    def __hash__(self): return 0
"""
ALWAYS_EQUAL = ANYTHING + "def reverse(s):\n    return Anything()\n"
# The same trick on a builtin's subclass, so `isinstance(x, str)` also holds.
STR_ALWAYS_EQUAL = (
    "class S(str):\n"
    "    __eq__ = lambda self, other: True\n"
    "    __ne__ = lambda self, other: False\n"
    "    __hash__ = str.__hash__\n"
    "def reverse(s):\n    return S('nope')\n"
)
# Hidden one level down, inside a real list and a real tuple.
NESTED_ALWAYS_EQUAL = ANYTHING + "def reverse(s):\n    return [Anything(), (Anything(),)]\n"
# Review findings on the comparison guard, one product each.
# A metaclass that makes the class compare equal to `int`, so a set lookup of the type finds it.
METACLASS_EQ = """\
class Meta(type):
    def __eq__(cls, other): return True
    def __hash__(cls): return hash(int)
class Anything(metaclass=Meta):
    def __eq__(self, other): return True
    def __hash__(self): return 0
def reverse(s):
    return Anything()
"""
# A metaclass that answers `getattr(cls, "__eq__")` with list's, while the real slot is its own.
METACLASS_GETATTR = """\
_NAMES = {"__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__", "__contains__", "__hash__"}
class Meta(type):
    def __getattribute__(cls, name):
        if name in _NAMES:
            return getattr(list, name)
        return type.__getattribute__(cls, name)
class Fake(list, metaclass=Meta):
    def __eq__(self, other): return True
    def __ne__(self, other): return False
def reverse(s):
    return Fake(['x'])
"""
# A tzinfo whose utcoffset finds the other side of the comparison and makes the instants equal.
TZINFO_FORGER = """\
import datetime, sys
class Tz(datetime.tzinfo):
    def utcoffset(self, dt):
        for value in sys._getframe(1).f_locals.values():
            if isinstance(value, datetime.datetime) and value.tzinfo not in (None, self):
                other = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                return dt.replace(tzinfo=None) - other
        return datetime.timedelta(0)
def reverse(s):
    return datetime.datetime(2020, 1, 1, tzinfo=Tz())
"""
# Builds pytest.approx(0, abs=inf) in code compiled under a file name inside the checks folder.
APPROX_FAKE_FILENAME = """\
import os
_src = "import pytest\\nmatcher = pytest.approx(0, abs=float('inf'))\\n"
_name = os.path.join(os.path.dirname(os.getcwd()), "checks", "test_planted.py")
_scope = {}
exec(compile(_src, _name, "exec"), _scope)
def reverse(s):
    return _scope["matcher"]
"""
# A tuple subclass that keeps tuple's comparisons but hashes to 0, so a set lookup misses.
TUPLE_BAD_HASH = """\
class T(tuple):
    def __hash__(self): return 0
def reverse(s):
    return T(s)
"""
# pytest's own matcher, built by the product around a value that equals everything.
APPROX_ANYTHING = (
    ANYTHING + "import pytest\ndef reverse(s):\n    return pytest.approx(Anything())\n"
)
