"""The import package is `antstreet`; `boss` is its old name and must keep working as an alias that
is the same module objects (never a second copy), from imports, `python -m boss.X`, the approve
guard, and ledgers written before the rename."""

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_plugin import _guard

import antstreet
import antstreet.cli
import antstreet.ledger
import antstreet.roles
from antstreet import signing
from antstreet.ledger import EventType, read_events

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"  # flat: other tests read every file in it
# The fixture was written by the pre-rename `boss` package with this test key; it is written back
# at run time so no key file is committed.
FIXTURE_KEY = bytes(range(32)).hex() + "\n"


def py(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=60, check=False
    )


def test_boss_is_the_antstreet_package_and_its_modules():
    import boss.bench.run
    import boss.ledger
    import boss.roles
    from boss.cli import main

    import antstreet.bench.run
    import boss

    assert boss is antstreet
    assert boss.ledger is antstreet.ledger
    assert boss.bench.run is antstreet.bench.run
    assert main is antstreet.cli.main
    assert boss.roles.registry is antstreet.roles.registry  # module state is shared, not copied
    assert sys.modules["boss.ledger"] is antstreet.ledger
    assert antstreet.ledger.__name__ == antstreet.ledger.__spec__.name == "antstreet.ledger"


@pytest.mark.parametrize("first", ["boss", "antstreet"])
def test_either_name_first_in_a_fresh_interpreter_gives_one_copy_of_each_module(first):
    other = "antstreet" if first == "boss" else "boss"
    code = (
        f"import sys, {first}.ledger, {first}.roles.org, {other}.ledger, {other}.roles.org\n"
        f"assert {first}.ledger is {other}.ledger and {first}.roles.org is {other}.roles.org\n"
        "dupes = [n for n, m in sys.modules.items() if m is not None\n"
        "         and n.split('.')[0] in ('boss', 'antstreet')\n"
        "         and not m.__name__.startswith('antstreet')]\n"
        "assert not dupes, dupes\n"
        "print('one copy')"
    )
    done = py("-c", code)
    assert (done.returncode, done.stdout.strip()) == (0, "one copy"), done.stderr


def test_an_unknown_boss_submodule_is_not_found():
    import boss  # noqa: F401  (installs the alias)

    assert importlib.util.find_spec("boss.no_such_module") is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("boss.no_such_module")


@pytest.mark.parametrize(
    "args",
    [["cli", "--version"], ["roles.org"]],
    ids=["cli --version", "roles.org"],
)
def test_python_m_boss_runs_what_python_m_antstreet_runs(args):
    module, *rest = args
    old = py("-m", f"boss.{module}", *rest)
    new = py("-m", f"antstreet.{module}", *rest)
    assert old.returncode == new.returncode == 0, (old.stderr, new.stderr)
    assert old.stdout == new.stdout and old.stdout.strip()


def test_python_m_boss_gets_the_real_code_and_file():
    import boss  # noqa: F401  (installs the alias)

    # runpy asks the finder in a fresh process, where `boss.cli` is not imported yet
    [alias] = [f for f in sys.meta_path if type(f).__module__ == "boss"]
    spec = alias.find_spec("boss.cli")
    assert spec is not None and spec.origin == antstreet.cli.__file__
    code = spec.loader.get_code("boss.cli")  # what runpy executes as __main__
    assert code is not None and code.co_filename == antstreet.cli.__file__


def test_nothing_in_antstreet_imports_the_alias():
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "src" / "antstreet").rglob("*.py")
        if any(
            line.lstrip().startswith(("import boss", "from boss"))
            for line in p.read_text(encoding="utf-8").splitlines()
        )
    ]
    assert not offenders


@pytest.mark.parametrize(
    "command",
    [
        "python -m boss.cli approve r1 --sheet 0123456789abcdef",
        "python -m antstreet.cli approve r1 --sheet 0123456789abcdef",
        "uv run python -m antstreet.cli approve",
        "python3 src/antstreet/cli.py approve",
        ".venv/bin/python -m antstreet.cli approve --dispute c05 --ruling drop",
    ],
)
def test_the_approve_guard_denies_both_module_names(command):
    assert _guard(command).returncode == 2, command


def test_the_approve_guard_ignores_a_project_folder_named_antstreet():
    done = _guard("ls /home/user/antstreet/src/antstreet && echo approve")
    assert (done.returncode, done.stdout) == (0, "")


@pytest.fixture
def old_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    for kind, dest in (
        ("ledger", "runs/r-prerename/ledger.jsonl"),
        ("anchor", "anchors/r-prerename"),
    ):
        target = project / ".boss" / dest
        target.parent.mkdir(parents=True)
        shutil.copyfile(FIXTURES / f"pre_rename_r-prerename.{kind}", target)
    key = project / ".boss" / signing.KEY_FILE
    fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(FIXTURE_KEY)
    return project


def test_a_ledger_written_before_the_rename_verifies_byte_for_byte(old_project):
    ledger = old_project / ".boss" / "runs" / "r-prerename" / "ledger.jsonl"
    before = ledger.read_bytes()
    events = read_events(ledger, old_project / ".boss" / signing.KEY_FILE)  # chain, macs, anchor
    assert [e.actor for e in events] == [
        "boss", "boss", "investor", "boss", "worker:w1", "gate", "rule", "role:critic", "boss",
    ]  # fmt: skip
    [approved] = [e for e in events if e.event is EventType.APPROVED]
    assert signing.verify(bytes(range(32)), approved)
    # the event is serialised exactly as before, so a line rewritten today hashes the same
    for line, event in zip(before.decode().splitlines(), events, strict=True):
        assert line.startswith(event.to_json()[:-1] + ', "mac": "')
    said: list[str] = []
    code = antstreet.cli.main(["verify", "r-prerename", "--dir", str(old_project)], say=said.append)
    assert code == 0 and "verifies: 9 events" in said[-1], said
    assert ledger.read_bytes() == before
