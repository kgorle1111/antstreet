"""The "Common objections" section of README-technical.md states numbers and code facts; each is
pinned here to the file or constant it comes from, so the prose cannot drift from them."""

import re

import pytest
from docs_support import DOCS, ROOT, read, section

from antstreet import worker
from antstreet.rule import FiringPolicy

BODY = " ".join(section(read(ROOT / "README-technical.md"), "Common objections").split())


def results(name: str) -> str:
    return " ".join(read(ROOT / "bench" / "results" / name / "README.md").split())


def test_the_section_has_the_seven_objections():
    items = re.findall(
        r"(?m)^(\d)\. \*\*\"", section(read(ROOT / "README-technical.md"), "Common objections")
    )
    assert items == list("1234567")


def test_workers_have_the_three_file_tools_and_no_shell():
    assert worker.WORKER_TOOLS == ("Read", "Write", "Edit")
    assert "only `Read`, `Write` and `Edit`" in BODY and "no shell" in BODY


def test_the_stall_and_slice_defaults_are_the_stated_ones():
    policy = FiringPolicy()
    assert (policy.stall_slices, policy.max_slices) == (2, 6)
    assert "`--stall-slices` (default 2)" in BODY and "`--max-slices` (default 6)" in BODY


@pytest.mark.parametrize(
    ("stated", "folder", "source"),
    [
        (
            "19 of 80 cells",
            "2026-10-07-e4b-critic",
            "19 of 80 cells that passed every visible check (24%)",
        ),
        ("24% false-pass rate", "2026-10-07-e4b-critic", "24% [16-34%] (19/80)"),
        ("self-review was 39% (34/88)", "2026-10-07-e4b-critic", "39% [29-49%] (34/88)"),
        (
            "4 of 10 on a held-out set",
            "2026-10-10-spec-gaps",
            "Held-out hand-checked recall is 4 of 10 [17%, 69%]",
        ),
    ],
)
def test_a_stated_benchmark_number_is_in_the_results_file_it_cites(stated, folder, source):
    assert stated in BODY
    assert source in results(folder)


def test_the_disputes_and_wrong_check_numbers_are_in_the_results_readme():
    text = " ".join(read(ROOT / "bench" / "results" / "README.md").split())
    assert "28 wrong checks out of 813" in text
    assert "The rule fired 4 workers. **All 4 were in cells with a wrong check" in text
    assert "28 wrong checks out of 813" in BODY and "all 4 firings" in BODY


def test_the_fault_injection_and_ledger_line_numbers_are_in_the_recovery_doc():
    text = " ".join(read(DOCS / "RECOVERY.md").split())
    assert "Across 27 faulted trials" in text and "0 double-spends" in text
    assert "12 ledger lines" in text
    assert "27 trials with 0 double-spends" in BODY and "writes 12 lines" in BODY


def test_every_threat_row_the_section_names_exists():
    threats = read(DOCS / "THREAT_MODEL.md")
    named = set(re.findall(r"\bT\d+\b", BODY.replace("THREAT_MODEL", "")))
    named |= {t.upper() for t in re.findall(r"THREAT_MODEL\.md#(t\d+)", BODY)}
    assert {"T12", "T13", "T33", "T38", "T44", "T53", "T55", "T58", "T66", "T67"} <= named
    for row in sorted(named):
        assert f"| {row} |" in threats, f"{row} is not a threat-model row"
