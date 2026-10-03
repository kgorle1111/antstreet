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
