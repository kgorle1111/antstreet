from slugify import slugify


def test_words_and_case():
    assert slugify("Hello World") == "hello-world"
    assert slugify("Python 3 Rocks") == "python-3-rocks"
