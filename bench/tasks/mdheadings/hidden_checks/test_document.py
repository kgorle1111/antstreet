import pytest
from mdheadings import extract_headings, heading_tree

DOCUMENT = """\
# Project

Intro text with a #hashtag and `# code`.

## Install ##

```bash
# install the thing
pip install project
```

## Usage

### Basic

~~~python
# comment, not a heading
~~~

### Basic

#### C#

#nospace

####### too deep

## Usage

Setext heading
==============

## FAQ?
"""


def test_a_whole_document():
    assert extract_headings(DOCUMENT) == [
        (1, "Project", "project"),
        (2, "Install", "install"),
        (2, "Usage", "usage"),
        (3, "Basic", "basic"),
        (3, "Basic", "basic-1"),
        (4, "C#", "c"),
        (2, "Usage", "usage-1"),
        (2, "FAQ?", "faq"),
    ]


def test_the_outline_of_a_whole_document():
    def shape(nodes):
        return [(n["anchor"], shape(n["children"])) for n in nodes]

    assert shape(heading_tree(DOCUMENT)) == [
        (
            "project",
            [
                ("install", []),
                ("usage", [("basic", []), ("basic-1", [("c", [])])]),
                ("usage-1", []),
                ("faq", []),
            ],
        )
    ]


def test_the_same_document_with_crlf_line_ends():
    assert extract_headings(DOCUMENT.replace("\n", "\r\n")) == extract_headings(DOCUMENT)


@pytest.mark.parametrize("bad", [None, 5, b"# A", ["# A"], 2.5])
def test_non_string_argument_raises_value_error(bad):
    with pytest.raises(ValueError):
        extract_headings(bad)
    with pytest.raises(ValueError):
        heading_tree(bad)
