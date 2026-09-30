from slugify import slugify


def test_accents_become_plain_letters():
    assert slugify("Crème Brûlée") == "creme-brulee"
    assert slugify("Über uns") == "uber-uns"


def test_characters_without_ascii_form_are_dropped():
    assert slugify("price 5€ now") == "price-5-now"
