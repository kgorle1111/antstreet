"""The mutator behind check strength: each operator, only changed lines, a fixed order, a cap."""

import ast

from antstreet.mutate import changed_lines, mutants

SOURCE = """\
def f(a, b, flag=True):
    if a < b and flag:
        raise ValueError("no")
    if a == b or a > 3:
        return a + b
    return None
"""


def one(source: str, old: str = "") -> dict[str, str]:
    """operator -> the first mutant made with it."""
    found, total = mutants({"m.py": (old, source)})
    assert total == len(found)
    made: dict[str, str] = {}
    for m in found:
        made.setdefault(m.operator, m.source)
    return made


def test_each_operator_makes_the_edit_it_names_and_the_mutant_parses():
    made = one(SOURCE)
    assert set(made) == {
        "< -> <=", "and -> or", "True -> False", "raise -> pass", "== -> !=", "or -> and",
        "> -> >=", "3 -> 4", "+ -> -", "return value -> return None",
        "if condition -> if not condition",
    }  # fmt: skip
    for source in made.values():
        ast.parse(source)
    assert "a <= b and flag" in made["< -> <="]
    assert "a < b or flag" in made["and -> or"]
    assert "flag=False" in made["True -> False"]
    assert "raise" not in made["raise -> pass"] and "pass" in made["raise -> pass"]
    assert "a != b or a > 3" in made["== -> !="]
    assert "a > 4" in made["3 -> 4"]
    assert "return a - b" in made["+ -> -"]
    assert "return a + b" not in made["return value -> return None"]
    assert "if not (a < b and flag)" in made["if condition -> if not condition"]


def test_an_if_is_negated_once_per_if_and_return_none_is_left_alone():
    found, _ = mutants({"m.py": ("", SOURCE)})
    negated = [m for m in found if m.operator.startswith("if ")]
    assert [m.line for m in negated] == [2, 4]
    assert sum(m.operator.startswith("return") for m in found) == 1  # not `return None`


def test_only_lines_the_change_added_or_edited_are_mutated():
    old = SOURCE.replace("return a + b", "return a * b")
    found, _ = mutants({"m.py": (old, SOURCE)})
    assert {m.line for m in found} == {5}
    assert {m.operator for m in found} == {"+ -> -", "return value -> return None"}
    assert changed_lines("a\nb\n", "a\nc\nb\nd\n") == {2, 4}
    assert mutants({"m.py": (SOURCE, SOURCE)}) == ([], 0)


def test_the_order_is_fixed_whatever_order_the_files_come_in():
    files = {"b.py": ("", "def g(x):\n    return x - 1\n"), "a.py": ("", SOURCE)}
    first = mutants(files)
    again = mutants(dict(reversed(list(files.items()))))
    assert first == again
    assert [m.path for m in first[0]][0] == "a.py" and first[0][-1].path == "b.py"


def test_the_cap_takes_mutants_spread_across_every_file():
    files = {f"m{i}.py": ("", SOURCE) for i in range(5)}
    found, total = mutants(files, cap=7)
    assert total == 60 and len(found) == 7
    assert {m.path for m in found} == set(files)
    assert mutants(files, cap=7) == (found, total)


def test_a_file_that_does_not_parse_is_skipped():
    found, total = mutants({"bad.py": ("", "def f(:\n"), "ok.py": ("", "X = 1\n")})
    assert total == 1 and [m.path for m in found] == ["ok.py"]
