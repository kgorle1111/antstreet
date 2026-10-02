from iniparse import parse_ini


def test_two_sections_with_keys():
    text = "[a]\nx = 1\ny = 2\n[b]\nz = 3\n"
    assert parse_ini(text) == {"a": {"x": "1", "y": "2"}, "b": {"z": "3"}}


def test_empty_text_and_blank_lines_give_an_empty_dict():
    assert parse_ini("") == {}
    assert parse_ini("\n\n   \n\t\n") == {}


def test_a_section_without_keys_is_still_in_the_result():
    assert parse_ini("[empty]") == {"empty": {}}
    assert parse_ini("[one]\n[two]\nk=v\n[three]\n") == {"one": {}, "two": {"k": "v"}, "three": {}}


def test_header_whitespace_is_trimmed_and_inner_space_is_kept():
    assert parse_ini("[ db ]\nk=v") == {"db": {"k": "v"}}
    assert parse_ini("[a b]\nk=v") == {"a b": {"k": "v"}}
    assert parse_ini("  [x]  \nk=v") == {"x": {"k": "v"}}


def test_section_names_and_keys_are_case_sensitive():
    assert parse_ini("[A]\nk=1\n[a]\nK=2\nk=3") == {"A": {"k": "1"}, "a": {"K": "2", "k": "3"}}


def test_dict_values_are_plain_dicts_of_strings():
    result = parse_ini("[a]\nn = 5\nflag = true")
    assert isinstance(result, dict) and isinstance(result["a"], dict)
    assert result["a"] == {"n": "5", "flag": "true"}
