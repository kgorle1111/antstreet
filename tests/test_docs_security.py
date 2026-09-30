"""SECURITY.md stays true: versions, stated limits, accepted risks, and no invented contact."""

import re
import tomllib

import pytest
from docs_support import DOCS, ROOT, read, section, table

from boss import doctor, limits, worker

DOC = ROOT / "SECURITY.md"
THREAT_MODEL = DOCS / "THREAT_MODEL.md"
ROW = re.compile(r"^\|\s*(T\d+)\s*\|")
STATUS = re.compile(r"^`([a-z ]+)`")


@pytest.fixture(scope="module")
def text() -> str:
    return read(DOC)


def threat_statuses() -> dict[str, str]:
    statuses = {}
    for line in read(THREAT_MODEL).splitlines():
        if ROW.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            statuses[cells[0]] = STATUS.match(cells[4]).group(1)
    return statuses


def test_the_supported_version_is_the_packages_version(text):
    version = tomllib.loads(read(ROOT / "pyproject.toml"))["project"]["version"]
    rows = table(section(text, "Supported versions"))
    assert [r[0].split(" ")[0] for r in rows] == [version]


def test_requirements_stated_are_the_ones_the_code_enforces(text):
    body = section(text, "Supported versions")
    cli = ".".join(map(str, worker.MIN_CLI_VERSION))
    python = ".".join(map(str, doctor._MIN_PYTHON))
    assert f"`claude` CLI {cli} or newer" in body and f"Python {python} or newer" in body
    requires = tomllib.loads(read(ROOT / "pyproject.toml"))["project"]["requires-python"]
    assert requires == f">={python}"


def test_the_environment_and_tools_and_limits_stated_are_the_real_ones(text):
    body = section(text, "What it protects")
    for name in worker._ENV_ALLOWLIST:
        assert f"`{name}`" in body, f"{name} is on the allowlist but not stated"
    assert "`ANTHROPIC_API_KEY`" in body
    assert "`Read`, `Write` and `Edit`" in body and worker.WORKER_TOOLS == ("Read", "Write", "Edit")
    run_limits = limits.RunLimits()
    assert f"{run_limits.max_slices} slices, {run_limits.max_workers} workers" in body


def test_every_accepted_risk_in_the_threat_model_is_listed_and_every_listed_one_is_accepted(text):
    statuses = threat_statuses()
    listed = {r[0]: r for r in table(section(text, "What it does not protect"))}
    accepted = {tid for tid, status in statuses.items() if status == "accepted"}
    assert set(listed) == accepted, (
        f"listed {sorted(listed)}, threat model accepts {sorted(accepted)}"
    )
    for tid, row in listed.items():
        assert row[2].strip("`") == statuses[tid]


def test_how_to_report_is_a_private_advisory_and_no_contact_is_invented(text):
    body = section(text, "Reporting a problem")
    assert "private security advisory" in body
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), "an email address was added"
    assert "mailto:" not in text


def test_it_links_the_threat_model(text):
    assert "(docs/THREAT_MODEL.md)" in text and THREAT_MODEL.is_file()
