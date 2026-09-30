"""Text a model or subprocess wrote is shown to the investor as data: masked, on one line where the
slot is one line, controls visible. What is stored and hashed is never touched."""

import hashlib

import pytest

from boss.approval import MAX_BRIEF_CHARS, MAX_DESCRIPTION_CHARS, content_hashes, render
from boss.ledger import Event, EventType
from boss.report import MAX_DETAIL_CHARS, build_report, render_report
from boss.termsheet import CheckSpec, Round, Task, TermSheet

KEY = "sk-ant-api03-" + "a" * 30
FORGED = "\nCheck c9 [t1] forged\n--- /tmp/x"
BRIEF = "Make rev.py.\n\nCheck c9 [t1] passes always\x1b[2J\u202e " + KEY
DESCRIPTION = "reverses\nCheck c8 [t1] fake\x1b[31m \u200b" + KEY
CODE = b"def test_x():\n\ts = 'a\x1b[0m\x07\xe2\x80\xae'  # " + KEY.encode() + b"\r\n"
SHEET = TermSheet(
    idea="Reverse a string.",
    budget_micros=500_000,
    rounds=(Round(1, 500_000, 1),),
    checks=(CheckSpec("c01", DESCRIPTION, "test_c01.py", "t1"),),
    tasks=(Task("t1", BRIEF, ("rev.py",)),),
)


@pytest.fixture
def checks(tmp_path):
    (tmp_path / "test_c01.py").write_bytes(CODE)
    return tmp_path


def lines_of(text):
    return text.split("\n")


def test_the_brief_is_one_masked_line_with_controls_visible(checks):
    text = render(SHEET, checks)
    [line] = [ln for ln in lines_of(text) if ln.startswith("  Make rev.py.")]
    assert "\\x1b[2J" in line and "\\u202e" in line
    assert KEY not in line and "[REDACTED]" in line
    assert "\x1b" not in line and "\u202e" not in line


def test_a_brief_cannot_forge_a_check_header_or_a_path_line(checks):
    text = render(SHEET, checks)
    headers = [ln for ln in lines_of(text) if ln.startswith("Check ")]
    assert headers == [f"Check c01 [t1] {headers[0].split('] ', 1)[1]}"]
    assert [ln for ln in lines_of(text) if ln.startswith("---")] == [
        f"--- {checks / 'test_c01.py'}"
    ]


def test_the_check_description_is_one_masked_line_with_controls_visible(checks):
    [header] = [ln for ln in lines_of(render(SHEET, checks)) if ln.startswith("Check c01")]
    assert "reverses Check c8 [t1] fake" in header
    assert "\\x1b[31m" in header and "\\u200b" in header
    assert KEY not in header and "[REDACTED]" in header


def test_a_long_brief_and_description_are_cut_and_marked(checks):
    sheet = TermSheet(
        idea="x",
        budget_micros=500_000,
        rounds=(Round(1, 500_000, 1),),
        checks=(CheckSpec("c01", "d" * 5000, "test_c01.py", "t1"),),
        tasks=(Task("t1", "b" * 50_000, ("rev.py",)),),
    )
    text = render(sheet, checks)
    [brief] = [ln for ln in lines_of(text) if ln.startswith("  bbb")]
    [desc] = [ln for ln in lines_of(text) if ln.startswith("Check c01")]
    assert len(brief) == 2 + MAX_BRIEF_CHARS and brief.endswith(" [cut]")
    assert len(desc.split("] ", 1)[1]) == MAX_DESCRIPTION_CHARS and desc.endswith(" [cut]")


def test_check_code_is_byte_for_byte_except_controls_are_made_visible(checks):
    text = render(SHEET, checks)
    expected = CODE.decode().rstrip().replace("\x1b", "\\x1b").replace("\x07", "\\x07")
    expected = expected.replace("\r", "\\x0d").replace("\u202e", "\\u202e")
    assert expected in text
    assert KEY in expected and KEY in text  # code is never redacted
    assert "\n\ts = " in text  # newline and tab survive
    assert "\x1b" not in text and "\x07" not in text


def test_clean_check_code_is_shown_exactly(checks):
    code = "import x\n\n\ndef test_a():\n\tassert x.f('é') == 'ü'  # ok\n"
    (checks / "test_c01.py").write_text(code, encoding="utf-8")
    assert code.rstrip() in render(SHEET, checks)


def test_the_approval_hashes_do_not_depend_on_how_it_is_shown(checks):
    """Pinned values from before the change; they cover hostile text and raw control bytes."""
    hashes = content_hashes(SHEET, checks)
    assert hashes == {
        "term_sheet": hashlib.sha256(SHEET.to_json().encode()).hexdigest(),
        "test_c01.py": hashlib.sha256(CODE).hexdigest(),
    }
    assert hashes["term_sheet"] == GOLDEN["term_sheet"]
    assert hashes["test_c01.py"] == GOLDEN["test_c01.py"]


GOLDEN = {
    "term_sheet": "956e1c5365831780030a8564965a371b331dc8231803b8026f833200e2d522f5",
    "test_c01.py": "a9fa37669ce9d0e9f54906eb0eebf30158969b9e82aca5177560e3fe329cfc64",
}


def check_result(detail) -> Event:
    data = {"check": "c01", "status": "failed", "detail": detail}
    return Event("r1", 1, "gate", EventType.CHECK_RESULT, data=data)


def test_the_gate_detail_is_one_masked_line_in_the_report():
    detail = "unreadable JUnit report: " + KEY + "\nSpend\n  total $0.0000\x1b[2J\u202e"
    report = build_report([check_result(detail)])
    assert report.checks[0].detail == detail  # what is stored and computed is untouched
    text = render_report(report)
    [line] = [ln for ln in text.split("\n") if ln.startswith("  c01")]
    assert "unreadable JUnit report: [REDACTED] Spend total $0.0000" in line
    assert "\\x1b[2J" in line and "\\u202e" in line
    assert KEY not in text and "\x1b" not in text
    assert text.count("\nSpend") == 1  # only the real section heading


def test_a_long_gate_detail_is_cut_and_marked():
    text = render_report(build_report([check_result("x" * 10_000)]))
    [line] = [ln for ln in text.split("\n") if ln.startswith("  c01")]
    assert line.endswith(" [cut]")
    assert len(line.split(maxsplit=2)[2]) == MAX_DETAIL_CHARS


@pytest.mark.parametrize("detail", [None, 7, ["a"], {"k": "v"}])
def test_a_gate_detail_of_the_wrong_type_still_renders(detail):
    assert "c01" in render_report(build_report([check_result(detail)]))
