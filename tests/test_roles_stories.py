"""User stories: the shape, and the gate that ties every acceptance criterion to the idea."""

import copy

import pytest

from antstreet.roles.stories import (
    MAX_CRITERIA,
    MAX_STORIES,
    STORIES_SCHEMA,
    Stories,
    StoriesError,
    is_fragment,
    normalise,
    parse_stories,
    story_problems,
)

IDEA = (
    "Create slugify.py with slugify(text, max_length=None).\n"
    "Lower-case the text and join words with single hyphens.\n"
    "If max_length is given, never cut a word in half."
)
GOOD = {
    "stories": [
        {
            "id": "S1",
            "as_a": "developer",
            "i_want": "a slug from any text",
            "so_that": "I can build URLs",
            "priority": "must",
            "criteria": [
                {
                    "id": "S1.1",
                    "given": "text with spaces",
                    "when": "slugify is called",
                    "then": "words are joined with single hyphens",
                    "source": "join words with single hyphens",
                },
                {
                    "id": "S1.2",
                    "given": "a max_length",
                    "when": "the slug would be longer",
                    "then": "no word is cut in half",
                    "source": "If max_length is given,  NEVER cut a word\nin half",
                },
            ],
        }
    ],
    "out_of_scope": ["transliteration"],
    "open_questions": [],
}


def changed(path, value) -> dict:
    data = copy.deepcopy(GOOD)
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return data


def problems(data) -> list[str]:
    return story_problems(parse_stories(data), IDEA)


def test_well_formed_stories_grounded_in_the_idea_pass_the_gate():
    stories = parse_stories(GOOD)
    assert story_problems(stories, IDEA) == []
    assert [c.id for c in stories.criteria()] == ["S1.1", "S1.2"]
    assert stories.out_of_scope == ("transliteration",)
    assert parse_stories(stories.to_data()) == stories


def test_a_quote_may_differ_from_the_idea_only_in_case_and_white_space():
    assert (
        problems(
            changed(["stories", 0, "criteria", 0, "source"], "JOIN   words\nwith single hyphens")
        )
        == []
    )
    reworded = problems(
        changed(["stories", 0, "criteria", 0, "source"], "joins the words with one hyphen")
    )
    assert reworded == [
        "S1.1: source is not a fragment of the idea: 'joins the words with one hyphen'"
    ]


def test_a_requirement_the_idea_does_not_contain_is_caught():
    invented = changed(["stories", 0, "criteria", 0, "source"], "must also strip emoji characters")
    assert problems(invented) == [
        "S1.1: source is not a fragment of the idea: 'must also strip emoji characters'"
    ]


@pytest.mark.parametrize("source", ["", "  ", "text", "hyphens"])
def test_a_quote_too_short_to_mean_anything_is_refused(source):
    [problem] = problems(changed(["stories", 0, "criteria", 0, "source"], source or " "))
    assert problem == "S1.1: source must quote at least 8 characters"


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (["stories", 0, "id"], "S2", "story 1 must have id S1, has 'S2'"),
        (["stories", 0, "id"], "story-1", "story 1 must have id S1, has 'story-1'"),
        (["stories", 0, "priority"], "urgent", "S1: priority must be one of must, should, could"),
        (["stories", 0, "as_a"], " ", "S1: as_a is empty"),
        (["stories", 0, "criteria", 1, "id"], "S1.3", "S1: criterion 2 must have id S1.2"),
        (["stories", 0, "criteria", 0, "then"], "", "S1.1: then is empty"),
        (["stories", 0, "criteria"], [], "S1: needs at least one acceptance criterion"),
    ],
)
def test_each_structural_problem_is_named(path, value, expected):
    assert expected in problems(changed(path, value))


def test_every_problem_is_reported_not_only_the_first():
    data = changed(["stories", 0, "priority"], "should")
    data["stories"][0]["criteria"][0]["source"] = "not in the idea at all"
    data["stories"][0]["criteria"][1]["when"] = ""
    found = problems(data)
    assert len(found) == 3 and "at least one story must have priority 'must'" in found


def test_the_number_of_stories_and_criteria_is_bounded():
    story = GOOD["stories"][0]
    many = {"stories": [story | {"id": f"S{n}"} for n in range(1, MAX_STORIES + 2)]}
    assert f"needs 1 to {MAX_STORIES} stories, has {MAX_STORIES + 1}" in problems(many)
    crowded = copy.deepcopy(GOOD)
    crowded["stories"][0]["criteria"] = [
        story["criteria"][0] | {"id": f"S1.{n}"} for n in range(1, MAX_CRITERIA + 2)
    ]
    assert f"at most {MAX_CRITERIA} criteria in all, has {MAX_CRITERIA + 1}" in problems(crowded)
    assert story_problems(Stories(()), IDEA)[0] == f"needs 1 to {MAX_STORIES} stories, has 0"


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "stories",
        {},
        {"stories": "S1"},
        {"stories": [None]},
        {"stories": [{"id": "S1"}]},
        changed(["stories", 0, "criteria"], "none"),
        changed(["stories", 0, "criteria", 0, "given"], 5),
        changed(["stories", 0, "as_a"], None),
        changed(["out_of_scope"], "nothing"),
        changed(["open_questions"], [1, 2]),
    ],
)
def test_data_that_is_not_shaped_like_stories_is_one_clear_error(data):
    with pytest.raises(StoriesError, match="not shaped like stories"):
        parse_stories(data)


def test_the_schema_asks_for_everything_the_parser_needs():
    story = STORIES_SCHEMA["properties"]["stories"]["items"]
    assert set(story["required"]) == {"id", "as_a", "i_want", "so_that", "priority", "criteria"}
    criterion = story["properties"]["criteria"]["items"]
    assert set(criterion["required"]) == {"id", "given", "when", "then", "source"}
    assert STORIES_SCHEMA["properties"]["stories"]["maxItems"] == MAX_STORIES


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("join words with single hyphens", True),
        ("  JOIN words\nwith   single hyphens ", True),
        ("the text and join", True),
        ("join words with one hyphen", False),
        ("", False),
        ("  \n ", False),
        ("hyphens are single", False),
    ],
)
def test_a_fragment_is_a_normalised_piece_of_the_normalised_idea(quote, expected):
    assert is_fragment(quote, IDEA) is expected
    assert normalise(" A\tB \n c ") == "a b c"


def test_the_shared_quote_helpers_agree_with_the_story_gate():
    from antstreet.roles.stories import MIN_SOURCE_CHARS, fragment_problem, is_quote_of

    good, short, invented = "join words with single hyphens", "hyphens", "strip every emoji first"
    assert is_quote_of(good, IDEA) and fragment_problem(good, IDEA) is None
    assert is_quote_of("JOIN  words\nwith single hyphens", IDEA)
    assert not is_quote_of(short, IDEA)
    assert fragment_problem(short, IDEA) == f"must quote at least {MIN_SOURCE_CHARS} characters"
    assert not is_quote_of(invented, IDEA)
    assert fragment_problem(invented, IDEA) == (
        "is not a fragment of the idea: 'strip every emoji first'"
    )
    for quote in (good, short, invented, ""):
        assert is_quote_of(quote, IDEA) is (fragment_problem(quote, IDEA) is None)


# Measured on 16 real product-manager drafts: nine in ten rejected quotes were the idea's own
# words with its Markdown backticks dropped or turned into quote marks, or two verbatim pieces
# joined with "...". Neither changes what the idea says.
MARKDOWN_IDEA = (
    "1. `width` below 1 raises `ValueError`, whatever the text is (even empty text).\n"
    "2. Durations are added: `1h30m` is 5400 seconds and `1m5ms` is 60.005 seconds.\n"
    '3. `add("0.1", "0.2")` is `"0.3"`; `\' "a"\'` (a space before the quote makes the\n'
    "   field unquoted) and a bare quote are errors."
)


@pytest.mark.parametrize(
    "quote",
    [
        "width below 1 raises ValueError, whatever the text is (even empty text)",
        "'1h30m' is 5400 seconds",
        "\u201c1h30m\u201d is 5400 seconds",
        'add("0.1", "0.2") is "0.3"',
        "add(0.1, 0.2) is 0.3",
        "`width` below 1 raises `ValueError`",
    ],
)
def test_a_quote_may_drop_or_change_the_ideas_backticks_and_quote_marks(quote):
    from antstreet.roles.stories import MIN_SOURCE_CHARS, is_fragment

    assert is_fragment(quote, MARKDOWN_IDEA, min_chars=MIN_SOURCE_CHARS)


@pytest.mark.parametrize(
    "quote",
    [
        "width below 2 raises ValueError",
        "width under 1 raises ValueError",
        "1h30m is 5401 seconds",
        "add(0.1, 0.2) is 0.30",
    ],
)
def test_a_changed_word_or_number_is_still_not_a_fragment(quote):
    from antstreet.roles.stories import is_fragment

    assert not is_fragment(quote, MARKDOWN_IDEA)


def test_a_quote_may_elide_text_when_every_piece_is_word_for_word_and_in_order():
    from antstreet.roles.stories import is_fragment, quote_pieces

    elided = "a space before the quote makes the field unquoted ... are errors"
    assert quote_pieces(elided) == [
        "a space before the quote makes the field unquoted",
        "are errors",
    ]
    assert is_fragment(elided, MARKDOWN_IDEA)
    assert is_fragment("width below 1 \u2026 whatever the text is", MARKDOWN_IDEA)
    assert not is_fragment("are errors ... a space before the quote", MARKDOWN_IDEA)  # order
    assert not is_fragment("width below 1 ... raises KeyError", MARKDOWN_IDEA)  # one piece invented
    assert not is_fragment(
        "width below 1 ... is", MARKDOWN_IDEA
    )  # a piece too short to mean anything
    assert not is_fragment("...", MARKDOWN_IDEA) and quote_pieces(" ... ") == []


def test_a_word_for_word_quote_of_an_idea_holding_a_literal_ellipsis_is_a_fragment():
    # Found in a benchmark run: the wildcard idea says "`[...]` is a set." and a role quoted it
    # exactly; split on the "..." it became "[" and "] is a set.", and "[" is too short.
    idea = "`*` matches any run. `[...]` is a set. `?` matches one character."
    assert is_fragment("`[...]` is a set.", idea, min_chars=8)
    assert not is_fragment("`[...]` is a list.", idea, min_chars=8)  # still word for word
    assert not is_fragment("[...]", idea, min_chars=8)  # still long enough to mean something


def test_the_story_gate_accepts_those_quotes_and_still_refuses_an_invented_one():
    data = changed(["stories", 0, "criteria", 0, "source"], "join words with SINGLE hyphens")
    assert problems(data) == []
    data = changed(
        ["stories", 0, "criteria", 0, "source"], "Lower-case the text ... single hyphens"
    )
    assert problems(data) == []
    data = changed(["stories", 0, "criteria", 0, "source"], "Lower-case the text ... drop emoji")
    assert problems(data) == [
        "S1.1: source is not a fragment of the idea: 'Lower-case the text ... drop emoji'"
    ]
    short = changed(["stories", 0, "criteria", 0, "source"], "a ... b")
    assert problems(short) == ["S1.1: source must quote at least 8 characters"]
