import pytest
from editdistance import edit_distance, edit_script


@pytest.mark.parametrize("bad", [None, 5, b"abc", ["a"], ("a",), 1.5, True])
@pytest.mark.parametrize("fn", [edit_distance, edit_script])
def test_a_non_string_argument_raises_type_error(fn, bad):
    with pytest.raises(TypeError):
        fn(bad, "abc")
    with pytest.raises(TypeError):
        fn("abc", bad)
    with pytest.raises(TypeError):
        fn(bad, bad)
