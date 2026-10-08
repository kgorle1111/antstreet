"""`boss audit` with the repo's own `.venv`: its packages reach the checks, inside the sandbox only,
and its startup hooks (`.pth`, `sitecustomize`) never run."""

import sys
from pathlib import Path

import pytest
from audit_support import DRAFT, RIGHT_SLUG, WRONG_SLUG, Audit, branch, git, later, write
from sandbox_support import working_sandbox

import antstreet.audit as audit_module
from antstreet.audit import repo_env
from antstreet.gate import Check, GateError, run_gate
from antstreet.sandbox import SandboxMode

TOOL = working_sandbox()
needs_sandbox = pytest.mark.skipif(TOOL is None, reason="no working OS sandbox on this machine")
TAG = f"python{sys.version_info.major}.{sys.version_info.minor}"
SITE = f".venv/lib/{TAG}/site-packages"
# Fails on the base (slugify only lower-cases) and passes on a right head, given the package.
C_DEP = (
    "import depzq\nfrom slug import slugify\n\n\n"
    "def test_uses_the_dependency():\n    assert slugify('Hello,  World') == depzq.EXPECTED\n"
)
DEP_DRAFT = {
    "tasks": DRAFT["tasks"],
    "checks": [{"description": "collapses runs, via a dependency", "task": "t1", "code": C_DEP}],
}


def make_venv(repo: Path, tag: str = TAG) -> Path:
    """A `.venv` as `uv sync` leaves it, holding `depzq`, a stand-in for a third-party package.
    The `.gitignore` of `*` inside it is what uv writes, so the working tree stays clean."""
    write(repo, ".venv/pyvenv.cfg", "home = /usr/bin\n")
    write(repo, ".venv/.gitignore", "*\n")
    site = repo / ".venv" / "lib" / tag / "site-packages"
    write(repo, f".venv/lib/{tag}/site-packages/depzq/__init__.py", "EXPECTED = 'hello-world'\n")
    return site


def sealed_with(folder: Path, venv: bool) -> Audit:
    audit = Audit(folder)
    audit.set_draft(DEP_DRAFT)
    if venv:
        make_venv(audit.repo)
    return audit


def heads(audit: Audit) -> None:
    branch(audit.repo, "good", {"slug.py": RIGHT_SLUG}, later())
    branch(audit.repo, "bad", {"slug.py": WRONG_SLUG}, later())


# --- end to end -------------------------------------------------------------------------------


def test_without_a_venv_a_check_needing_a_package_is_blocked_and_the_output_says_what_to_run(
    tmp_path,
):
    audit = sealed_with(tmp_path, venv=False)
    code, said = audit.plan()
    assert code == 0, said
    assert "has no .venv" in said and "uv sync" in said
    assert "c01: cannot run here: not counted (needs module 'depzq')" in said
    heads(audit)
    code, said = audit.check(audit.run_id(), "good", "--claim", "done")
    assert code == 3 and "Verdict: INCONCLUSIVE" in said
    assert "Environment:" in said and "uv sync" in said


@needs_sandbox
def test_with_the_repos_venv_the_check_is_counted_and_decides_the_verdict(tmp_path):
    audit = sealed_with(tmp_path, venv=True)
    code, said = audit.plan()
    assert code == 0, said
    assert "the repo's own .venv" in said and "nothing was installed" in said
    assert "c01: fails on the base: counted" in said
    heads(audit)
    run = audit.run_id()
    code, said = audit.check(run, "good", "--claim", "done")
    assert code == 0 and "Verdict: UNREFUTED" in said, said
    code, said = audit.check(run, "bad", "--claim", "done")
    assert code == 3 and "Verdict: REFUTED" in said, said


@needs_sandbox
def test_a_hostile_venv_cannot_run_startup_hooks_write_outside_or_flip_the_verdict(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    audit = sealed_with(tmp_path / "a", venv=True)
    site = audit.repo / SITE
    # Either hook, if it ran, would swap in a `depzq` that makes the right head fail (a flipped
    # verdict the gate's plugin cannot see), then try to leave a mark outside the sandbox.
    swap = (
        "import sys, types; m = types.ModuleType('depzq'); m.EXPECTED = 'flipped'; "
        "sys.modules['depzq'] = m"
    )
    (site / "sitecustomize.py").write_text(
        f"{swap}\nopen({str(outside / 'sitecustomize')!r}, 'w').write('ran')\n"
    )
    (site / "zz_evil.pth").write_text(
        f"{swap}\nimport os; open({str(outside / 'pth')!r}, 'w').write('ran')\n"
    )
    # A pytest plugin by entry point: pytest would auto-load it once the site-packages is on
    # sys.path, unless PYTEST_DISABLE_PLUGIN_AUTOLOAD (gate._env) stays set.
    (site / "zz_evilplug.py").write_text(
        f"{swap}\nopen({str(outside / 'plugin')!r}, 'w').write('ran')\n"
    )
    dist = site / "zz_evilplug-0.1.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: zz-evilplug\nVersion: 0.1\n")
    (dist / "entry_points.txt").write_text("[pytest11]\nevil = zz_evilplug\n")
    # The package a check imports does run (that is the point of it); it still cannot write out.
    (site / "depzq" / "__init__.py").write_text(
        "EXPECTED = 'hello-world'\n"
        "try:\n"
        f"    open({str(outside / 'imported')!r}, 'w').write('ran')\n"
        "except OSError:\n"
        "    pass\n"
    )
    assert audit.plan()[0] == 0
    heads(audit)
    code, said = audit.check(audit.run_id(), "good", "--claim", "done")
    assert code == 0 and "Verdict: UNREFUTED" in said, said
    assert list(outside.iterdir()) == []


@needs_sandbox
def test_the_check_after_a_plan_defaults_to_the_latest_run_and_to_head(tmp_path):
    audit = sealed_with(tmp_path, venv=True)
    assert audit.plan()[0] == 0
    good = branch(audit.repo, "good", {"slug.py": RIGHT_SLUG}, later())
    git(audit.repo, "checkout", "-q", "good")
    code, said = audit.run("check", "--repo", str(audit.repo), "--claim", "done")
    assert code == 0 and "Verdict: UNREFUTED" in said and f"head {good[:12]}" in said, said


# --- what is found, and what is refused --------------------------------------------------------


def test_a_venv_for_another_python_is_not_used_and_says_so(tmp_path):
    make_venv(tmp_path, tag="python3.0")
    found = repo_env(tmp_path, tmp_path / "store")
    assert found.site_packages is None
    assert "for python3.0" in found.note and TAG in found.note


def test_a_site_packages_that_resolves_outside_the_repo_is_refused(tmp_path):
    repo, elsewhere = tmp_path / "repo", tmp_path / "elsewhere"
    elsewhere.mkdir()
    write(repo, ".venv/pyvenv.cfg", "home = /usr/bin\n")
    (repo / ".venv" / "lib" / TAG).mkdir(parents=True)
    (repo / SITE).symlink_to(elsewhere)
    found = repo_env(repo, tmp_path / "store")
    assert found.site_packages is None and "outside the repo" in found.note


def test_a_site_packages_holding_the_audit_store_is_refused(tmp_path):
    site = make_venv(tmp_path)
    found = repo_env(tmp_path, site / "store")
    assert found.site_packages is None and "audit store" in found.note


def test_without_a_sandbox_the_venv_is_not_used(tmp_path, monkeypatch):
    make_venv(tmp_path)
    monkeypatch.setattr(audit_module, "sandbox_available", lambda: False)
    found = repo_env(tmp_path, tmp_path / "store")
    assert found.site_packages is None and "OS sandbox" in found.note


def test_the_gate_refuses_a_site_packages_without_a_sandbox(tmp_path):
    site = make_venv(tmp_path)
    (tmp_path / "checks").mkdir()
    (tmp_path / "checks" / "c.py").write_text("def test_x():\n    pass\n")
    with pytest.raises(GateError, match="without an OS sandbox"):
        run_gate(
            tmp_path, tmp_path / "checks", [Check("c", "c.py")], sandbox=SandboxMode.OFF,
            site_packages=site,
        )  # fmt: skip
