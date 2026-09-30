from wildcard import filter_names


def test_keeps_only_matching_names():
    names = ["a.py", "b.txt", "c.py", "d.md"]
    assert filter_names("*.py", names) == ["a.py", "c.py"]
    assert filter_names("?.txt", names) == ["b.txt"]
    assert filter_names("[a-c].*", names) == ["a.py", "b.txt", "c.py"]


def test_original_order_and_duplicates_are_kept():
    assert filter_names("[ab]", ["b", "a", "b", "c", "a"]) == ["b", "a", "b", "a"]
    assert filter_names("*", ["z", "y", "x"]) == ["z", "y", "x"]


def test_no_match_gives_an_empty_list():
    assert filter_names("*.rs", ["a.py", "b.txt"]) == []
    assert filter_names("*", []) == []


def test_result_is_a_new_list():
    names = ["a", "b"]
    result = filter_names("*", names)
    assert result == names
    assert result is not names
    result.append("c")
    assert names == ["a", "b"]


def test_accepts_any_iterable_of_strings():
    assert filter_names("a*", ("ab", "ba", "ac")) == ["ab", "ac"]
    assert filter_names("a*", (n for n in ["ab", "ba", "ac"])) == ["ab", "ac"]
    assert filter_names("a*", iter(["ab", "ba"])) == ["ab"]
    assert filter_names("a*", {"ab": 1, "ba": 2}) == ["ab"]


def test_is_case_sensitive():
    assert filter_names("*.py", ["A.PY", "a.py", "B.Py"]) == ["a.py"]


def test_empty_names_are_handled_like_match_would():
    assert filter_names("*", ["", "a"]) == ["", "a"]
    assert filter_names("?", ["", "a"]) == ["a"]
    assert filter_names("", ["", "a"]) == [""]


def test_escapes_and_sets_are_honoured():
    assert filter_names("a\\*b", ["a*b", "axb"]) == ["a*b"]
    assert filter_names("[]x]", ["]", "x", "a"]) == ["]", "x"]
    assert filter_names("[!.]*", [".hidden", "shown"]) == ["shown"]
    assert filter_names("data_??.csv", ["data_01.csv", "data_1.csv", "data_001.csv"]) == [
        "data_01.csv"
    ]
