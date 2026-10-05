"""docs/BACKLOG.md is the register of everything skipped or deferred. These tests keep it honest:
a shortcut marked `kn:` in the source must be listed there, and every entry must have a status."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = (ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
STATUSES = ("open", "building", "done", "wont")
ROW = re.compile(r"^\| (B\d{2,3}) \| (.+) \|$", re.M)
KN = re.compile(r"#.*?\bkn: (.+)$")
QUOTED = 40  # characters of a kn comment that must appear in the register


def rows() -> list[tuple[str, list[str]]]:
    return [(m[1], [cell.strip() for cell in m[2].split(" | ")]) for m in ROW.finditer(BACKLOG)]


def shortcuts() -> list[tuple[str, str]]:
    found = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if m := KN.search(line):
                found.append((path.relative_to(ROOT).as_posix(), m[1].strip()))
    return found


def test_ids_are_unique_and_increasing():
    numbers = [
        int(rid[1:]) for rid, _ in rows()
    ]  # gaps are allowed: parallel branches reserve ranges
    assert numbers == sorted(set(numbers))


def test_every_entry_says_what_it_is_and_has_a_known_status():
    for rid, cells in rows():
        assert cells[0], f"{rid} has no description"
        status = cells[-1].split(":")[0].strip()
        assert status in STATUSES, f"{rid} has status {cells[-1]!r}"


def test_a_closed_entry_says_where_or_why():
    for rid, cells in rows():
        status, _, note = cells[-1].partition(":")
        if status.strip() in ("done", "wont"):
            assert note.strip(), f"{rid} is {status.strip()} without saying where or why"


def test_every_shortcut_in_the_source_is_in_the_register():
    assert shortcuts(), "no kn: comments found; has the marker changed?"
    missing = [
        f"{path}: kn: {text}"
        for path, text in shortcuts()
        if f"kn: {text[:QUOTED]}".rstrip() not in BACKLOG
    ]
    assert not missing, "not in docs/BACKLOG.md:\n" + "\n".join(missing)
