from slugify import slugify


def test_runs_collapse_and_edges_are_trimmed():
    assert slugify("  --Hello,,,   World!!  ") == "hello-world"
    assert slugify("a_b.c/d") == "a-b-c-d"


def test_nothing_usable_gives_empty_string():
    assert slugify("") == ""
    assert slugify("?!... ---") == ""
