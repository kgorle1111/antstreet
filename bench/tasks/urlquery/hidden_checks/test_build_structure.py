from urlquery import build_query


def test_empty_dict_gives_empty_string():
    assert build_query({}) == ""


def test_pairs_follow_dict_order_and_have_no_question_mark():
    assert build_query({"b": "2", "a": "1"}) == "b=2&a=1"


def test_a_list_gives_one_pair_per_value_in_order():
    assert build_query({"a": ["1", "2", "3"]}) == "a=1&a=2&a=3"
    assert build_query({"a": ("x", "y")}) == "a=x&a=y"


def test_a_string_counts_as_a_one_item_list():
    assert build_query({"a": "1"}) == build_query({"a": ["1"]}) == "a=1"


def test_an_empty_list_gives_no_pairs():
    assert build_query({"a": []}) == ""
    assert build_query({"a": [], "b": "1", "c": []}) == "b=1"


def test_an_empty_value_is_written_with_an_equals_sign():
    assert build_query({"a": ""}) == "a="
    assert build_query({"a": ["", "x", ""]}) == "a=&a=x&a="


def test_keys_with_lists_interleave_in_key_order():
    params = {"z": ["1", "2"], "a": "x", "m": ["p", "q"]}
    assert build_query(params) == "z=1&z=2&a=x&m=p&m=q"


def test_the_input_is_not_modified():
    params = {"a": ["1", "2"], "b": "x"}
    build_query(params)
    assert params == {"a": ["1", "2"], "b": "x"}
