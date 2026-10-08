"""Finding the sandbox for tests that need one. Not a test module."""

import os

from antstreet import sandbox
from antstreet.gate import SANDBOX_ENV
from antstreet.sandbox import Sandbox, SandboxMode


def working_sandbox() -> Sandbox | None:
    """What `detect()` finds. Under `BOSS_GATE_SANDBOX=require` a missing one raises instead.

    Without this the `skipif(TOOL is None)` guards would skip every sandbox test when bwrap cannot
    start, and a CI run that asked for a sandbox would go green having tested none.
    """
    if os.environ.get(SANDBOX_ENV, "").strip().lower() == SandboxMode.REQUIRE:
        return sandbox.select(SandboxMode.REQUIRE)
    return sandbox.detect()
