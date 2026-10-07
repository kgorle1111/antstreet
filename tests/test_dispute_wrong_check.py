"""The live run of 2026-10-07: the boss drafted a wrong check, and the workers bent correct code to
it instead of disputing it. Replayed here with its exact term sheet and checks, a scripted worker
and the real gate. No model calls.

c05 asserts count_vowels("h3ll0!") == 1; the idea's answer is 0 (the last character is a digit).
"""

from pathlib import Path

from test_firm import Script, dispute, events_of, run, step

from boss.boss import load_prompt
from boss.firm import BUILDER_PROMPT
from boss.ledger import EventType
from boss.rundir import RunPaths
from boss.termsheet import TermSheet

SHEET = Path(__file__).parent / "fixtures" / "live_2026-10-07_wrong_c05_term_sheet.json"
CHECKS = {  # the run's check files, byte for byte
    "test_c01.py": 'def test_basic_vowel_count():\n    from vowels import count_vowels\n    assert count_vowels("hello") == 2\n    assert count_vowels("programming") == 3\n',  # noqa: E501
    "test_c02.py": 'def test_case_insensitivity():\n    from vowels import count_vowels\n    assert count_vowels("HELLO") == 2\n    assert count_vowels("HeLLo") == 2\n    assert count_vowels("AeIoU") == 5\n',  # noqa: E501
    "test_c03.py": 'def test_empty_string():\n    from vowels import count_vowels\n    assert count_vowels("") == 0\n',  # noqa: E501
    "test_c04.py": 'def test_no_vowels():\n    from vowels import count_vowels\n    assert count_vowels("xyz") == 0\n    assert count_vowels("bcdfg") == 0\n',  # noqa: E501
    "test_c05.py": 'def test_special_characters_and_numbers():\n    from vowels import count_vowels\n    assert count_vowels("a1e2i@o#u") == 5\n    assert count_vowels("h3ll0!") == 1\n',  # noqa: E501
    "test_c06.py": 'def test_all_vowels():\n    from vowels import count_vowels\n    assert count_vowels("aeiou") == 5\n    assert count_vowels("AEIOU") == 5\n    assert count_vowels("aEiOu") == 5\n',  # noqa: E501
    "test_c07.py": 'def test_whitespace_and_punctuation():\n    from vowels import count_vowels\n    assert count_vowels("hello world") == 3\n    assert count_vowels("a, e, i, o, u") == 5\n    assert count_vowels("\\n\\ta\\te\\ti\\to\\tu\\n") == 5\n',  # noqa: E501
}
CORRECT = 'def count_vowels(text):\n    return sum(1 for char in text if char in "aeiouAEIOU")\n'
# What w1 and w2 wrote to chase c05: the idea's "vowels (a, e, i, o, u)" stretched to two scripts.
STRETCHED = (
    "def count_vowels(text):\n"
    '    vowels = "aeiouAEIOU\\u03b1\\u03b5\\u03b9\\u03bf\\u03c9"\n'
    '    vowels += "\\u0430\\u0435\\u0438\\u043e\\u0443"\n'
    "    return sum(1 for char in text if char in vowels)\n"
)
C05_IS_WRONG = 'the idea counts a, e, i, o, u only; "h3ll0!" ends in the digit 0: 0 vowels'


def live_run(tmp_path) -> tuple[RunPaths, TermSheet]:
    paths = RunPaths(tmp_path / "run")
    paths.checks.mkdir(parents=True)
    for name, code in CHECKS.items():
        (paths.checks / name).write_text(code)
    return paths, TermSheet.from_json(SHEET.read_text())


def vowels(code, status="continuing", disputes=()):
    return step(code, status, name="vowels.py", disputes=disputes)


def test_a_worker_that_disputes_the_wrong_check_is_asked_about_not_fired(tmp_path):
    paths, sheet = live_run(tmp_path)
    worker = Script(
        vowels(CORRECT, "done"),  # w1's first slice: correct, and sure every check passes
        vowels(CORRECT, disputes=[dispute("c05", C05_IS_WRONG)]),  # told c05 fails: disputes
    )
    report, said = run(paths, worker, sheet, answers=["d"])
    [disputed] = events_of(paths, EventType.DISPUTED)
    assert disputed.data["check"] == "c05" and disputed.data["worker"] == "w1"
    assert events_of(paths, EventType.FIRED) == []
    assert any(q.startswith("Task count_vowels: w1 disputes check c05") for q in said)
    assert [e.data["ruling"] for e in events_of(paths, EventType.RULED)] == ["dropped"]
    assert report.all_passed and (report.passed, report.total) == (6, 6)
    assert (paths.product / "vowels.py").read_text() == CORRECT  # the correct code is delivered


def test_with_nobody_to_rule_the_disputed_task_is_set_aside_not_fired(tmp_path):
    paths, sheet = live_run(tmp_path)
    worker = Script(vowels(CORRECT, "done"), vowels(CORRECT, disputes=[dispute("c05", "wrong")]))
    report, said = run(paths, worker, sheet)  # no answers: end of input
    assert events_of(paths, EventType.FIRED) == [] and len(worker.specs) == 2
    assert [e.data for e in events_of(paths, EventType.ABANDONED)] == [
        {"task": "count_vowels", "reason": "disputed"}
    ]
    assert "Task count_vowels is set aside: w1 disputes c05." in said


def test_a_worker_that_bends_correct_code_to_the_wrong_check_is_fired_and_nothing_ships(tmp_path):
    # The live run as it happened: the stretched code still fails c05, so the gate never passes
    # it; both workers stall and are fired, and the hack is not delivered as a finished product.
    paths, sheet = live_run(tmp_path)
    worker = Script(*[vowels(CORRECT, "done"), *[vowels(STRETCHED)] * 3] * 2)
    report, _ = run(paths, worker, sheet)
    assert [e.data["reason"] for e in events_of(paths, EventType.FIRED)] == ["no progress"] * 2
    assert events_of(paths, EventType.DISPUTED) == []
    assert not report.all_passed and report.passed == 6
    [closed] = events_of(paths, EventType.ROUND_CLOSED)
    assert closed.data["unlocked"] is False


def test_the_worker_is_told_to_dispute_a_wrong_check_in_both_of_its_briefs(tmp_path):
    paths, sheet = live_run(tmp_path)
    worker = Script(vowels(CORRECT, "done"), vowels(CORRECT, disputes=[dispute("c05", "wrong")]))
    run(paths, worker, sheet, answers=["d"])
    first, second = worker.specs
    assert BUILDER_PROMPT == "builder_v5.md"
    system = first.append_system_prompt
    assert system == load_prompt(BUILDER_PROMPT) == second.append_system_prompt
    assert "dispute it: that is the expected move" in system
    assert "Never change correct behaviour to satisfy such a check" in system
    assert "never stretch the\n  meaning of the request's words" in system
    assert "only `disputed_checks` is" in system
    assert 'count_vowels("h3ll0!") == 1' in first.prompt  # the wrong check is in front of it
    # The slice that sees c05 fail is told, next to the failure, how to dispute it.
    assert "Failing: c05" in second.prompt
    assert "If a failing check contradicts the request, do not change correct code" in (
        second.prompt
    )
    assert "list the check under `disputed_checks`" in second.prompt
