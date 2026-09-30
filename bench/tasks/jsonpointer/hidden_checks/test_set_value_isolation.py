import copy

from jsonpointer import resolve, set_value


def make_doc():
    return {"a": {"b": [1, {"c": 2}], "d": "x"}, "e": [[1], [2]], "f": None}


def test_input_document_is_not_modified():
    doc = make_doc()
    set_value(doc, "/a/b/0", 99)
    set_value(doc, "/a/new", 1)
    set_value(doc, "/e/-", [3])
    set_value(doc, "/a/b/1/c", "changed")
    set_value(doc, "/f", {"g": 1})
    assert doc == make_doc()


def test_result_is_a_new_object():
    doc = make_doc()
    result = set_value(doc, "/a/d", "y")
    assert result is not doc
    assert result["a"] is not doc["a"]
    assert resolve(doc, "/a/d") == "x"
    assert resolve(result, "/a/d") == "y"


def test_untouched_branches_are_copies_too():
    doc = make_doc()
    result = set_value(doc, "/a/d", "y")
    assert result["e"] == doc["e"]
    assert result["e"] is not doc["e"]
    assert result["e"][0] is not doc["e"][0]
    assert result["a"]["b"] is not doc["a"]["b"]
    assert result["a"]["b"][1] is not doc["a"]["b"][1]


def test_changing_the_result_later_does_not_touch_the_input():
    doc = make_doc()
    result = set_value(doc, "/a/d", "y")
    result["e"][0].append("boom")
    result["a"]["b"][1]["c"] = "boom"
    result["a"]["b"].append("boom")
    assert doc == make_doc()


def test_changing_the_input_later_does_not_touch_the_result():
    doc = make_doc()
    result = set_value(doc, "/a/d", "y")
    snapshot = copy.deepcopy(result)
    doc["e"][1].append("boom")
    doc["a"]["b"][1]["c"] = "boom"
    assert result == snapshot


def test_root_list_is_copied_when_appending():
    doc = [[1], [2]]
    result = set_value(doc, "/-", [3])
    assert result == [[1], [2], [3]]
    assert doc == [[1], [2]]
    assert result[0] is not doc[0]


def test_failed_set_leaves_the_input_untouched():
    doc = make_doc()
    for pointer in ("/a/b/9", "/zz/y", "/f/x", "/a/d/0", "/e/-/0", "/a/b/01"):
        try:
            set_value(doc, pointer, 1)
        except KeyError:
            pass
        else:
            raise AssertionError(f"{pointer} should have raised KeyError")
    assert doc == make_doc()
