"""The built wheel carries the runtime data (prompts, skills, rubrics) and nothing from the repo."""

import shutil
import subprocess
import zipfile

import pytest
from docs_support import ROOT

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv builds the wheel")

PKG = ROOT / "src" / "antstreet"
NOT_SHIPPED = ("tests/", "bench/", ".claude/", "docs/", "ops/", "posts/")


@pytest.fixture(scope="module")
def wheel_names(tmp_path_factory) -> set[str]:
    out = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        ["uv", "build", "--wheel", "-o", str(out)], cwd=ROOT, check=True, capture_output=True
    )
    (built,) = out.glob("*.whl")
    return set(zipfile.ZipFile(built).namelist())


def test_every_non_python_runtime_file_is_in_the_wheel(wheel_names):
    data = [p for p in PKG.rglob("*") if p.is_file() and p.suffix in {".md", ".json"}]
    assert data, "no prompts, skills or rubrics found"
    wanted = {p.relative_to(PKG.parent).as_posix() for p in data}
    assert not wanted - wheel_names, f"not in the wheel: {sorted(wanted - wheel_names)}"


def test_nothing_from_the_repo_outside_the_package_is_in_the_wheel(wheel_names):
    leaked = [n for n in wheel_names if n.startswith(NOT_SHIPPED)]
    assert not leaked, f"leaked into the wheel: {leaked[:5]}"


def test_the_wheel_ships_antstreet_and_the_boss_alias(wheel_names):
    assert {"antstreet/__init__.py", "antstreet/cli.py", "boss/__init__.py"} <= wheel_names
    alias = {n for n in wheel_names if n.startswith("boss/") and not n.endswith("/")}
    assert alias == {"boss/__init__.py"}  # the alias is one file; the code is only in antstreet/
