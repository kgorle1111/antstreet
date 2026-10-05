"""boss.spec anchors: what a test of a rule must contain, and whether a check contains it."""

import time

import pytest

from boss import spec
from boss.spec import Anchor, extract_anchors, facts, missing, present


def a(text: str) -> list[tuple[str, str]]:
    return [(x.type, x.value) for x in extract_anchors(text)]


def has(anchor: Anchor, source: str) -> bool:
    found = facts(source)
    assert found is not None
    return present(anchor, [found])


# --- extraction ------------------------------------------------------------------------------


def test_a_data_literal_in_backticks_is_an_anchor_but_a_name_or_signature_is_not():
    assert a("`79927398713` is valid") == [("literal", "79927398713")]
    assert a("The function `max_length` and `slugify.py` and `f(x: int) -> int`") == []
    assert a("Use `True`, `None` and `ValueError`") == [("exception", "ValueError")]


def test_a_sentence_listing_three_or_more_literals_gets_one_anchor_per_item():
    got = a("`.5`, `1.`, `1.5.5` and `1e3` are invalid")
    assert got == [
        ("enum_item", ".5"),
        ("enum_item", "1."),
        ("enum_item", "1.5.5"),
        ("enum_item", "1e3"),
    ]
    assert [t for t, _ in a("`.5` and `1.` are invalid")] == ["literal", "literal"]


def test_an_operator_or_placeholder_in_backticks_is_not_test_data():
    assert a("Operators are `+`, `-`, `*` and `/`") == []
    assert a("`[...]` is a set and `<name>` is a tag and `a-z` is a range") == []
    assert a('The empty string `""` and `[]` and `()` are valid') == [
        ("enum_item", '""'),
        ("enum_item", "[]"),
        ("enum_item", "()"),
    ]


def test_an_exception_name_is_an_anchor_with_or_without_backticks():
    assert a("raises `ValueError` or KeyError") == [
        ("exception", "ValueError"),
        ("exception", "KeyError"),
    ]


def test_a_type_is_an_anchor_only_when_it_is_what_the_code_returns():
    assert a("`available()` returns the tokens as a `float`.") == [("type", "float")]
    assert a("The result is an `int`.") == [("type", "int")]
    assert a("A non-string argument (`bytes`, a list) raises.") == []
    assert a("It accepts an input that is a `str`.") == []


def test_a_size_in_the_rule_is_a_magnitude_anchor():
    assert ("magnitude", "2000") in a("an expression of 2000 operands joined by `+` is valid")
    assert ("magnitude", "50") in a("can be nested at least 50 levels deep")
    assert ("magnitude", "10000") in a("a chain of 10,000 nodes")
    assert a("the second of 3 items") == []
    assert a("takes 7 rows") == []


def test_non_ascii_is_an_anchor_however_the_rule_words_it():
    for text in (
        "non-ASCII digits are not valid",
        "digits that are not ASCII 0-9",
        "a digit of another script such as one in full-width form",
        "Arabic-Indic digits",
        "only ASCII letters",
    ):
        assert ("non_ascii", "non-ASCII") in a(text), text
    assert a("plain words only") == []


def test_duplicates_collapse_and_the_count_is_capped():
    assert a("`12` and `12`") == [("literal", "12")]
    many = " ".join(f"`{n}1`" for n in range(30))
    assert len(extract_anchors(many)) == spec.MAX_ANCHORS


def test_an_anchor_type_must_be_known():
    with pytest.raises(ValueError, match="anchor type"):
        Anchor("nonsense", "x")


# --- presence in a check ---------------------------------------------------------------------


def test_non_ascii_needs_a_string_constant_with_a_code_point_above_127():
    anchor = Anchor("non_ascii", "non-ASCII")
    assert has(anchor, "def test_a():\n    assert f('٣') is False\n")
    assert has(anchor, "def test_a():\n    assert f('\\u0663') is False\n")
    assert not has(anchor, "def test_a():\n    assert f('3') is False\n")


def test_non_ascii_in_a_docstring_or_a_comment_does_not_count():
    anchor = Anchor("non_ascii", "non-ASCII")
    assert not has(anchor, 'def test_a():\n    """٣"""\n    assert f("3")\n')
    assert not has(anchor, '"""٣ module"""\ndef test_a():\n    assert f("3")\n')
    assert not has(anchor, "def test_a():\n    assert f('3')  # ٣\n")


def test_the_type_float_needs_the_name_not_a_float_literal():
    anchor = Anchor("type", "float")
    assert not has(anchor, "def test_a():\n    assert bucket.available() == 5.0\n")
    assert has(anchor, "def test_a():\n    assert isinstance(bucket.available(), float)\n")


def test_an_exception_needs_its_name_in_the_check():
    anchor = Anchor("exception", "ValueError")
    assert has(
        anchor, "import pytest\ndef test_a():\n    with pytest.raises(ValueError):\n        f(1)\n"
    )
    assert has(
        anchor, "def test_a():\n    try:\n        f(1)\n    except ValueError:\n        pass\n"
    )
    assert not has(
        anchor, "import pytest\ndef test_a():\n    with pytest.raises(KeyError):\n        f(1)\n"
    )
    assert not has(anchor, "def test_a():\n    assert f('ValueError')\n"), "a string is not a name"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def test_a():\n    assert f('+'.join(['1'] * 2000))\n", True),
        ("def test_a():\n    assert f('1' * 10**4)\n", True),
        ("def test_a():\n    assert f(' + '.join(str(i) for i in range(2000)))\n", True),
        ("def test_a():\n    assert f('+'.join(['1'] * 100))\n", False),
        ("def test_a():\n    assert f('(' * 49)\n", False),
        ("def test_a():\n    assert f(2 ** 99999999)\n", True),  # the exponent is a constant too
        ("def test_a():\n    assert f(1_000 * 3)\n", True),
    ],
)
def test_a_magnitude_needs_a_number_at_least_that_large_once_products_are_folded(source, expected):
    assert has(Anchor("magnitude", "2000"), source) is expected


def test_a_hostile_check_cannot_make_folding_slow_or_huge():
    source = "def test_a():\n    assert f(" + "(" * 80 + "9**9**9**9**9" + ")" * 80 + ")\n"
    started = time.perf_counter()
    facts(source)
    assert time.perf_counter() - started < 2.0


@pytest.mark.parametrize(
    ("literal", "source", "expected"),
    [
        (".5", "def test_a():\n    assert g('.5s') == 0.5\n", True),
        ("1e3", "def test_a():\n    assert g('1e3s') is None\n", True),
        ("1e3", "def test_a():\n    assert g(1000.0) == 1\n", True),
        ('"- 1s"', "def test_a():\n    assert g('- 1s') is None\n", True),
        ("[]", "def test_a():\n    assert g([]) == []\n", True),
        ("()", "def test_a():\n    assert g(()) == 0\n", True),
        ("1.5.5", "def test_a():\n    assert g('1.5s') == 1.5\n", False),
        ("0", "def test_a():\n    assert g('10') == 10\n", False),
        ("0", "def test_a():\n    assert g(0) == 0\n", True),
        ("4111 1111", "def test_a():\n    assert g('4111 1111 1111') is True\n", True),
        ("[]", "def test_a():\n    assert g('x') == 1\n", False),
    ],
)
def test_a_literal_is_present_as_text_or_as_a_value(literal, source, expected):
    assert has(Anchor("literal", literal), source) is expected


def test_one_example_standing_for_a_list_leaves_the_other_items_missing():
    """The examiner tested `.5s` for a sentence that lists five invalid forms."""
    anchors = extract_anchors("`.5`, `1.`, `1.5.5`, `1e3` and `1_0` are not valid")
    found = facts("def test_a():\n    with raises(ValueError):\n        parse('.5s')\n")
    assert found is not None
    assert [x.value for x in missing(anchors, [found])] == ["1.", "1.5.5", "1e3", "1_0"]


def test_an_unparsable_check_has_no_facts():
    assert facts("def test_a(:\n") is None
    assert facts("\x00") is None


def test_a_bom_does_not_stop_a_check_from_parsing():
    assert facts("﻿def test_a():\n    assert f('x')\n") is not None


def test_present_over_several_checks_is_any_of_them():
    one = facts("def test_a():\n    assert f('٣')\n")
    two = facts("def test_b():\n    assert f('x')\n")
    assert one is not None and two is not None
    assert present(Anchor("non_ascii", "non-ASCII"), [two, one])
    assert not present(Anchor("non_ascii", "non-ASCII"), [two])
    assert not present(Anchor("non_ascii", "non-ASCII"), [])
