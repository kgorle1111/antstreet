"""Layering: roles and the core never import the CLI or the benchmark (docs/DECISIONS.md D42)."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "antstreet"
CORE = ("rule", "gate", "ledger", "signing", "sandbox", "runner", "worker", "budget", "firm")
FORBIDDEN = ("antstreet.cli", "antstreet.bench")
# module (relative to src/antstreet) -> why it may import a forbidden layer. Empty: no exceptions.
ALLOWED: dict[str, str] = {}


def _guarded() -> list[Path]:
    paths = sorted((SRC / "roles").rglob("*.py"))
    paths += [SRC / f"{name}.py" for name in (*CORE, "pipeline")]
    return paths


def _package(path: Path, root: Path) -> list[str]:
    return ["antstreet", *path.relative_to(root).parent.parts]


def _imports(path: Path, root: Path = SRC) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _package(path, root)
            if node.level:
                base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                parts = [*base, *(node.module.split(".") if node.module else [])]
            else:
                parts = (node.module or "").split(".")
            if not parts or parts == [""]:
                continue
            mod = ".".join(parts)
            found.add(mod)
            found.update(f"{mod}.{a.name}" for a in node.names)
    return found


def _forbidden(path: Path, root: Path = SRC) -> set[str]:
    return {
        n for n in _imports(path, root) if any(n == b or n.startswith(b + ".") for b in FORBIDDEN)
    }


@pytest.mark.parametrize("path", _guarded(), ids=lambda p: p.relative_to(SRC).as_posix())
def test_no_role_or_core_module_imports_the_cli_or_the_benchmark(path):
    rel = path.relative_to(SRC).as_posix()
    if rel in ALLOWED:
        return
    assert not _forbidden(path), f"{rel} imports {sorted(_forbidden(path))}: see D42"


def test_the_guard_names_real_files():
    assert len(_guarded()) > 10
    assert all(p.is_file() for p in _guarded())


def test_the_guard_can_fail(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("from antstreet.cli import EXECUTABLE_VAR\nimport antstreet.bench.table\n")
    assert _forbidden(f, tmp_path) == {
        "antstreet.cli",
        "antstreet.cli.EXECUTABLE_VAR",
        "antstreet.bench.table",
    }


def test_the_guard_resolves_relative_imports(tmp_path):
    (tmp_path / "roles").mkdir()
    f = tmp_path / "roles" / "m.py"
    f.write_text("from ..bench import table\nfrom ..cli import x\nfrom . import judge\n")
    assert _forbidden(f, tmp_path) == {
        "antstreet.bench",
        "antstreet.bench.table",
        "antstreet.cli",
        "antstreet.cli.x",
    }


def _all_modules() -> list[str]:
    names = []
    for p in sorted(SRC.rglob("*.py")):
        # _gate_plugin deletes its own file when imported: it is only ever loaded by the gate.
        if p.name in ("__main__.py", "_gate_plugin.py"):
            continue
        parts = ("antstreet", *p.relative_to(SRC).with_suffix("").parts)
        names.append(".".join(parts).removesuffix(".__init__"))
    return names


@pytest.mark.parametrize("module", _all_modules())
def test_every_module_imports_in_a_fresh_interpreter(module):
    done = subprocess.run(
        [sys.executable, "-c", f"import {module}"], capture_output=True, text=True, timeout=60
    )
    assert done.returncode == 0, done.stderr[-500:]
