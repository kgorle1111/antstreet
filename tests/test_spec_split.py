"""boss.spec.split: the rules of a request. Properties are checked on all the benchmark ideas,
because those are real ideas with real list markers, signatures and hard-wrapped sentences."""

import contextlib
import json
import random
import re
import time
from pathlib import Path

import pytest

from boss import spec
from boss.spec import MAX_RULES, SpecError, split

TASKS = Path(__file__).parent.parent / "bench" / "tasks"
IDEAS = {
    d.name: (d / "idea.md").read_text(encoding="utf-8").strip() for d in sorted(TASKS.iterdir())
}
NUMBERED_LINE = re.compile(r"^[ \t]{0,3}(\d{1,3})[.)][ \t]+", re.M)


def check_properties(idea: str) -> spec.Split:
    s = split(idea)
    previous_end = 0
    for n, rule in enumerate(s.rules, start=1):
        assert rule.id == f"R{n:02d}"
        assert rule.text == idea[rule.start : rule.end], "offsets must reproduce the text"
        assert rule.text == rule.text.strip() and any(c.isalpha() for c in rule.text), "empty rule"
        assert previous_end <= rule.start < rule.end, "rules overlap or are out of order"
        previous_end = rule.end
        assert rule.kind in spec.KINDS
        if not rule.scored:
            assert rule.anchors == ()
    assert len(s.rules) <= MAX_RULES
    assert s == split(idea), "same idea, same rules"
    return s


def test_the_benchmark_ideas_are_all_present():
    assert len(IDEAS) == 59


@pytest.mark.parametrize("task", sorted(IDEAS))
def test_offsets_round_trip_and_no_rule_is_empty_on_every_benchmark_idea(task):
    check_properties(IDEAS[task])


@pytest.mark.parametrize("task", sorted(IDEAS))
def test_every_numbered_item_of_a_benchmark_idea_yields_a_rule(task):
    idea = IDEAS[task]
    s = split(idea)
    wanted = {f"G{m[1]}" for m in NUMBERED_LINE.finditer(idea)}
    assert wanted, "every benchmark idea has a numbered list"
    assert wanted <= {r.group for r in s.rules}
    assert any(r.scored for r in s.rules)
    assert any(r.group == "G0" and not r.scored for r in s.rules), "the preamble is context"


@pytest.mark.parametrize("task", sorted(IDEAS))
def test_a_benchmark_idea_with_its_numbering_stripped_and_lines_rewrapped_still_splits(task):
    """Real requests are prose. The same sentences with no list markers and one line a paragraph
    must still satisfy every property and keep most of the rules."""
    lines = [NUMBERED_LINE.sub("", line) for line in IDEAS[task].split("\n")]
    prose = "\n".join(" ".join(p.split()) for p in "\n".join(lines).split("\n\n"))
    assert check_properties(prose).scorable


def test_a_sentence_is_a_rule_and_a_numbered_item_is_a_group():
    s = split("Make a thing.\n\n1. It adds. It is fast.\n2. It never crashes.")
    assert [(r.group, r.text, r.scored) for r in s.rules] == [
        ("G0", "Make a thing.", False),
        ("G1", "It adds.", True),
        ("G1", "It is fast.", True),
        ("G2", "It never crashes.", True),
    ]


def test_a_hard_wrapped_sentence_is_one_rule_with_its_newline_inside_the_offsets():
    idea = "1. A sentence that is\n   wrapped over two lines. Next one."
    s = split(idea)
    assert [r.text for r in s.rules] == [
        "A sentence that is\n   wrapped over two lines.",
        "Next one.",
    ]


@pytest.mark.parametrize(
    "idea",
    [
        "1. Use e.g. Python lists. It works.",
        "1. Values such as `a. B` are kept. Done.",
        "1. Version 1.2.3 is valid. 01.2.3 is not.",
        "1. It costs about 2.5 dollars. Fine.",
    ],
)
def test_a_period_is_not_a_boundary_in_an_abbreviation_a_backtick_span_or_a_number(idea):
    s = split(idea)
    assert [r.text for r in s.rules][-1] in ("It works.", "Done.", "01.2.3 is not.", "Fine.")
    assert len(s.rules) == 2


def test_a_sentence_boundary_needs_a_capital_letter_a_digit_or_a_quote_after_it():
    assert len(split("1. It ends. then it goes on.").rules) == 1
    assert len(split("1. It ends. Then it stops. `x` is 1.").rules) == 3


def test_a_heading_and_a_bare_signature_are_context_not_rules_to_cover():
    s = split(
        "Create `m.py`.\n\n    f(x: int) -> int\n\n1. It adds.\n\nInput text:\n\n"
        "2. It rejects bad input."
    )
    kinds = {r.text: r.kind for r in s.rules}
    assert kinds["Input text:"] == "context"
    assert s.code_lines == 1
    assert [r.text for r in s.rules if r.scored] == ["It adds.", "It rejects bad input."]


def test_indented_prose_after_a_blank_line_is_not_swallowed_as_code():
    s = split("1. First point.\n\n    The second paragraph of the same item still counts as text.")
    assert any("second paragraph" in r.text for r in s.rules)
    assert s.code_lines == 0


def test_fenced_and_indented_code_is_not_a_rule():
    s = split("1. It parses.\n\n```\nassert f('x') == 1\n```\n\n    g(a, b)\n\n2. It prints.")
    assert [r.text for r in s.rules] == ["It parses.", "It prints."]
    assert s.code_lines == 2


def test_bullets_and_windows_line_endings_split_the_same_way():
    unix = split("1. Rules:\n- It adds.\n- It subtracts.\n2. It divides.")
    dos = split("1. Rules:\r\n- It adds.\r\n- It subtracts.\r\n2. It divides.")
    assert [r.text for r in unix.rules] == [r.text for r in dos.rules]
    assert [r.text for r in unix.rules if r.scored] == ["It adds.", "It subtracts.", "It divides."]


def test_an_idea_with_no_numbered_items_gets_one_group_per_paragraph_and_no_context_preamble():
    s = split("Build a parser. It reads text.\n\nIt rejects junk.")
    assert [(r.group, r.scored) for r in s.rules] == [("G1", True), ("G1", True), ("G2", True)]


@pytest.mark.parametrize("idea", ["", "   \n\n  ", "...", "1.", "```\n```", "- \n- "])
def test_an_idea_with_no_sentence_has_no_rules_and_does_not_raise(idea):
    assert split(idea).rules == ()


def test_too_many_sentences_fall_back_to_one_rule_per_group_and_say_so():
    idea = "\n".join(f"{n}. First {n}. Second {n}. Third {n}." for n in range(1, 21))
    s = split(idea)
    assert s.coarse and len(s.rules) == 20
    assert s.rules[0].text == "First 1. Second 1. Third 1."
    assert check_properties(idea).coarse


def test_more_groups_than_the_cap_is_refused_not_silently_truncated():
    idea = "\n\n".join(f"Rule number {n} holds." for n in range(MAX_RULES + 5))
    with pytest.raises(SpecError, match=f"at most {MAX_RULES}"):
        split(idea)


def test_a_huge_idea_goes_coarse():
    paragraph = "It does a thing. " * 3
    idea = "\n".join(f"{n}. {paragraph}" for n in range(1, 12)) + "x" * spec.MAX_IDEA_CHARS
    assert split(idea).coarse


def test_ids_are_sequential_and_kinds_are_hints_only():
    s = split("1. It raises ValueError.\n2. An empty list gives zero.\n3. Output has a separator.")
    assert [r.id for r in s.rules] == ["R01", "R02", "R03"]
    assert [r.kind for r in s.rules] == ["error", "edge", "format"]


@pytest.mark.parametrize("seed", range(40))
def test_random_text_never_breaks_a_property(seed):
    rng = random.Random(seed)
    alphabet = [
        "a",
        "B",
        " ",
        " ",
        "\n",
        "\n\n",
        ".",
        "!",
        "?",
        "`",
        "1",
        "2.",
        "3) ",
        "- ",
        "    ",
        "\t",
        "\r",
        "e.g.",
        "٣",
        "‮",
        "x" * 30,
        "```",
        ":",
        "(",
        ")",
    ]
    idea = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 400)))
    with contextlib.suppress(SpecError):  # the only allowed refusal: more groups than MAX_RULES
        check_properties(idea)


@pytest.mark.parametrize(
    "text",
    [".", "`", "1. ", "a. ", "\n", " ", "1.\n", "x.\n\n", "A. ", "`a. ` ", "`a. B` ", "e.g. "],
)
def test_pathological_input_does_not_take_quadratic_time(text):
    started = time.perf_counter()
    with contextlib.suppress(SpecError):
        split(text * (200_000 // len(text)))
    assert time.perf_counter() - started < 2.0


def test_the_stored_rule_list_round_trips_and_is_checked_against_the_idea(tmp_path):
    idea = IDEAS["luhn"]
    path = tmp_path / spec.RULES_FILE
    path.write_text(spec.dumps(split(idea)), encoding="utf-8")
    assert spec.load(path, idea) == split(idea)


def test_a_stored_rule_list_with_a_rule_dropped_or_a_text_edited_is_refused(tmp_path):
    idea = IDEAS["luhn"]
    path = tmp_path / spec.RULES_FILE
    data = spec.to_data(split(idea))
    dropped = {**data, "rules": data["rules"][:-1]}
    path.write_text(json.dumps(dropped), encoding="utf-8")
    with pytest.raises(SpecError, match="not the rule list"):
        spec.load(path, idea)
    edited = json.loads(json.dumps(data))
    edited["rules"][5]["text"] = "nothing to see"
    path.write_text(json.dumps(edited), encoding="utf-8")
    with pytest.raises(SpecError):
        spec.load(path, idea)


def test_a_stored_rule_list_for_another_idea_or_an_unreadable_file_is_refused(tmp_path):
    path = tmp_path / spec.RULES_FILE
    path.write_text(spec.dumps(split(IDEAS["luhn"])), encoding="utf-8")
    with pytest.raises(SpecError):
        spec.load(path, IDEAS["slugify"])
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SpecError, match="cannot read"):
        spec.load(path, IDEAS["luhn"])
    with pytest.raises(SpecError, match="cannot read"):
        spec.load(tmp_path / "missing.json", IDEAS["luhn"])


def test_the_digest_changes_when_any_rule_changes():
    a, b = split("1. It adds."), split("1. It adds!")
    assert spec.rules_digest(a) != spec.rules_digest(b)
    assert spec.rules_digest(a) == spec.rules_digest(split("1. It adds."))


def test_an_idea_over_the_hard_cap_is_refused_before_any_work_is_done():
    started = time.perf_counter()
    with pytest.raises(SpecError, match="split it into runs"):
        split("`a. ` " * (spec.REFUSED_IDEA_CHARS // 6 + 1))
    assert time.perf_counter() - started < 0.5
    assert split("x. " * (spec.REFUSED_IDEA_CHARS // 3)).coarse
