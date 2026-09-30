from wildcard import filter_names, match

LONG = 10_000


def test_repeated_stars_against_a_long_run_fail_fast():
    assert not match("a*a*a*a*a*b", "a" * LONG)
    assert not match("a*" * 30 + "b", "a" * LONG)
    assert not match("*a" * 25 + "b", "a" * LONG)


def test_repeated_stars_against_a_long_run_still_match_when_they_should():
    assert match("a*a*a*a*a*b", "a" * LONG + "b")
    assert match("a*" * 30 + "b", "a" * LONG + "b")
    assert match("a*a*a*a*a*", "a" * LONG)


def test_many_adjacent_stars():
    assert not match("*" * 50 + "b", "a" * LONG)
    assert match("*" * 50 + "b", "a" * LONG + "b")
    assert match("*" * 100, "a" * LONG)


def test_stars_with_sets_and_question_marks():
    assert not match("*?*[a]*?*[!b]*b", "a" * LONG)
    assert match("*?*[a]*?*[!b]*b", "a" * (LONG - 1) + "b")
    assert not match("*[ab]*[ab]*[ab]*[ab]*c", "ab" * (LONG // 2))
    assert match("*[ab]*[ab]*[ab]*[ab]*c", "ab" * (LONG // 2) + "c")


def test_long_text_with_a_late_mismatch():
    assert not match("a*a*a*a*a*c", ("ab" * (LONG // 2)))
    assert not match("*" + "?" * 100, "a" * 99)
    assert match("*" + "?" * 100, "a" * LONG)


def test_long_texts_do_not_hit_the_recursion_limit():
    assert match("a*b", "a" + "x" * (LONG - 2) + "b")
    assert match("*", "x" * LONG)
    assert match("?" * 100 + "*", "x" * LONG)
    assert not match("*x", "x" * (LONG - 1) + "y")


def test_filter_names_on_many_hard_names():
    names = ["a" * 2000 for _ in range(200)] + ["a" * 2000 + "b"]
    assert filter_names("a*a*a*a*a*b", names) == ["a" * 2000 + "b"]
