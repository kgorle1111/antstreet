"""The Linux sandbox reads the whole root, so secrets outside /home, /root, /tmp and /run (a
project under /srv, /opt or /work) are masked by name. macOS denies every unlisted read.

The argv tests run anywhere. The `bwrap` test runs only where bwrap works (Linux CI, with
BOSS_GATE_SANDBOX=require); the seatbelt test only on macOS. Threat model: T46, T13.
"""

import re
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest
from sandbox_support import working_sandbox
from test_gate_sandbox import HONEST, PROBE, RIGHT, denied

from boss import gate as gate_module
from boss import sandbox
from boss.gate import AUDIT_HOME_ENV, Check, CheckStatus, run_gate, secret_paths
from boss.sandbox import Sandbox, SandboxMode, bwrap_argv

ON, OFF = SandboxMode.REQUIRE, SandboxMode.OFF


@pytest.fixture
def anywhere(monkeypatch):
    """Argv tests build paths under pytest's tmp dir, which Linux CI keeps under /tmp (already
    hidden); with the four roots emptied the masks are emitted as they would be under /srv."""
    monkeypatch.setattr(sandbox, "_BWRAP_HIDDEN_ROOTS", ())


def layout(root: Path) -> tuple[Path, Path, Path, Path]:
    """`<root>/p/.boss/{investor.key, runs/r1/{ws,checks}}` and a key store outside the project."""
    boss = root / "p" / ".boss"
    run = boss / "runs" / "r1"
    (run / "ws").mkdir(parents=True)
    (run / "checks").mkdir()
    (boss / "investor.key").write_text("00" * 32)
    (boss / "runs" / "r1" / "ledger.jsonl").write_text("{}\n")
    store = root / "store"
    store.mkdir()
    (store / "audit.key").write_text("11" * 32)
    return boss, run / "ws", run / "checks", store / "audit.key"


def index_of(argv: list[str], *seq: str) -> int:
    """Return the first position of a consecutive argument sequence, or raise StopIteration."""
    return next(i for i in range(len(argv)) if argv[i : i + len(seq)] == list(seq))


def test_the_mask_comes_after_the_root_and_before_every_bind(tmp_path, anywhere):
    """Ensure secret masks follow the root mounts and precede explicit access grants."""
    boss, ws, checks, outside_key = layout(tmp_path)
    work = boss / "runs" / "r1" / "gate"  # the writable folder may itself live under `.boss`
    work.mkdir()
    argv = bwrap_argv(
        "bwrap", ["x"], writable=work, readable=[checks, Path("/usr")], hidden=[boss, outside_key]
    )
    root, run_tmpfs = index_of(argv, "--ro-bind", "/", "/"), index_of(argv, "--tmpfs", "/run")
    dir_mask = index_of(argv, "--tmpfs", str(boss))
    file_mask = index_of(argv, "--ro-bind", "/dev/null", str(outside_key))
    first_bind = min(
        index_of(argv, "--ro-bind", str(checks), str(checks)),
        index_of(argv, "--bind", str(work), str(work)),
    )
    assert root < run_tmpfs < dir_mask < first_bind
    assert run_tmpfs < file_mask < first_bind


def test_the_workspace_and_the_checks_stay_bound_after_the_mask(tmp_path, anywhere):
    """Keep workspace and check binds available beneath a masked project directory."""
    boss, ws, checks, _ = layout(tmp_path)
    argv = bwrap_argv("bwrap", ["x"], writable=ws, readable=[checks], hidden=[boss])
    tail = argv[index_of(argv, "--tmpfs", str(boss)) :]
    assert tail[2:] == [
        "--ro-bind",
        str(checks),
        str(checks),
        "--bind",
        str(ws),
        str(ws),
        "--",
        "x",
    ]


def test_a_secret_under_a_hidden_root_or_missing_adds_nothing(tmp_path):
    """Avoid redundant masks for paths already hidden or absent from the filesystem."""
    plain = bwrap_argv("bwrap", ["x"], writable=tmp_path, readable=[])
    gone = [Path("/home/u/p/.boss"), Path("/srv/does-not-exist/.boss"), tmp_path / "nope"]
    assert bwrap_argv("bwrap", ["x"], writable=tmp_path, readable=[], hidden=gone) == plain


def test_wrap_gives_seatbelt_no_masks_because_its_profile_is_deny_by_default(tmp_path):
    """Apply hidden-path masks only to bubblewrap, leaving seatbelt arguments unchanged."""
    kwargs = {"writable": tmp_path, "readable": [Path("/usr")]}
    mac = Sandbox("sandbox-exec", "/e")
    assert mac.wrap(["c"], **kwargs, hidden=[tmp_path]) == mac.wrap(["c"], **kwargs)
    assert "--tmpfs" in Sandbox("bwrap", "/e").wrap(["c"], **kwargs, hidden=[tmp_path])


def test_secret_paths_finds_the_project_dot_boss_from_any_path_the_gate_is_given(
    tmp_path, monkeypatch
):
    """Discover and deduplicate project secret directories from workspace and check paths."""
    monkeypatch.delenv(AUDIT_HOME_ENV, raising=False)
    boss, ws, checks, _ = layout(tmp_path)
    assert secret_paths(ws, checks) == (boss,)
    assert secret_paths(tmp_path / "elsewhere", checks) == (boss,)
    assert secret_paths(tmp_path, tmp_path / "x") == ()


def test_secret_paths_adds_the_audit_home_when_set_and_present(tmp_path, monkeypatch):
    """Include an existing absolute audit home and ignore a relative setting."""
    home = tmp_path / "audit"
    home.mkdir()
    monkeypatch.setenv(AUDIT_HOME_ENV, str(home))
    assert secret_paths(tmp_path / "ws") == (home.resolve(),)
    monkeypatch.setenv(AUDIT_HOME_ENV, "relative")
    assert secret_paths(tmp_path / "ws") == ()


def test_run_gate_and_run_tree_hand_the_project_secrets_to_the_sandbox(tmp_path, monkeypatch):
    """Verify both gate entry points pass project secret paths to the sandbox wrapper."""
    calls: list[list[Path]] = []

    class Recording(Sandbox):
        def wrap(self, argv, *, writable, readable, hidden=()):
            """Record secret paths passed to the sandbox without confining the command."""
            calls.append(list(hidden))
            return list(argv)

    monkeypatch.delenv(AUDIT_HOME_ENV, raising=False)
    monkeypatch.setattr(gate_module, "select", lambda mode: Recording("bwrap", "/e"))
    boss, ws, checks, _ = layout(tmp_path)
    (checks / "test_c01.py").write_text(HONEST)
    (ws / "rev.py").write_text(RIGHT)
    [one] = run_gate(ws, checks, [Check("c01", "test_c01.py")], sandbox=ON)
    assert one.status is CheckStatus.PASSED and calls == [[boss]]
    calls.clear()
    gate_module.run_tree(ws, checks, "tests_here", sandbox=ON)
    assert calls == [[boss]]


def test_a_dot_boss_inside_the_workspace_or_tree_is_not_copied_into_the_sandbox(
    tmp_path, monkeypatch
):
    """Exclude nested .boss directories from copied workspaces and imported test trees."""
    seen: list[tuple[bool, bool, bool]] = []

    class Recording(Sandbox):
        def wrap(self, argv, *, writable, readable, hidden=()):
            """Record which files survived the workspace copy without confining the command."""
            ws = writable / "ws"  # the copy the sandbox binds writable, as it is at wrap time
            seen.append(
                ((ws / "keep.py").exists(), (ws / ".boss").exists(), any(ws.rglob(".boss")))
            )
            return list(argv)

    monkeypatch.delenv(AUDIT_HOME_ENV, raising=False)
    monkeypatch.setattr(gate_module, "select", lambda mode: Recording("bwrap", "/e"))
    _, ws, checks, _ = layout(tmp_path)
    for root in (ws, ws / "tests_here"):
        (root / "sub" / ".boss").mkdir(parents=True)
        (root / "sub" / ".boss" / "investor.key").write_text("00" * 32)
        (root / ".boss").mkdir(exist_ok=True)
        (root / ".boss" / "investor.key").write_text("00" * 32)
    (ws / "keep.py").write_text(RIGHT)
    (checks / "test_c01.py").write_text(HONEST)
    run_gate(ws, checks, [Check("c01", "test_c01.py")], sandbox=ON)
    gate_module.run_tree(ws, ws / "tests_here", "tests_here", sandbox=ON)
    assert seen == [(True, False, False)] * 2


# --- real runs -------------------------------------------------------------------------------


def reads(ws: Path, checks: Path, target: Path, mode: SandboxMode) -> str:
    """'allowed' or 'denied:<Error>' for a check, run from the project layout, reading `target`."""
    body = textwrap.indent(f"open({str(target)!r}).read()", " " * 8)
    (checks / "test_c01.py").write_text(PROBE.format(body=body))
    [result] = run_gate(ws, checks, [Check("c01", "test_c01.py")], timeout_s=30.0, sandbox=mode)
    found = re.search(r"OUTCOME=([\w:]+)", result.output_tail)
    assert found, result.output_tail
    return found.group(1)


@pytest.fixture
def outside_the_hidden_roots():
    """A project under /var/tmp, which bwrap leaves readable like /srv, /opt and /work."""
    root = Path(tempfile.mkdtemp(dir="/var/tmp", prefix="boss_secret_"))
    yield root.resolve()
    shutil.rmtree(root, ignore_errors=True)


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="needs bubblewrap (Linux)")
@pytest.mark.skipif(not Path("/var/tmp").is_dir(), reason="needs a folder bwrap leaves readable")
def test_a_check_cannot_read_the_investor_key_of_a_project_outside_the_hidden_roots(
    outside_the_hidden_roots, monkeypatch
):
    """Verify Linux masks project and audit secrets while allowing an honest check."""
    tool = working_sandbox()
    assert tool is not None and tool.name == "bwrap"
    monkeypatch.delenv(AUDIT_HOME_ENV, raising=False)
    boss, ws, checks, audit_key = layout(outside_the_hidden_roots)
    for target in (boss / "investor.key", boss / "runs" / "r1" / "ledger.jsonl"):
        assert reads(ws, checks, target, OFF) == "allowed"  # the probe is not vacuous
        assert denied(reads(ws, checks, target, ON)), target
    # a key store outside the project is masked when the run names it
    monkeypatch.setenv(AUDIT_HOME_ENV, str(audit_key.parent))
    assert reads(ws, checks, audit_key, OFF) == "allowed"
    assert denied(reads(ws, checks, audit_key, ON))
    # the workspace and the checks a gate needs still work with the project masked
    (checks / "test_c01.py").write_text(HONEST)
    (ws / "rev.py").write_text(RIGHT)
    [honest] = run_gate(ws, checks, [Check("c01", "test_c01.py")], sandbox=ON)
    assert honest.status is CheckStatus.PASSED, honest.output_tail


@pytest.mark.skipif(sys.platform != "darwin", reason="pins the macOS seatbelt profile")
def test_seatbelt_denies_reading_the_investor_key_and_ledger_of_a_real_project_layout(tmp_path):
    """Verify macOS denies project secret reads that succeed with the sandbox disabled."""
    tool = working_sandbox()
    if tool is None or tool.name != "sandbox-exec":
        pytest.skip("sandbox-exec cannot run here")
    boss, ws, checks, _ = layout(tmp_path)
    for target in (boss / "investor.key", boss / "runs" / "r1" / "ledger.jsonl"):
        assert reads(ws, checks, target, OFF) == "allowed"
        assert denied(reads(ws, checks, target, ON)), target
