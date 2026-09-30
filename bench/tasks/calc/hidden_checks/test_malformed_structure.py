import pytest
from calc import evaluate


@pytest.mark.parametrize("bad", ["", " ", "   ", "\t", "\n", " \t\r\n "])
def test_empty_or_whitespace_only_raises(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


@pytest.mark.parametrize(
    "bad",
    ["(1 + 2", "1 + 2)", "((1)", "(1))", ")(", "(", ")", "1 + (2 * 3", "((((1 + 2)))", ")1 + 2("],
)
def test_unbalanced_parentheses_raise(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


@pytest.mark.parametrize("bad", ["()", "( )", "1 + ()", "() + 1", "2 * ()", "(())", "-()"])
def test_empty_parentheses_raise(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "1 +",
        "1 -",
        "1 *",
        "1 /",
        "* 2",
        "/ 2",
        "1 + * 2",
        "1 * / 2",
        "1 +* 2",
        "+",
        "-",
        "*",
        "/",
        "(-)",
        "(1 +)",
        "(* 2)",
        "1 + (2 *)",
        "1 2 +",
        "- - ",
    ],
)
def test_missing_operand_raises(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


@pytest.mark.parametrize("bad", ["1 2", "1 2 3", "2 (3)", "(1)(2)", "(1) 2", "1 (2)", "(1)2"])
def test_adjacent_operands_raise(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


@pytest.mark.parametrize("bad", ["1 / 0 +", "1 / 0 )", "(1 / 0", "1 / 0 2", "1 / 0 + * 2", "0 * "])
def test_syntax_is_checked_before_evaluation(bad):
    with pytest.raises(ValueError):
        evaluate(bad)
