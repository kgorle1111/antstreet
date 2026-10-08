"""The import package is `antstreet`, and there is no `boss` import package (it would clash with
`boss` on PyPI). What users already have keeps working: the `boss` command is still denied
approval by the guard in every module form, and ledgers written before the rename verify."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_plugin import _guard

import antstreet
import antstreet.cli
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


def test_there_is_no_boss_import_package():
    # `boss` on PyPI is someone else's package; shipping one of ours would clash with it.
    for code in ("import boss", "import boss.cli"):
        done = py("-c", code)
        assert done.returncode == 1 and "ModuleNotFoundError: No module named 'boss'" in done.stderr
    assert py("-m", "boss.cli", "--version").returncode == 1
    assert not (ROOT / "src" / "boss").exists()


def test_python_m_antstreet_cli_runs():
    done = py("-m", "antstreet.cli", "--version")
    assert (done.returncode, done.stdout.strip()) == (0, f"boss {antstreet.__version__}")


def test_nothing_in_antstreet_imports_the_old_name():
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
