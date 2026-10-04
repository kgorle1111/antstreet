"""The CI shards partition the suite, and a hung test is ended: both come from tests/conftest.py."""

import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import SHARD_ENV, TIMEOUT_ENV, parse_shard, shard_of

TESTS = Path(__file__).resolve().parent


@pytest.mark.parametrize("raw", ["", "3", "3/3", "-1/3", "a/b", "0/0", "1/2/3"])
def test_a_malformed_shard_is_refused_not_ignored(raw):
    with pytest.raises(pytest.UsageError):
        parse_shard(raw)


def test_every_test_file_belongs_to_exactly_one_shard():
    files = sorted(p.name for p in TESTS.glob("test_*.py"))
    for count in (1, 2, 3, 4):
        owners = [[f for f in files if shard_of(f, count) == i] for i in range(count)]
        assert sorted(sum(owners, [])) == files
    assert len({shard_of(f, 3) for f in files}) == 3, "a shard would be empty"


def collected(shard: str | None) -> int:
    env = {"PATH": "/usr/bin:/bin", "HOME": str(TESTS)}
    if shard is not None:
        env[SHARD_ENV] = shard
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
    cmd += ["-n", "0", "-m", "slow or not slow", "tests"]
    out = subprocess.run(
        cmd, cwd=TESTS.parent, env=env, capture_output=True, text=True, timeout=300
    ).stdout
    return sum(int(line.rsplit(": ", 1)[1]) for line in out.splitlines() if ": " in line)


@pytest.mark.slow
def test_the_shards_together_collect_exactly_the_whole_suite():
    whole = collected(None)
    assert whole > 1000
    assert sum(collected(f"{i}/3") for i in range(3)) == whole


def test_a_test_that_outlives_the_timeout_ends_the_process(tmp_path):
    (tmp_path / "test_hang.py").write_text("import time\n\ndef test_hangs():\n    time.sleep(60)\n")
    (tmp_path / "conftest.py").write_text((TESTS / "conftest.py").read_text())
    start = time.monotonic()
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist"],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", TIMEOUT_ENV: "2"},
        capture_output=True,
        text=True,
        timeout=50,
    )
    assert done.returncode != 0 and time.monotonic() - start < 30
