from iniparse import parse_ini


def test_a_repeated_key_takes_the_later_value():
    assert parse_ini("[s]\nk = 1\nk = 2\nk = 3") == {"s": {"k": "3"}}


def test_a_repeated_header_continues_the_section():
    text = "[a]\nx = 1\n[b]\ny = 2\n[a]\nz = 3\n"
    assert parse_ini(text) == {"a": {"x": "1", "z": "3"}, "b": {"y": "2"}}


def test_a_continued_section_can_override_an_earlier_key():
    assert parse_ini("[a]\nk = old\nj = keep\n[b]\n[a]\nk = new") == {
        "a": {"k": "new", "j": "keep"},
        "b": {},
    }


def test_the_same_key_in_different_sections_is_independent():
    assert parse_ini("[a]\nk = 1\n[b]\nk = 2") == {"a": {"k": "1"}, "b": {"k": "2"}}


def test_a_repeated_empty_section_stays_one_section():
    assert parse_ini("[a]\n[a]\n[a]") == {"a": {}}


def test_header_spelled_with_different_spacing_is_the_same_section():
    assert parse_ini("[a]\nx = 1\n[ a ]\ny = 2") == {"a": {"x": "1", "y": "2"}}


def test_keys_before_any_header_are_not_part_of_a_later_section():
    assert parse_ini("k = 1\n[s]\nk = 2") == {"": {"k": "1"}, "s": {"k": "2"}}
