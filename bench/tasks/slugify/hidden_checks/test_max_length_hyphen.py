from slugify import slugify


def test_cut_at_last_hyphen_that_fits():
    assert slugify("hello wonderful world", max_length=15) == "hello-wonderful"
    assert slugify("hello wonderful world", max_length=14) == "hello"
    assert slugify("hello world", max_length=5) == "hello"


def test_no_cut_when_it_already_fits():
    assert slugify("hello world", max_length=11) == "hello-world"
    assert slugify("hello world", max_length=50) == "hello-world"
