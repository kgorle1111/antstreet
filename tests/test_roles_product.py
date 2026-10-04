"""The product department: the product manager's call and gate, the deterministic coverage guard,
and the user agent's advisory review and its gate. No model calls: a fake `claude` plays the
model."""

import json
import re
import sys

import pytest
from boss_init import BOSS_INIT_LINE

from boss.boss import load_prompt
from boss.errors import Outcome
from boss.roles import registry
from boss.roles.base import RoleError, RoleOutputError, system_prompt
from boss.roles.product import (
    MAX_FINDINGS,
    PRODUCT_MANAGER,
    REVIEW_SCHEMA,
    USER_AGENT,
    Misread,
    Missing,
    ReviewError,
    StoryReview,
    parse_review,
    review_problems,
    review_stories,
    uncovered_fragments,
    write_stories,
)
from boss.roles.stories import STORIES_SCHEMA, parse_stories, story_problems
from boss.skills import all_skill_ids, load_skill
from boss.stream import Usage

IDEA = (
    "Create slugify.py with slugify(text, max_length=None).\n"
    "Lower-case the text and join words with single hyphens.\n"
    "If max_length is given, never cut a word in half."
)
FAKE = f"""#!{sys.executable}
import json, os, sys
open(os.environ["FAKE_ARGV"], "w").write(json.dumps(sys.argv))
open(os.environ["FAKE_ARGV"] + ".thinking", "w").write(os.environ.get("MAX_THINKING_TOKENS", "-"))
print({BOSS_INIT_LINE!r})
print(os.environ["FAKE_OUTPUT"])
"""
RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "terminal_reason": "completed",
    "total_cost_usd": 0.0123,
    "modelUsage": {"m": {"inputTokens": 100, "outputTokens": 50, "cacheReadInputTokens": 7}},
}
USAGE = Usage(12_300, 100, 50, 7)


def criterion(n: int, m: int, source: str) -> dict:
    return {
        "id": f"S{n}.{m}",
        "given": "some text",
        "when": "slugify is called",
        "then": "the slug is returned",
        "source": source,
    }


def story(n: int, *sources: str, priority: str = "must") -> dict:
    return {
        "id": f"S{n}",
        "as_a": "developer",
        "i_want": "a slug",
        "so_that": "I can build URLs",
        "priority": priority,
        "criteria": [criterion(n, m, s) for m, s in enumerate(sources, start=1)],
    }


GOOD = {
    "stories": [
        story(1, "join words with single hyphens", "never cut a word in half"),
    ],
    "out_of_scope": ["transliteration"],
    "open_questions": [],
}


def stories_from(idea_sources: list[str]):
    return parse_stories({"stories": [story(1, *idea_sources)]})


@pytest.fixture
def cli(tmp_path):
    exe = tmp_path / "fake-claude"
    exe.write_text(FAKE)
    exe.chmod(0o755)
    argv_file = tmp_path / "argv.json"

    class Cli:
        path = str(exe)
        calls = 0

        def env(self, output):
            text = output if isinstance(output, str) else json.dumps(output)
            return {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "FAKE_ARGV": str(argv_file),
                    "FAKE_OUTPUT": text}  # fmt: skip

        def argv(self):
            return json.loads(argv_file.read_text())

    return Cli()


def write(cli, structured, idea=IDEA, **kwargs):
    output = RESULT | {"structured_output": structured}
    return write_stories(idea, env=cli.env(output), model="haiku", executable=cli.path, **kwargs)


# --- the call ---------------------------------------------------------------------------------


def test_the_call_has_no_tools_the_roles_system_prompt_with_every_skill_and_the_schema(cli):
    write(cli, GOOD)
    argv = cli.argv()
    assert argv[argv.index("--tools") + 1] == ""
    system = argv[argv.index("--system-prompt") + 1]
    assert system == system_prompt(PRODUCT_MANAGER)
    for skill_id in PRODUCT_MANAGER.skills:
        assert load_skill(skill_id).text in system
    assert json.loads(argv[argv.index("--json-schema") + 1]) == STORIES_SCHEMA
    assert argv[argv.index("--model") + 1] == "haiku"
    assert argv[-1] == f"Idea:\n{IDEA}"


def test_a_good_output_is_parsed_gated_and_returned_with_the_usage(cli):
    stories, usage = write(cli, GOOD)
    assert story_problems(stories, IDEA) == []
    assert [c.id for c in stories.criteria()] == ["S1.1", "S1.2"]
    assert stories.out_of_scope == ("transliteration",)
    assert usage == USAGE


def test_the_thinking_budget_reaches_the_call(cli, tmp_path):
    write(cli, GOOD, thinking_tokens=0)
    assert (tmp_path / "argv.json.thinking").read_text() == "0"


@pytest.mark.parametrize("idea", ["", "  \n "])
def test_an_empty_idea_is_refused_before_any_call(idea):
    with pytest.raises(ValueError, match="idea"):
        write_stories(idea, env={}, model="haiku", executable="/no/such/binary")


def test_an_idea_that_starts_with_a_dash_is_not_mistaken_for_a_flag(cli):
    idea = "- Lower-case the text and join words with single hyphens."
    stories, _ = write(cli, {"stories": [story(1, "join words with single hyphens")]}, idea)
    assert stories.stories
    assert cli.argv()[-1] == f"Idea:\n{idea}"


# --- output that fails the gate ---------------------------------------------------------------


def fails(cli, structured) -> RoleOutputError:
    with pytest.raises(RoleOutputError) as info:
        write(cli, structured)
    assert info.value.usage == USAGE and info.value.outcome is Outcome.COMPLETED
    assert info.value.role == "product_manager"
    return info.value


@pytest.mark.parametrize(
    "structured",
    [
        {},
        {"stories": "S1"},
        {"stories": [{"id": "S1"}]},
        {"stories": [story(1, "join words with single hyphens") | {"criteria": "none"}]},
        {"stories": [story(1, "join words with single hyphens")], "out_of_scope": "nothing"},
    ],
)
def test_output_that_is_not_shaped_like_stories_raises_with_the_usage_kept(cli, structured):
    error = fails(cli, structured)
    assert len(error.problems) == 1 and "not shaped like stories" in error.problems[0]


def test_a_quote_that_is_not_in_the_idea_is_a_named_problem(cli):
    error = fails(cli, {"stories": [story(1, "join words with single hyphens", "strip all emoji")]})
    assert error.problems == ["S1.2: source is not a fragment of the idea: 'strip all emoji'"]


def test_a_paraphrase_of_the_idea_is_not_a_quote(cli):
    error = fails(cli, {"stories": [story(1, "words are joined by one hyphen")]})
    assert "S1.1: source is not a fragment of the idea" in error.problems[0]


def test_wrong_ids_are_named(cli):
    wrong = story(1, "join words with single hyphens", "never cut a word in half")
    wrong["id"] = "S2"
    wrong["criteria"][1]["id"] = "S1.7"
    error = fails(cli, {"stories": [wrong]})
    assert "story 1 must have id S1, has 'S2'" in error.problems
    assert "S2: criterion 2 must have id S1.2" in error.problems


def test_every_problem_is_listed_not_only_the_first(cli):
    bad = story(1, "invented requirement text", "join", priority="urgent")
    error = fails(cli, {"stories": [bad, story(2, "never cut a word in half", priority="should")]})
    assert error.problems == [
        "S1: priority must be one of must, should, could",
        "S1.1: source is not a fragment of the idea: 'invented requirement text'",
        "S1.2: source must quote at least 8 characters",
        "at least one story must have priority 'must'",
    ]
    assert str(error).count(";") == 3


# --- a call that failed -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("output", "outcome"),
    [
        (
            RESULT | {"is_error": True, "api_error_status": 401, "terminal_reason": "api_error"},
            Outcome.LOGIN,
        ),
        (
            RESULT | {"subtype": "error_max_budget_usd", "terminal_reason": "budget_exhausted"},
            Outcome.CAPPED,
        ),
    ],
)
def test_a_failed_call_raises_a_role_error_with_its_outcome_and_cost(cli, output, outcome):
    with pytest.raises(RoleError) as info:
        write_stories(IDEA, env=cli.env(output), model="haiku", executable=cli.path)
    assert type(info.value) is RoleError
    assert info.value.outcome is outcome and info.value.usage.cost_micros == 12_300


def test_a_call_that_returns_no_object_is_a_role_error_that_keeps_its_cost(cli):
    with pytest.raises(RoleError, match="no structured output") as info:
        write(cli, ["S1"])
    assert type(info.value) is RoleError and info.value.usage == USAGE


# --- the deterministic coverage guard ---------------------------------------------------------


LINE1 = "Create slugify.py with slugify(text, max_length=None)."
LINE2 = "Lower-case the text and join words with single hyphens."
LINE3 = "If max_length is given, never cut a word in half."


def test_the_sentences_no_criterion_quotes_are_returned_in_order():
    stories = stories_from(["join words with single hyphens"])
    assert uncovered_fragments(IDEA, stories) == [LINE1, LINE3]


def test_an_idea_with_nothing_in_it_has_nothing_uncovered():
    stories = stories_from(["join words with single hyphens"])
    assert uncovered_fragments("", stories) == []
    assert uncovered_fragments("  \n\n \t ", stories) == []


def test_with_no_criterion_every_sentence_is_uncovered():
    assert uncovered_fragments(IDEA, parse_stories({"stories": []})) == [LINE1, LINE2, LINE3]


def test_a_sentence_quoted_twice_is_covered_once_over_and_not_listed():
    stories = stories_from(["join words with single hyphens", "Lower-case the text"])
    assert uncovered_fragments(IDEA, stories) == [LINE1, LINE3]


def test_a_sentence_written_twice_in_the_idea_is_covered_at_both_places():
    idea = "Never cut a word in half. Sort the words. Never cut a word in half."
    assert uncovered_fragments(idea, stories_from(["never cut a word in half"])) == [
        "Sort the words."
    ]


def test_a_quote_spanning_two_sentences_covers_both_and_no_third():
    idea = "Cut at the last hyphen. The result never ends with a hyphen. Raise ValueError below 1."
    stories = stories_from(["last hyphen. The result never ends"])
    assert uncovered_fragments(idea, stories) == ["Raise ValueError below 1."]


def test_a_quote_that_ends_where_a_sentence_ends_does_not_cover_the_next_one():
    stories = stories_from(["join words with single hyphens."])
    assert uncovered_fragments(IDEA, stories) == [LINE1, LINE3]


def test_a_quote_is_matched_ignoring_case_and_line_breaks():
    idea = "If max_length is given,\nnever cut a word in half. Sort them."
    stories = stories_from(["IF max_length   is given, NEVER cut a word\nin half."])
    assert uncovered_fragments(idea, stories) == ["Sort them."]


def test_a_source_too_short_or_not_in_the_idea_covers_nothing():
    stories = stories_from(["hyphens", "strip every emoji character"])
    assert uncovered_fragments(IDEA, stories) == [LINE1, LINE2, LINE3]


def test_a_numbered_list_marker_stays_with_its_item_and_items_split_at_sentence_ends():
    idea = "1. Accented letters become ASCII. Everything is lowercased.\n2) Runs become a hyphen."
    stories = stories_from(["Everything is lowercased."])
    assert uncovered_fragments(idea, stories) == [
        "1. Accented letters become ASCII.",
        "2) Runs become a hyphen.",
    ]


def test_code_like_lines_are_whole_fragments_and_never_cut():
    idea = (
        "It has one function:\n"
        "\n"
        "    slugify(text: str, max_length: int | None = None) -> str\n"
        "\n"
        "```python\n"
        "x = slugify('a. b')\n"
        "```\n"
        "Version 1.5 is fine."
    )
    assert uncovered_fragments(idea, stories_from(["Version 1.5 is fine."])) == [
        "It has one function:",
        "slugify(text: str, max_length: int | None = None) -> str",
        "x = slugify('a. b')",
    ]
    covered = stories_from(["slugify(text: str, max_length: int | None"])
    assert "slugify(text: str, max_length: int | None = None) -> str" not in uncovered_fragments(
        idea, covered
    )


def test_lines_with_no_letters_and_fence_lines_are_not_reported():
    idea = "---\n42\n1.\n```\n```\nNever cut a word in half."
    assert uncovered_fragments(idea, stories_from(["never cut a word in half"])) == []


def test_a_quote_reaching_across_a_line_break_covers_both_lines():
    stories = stories_from(["join words with single hyphens. If max_length is given,"])
    assert uncovered_fragments(IDEA, stories) == [LINE1]


def test_a_hard_wrapped_sentence_is_one_fragment_and_covered_by_a_quote_from_any_of_its_lines():
    idea = (
        "5. If `max_length` is given, cut the slug at the last hyphen such\nthat the result fits."
    )
    whole = (
        "5. If `max_length` is given, cut the slug at the last hyphen such that the result fits."
    )
    assert uncovered_fragments(idea, stories_from(["nothing quoted here"])) == [whole]
    assert uncovered_fragments(idea, stories_from(["that the result fits"])) == []
    assert uncovered_fragments(idea, stories_from(["cut the slug at the last"])) == []


def test_bullets_blank_lines_and_code_end_a_paragraph():
    idea = "Intro text\n- first rule\n- second rule\n\nOuter text\n    code line\nTail text"
    assert uncovered_fragments(idea, stories_from(["second rule"])) == [
        "Intro text",
        "- first rule",
        "Outer text",
        "code line",
        "Tail text",
    ]


def test_question_and_exclamation_marks_end_sentences_like_full_stops():
    idea = "Is it empty? Return nothing! Then stop."
    assert uncovered_fragments(idea, stories_from(["Return nothing!"])) == [
        "Is it empty?",
        "Then stop.",
    ]


def test_tab_indented_lines_and_prose_after_a_closed_fence_are_told_apart():
    idea = "\tx = f('a. b')\n```\ny = 1. z\n```\nOne. Two."
    assert uncovered_fragments(idea, stories_from(["nothing quoted here"])) == [
        "x = f('a. b')",
        "y = 1. z",
        "One.",
        "Two.",
    ]


def test_the_idea_is_sent_without_its_surrounding_white_space(cli):
    write(cli, {"stories": [story(1, "join words with single hyphens")]}, f"\n  {IDEA}\n\n")
    assert cli.argv()[-1] == f"Idea:\n{IDEA}"


# --- the registry, the skills and the prompt --------------------------------------------------


def test_the_product_manager_is_registered_with_its_skills_shipped_and_loadable():
    spec = registry()["product_manager"]
    assert spec is PRODUCT_MANAGER
    assert (spec.department, spec.reports_to, spec.actor) == (
        "product",
        "boss",
        "role:product_manager",
    )
    assert spec.default_on is False and spec.gate and spec.purpose
    assert 2 <= len(spec.skills) <= 3
    for skill_id in spec.skills:
        assert skill_id in all_skill_ids()
        skill = load_skill(skill_id)
        assert skill.id == skill_id and skill.version >= 1 and skill.text


def test_the_prompt_states_the_grounding_rule():
    prompt = load_prompt(PRODUCT_MANAGER.prompt)
    assert "word for word" in prompt and "does not belong" in prompt


def test_the_prompts_worked_example_passes_the_gate_it_teaches():
    prompt = load_prompt(PRODUCT_MANAGER.prompt)
    idea = re.search(r'^Idea: "(.*)"$', prompt, re.M)[1]
    example = json.loads(re.search(r"```json\n(.*?)\n```", prompt, re.S)[1])
    stories = parse_stories(example)
    assert story_problems(stories, idea) == []
    assert uncovered_fragments(idea, stories) == []


# --- the user agent ---------------------------------------------------------------------------

STORIES = parse_stories(GOOD)
MISSING = {"quote": "Lower-case the text", "why": "no criterion checks lower-casing"}
MISREAD = {
    "criterion": "S1.2",
    "quote": "If max_length is given, never cut a word in half",
    "why": "the criterion cuts a word",
}
REVISE = {"missing": [MISSING], "misread": [MISREAD], "verdict": "revise"}
ACCEPT = {"missing": [], "misread": [], "verdict": "accept"}


def review(cli, structured, idea=IDEA, stories=STORIES):
    output = RESULT | {"structured_output": structured}
    return review_stories(idea, stories, env=cli.env(output), model="haiku", executable=cli.path)


def review_fails(cli, structured) -> RoleOutputError:
    with pytest.raises(RoleOutputError) as info:
        review(cli, structured)
    assert info.value.usage == USAGE and info.value.outcome is Outcome.COMPLETED
    assert info.value.role == "user_agent"
    return info.value


def test_the_review_call_has_no_tools_both_skills_the_schema_and_the_idea_with_the_stories(cli):
    review(cli, ACCEPT)
    argv = cli.argv()
    assert argv[argv.index("--tools") + 1] == ""
    system = argv[argv.index("--system-prompt") + 1]
    assert system == system_prompt(USER_AGENT)
    for skill_id in USER_AGENT.skills:
        assert load_skill(skill_id).text in system
    assert json.loads(argv[argv.index("--json-schema") + 1]) == REVIEW_SCHEMA
    idea_part, stories_part = argv[-1].split("\n\nStories:\n")
    assert idea_part == f"Idea:\n{IDEA}"
    assert json.loads(stories_part) == STORIES.to_data()


def test_a_review_with_findings_is_parsed_gated_and_returned_with_the_usage(cli):
    got, usage = review(cli, REVISE)
    assert got == StoryReview((Missing(**MISSING),), (Misread(**MISREAD),), "revise")
    assert got.to_data() == REVISE and parse_review(got.to_data()) == got
    assert usage == USAGE


def test_a_review_with_no_findings_is_accepted(cli):
    got, _ = review(cli, ACCEPT)
    assert got == StoryReview((), (), "accept")


def test_the_review_call_sends_the_idea_without_surrounding_white_space(cli):
    review(cli, ACCEPT, f"\n {IDEA}\n\n")
    assert cli.argv()[-1].startswith(f"Idea:\n{IDEA}\n\nStories:\n")


def test_the_review_leaves_the_stories_as_they_were(cli):
    before = STORIES.to_data()
    review(cli, REVISE)
    assert STORIES.to_data() == before


@pytest.mark.parametrize("idea", ["", " \n"])
def test_an_empty_idea_is_refused_before_a_review_call(idea):
    with pytest.raises(ValueError, match="idea"):
        review_stories(idea, STORIES, env={}, model="haiku", executable="/no/such/binary")


@pytest.mark.parametrize(
    "structured",
    [
        {},
        {"missing": [], "misread": []},
        {"missing": "none", "misread": [], "verdict": "accept"},
        {"missing": [{"quote": "Lower-case the text"}], "misread": [], "verdict": "revise"},
        {"missing": [], "misread": [{"quote": "x", "why": "y"}], "verdict": "revise"},
        {"missing": [], "misread": [None], "verdict": "revise"},
        {"missing": [], "misread": [], "verdict": 1},
        {"missing": [MISSING | {"why": None}], "misread": [], "verdict": "revise"},
    ],
)
def test_output_that_is_not_shaped_like_a_review_raises_with_the_usage_kept(cli, structured):
    error = review_fails(cli, structured)
    assert len(error.problems) == 1 and "not shaped like a story review" in error.problems[0]


def test_a_quote_that_is_not_in_the_idea_is_named_in_either_list(cli):
    invented = "strip every emoji character"
    error = review_fails(
        cli,
        {
            "missing": [MISSING | {"quote": invented}],
            "misread": [MISREAD | {"quote": invented}],
            "verdict": "revise",
        },
    )
    assert error.problems == [
        f"missing 1: quote is not a fragment of the idea: {invented!r}",
        f"misread 1: quote is not a fragment of the idea: {invented!r}",
    ]


def test_a_quote_from_the_stories_rather_than_the_idea_is_refused(cli):
    error = review_fails(
        cli, ACCEPT | {"missing": [MISSING | {"quote": "words are joined"}], "verdict": "revise"}
    )
    assert "missing 1: quote is not a fragment" in error.problems[0]


def test_a_quote_too_short_to_mean_anything_is_refused(cli):
    error = review_fails(
        cli, ACCEPT | {"missing": [MISSING | {"quote": "text"}], "verdict": "revise"}
    )
    assert error.problems == ["missing 1: quote must be at least 8 characters"]


def test_a_criterion_that_does_not_exist_is_named(cli):
    error = review_fails(
        cli, {"missing": [], "misread": [MISREAD | {"criterion": "S9.1"}], "verdict": "revise"}
    )
    assert error.problems == ["misread 1: there is no criterion 'S9.1'"]


def test_an_empty_why_is_refused(cli):
    error = review_fails(cli, ACCEPT | {"missing": [MISSING | {"why": "  "}], "verdict": "revise"})
    assert error.problems == ["missing 1: why is empty"]


@pytest.mark.parametrize(
    ("structured", "count"),
    [
        (REVISE | {"verdict": "accept"}, 2),
        (ACCEPT | {"verdict": "revise"}, 0),
        (ACCEPT | {"missing": [MISSING], "verdict": "accept"}, 1),
    ],
)
def test_a_verdict_that_disagrees_with_the_findings_is_refused(cli, structured, count):
    [problem] = review_fails(cli, structured).problems
    assert problem.endswith(
        f"with {count} findings; it must be 'revise' exactly when there is at least one"
    )


def test_a_verdict_outside_the_two_words_is_refused(cli):
    error = review_fails(cli, ACCEPT | {"verdict": "approve"})
    assert error.problems == ["verdict must be one of accept, revise, is 'approve'"]


def test_the_number_of_findings_is_bounded_across_both_lists(cli):
    many = {
        "missing": [MISSING] * (MAX_FINDINGS - 1),
        "misread": [MISREAD] * 2,
        "verdict": "revise",
    }
    assert review_fails(cli, many).problems == [
        f"at most {MAX_FINDINGS} findings in all, has {MAX_FINDINGS + 1}"
    ]
    exactly = many | {"misread": [MISREAD]}
    assert review(cli, exactly)[0].verdict == "revise"


def test_every_problem_in_a_review_is_listed_not_only_the_first(cli):
    error = review_fails(
        cli,
        {
            "missing": [MISSING | {"quote": "not in the idea at all"}, MISSING | {"why": ""}],
            "misread": [MISREAD | {"criterion": "S3.1", "quote": "abc"}],
            "verdict": "accept",
        },
    )
    assert error.problems == [
        "missing 1: quote is not a fragment of the idea: 'not in the idea at all'",
        "missing 2: why is empty",
        "misread 1: there is no criterion 'S3.1'",
        "misread 1: quote must be at least 8 characters",
        "verdict is 'accept' with 3 findings; it must be 'revise' exactly when there is at "
        "least one",
    ]
    assert "; ".join(error.problems) in str(error)


@pytest.mark.parametrize(
    ("output", "outcome"),
    [
        (
            RESULT | {"is_error": True, "api_error_status": 401, "terminal_reason": "api_error"},
            Outcome.LOGIN,
        ),
        (
            RESULT | {"subtype": "error_max_budget_usd", "terminal_reason": "budget_exhausted"},
            Outcome.CAPPED,
        ),
    ],
)
def test_a_failed_review_call_raises_a_role_error_with_its_outcome_and_cost(cli, output, outcome):
    with pytest.raises(RoleError) as info:
        review_stories(IDEA, STORIES, env=cli.env(output), model="haiku", executable=cli.path)
    assert type(info.value) is RoleError and info.value.role == "user_agent"
    assert info.value.outcome is outcome and info.value.usage.cost_micros == 12_300


def test_the_gate_is_pure_code_over_data():
    assert review_problems(StoryReview((), (), "accept"), IDEA, STORIES) == []
    assert review_problems(StoryReview((), (), "revise"), IDEA, STORIES) != []
    with pytest.raises(ReviewError):
        parse_review(None)


def test_the_schema_asks_for_everything_the_parser_needs():
    assert set(REVIEW_SCHEMA["required"]) == {"missing", "misread", "verdict"}
    props = REVIEW_SCHEMA["properties"]
    assert set(props["missing"]["items"]["required"]) == {"quote", "why"}
    assert set(props["misread"]["items"]["required"]) == {"criterion", "quote", "why"}
    assert props["verdict"]["enum"] == ["accept", "revise"]
    assert props["missing"]["maxItems"] == props["misread"]["maxItems"] == MAX_FINDINGS


def test_the_user_agent_is_registered_advisory_and_reports_to_the_product_manager():
    spec = registry()["user_agent"]
    assert spec is USER_AGENT
    assert (spec.department, spec.reports_to) == ("product", "product_manager")
    assert spec.actor == "role:user_agent" and spec.default_on is False
    assert "advisory" in spec.purpose and "advisory" in spec.gate
    assert 2 <= len(spec.skills) <= 3
    for skill_id in spec.skills:
        assert skill_id in all_skill_ids() and load_skill(skill_id).text


def test_the_user_agent_prompt_states_the_grounding_rule_and_the_verdict_rule():
    prompt = load_prompt(USER_AGENT.prompt)
    assert "word for word" in prompt and "does not belong" in prompt
    assert "if and only if" in prompt and "advisory" in prompt
    assert f"At most {MAX_FINDINGS} findings" in prompt  # the prompt says what the gate enforces
    assert MAX_FINDINGS == 8


def test_the_user_agent_prompts_worked_example_passes_the_gate_it_teaches():
    prompt = load_prompt(USER_AGENT.prompt)
    idea = re.search(r'^Idea: "(.*)"$', prompt, re.M)[1]
    example = json.loads(re.search(r"```json\n(.*?)\n```", prompt, re.S)[1])
    stories = parse_stories(
        {
            "stories": [
                story(
                    1, "reverses the order of the words, so 'a b c' gives 'c b a'", "Runs of spaces"
                )
            ]
        }
    )
    assert review_problems(parse_review(example), idea, stories) == []


def test_every_skill_of_both_roles_is_under_the_size_limit_and_versioned():
    for spec in (PRODUCT_MANAGER, USER_AGENT):
        for skill_id in spec.skills:
            skill = load_skill(skill_id)
            assert len(skill.text) < 4_000 and skill.version == 1 and skill.description
