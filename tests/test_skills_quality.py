"""Quality bar for every skill shipped, including the ones other engineers add later. A skill is
paid for on every call that loads it, so it earns its place or it fails here.

The rules live in `skills_support.py` as functions over skills, so each is tested on a bad skill
made for the purpose as well as on the shipped ones: a rule that never fires proves nothing."""

import pytest
from skills_support import (
    BANNED_PHRASES,
    MAX_COMBINED_CHARS,
    combined_problems,
    duplicate_problems,
    shipped,
    skill_problems,
    usage_problems,
    users,
)

from boss.skills import MAX_SKILL_CHARS, Skill, SkillError, all_skill_ids, load_skill, parse_skill


def skill(text: str, name: str = "x", description: str = "d") -> Skill:
    return Skill(f"owner/{name}", 1, description, text)


def test_every_shipped_skill_parses_and_passes_the_bar():
    assert all_skill_ids(), "no skills shipped"
    for skill_id in all_skill_ids():
        loaded = load_skill(skill_id)  # raises SkillError for a bad header or an oversized body
        assert loaded.id == skill_id and loaded.version >= 1
        assert skill_problems(loaded) == []


def test_a_header_that_does_not_parse_is_refused_before_the_bar_is_applied():
    with pytest.raises(SkillError, match="header"):
        parse_skill("owner/x", "no header here")


def test_a_skill_over_the_size_limit_is_named():
    assert skill_problems(skill("x" * MAX_SKILL_CHARS)) == []
    assert "over 4000" in skill_problems(skill("x" * (MAX_SKILL_CHARS + 1)))[0]


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_each_banned_phrase_is_caught_in_any_case_and_only_as_whole_words(phrase):
    assert skill_problems(skill(f"Trace the code. {phrase.upper()} and stop.")) != []
    assert skill_problems(skill(f"Start: {phrase}, then stop.")) != []
    assert skill_problems(skill(f"a{phrase}z is not the phrase")) == []


def test_the_banned_list_is_short_and_lowercase():
    assert len(BANNED_PHRASES) <= 8 and all(p == p.lower() for p in BANNED_PHRASES)


def test_no_two_shipped_skills_share_a_body_or_a_description():
    assert duplicate_problems(shipped()) == []


def test_duplicate_bodies_and_descriptions_are_caught_ignoring_case_and_spacing():
    a, b = skill("Read the request.", "a", "One idea."), skill("read  the\nrequest.", "b", "Two.")
    assert duplicate_problems([a, b]) == ["owner/a and owner/b have the same text"]
    c = skill("Different.", "c", "one  IDEA.")
    assert duplicate_problems([a, c]) == ["owner/a and owner/c have the same description"]
    assert duplicate_problems([a, skill("Other.", "d", "Other.")]) == []


def test_every_shipped_skill_is_used_and_every_skill_named_exists():
    assert usage_problems(all_skill_ids(), users()) == []


def test_an_unused_skill_is_named_and_so_is_a_missing_one():
    ids = ["a/used", "a/unused"]
    assert usage_problems(ids, {"role:r": ("a/used",)}) == [
        "a/unused is used by no role and no profile: delete it or use it"
    ]
    assert usage_problems(ids, {"role:r": ("a/used", "a/unused"), "profile:p": ("a/gone",)}) == [
        "profile:p names a/gone, which is not shipped"
    ]


def test_the_skills_of_any_one_role_or_profile_stay_under_the_combined_limit():
    size = {skill_id: len(load_skill(skill_id).text) for skill_id in all_skill_ids()}
    assert combined_problems(users(), size) == []


def test_a_set_of_skills_over_the_combined_limit_is_named_and_the_limit_itself_is_allowed():
    half = MAX_COMBINED_CHARS // 2
    size = {"a/one": half, "a/two": half, "a/three": 1}
    assert combined_problems({"role:fits": ("a/one", "a/two")}, size) == []
    over = combined_problems({"role:big": ("a/one", "a/two", "a/three")}, size)
    assert over == [f"role:big carries {MAX_COMBINED_CHARS + 1} characters of skills, over 10000"]
