import pytest
from mdheadings import extract_headings, heading_tree


def node(level, title, anchor, *children):
    return {"level": level, "title": title, "anchor": anchor, "children": list(children)}


def test_a_flat_list_of_same_level_headings_gives_roots():
    assert heading_tree("# A\n# B") == [node(1, "A", "a"), node(1, "B", "b")]


def test_nesting_by_level():
    text = "# A\n## B\n### C\n## D\n# E\n## F\n"
    assert heading_tree(text) == [
        node(1, "A", "a", node(2, "B", "b", node(3, "C", "c")), node(2, "D", "d")),
        node(1, "E", "e", node(2, "F", "f")),
    ]


def test_a_skipped_level_still_nests_under_the_nearest_smaller_heading():
    assert heading_tree("# A\n### B\n#### C") == [
        node(1, "A", "a", node(3, "B", "b", node(4, "C", "c")))
    ]


def test_a_deeper_heading_after_a_deep_one_pops_several_levels():
    text = "# A\n## B\n### C\n#### D\n## E"
    assert heading_tree(text) == [
        node(
            1,
            "A",
            "a",
            node(2, "B", "b", node(3, "C", "c", node(4, "D", "d"))),
            node(2, "E", "e"),
        )
    ]


def test_a_return_to_a_shallower_level_closes_all_deeper_ones():
    text = "## A\n#### B\n##### C\n### D\n## E"
    assert heading_tree(text) == [
        node(2, "A", "a", node(4, "B", "b", node(5, "C", "c")), node(3, "D", "d")),
        node(2, "E", "e"),
    ]


def test_headings_before_the_first_top_level_heading_are_roots_in_order():
    text = "### Deep\n## Mid\n# Top\n## Under"
    assert heading_tree(text) == [
        node(3, "Deep", "deep"),
        node(2, "Mid", "mid"),
        node(1, "Top", "top", node(2, "Under", "under")),
    ]


def test_a_smaller_heading_after_a_larger_one_starts_a_new_root():
    assert heading_tree("## A\n# B\n## C") == [
        node(2, "A", "a"),
        node(1, "B", "b", node(2, "C", "c")),
    ]


def test_equal_level_after_deeper_children_is_a_sibling_not_a_child():
    text = "# R\n## A\n### A1\n## B\n### B1"
    assert heading_tree(text) == [
        node(
            1,
            "R",
            "r",
            node(2, "A", "a", node(3, "A1", "a1")),
            node(2, "B", "b", node(3, "B1", "b1")),
        )
    ]


def test_titles_and_anchors_are_the_same_as_extract_headings():
    text = "# Setup\n## Setup ##\n```\n# no\n```\n## Café, au lait\n# Setup"
    flat = []

    def walk(nodes):
        for item in nodes:
            flat.append((item["level"], item["title"], item["anchor"]))
            walk(item["children"])

    walk(heading_tree(text))
    assert flat == extract_headings(text)
    assert [a for _, _, a in flat] == ["setup", "setup-1", "café-au-lait", "setup-2"]


def test_no_headings_gives_an_empty_list():
    assert heading_tree("") == []
    assert heading_tree("just text\n") == []


@pytest.mark.parametrize("text", ["# A", "# A\n## B"])
def test_nodes_have_exactly_the_four_keys_and_a_list_of_children(text):
    def check(nodes):
        for item in nodes:
            assert set(item) == {"level", "title", "anchor", "children"}
            assert type(item["level"]) is int and type(item["children"]) is list
            check(item["children"])

    result = heading_tree(text)
    assert type(result) is list
    check(result)


def test_a_long_outline():
    lines = []
    for chapter in range(1, 4):
        lines.append(f"# Chapter {chapter}")
        for section in range(1, 3):
            lines.append(f"## Section {chapter}.{section}")
    tree = heading_tree("\n".join(lines))
    assert [n["title"] for n in tree] == ["Chapter 1", "Chapter 2", "Chapter 3"]
    assert [[c["title"] for c in n["children"]] for n in tree] == [
        ["Section 1.1", "Section 1.2"],
        ["Section 2.1", "Section 2.2"],
        ["Section 3.1", "Section 3.2"],
    ]
    assert tree[0]["children"][0]["anchor"] == "section-11"
