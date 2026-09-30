from jsonpointer import resolve, set_value


def test_tilde_one_is_slash():
    assert resolve({"a/b": 1, "a": {"b": 2}}, "/a~1b") == 1
    assert resolve({"/": 1}, "/~1") == 1
    assert resolve({"//": 1}, "/~1~1") == 1


def test_tilde_zero_is_tilde():
    assert resolve({"m~n": 8}, "/m~0n") == 8
    assert resolve({"~": 1}, "/~0") == 1
    assert resolve({"~~": 1}, "/~0~0") == 1


def test_tilde_zero_one_means_literal_tilde_one():
    doc = {"~1": "tilde-one", "/": "slash"}
    assert resolve(doc, "/~01") == "tilde-one"
    assert resolve(doc, "/~1") == "slash"


def test_tilde_one_zero_means_slash_then_zero():
    doc = {"/0": "slash-zero", "~": "tilde"}
    assert resolve(doc, "/~10") == "slash-zero"
    assert resolve(doc, "/~0") == "tilde"


def test_escapes_inside_longer_tokens_and_paths():
    doc = {"a/b": {"c~d": [1, 2]}}
    assert resolve(doc, "/a~1b/c~0d/1") == 2


def test_a_tilde_zero_key_is_not_treated_as_a_slash_escape():
    assert resolve({"~0": 1, "~": 2}, "/~00") == 1


def test_escapes_apply_when_setting():
    assert set_value({}, "/a~1b", 1) == {"a/b": 1}
    assert set_value({"x": {}}, "/x/~1", 9) == {"x": {"/": 9}}


def test_set_value_uses_the_decoded_key():
    assert set_value({}, "/m~0n", 1) == {"m~n": 1}
    assert set_value({}, "/~01", 1) == {"~1": 1}
    assert set_value({"~1": 0, "/": 5}, "/~01", 1) == {"~1": 1, "/": 5}
