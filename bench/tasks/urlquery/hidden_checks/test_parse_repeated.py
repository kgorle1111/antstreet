from urlquery import parse_query


def test_repeated_keys_collect_values_in_order():
    assert parse_query("a=1&b=2&a=3") == {"a": ["1", "3"], "b": ["2"]}


def test_a_value_may_repeat():
    assert parse_query("t=x&t=x&t=y") == {"t": ["x", "x", "y"]}


def test_empty_values_are_kept_in_the_list():
    assert parse_query("a=&a=1&a") == {"a": ["", "1", ""]}


def test_keys_are_in_order_of_first_appearance():
    result = parse_query("z=1&a=2&z=3&m=4&a=5")
    assert list(result) == ["z", "a", "m"]
    assert result == {"z": ["1", "3"], "a": ["2", "5"], "m": ["4"]}


def test_different_spellings_of_one_key_are_one_key():
    assert parse_query("a%20b=1&a+b=2&a%2Bb=3") == {"a b": ["1", "2"], "a+b": ["3"]}


def test_keys_are_case_sensitive():
    assert parse_query("A=1&a=2") == {"A": ["1"], "a": ["2"]}


def test_many_repeats():
    qs = "&".join(f"k={i}" for i in range(100))
    assert parse_query(qs) == {"k": [str(i) for i in range(100)]}
