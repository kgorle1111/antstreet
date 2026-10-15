"""scripts/verify_task_set.py: the stdlib-only check a third party runs on a published folder."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from antstreet.bench.tasks import load_tasks, task_set_digest, task_set_hash

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "verify_task_set.py"
POOLS = [ROOT / "bench" / "tasks", ROOT / "bench" / "tasks-multi"]


def verify(pool: Path, expect: str) -> subprocess.CompletedProcess[str]:
    # -I: no site-packages, no cwd on sys.path, so antstreet could not be imported even by accident.
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(pool), "--expect", expect],
        capture_output=True,
        text=True,
        check=False,
        cwd="/",
    )


@pytest.mark.parametrize("pool", POOLS, ids=lambda p: p.name)
def test_the_script_prints_what_the_library_computes_and_exits_0_on_a_match(pool):
    digest = task_set_digest(pool)
    run = verify(pool, digest)
    assert run.returncode == 0, run.stderr
    assert f"digest {digest}" in run.stdout
    assert f"hash   {task_set_hash(load_tasks(pool))}" in run.stdout


def test_a_mismatch_exits_1_and_names_both_digests():
    pool = POOLS[1]
    wrong = "0" * 64
    run = verify(pool, wrong)
    assert run.returncode == 1
    assert wrong in run.stderr and task_set_digest(pool) in run.stderr


def test_malformed_expect_and_missing_dir_exit_2():
    assert verify(POOLS[1], "abc").returncode == 2
    assert verify(ROOT / "nope", "0" * 64).returncode == 2


def test_the_script_refuses_what_the_library_refuses(tmp_path):
    (tmp_path / ".DS_Store").write_bytes(b"x")
    run = verify(tmp_path, "0" * 64)
    assert run.returncode == 2 and "remove it and rerun" in run.stderr


def test_the_script_imports_only_the_standard_library():
    tree = ast.parse(SCRIPT.read_text())
    imported = {
        (n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [None])
    }
    assert imported <= set(sys.stdlib_module_names), imported
