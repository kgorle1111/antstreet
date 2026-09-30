from slugify import slugify


def test_first_word_longer_than_limit_is_cut_exactly():
    assert slugify("internationalization today", max_length=5) == "inter"
    assert slugify("abc", max_length=1) == "a"
