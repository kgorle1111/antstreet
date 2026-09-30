import pytest
from bigdecimal import add, compare, multiply, subtract

FUNCTIONS = [add, subtract, multiply, compare]
IDS = ["add", "subtract", "multiply", "compare"]

INVALID_STRINGS = [
    "",
    "-",
    ".",
    "-.",
    "+5",
    "+0",
    "1.",
    "-1.",
    ".5",
    "-.5",
    "1e5",
    "1E5",
    "1.5e2",
    "1.2.3",
    "1..5",
    "--5",
    "5-",
    "1_000",
    "1,5",
    "1/2",
    "(5)",
    "0x10",
    "NaN",
    "inf",
    "-Infinity",
    "abc",
    " 5",
    "5 ",
    "\t5",
    "5\n",
    "1 000",
    "1 .5",
    "- 5",
    "5\x00",
    "١٢٣",
    "５",
    "1.٥",
]

NON_STRINGS = [5, 0, 1.5, None, b"5", True, [], ["5"], ("5",)]


@pytest.mark.parametrize("fn", FUNCTIONS, ids=IDS)
@pytest.mark.parametrize("bad", INVALID_STRINGS)
def test_invalid_string_as_first_argument(fn, bad):
    with pytest.raises(ValueError):
        fn(bad, "1")


@pytest.mark.parametrize("fn", FUNCTIONS, ids=IDS)
@pytest.mark.parametrize("bad", INVALID_STRINGS)
def test_invalid_string_as_second_argument(fn, bad):
    with pytest.raises(ValueError):
        fn("1", bad)


@pytest.mark.parametrize("fn", FUNCTIONS, ids=IDS)
@pytest.mark.parametrize("bad", ["abc", "1.", "+1", " 0", "", "5\n"])
def test_the_other_operand_being_zero_does_not_excuse_an_invalid_one(fn, bad):
    with pytest.raises(ValueError):
        fn("0", bad)
    with pytest.raises(ValueError):
        fn(bad, "0")
    with pytest.raises(ValueError):
        fn("-0.0", bad)
    with pytest.raises(ValueError):
        fn(bad, "-0.0")


@pytest.mark.parametrize("fn", FUNCTIONS, ids=IDS)
@pytest.mark.parametrize("bad", NON_STRINGS, ids=repr)
def test_non_string_arguments_raise_value_error(fn, bad):
    with pytest.raises(ValueError):
        fn(bad, "1")
    with pytest.raises(ValueError):
        fn("1", bad)
    with pytest.raises(ValueError):
        fn("0", bad)


@pytest.mark.parametrize("fn", FUNCTIONS, ids=IDS)
def test_both_arguments_invalid(fn):
    with pytest.raises(ValueError):
        fn("x", "y")
    with pytest.raises(ValueError):
        fn(None, None)


@pytest.mark.parametrize(
    "good",
    ["0", "-0", "-0.0", "007", "-000.50", "1.500", "0.0", "123456789.987654321", "-9"],
)
def test_valid_spellings_are_accepted_everywhere(good):
    for fn in FUNCTIONS:
        fn(good, "1")
        fn("1", good)
        fn(good, good)
