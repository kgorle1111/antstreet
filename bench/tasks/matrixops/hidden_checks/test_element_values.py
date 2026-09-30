from matrixops import rotate, spiral, transpose


def same_objects(actual, expected):
    return len(actual) == len(expected) and all(
        a is e for a, e in zip(actual, expected, strict=True)
    )


def test_falsy_and_equal_elements_are_moved_like_any_other():
    m = [[None, 0, ""], [0, "", None]]
    assert spiral(m) == [None, 0, "", None, "", 0]
    assert transpose(m) == [[None, 0], [0, ""], ["", None]]
    assert rotate(m) == [[0, None], ["", 0], [None, ""]]
    assert spiral([[0, 0], [0, 0]]) == [0, 0, 0, 0]
    assert rotate([[0, 0], [0, 0]], 3) == [[0, 0], [0, 0]]


def test_strings_and_mixed_types_are_not_inspected():
    m = [["ab", 1.5], [None, ("t",)]]
    assert spiral(m) == ["ab", 1.5, ("t",), None]
    assert rotate(m) == [[None, "ab"], [("t",), 1.5]]


def test_the_same_element_objects_are_returned_not_copies():
    a, b, c, d, e, f = (object() for _ in range(6))
    m = [[a, b, c], [d, e, f]]
    assert same_objects(spiral(m), [a, b, c, f, e, d])
    rotated = rotate(m)
    assert same_objects(rotated[0], [d, a])
    assert same_objects(rotated[2], [f, c])
    transposed = transpose(m)
    assert same_objects(transposed[1], [b, e])
    assert same_objects(rotate(m, 0)[1], [d, e, f])


def test_list_elements_are_not_flattened_or_copied():
    inner = [[1], [2]]
    m = [[inner, [3]], [[4], [5]]]
    result = rotate(m)
    assert result[0][1] is inner
    assert result[0][1] == [[1], [2]]
    assert spiral(m)[0] is inner
    assert transpose(m)[0][0] is inner
