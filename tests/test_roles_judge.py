"""The judge: rubrics as data, one structured call, a gate that refuses a score with no quote, and
(below) the calibration that decides whether a person may act on its scores. No model calls: a
fake `claude` plays the model."""

import copy
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import replace

import pytest
from boss_init import BOSS_INIT_LINE

from boss.bench.table import wilson_interval
from boss.errors import Outcome
from boss.roles import registry
from boss.roles.base import RoleError, RoleOutputError, system_prompt
from boss.roles.judge import (
    ANCHOR_POINTS,
    JUDGE,
    JUDGE_SCHEMA,
    MIN_CASES,
    MIN_WEIGHTED_KAPPA,
    MIN_WITHIN_ONE,
    Calibration,
    CalibrationError,
    Case,
    CaseFileError,
    CaseResult,
    Judgement,
    RubricError,
    Score,
    UncalibratedJudgeError,
    all_rubric_ids,
    applies_to,
    bar_shortfalls,
    calibrate,
    judge_artifact,
    judge_identity,
    judge_prompt,
    load_cases,
    load_rubric,
    main,
    meets_bar,
    parse_cases,
    parse_rubric,
    render_calibration,
    render_judgement,
    require_calibrated,
    verdict_problems,
    weighted_kappa,
    write_template,
)
from boss.roles.stories import normalise
from boss.skills import load_skill
from boss.stream import Usage

ARTIFACT = (
    "As a shopper I want to see my cart total so that I know what I will pay.\n"
    "Given two items at $5 and $7, when I open the cart, then the total shows $12."
)
CONTEXT = "Idea: a shopping cart that shows the total price."
FAKE = f"""#!{sys.executable}
import json, os, sys
open(os.environ["FAKE_ARGV"], "w").write(json.dumps(sys.argv))
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
QUOTES = {
    "clarity": "As a shopper I want to see my cart total",
    "checkable": "Given two items at $5 and $7, when I open the cart",
    "faithful": "so that I know what I will pay",
    "complete": "then the total shows $12",
}


@pytest.fixture
def rubric():
    return load_rubric("stories")


def verdict(**over):
    data = {
        "scores": [
            {"criterion": name, "score": 4, "evidence": quote} for name, quote in QUOTES.items()
        ],
        "summary": "Clear and checkable.",
    }
    return data | over


def with_score(index, **fields):
    scores = copy.deepcopy(verdict()["scores"])
    scores[index] |= fields
    return {"scores": scores}


@pytest.fixture
def fake_cli(tmp_path):
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE)
    cli.chmod(0o755)
    argv_file = tmp_path / "argv.json"

    def run(output, *, rubric_id="stories", model="haiku", **kwargs):
        text = output if isinstance(output, str) else json.dumps(output)
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "FAKE_ARGV": str(argv_file)}
        env |= {"FAKE_OUTPUT": text}
        return judge_artifact(
            load_rubric(rubric_id),
            kwargs.pop("artifact", ARTIFACT),
            CONTEXT,
            env=env,
            model=model,
            executable=str(cli),
            **kwargs,
        )

    run.argv = lambda: json.loads(argv_file.read_text())
    return run


def ok(structured=None):
    return RESULT | {"structured_output": verdict() if structured is None else structured}


# --- rubrics ---------------------------------------------------------------------------------


def test_the_three_shipped_rubrics_load_with_three_to_five_anchored_criteria():
    assert all_rubric_ids() == ["demo", "stories", "usage"]
    for rubric_id in all_rubric_ids():
        rubric = load_rubric(rubric_id)
        assert (rubric.id, rubric.version) == (rubric_id, 1) and rubric.title
        assert 3 <= len(rubric.criteria) <= 5
        for criterion in rubric.criteria:
            assert len(criterion.anchors) == len(ANCHOR_POINTS) == 3
            assert len(set(criterion.anchors)) == 3 and "\n" not in criterion.question


def test_the_stories_rubric_has_the_criteria_its_title_promises():
    ids = [c.id for c in load_rubric("stories").criteria]
    assert ids == ["clarity", "checkable", "faithful", "complete"]


@pytest.mark.parametrize("bad", ["../stories", "stories/../x", "Stories", "s", "", "a.b", "a b"])
def test_a_rubric_id_cannot_name_a_file_outside_the_rubrics_folder(bad):
    with pytest.raises(RubricError):
        load_rubric(bad)


def test_a_missing_rubric_is_an_error_not_an_empty_one():
    with pytest.raises(RubricError, match="no rubric"):
        load_rubric("nonexistent")


def valid_rubric() -> dict:
    return {
        "id": "demo",
        "version": 2,
        "title": "A title",
        "criteria": [
            {
                "id": f"crit_{n}",
                "question": "Is it so?",
                "anchors": {"1": "bad", "3": "middling", "5": "good"},
            }
            for n in range(3)
        ],
    }


def broken(mutate) -> str:
    data = valid_rubric()
    mutate(data)
    return json.dumps(data)


def test_a_valid_rubric_parses():
    rubric = parse_rubric("demo", json.dumps(valid_rubric()))
    assert rubric.version == 2 and [c.id for c in rubric.criteria] == ["crit_0", "crit_1", "crit_2"]
    assert rubric.criteria[0].anchors == ("bad", "middling", "good")


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not json", "not valid JSON"),
        ("[]", "exactly id, version"),
        ('{"id": "demo", "id": "demo"}', "more than once"),
        (broken(lambda d: d.pop("title")), "exactly id, version"),
        (broken(lambda d: d.update(extra=1)), "exactly id, version"),
        (broken(lambda d: d.update(id="other")), "not the file's name"),
        (broken(lambda d: d.update(version=0)), "version"),
        (broken(lambda d: d.update(version=True)), "version"),
        (broken(lambda d: d.update(version="1")), "version"),
        (broken(lambda d: d.update(version=1.0)), "version"),
        (broken(lambda d: d.update(title="")), "title"),
        (broken(lambda d: d.update(title="a\nb")), "title"),
        (broken(lambda d: d.update(title=5)), "title"),
        (broken(lambda d: d.update(criteria=d["criteria"][:2])), "3 to 5 criteria"),
        (broken(lambda d: d.update(criteria=d["criteria"] * 2)), "3 to 5 criteria"),
        (broken(lambda d: d.update(criteria="x")), "3 to 5 criteria"),
        (broken(lambda d: d["criteria"].__setitem__(0, "x")), "each criterion"),
        (broken(lambda d: d["criteria"][0].pop("anchors")), "each criterion"),
        (broken(lambda d: d["criteria"][0].update(id="Bad Id")), "lower_snake_case"),
        (broken(lambda d: d["criteria"][0].update(id=3)), "lower_snake_case"),
        (broken(lambda d: d["criteria"][1].update(id="crit_0")), "appears twice"),
        (broken(lambda d: d["criteria"][0].update(question="")), "question"),
        (broken(lambda d: d["criteria"][0].update(question="a\nb")), "question"),
        (broken(lambda d: d["criteria"][0]["anchors"].pop("3")), "anchors must be exactly"),
        (broken(lambda d: d["criteria"][0]["anchors"].update({"2": "x"})), "anchors must be"),
        (broken(lambda d: d["criteria"][0]["anchors"].update({"5": " "})), "needs text"),
        (broken(lambda d: d["criteria"][0]["anchors"].update({"5": 5})), "needs text"),
    ],
)
def test_a_malformed_rubric_is_an_error_naming_the_problem(raw, message):
    with pytest.raises(RubricError, match=message):
        parse_rubric("demo", raw)


def test_the_judge_is_a_quality_role_reporting_to_the_boss_and_off_by_default():
    found = registry()["judge"]
    assert found is JUDGE and found.department == "quality" and found.reports_to == "boss"
    assert found.default_on is False and found.actor == "role:judge"
    assert "fragment of the artifact" in found.gate


def test_the_judge_skills_are_shipped_short_and_named_in_its_system_prompt():
    assert 2 <= len(JUDGE.skills) <= 3
    prompt = system_prompt(JUDGE)
    for skill_id in JUDGE.skills:
        skill = load_skill(skill_id)
        assert len(skill.text) < 4000 and skill.text in prompt
    assert "known-judge-biases" in JUDGE.skills[1]
    for word in ("Position bias", "Verbosity bias", "Self-preference bias"):
        assert word in prompt


def test_the_prompt_demands_a_quote_for_every_score():
    assert "A score without a quote is invalid" in system_prompt(JUDGE)


# --- the call --------------------------------------------------------------------------------


def test_the_call_has_no_tools_the_judge_prompt_and_the_rubric_context_and_artifact(
    fake_cli, rubric
):
    judgement, usage = fake_cli(ok())
    argv = fake_cli.argv()
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--system-prompt") + 1] == system_prompt(JUDGE)
    assert json.loads(argv[argv.index("--json-schema") + 1]) == JUDGE_SCHEMA
    assert argv[argv.index("--max-budget-usd") + 1] == "0.15"
    assert argv[argv.index("--model") + 1] == "haiku" and "--safe-mode" in argv
    prompt = argv[-1]
    assert prompt == judge_prompt(rubric, ARTIFACT, CONTEXT)
    assert f"<artifact>\n{ARTIFACT}\n</artifact>" in prompt
    assert (
        prompt.index("Criterion clarity") < prompt.index("<context>") < prompt.index("<artifact>")
    )
    assert f"<context>\n{CONTEXT}\n</context>" in prompt
    for criterion in rubric.criteria:
        assert f"Criterion {criterion.id}: {criterion.question}" in prompt
        assert all(anchor in prompt for anchor in criterion.anchors)
    assert usage == Usage(12_300, 100, 50, 7)
    assert judgement.model == "haiku" and judgement.prompt == "judge_v1.md"


def test_a_good_output_becomes_a_judgement_in_the_rubrics_order_with_its_mean(fake_cli, rubric):
    shuffled = verdict(scores=list(reversed(verdict()["scores"])))
    judgement, _ = fake_cli(ok(shuffled))
    assert [s.criterion for s in judgement.scores] == [c.id for c in rubric.criteria]
    assert judgement.scores[0] == Score("clarity", 4, QUOTES["clarity"])
    assert (judgement.rubric_id, judgement.rubric_version) == ("stories", 1)
    assert judgement.mean == 4.0 and judgement.summary == "Clear and checkable."
    assert judgement.calibrated is False


def test_the_summary_is_trimmed(fake_cli):
    judgement, _ = fake_cli(ok(verdict(summary="  Clear and checkable.\n")))
    assert judgement.summary == "Clear and checkable."


def test_the_mean_is_the_mean_of_the_scores(fake_cli):
    scores = verdict()["scores"]
    for score, value in zip(scores, (1, 2, 5, 5), strict=True):
        score["score"] = value
    judgement, _ = fake_cli(ok(verdict(scores=scores)))
    assert judgement.mean == 13 / 4


def test_evidence_may_differ_from_the_artifact_in_case_and_line_breaks_only(fake_cli):
    scores = verdict()["scores"]
    scores[0]["evidence"] = "AS A SHOPPER   I want\nto see my cart total"
    judgement, _ = fake_cli(ok(verdict(scores=scores)))
    assert judgement.scores[0].evidence.startswith("AS A SHOPPER")


@pytest.mark.parametrize(
    ("output", "outcome"),
    [
        (
            RESULT | {"is_error": True, "api_error_status": 401, "terminal_reason": "api_error"},
            Outcome.LOGIN,
        ),
        ("not json at all", Outcome.CRASHED),
    ],
)
def test_a_failed_call_raises_a_role_error_with_its_outcome(fake_cli, output, outcome):
    with pytest.raises(RoleError) as info:
        fake_cli(output)
    assert info.value.outcome is outcome and not isinstance(info.value, RoleOutputError)


@pytest.mark.parametrize(
    ("artifact", "context"), [("", CONTEXT), ("  \n", CONTEXT), (ARTIFACT, ""), (ARTIFACT, " ")]
)
def test_an_empty_artifact_or_context_is_refused_before_any_call(rubric, artifact, context):
    with pytest.raises(ValueError, match="must both be text"):
        judge_artifact(
            rubric, artifact, context, env={}, model="haiku", executable="/no/such/binary"
        )


@pytest.mark.parametrize("model", ["", "-x", "--dangerously-skip-permissions"])
def test_a_model_that_reads_as_a_flag_is_refused_before_any_call(rubric, model):
    with pytest.raises(ValueError, match="model"):
        judge_artifact(rubric, ARTIFACT, CONTEXT, env={}, model=model, executable="/no/such/binary")


# --- the gate --------------------------------------------------------------------------------


def test_a_verdict_that_follows_the_rules_has_no_problems(rubric):
    assert verdict_problems(rubric, ARTIFACT, verdict()) == []


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (verdict(summary=""), "summary is missing"),
        (verdict(summary="  "), "summary is missing"),
        (verdict(summary=None), "summary is missing"),
        (verdict(summary=["x"]), "summary is missing"),
        ({"summary": "x"}, "scores is not a list"),
        ({"summary": "x", "scores": "text"}, "scores is not a list"),
        ({"summary": "x", "scores": {"clarity": 4}}, "scores is not a list"),
        (verdict(scores=verdict()["scores"][:3]), "criteria not scored: complete"),
        (verdict(scores=[]), "criteria not scored: checkable, clarity, complete, faithful"),
        (
            verdict(
                scores=verdict()["scores"]
                + [{"criterion": "style", "score": 3, "evidence": "As a shopper I want"}]
            ),
            "score 5: not a criterion of stories: 'style'",
        ),
        (
            verdict(scores=verdict()["scores"] + [verdict()["scores"][0]]),
            "clarity: scored more than once",
        ),
        (verdict(scores=["clarity"] + verdict()["scores"][1:]), "score 1 is not an object"),
        (with_score(0, criterion=None), "score 1: not a criterion"),
        (with_score(0, criterion=7), "score 1: not a criterion"),
        (with_score(0, score=0), "clarity: score must be an integer from 1 to 5, got 0"),
        (with_score(0, score=6), "clarity: score must be an integer from 1 to 5, got 6"),
        (with_score(0, score=-1), "score must be an integer"),
        (with_score(0, score=3.0), "got 3.0"),
        (with_score(0, score=3.5), "got 3.5"),
        (with_score(0, score="3"), "got '3'"),
        (with_score(0, score=True), "got True"),
        (with_score(0, score=False), "got False"),
        (with_score(0, score=None), "got None"),
        (with_score(0, evidence=""), "clarity: evidence must quote at least 8"),
        (with_score(0, evidence="   \n "), "clarity: evidence must quote at least 8"),
        (with_score(0, evidence="As a"), "clarity: evidence must quote at least 8"),
        (with_score(0, evidence=None), "clarity: evidence must quote at least 8"),
        (with_score(0, evidence=["As a shopper I want"]), "clarity: evidence must quote"),
        (
            with_score(0, evidence="a fragment the artifact never contained"),
            "clarity: evidence is not a fragment of the artifact",
        ),
        (with_score(0, evidence="As a shopper ... my cart total"), "evidence is not a fragment"),
        (
            with_score(0, evidence="As a shopper I want to see my cart total. Given"),
            "evidence is not a fragment",
        ),
    ],
)
def test_every_class_of_bad_output_is_named_by_the_gate(rubric, data, message):
    data = {"summary": "s"} | data
    assert any(message in p for p in verdict_problems(rubric, ARTIFACT, data)), message


@pytest.mark.parametrize("data", [None, "text", 5, ["scores"], [{"criterion": "clarity"}]])
def test_output_that_is_not_an_object_fails_the_gate(rubric, data):
    assert verdict_problems(rubric, ARTIFACT, data) == ["output is not an object"]


def test_a_score_with_no_evidence_is_never_accepted_even_when_every_number_is_right(
    fake_cli,
):
    scores = verdict()["scores"]
    scores[2]["evidence"] = "text that appears nowhere in the artifact at all"
    with pytest.raises(RoleOutputError) as info:
        fake_cli(ok(verdict(scores=scores)))
    assert info.value.problems == [
        "faithful: evidence is not a fragment of the artifact: "
        "'text that appears nowhere in the artifact at all'"
    ]
    assert info.value.usage.cost_micros == 12_300  # the call was paid for


def test_a_failed_gate_lists_every_problem_and_keeps_the_cost(fake_cli):
    scores = verdict()["scores"][:2]
    scores[0]["score"] = 9
    with pytest.raises(RoleOutputError) as info:
        fake_cli(ok(verdict(scores=scores, summary="")))
    assert len(info.value.problems) == 3
    assert info.value.outcome is Outcome.COMPLETED and info.value.usage.cost_micros == 12_300


def test_gate_messages_never_carry_control_characters_from_the_model(rubric):
    data = verdict() | {
        "scores": [{"criterion": "x\x1b[31m", "score": "\x1b]0;t\x07", "evidence": "\x1b[2J"}]
    }
    text = "\n".join(verdict_problems(rubric, ARTIFACT, data))
    assert "\x1b" not in text and "\x07" not in text


def test_normalise_is_public_and_folds_case_and_whitespace_only():
    assert normalise("  A  b\nC\t") == "a b c"
    assert normalise("") == ""


# --- rendering and the calibration rule -------------------------------------------------------


def judgement(**over) -> Judgement:
    fields = {
        "rubric_id": "stories",
        "rubric_version": 1,
        "model": "haiku",
        "prompt": "judge_v1.md",
        "scores": (Score("clarity", 4, "a quote"), Score("checkable", 2, "another")),
        "summary": "A summary.",
    }
    return Judgement(**fields | over)


def test_an_uncalibrated_judgement_says_so_in_words_in_every_rendering():
    text = render_judgement(judgement())
    assert "uncalibrated" in text.splitlines()[0] and "advisory" in text
    assert "stories v1 by haiku: mean 3.0 of 5" in text
    assert '  clarity: 4  "a quote"' in text and "summary: A summary." in text


def test_a_calibrated_judgement_does_not_say_uncalibrated():
    text = render_judgement(judgement(calibrated=True))
    assert "uncalibrated" not in text and "calibrated" in text.splitlines()[0]


def test_rendering_flattens_and_cuts_model_text_and_hides_control_characters():
    long = "word " * 100
    text = render_judgement(
        judgement(
            scores=(Score("clarity", 4, "line one\nline two\x1b[31m " + long),), summary="a\nb"
        )
    )
    assert "\x1b" not in text and len(text.splitlines()) == 3
    assert "line one line two" in text and "[cut]" in text


def test_require_calibrated_refuses_an_uncalibrated_judgement_with_a_clear_reason():
    with pytest.raises(UncalibratedJudgeError, match="stories v1.*haiku.*uncalibrated.*advisory"):
        require_calibrated(judgement())


def test_require_calibrated_returns_a_calibrated_judgement_unchanged():
    calibrated = judgement(calibrated=True)
    assert require_calibrated(calibrated) is calibrated


def test_a_judgement_from_the_judge_is_uncalibrated_unless_something_says_otherwise(fake_cli):
    judgement_, _ = fake_cli(ok())
    with pytest.raises(UncalibratedJudgeError):
        require_calibrated(judgement_)


# --- kappa, by hand --------------------------------------------------------------------------
# Every table below is (person score -> judge score: count), so a reader can redo the sums.
# kappa = 1 - observed / expected; observed = mean squared difference over the pairs, expected =
# sum over person score i and judge score j of (person count of i) * (judge count of j) * (i - j)^2,
# divided by n^2.


def test_kappa_is_one_for_perfect_agreement():
    # 1->1, 2->2, 3->3, 5->5: observed 0
    assert weighted_kappa([(1, 1), (2, 2), (3, 3), (5, 5)]) == 1.0
    assert weighted_kappa([(1, 1), (1, 1), (5, 5)]) == 1.0


def test_kappa_is_zero_at_chance_level():
    # 1->1, 1->3, 3->1, 3->3. observed = (0+4+4+0)/4 = 2.
    # person {1: 2, 3: 2}, judge {1: 2, 3: 2}: expected = (2*2*4 + 2*2*4)/16 = 2. kappa = 0.
    assert weighted_kappa([(1, 1), (1, 3), (3, 1), (3, 3)]) == 0.0


def test_kappa_is_minus_one_when_the_judge_reverses_the_scale():
    # 1->5, 5->1. observed = 16. person {1: 1, 5: 1}, judge {5: 1, 1: 1}:
    # expected = (1*1*16 + 1*1*16)/4 = 8. kappa = 1 - 16/8 = -1.
    assert weighted_kappa([(1, 5), (5, 1)]) == -1.0


def test_a_systematic_offset_of_one_point_costs_kappa_but_keeps_it_positive():
    # 1->2, 2->3, 3->4, 4->5. observed = 1. person {1,2,3,4}, judge {2,3,4,5}, one each:
    # sum over i,j of (i-j)^2 = 30 + 14 + 6 + 6 = 56, expected = 56/16 = 3.5. kappa = 1 - 1/3.5.
    assert weighted_kappa([(1, 2), (2, 3), (3, 4), (4, 5)]) == pytest.approx(5 / 7)


def test_kappa_is_quadratically_weighted_not_plain_agreement():
    # 1->1, 1->2, 5->5, 5->4. observed = (0+1+0+1)/4 = 0.5. person {1: 2, 5: 2},
    # judge {1: 1, 2: 1, 4: 1, 5: 1}: for person 1 the sum of count*(i-j)^2 is 0+1+9+16 = 26,
    # for person 5 it is 16+9+1+0 = 26, so expected = (2*26 + 2*26)/16 = 6.5. kappa = 1 - 0.5/6.5.
    # Unweighted kappa on the same pairs is 1/3: near misses would be punished like far ones.
    assert weighted_kappa([(1, 1), (1, 2), (5, 5), (5, 4)]) == pytest.approx(12 / 13)


def test_a_far_miss_costs_more_than_a_near_one_with_the_same_number_of_exact_matches():
    near = weighted_kappa([(1, 1), (3, 3), (5, 5), (2, 3)])
    far = weighted_kappa([(1, 1), (3, 3), (5, 5), (2, 5)])
    assert near is not None and far is not None and near > far


@pytest.mark.parametrize(
    "pairs",
    [
        [],
        [(3, 3), (3, 3), (3, 3)],  # both raters constant: 0/0
        [(3, 1), (3, 3), (3, 5), (3, 3)],  # the person is constant: the formula would give 0
        [(1, 3), (3, 3), (5, 3), (3, 3)],  # the judge is constant: the formula would give 0
        [(2, 4)],
    ],
)
def test_kappa_is_none_when_either_rater_used_a_single_score(pairs):
    # Perfect agreement on one score, or a judge that always says 3, shows nothing about whether
    # the judge separates good from bad: undefined, and never at or above any threshold.
    assert weighted_kappa(pairs) is None


# --- figures and calibrate -------------------------------------------------------------------
# Two criteria, six cases. Rows are (person, judge):
#   a: (1,1) (2,2) (3,4) (4,5) (5,5) (3,1)   differences judge-person 0 0 +1 +1 0 -2
#   b: (2,3) (2,3) (4,4) (4,5) (1,1) (5,5)   differences             +1 +1 0 +1 0 0
# a: exact 3, within one 5, mean diff 0. b: exact 3, within one 6, mean diff +0.5.
# overall: exact 6 of 12, within one 11 of 12, mean diff 3/12 = 0.25.
# kappa a: observed 1, expected 168/36, so 1 - 3/14 = 11/14. kappa b: observed 0.5, expected
# 150/36, so 1 - 0.12 = 0.88. Overall: observed 9/12; person counts {1:2, 2:3, 3:2, 4:3, 5:2},
# judge counts {1:3, 2:1, 3:2, 4:2, 5:4}, expected = 636/144, so 1 - 108/636 = 44/53.
HUMAN_A, JUDGE_A = [1, 2, 3, 4, 5, 3], [1, 2, 4, 5, 5, 1]
HUMAN_B, JUDGE_B = [2, 2, 4, 4, 1, 5], [3, 3, 4, 5, 1, 5]


def hand_calibration(**over):
    results = tuple(
        CaseResult(f"c{i}", {"a": ha, "b": hb}, {"a": ja, "b": jb})
        for i, (ha, hb, ja, jb) in enumerate(zip(HUMAN_A, HUMAN_B, JUDGE_A, JUDGE_B, strict=True))
    )
    return replace(good_identity(results), **over)


def good_identity(results, **over):
    prompt, skills = judge_identity()
    fields = {
        "rubric_id": "stories",
        "rubric_version": 1,
        "model": "haiku",
        "prompt": prompt,
        "skills": skills,
        "cases_sha": "ab" * 32,
        "results": tuple(results),
    }
    return Calibration(**fields | over)


def test_the_figures_match_the_hand_worked_values():
    cal = hand_calibration()
    a, b = cal.per_criterion["a"], cal.per_criterion["b"]
    assert (a.pairs, a.compared, a.exact, a.within_one, a.mean_diff) == (6, 6, 3, 5, 0.0)
    assert (b.pairs, b.compared, b.exact, b.within_one, b.mean_diff) == (6, 6, 3, 6, 0.5)
    assert a.kappa == pytest.approx(11 / 14) and b.kappa == pytest.approx(0.88)
    o = cal.overall
    assert (o.pairs, o.compared, o.exact, o.within_one, o.mean_diff) == (12, 12, 6, 11, 0.25)
    assert o.kappa == pytest.approx(44 / 53)
    assert (o.exact_rate, o.within_one_rate) == (0.5, 11 / 12)
    assert (cal.cases, cal.failed, cal.criteria) == (6, 0, ("a", "b"))


def test_a_judge_that_scores_higher_than_the_person_has_a_positive_mean_difference():
    cal = good_identity([CaseResult("c", {"a": 2, "b": 2}, {"a": 4, "b": 3})])
    assert cal.overall.mean_diff == 1.5
    low = good_identity([CaseResult("c", {"a": 4, "b": 4}, {"a": 3, "b": 3})])
    assert low.overall.mean_diff == -1.0


def case_for(name, scores, rubric="stories"):
    return Case(name, rubric, f"artifact {name}", "context", scores)


def judgement_of(scores):
    return Judgement(
        "stories", 1, "haiku", "judge_v1.md",
        tuple(Score(c, s, "evidence") for c, s in scores.items()), "s",
    )  # fmt: skip


def test_calibrate_runs_the_judge_on_every_case_and_records_both_sets_of_scores(rubric):
    cases = [
        case_for("x", {"clarity": 4, "checkable": 2}),
        case_for("y", {"clarity": 1, "checkable": 5}),
    ]
    seen = []

    def judge_fn(case):
        seen.append(case.id)
        return judgement_of({"clarity": 3, "checkable": 2})

    cal = calibrate(cases, judge_fn, rubric=rubric, model="haiku", cases_sha="s" * 64)
    assert seen == ["x", "y"]
    assert cal.results == (
        CaseResult("x", {"clarity": 4, "checkable": 2}, {"clarity": 3, "checkable": 2}),
        CaseResult("y", {"clarity": 1, "checkable": 5}, {"clarity": 3, "checkable": 2}),
    )
    assert (cal.rubric_id, cal.rubric_version, cal.model) == ("stories", 1, "haiku")
    assert (cal.prompt, cal.skills) == judge_identity() and cal.cases_sha == "s" * 64
    assert cal.skills == ("judge/anchored-scoring@1", "judge/known-judge-biases@1")


def test_failed_judge_calls_are_counted_reported_and_never_agreement(rubric):
    cases = [case_for(str(n), {"clarity": 3, "checkable": 3}) for n in range(4)]

    def judge_fn(case):
        if case.id == "1":
            raise RoleError("judge", "boom", Outcome.TIMEOUT, Usage(None, 0, 0, 0))
        if case.id == "2":
            raise RoleOutputError(
                "judge", ["clarity: evidence is not a fragment"], Usage(1, 0, 0, 0)
            )
        return judgement_of({"clarity": 3, "checkable": 3})

    cal = calibrate(cases, judge_fn, rubric=rubric, model="haiku", cases_sha="s")
    assert (cal.cases, cal.failed) == (4, 2)
    assert [r.judge is None for r in cal.results] == [False, True, True, False]
    assert "boom" in cal.results[1].failure and "not a fragment" in cal.results[2].failure
    o = cal.overall
    assert (o.pairs, o.compared, o.exact, o.within_one) == (8, 4, 4, 4)
    assert o.exact_rate == 0.5 and o.within_one_rate == 0.5  # 4 of 8 pairs, not 4 of 4
    assert o.mean_diff == 0.0 and o.kappa is None  # only the compared pairs, all constant


def test_when_every_call_fails_nothing_agrees_and_nothing_is_undefined_by_accident(rubric):
    def judge_fn(case):
        raise RoleError("judge", "down", Outcome.CRASHED, Usage(None, 0, 0, 0))

    cal = calibrate(
        [case_for("x", {"clarity": 3, "checkable": 3})],
        judge_fn,
        rubric=rubric,
        model="m",
        cases_sha="s",
    )
    o = cal.overall
    assert (o.pairs, o.compared, o.exact, o.within_one) == (2, 0, 0, 0)
    assert o.mean_diff is None and o.kappa is None and cal.failed == 1
    assert not meets_bar(cal, min_cases=1, min_weighted_kappa=-1, min_within_one=0.0)


def test_a_judgement_of_the_wrong_criteria_is_a_failed_case(rubric):
    cal = calibrate(
        [case_for("x", {"clarity": 3, "checkable": 3})],
        lambda case: judgement_of({"clarity": 3}),
        rubric=rubric,
        model="m",
        cases_sha="s",
    )
    assert cal.failed == 1 and "other criteria" in cal.results[0].failure


def test_a_bug_in_the_judge_function_is_not_swallowed_as_a_failed_case(rubric):
    def judge_fn(case):
        raise KeyError("a bug")

    with pytest.raises(KeyError):
        calibrate(
            [case_for("x", {"clarity": 3})], judge_fn, rubric=rubric, model="m", cases_sha="s"
        )


def test_calibrate_refuses_no_cases_and_cases_of_another_rubric(rubric):
    with pytest.raises(ValueError, match="no cases"):
        calibrate([], lambda case: judgement_of({}), rubric=rubric, model="m", cases_sha="s")
    with pytest.raises(ValueError, match="rubric 'usage'"):
        calibrate(
            [case_for("x", {"a": 1}, rubric="usage")],
            lambda case: judgement_of({}),
            rubric=rubric,
            model="m",
            cases_sha="s",
        )


# --- the bar ---------------------------------------------------------------------------------


def bar_calibration(n=20, failed=0, **over):
    """n cases over four criteria; the judge is within one point almost always and not exact."""
    results = []
    for i in range(n):
        human = {c: (i + k) % 5 + 1 for k, c in enumerate(CRITERIA)}
        judge = {
            c: min(5, max(1, s + (1 if (i + k) % 3 == 0 else 0)))
            for k, (c, s) in enumerate(human.items())
        }
        results.append(
            CaseResult(f"c{i}", human, None if i < failed else judge, "down" if i < failed else "")
        )
    return good_identity(results, **over)


CRITERIA = ("clarity", "checkable", "faithful", "complete")


def test_the_thresholds_are_named_constants_with_the_documented_starting_values():
    assert (MIN_CASES, MIN_WEIGHTED_KAPPA, MIN_WITHIN_ONE) == (20, 0.6, 0.8)


def test_a_good_calibration_meets_the_bar_and_lists_no_shortfalls():
    cal = bar_calibration()
    assert cal.overall.kappa is not None and 0.6 < cal.overall.kappa < 1.0
    assert 0.8 < cal.overall.within_one_rate <= 1.0 and cal.overall.exact_rate < 1.0
    assert meets_bar(cal) and bar_shortfalls(cal) == []


def test_meets_bar_at_the_case_count_boundary_counts_scored_cases_only():
    assert meets_bar(bar_calibration(n=20)) is True
    assert meets_bar(bar_calibration(n=19)) is False
    assert meets_bar(bar_calibration(n=21, failed=1)) is True  # 20 scored
    assert meets_bar(bar_calibration(n=20, failed=1)) is False  # 19 scored
    assert bar_shortfalls(bar_calibration(n=19)) == ["19 scored cases, needs 20"]
    assert meets_bar(bar_calibration(n=5), min_cases=5) is True
    assert meets_bar(bar_calibration(n=5), min_cases=6) is False


def test_meets_bar_at_the_kappa_boundary_is_inclusive():
    cal = bar_calibration()
    kappa = cal.overall.kappa
    assert meets_bar(cal, min_weighted_kappa=kappa) is True
    assert meets_bar(cal, min_weighted_kappa=math.nextafter(kappa, 2)) is False
    assert "weighted kappa" in bar_shortfalls(cal, min_weighted_kappa=1.0)[0]


def test_meets_bar_at_the_within_one_boundary_is_inclusive():
    cal = good_identity(
        [
            CaseResult(f"c{i}", {"a": 3, "b": 1 + i % 5}, {"a": 3 + (i % 2) * 2, "b": 1 + i % 5})
            for i in range(20)
        ]
    )
    rate = cal.overall.within_one_rate
    assert rate == 0.75 and cal.overall.kappa is not None
    assert meets_bar(cal, min_cases=20, min_weighted_kappa=-1.0, min_within_one=rate) is True
    assert meets_bar(cal, min_cases=20, min_weighted_kappa=-1.0, min_within_one=0.76) is False
    assert "within one point 75%, needs 76%" in bar_shortfalls(
        cal, min_weighted_kappa=-1.0, min_within_one=0.76
    )


def test_a_calibration_whose_kappa_is_undefined_never_meets_the_bar():
    always_three = good_identity(
        [CaseResult(f"c{i}", {"a": 1 + i % 5}, {"a": 3}) for i in range(20)]
    )
    assert always_three.overall.kappa is None and always_three.overall.within_one_rate == 0.6
    assert not meets_bar(always_three, min_within_one=0.0)
    assert "undefined" in bar_shortfalls(always_three, min_within_one=0.0)[0]


def test_failed_calls_pull_the_within_one_rate_down_until_the_bar_is_missed():
    assert meets_bar(bar_calibration(n=30, failed=3)) is True
    cal = bar_calibration(n=30, failed=12)
    assert cal.cases - cal.failed < MIN_CASES or not meets_bar(cal)
    heavy = bar_calibration(n=60, failed=20)  # 40 scored, but a third of all pairs failed
    assert heavy.overall.within_one_rate < 0.8 and not meets_bar(heavy)


# --- a calibration covers one judge ------------------------------------------------------------


def test_a_calibration_applies_to_its_own_rubric_version_model_prompt_and_skills(rubric):
    cal = bar_calibration()
    assert applies_to(cal, rubric, "haiku")
    assert not applies_to(cal, rubric, "sonnet")
    assert not applies_to(replace(cal, rubric_version=2), rubric, "haiku")
    assert not applies_to(replace(cal, rubric_id="usage"), rubric, "haiku")
    assert not applies_to(replace(cal, prompt="judge_v2.md"), rubric, "haiku")
    assert not applies_to(
        replace(cal, skills=("judge/anchored-scoring@2", cal.skills[1])), rubric, "haiku"
    )
    assert not applies_to(replace(cal, skills=cal.skills[:1]), rubric, "haiku")


def calibrated_call(fake_cli, calibration, **kwargs):
    return fake_cli(ok(), calibration=calibration, **kwargs)[0]


def test_a_judgement_is_calibrated_only_when_a_matching_calibration_meets_the_bar(fake_cli, rubric):
    good = bar_calibration()
    judged = calibrated_call(fake_cli, good)
    assert judged.calibrated is True and require_calibrated(judged) is judged
    assert "uncalibrated" not in render_judgement(judged)
    assert calibrated_call(fake_cli, None).calibrated is False
    assert calibrated_call(fake_cli, good, model="sonnet").calibrated is False
    bumped = replace(good, rubric_version=rubric.version + 1)
    assert calibrated_call(fake_cli, bumped).calibrated is False
    assert calibrated_call(fake_cli, replace(good, prompt="judge_v0.md")).calibrated is False
    assert calibrated_call(fake_cli, replace(good, skills=())).calibrated is False
    assert calibrated_call(fake_cli, bar_calibration(n=19)).calibrated is False  # too few cases
    weak = good_identity(
        [CaseResult(f"c{i}", {"a": 1 + i % 5}, {"a": 5 - i % 5}) for i in range(20)]
    )
    assert calibrated_call(fake_cli, weak).calibrated is False  # matches, but does not meet the bar
    with pytest.raises(UncalibratedJudgeError):
        require_calibrated(calibrated_call(fake_cli, replace(good, model="other")))


def test_a_calibration_for_a_different_rubric_does_not_calibrate_this_one(fake_cli):
    other = replace(bar_calibration(), rubric_id="usage")
    assert calibrated_call(fake_cli, other).calibrated is False


# --- saving and loading ----------------------------------------------------------------------


def test_a_calibration_survives_a_save_and_load_and_records_its_figures(tmp_path):
    cal = bar_calibration(n=22, failed=2)
    path = tmp_path / "cal.json"
    cal.save(path)
    assert Calibration.load(path) == cal
    saved = json.loads(path.read_text())
    assert saved["rubric_id"] == "stories" and saved["rubric_version"] == 1
    assert saved["prompt"] == "judge_v1.md" and saved["cases_sha"] == "ab" * 32
    assert saved["cases"] == 22 and saved["failed"] == 2
    assert saved["overall"]["kappa"] == cal.overall.kappa
    assert set(saved["per_criterion"]) == set(CRITERIA)
    assert saved["results"][0]["judge"] is None and saved["results"][0]["failure"] == "down"


def test_saving_never_replaces_an_earlier_calibration(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text("earlier")
    with pytest.raises(FileExistsError):
        bar_calibration().save(path)
    assert path.read_text() == "earlier"


def saved_data(tmp_path):
    path = tmp_path / "cal.json"
    bar_calibration(n=22, failed=2).save(path)
    return path, json.loads(path.read_text())


def rewrite(path, data):
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d: d.pop("model"), "format 1 calibration object"),
        (lambda d: d.update(format=2), "format 1"),
        (lambda d: d.update(extra=1), "format 1"),
        (lambda d: d.update(model=""), "must be text"),
        (lambda d: d.update(prompt=5), "must be text"),
        (lambda d: d.update(rubric_version=True), "rubric_version"),
        (lambda d: d.update(rubric_version=0), "rubric_version"),
        (lambda d: d.update(skills="x"), "skills"),
        (lambda d: d.update(skills=[1]), "skills"),
        (lambda d: d.update(results=[]), "non-empty list"),
        (lambda d: d.update(results="x"), "non-empty list"),
        (lambda d: d["results"][0].pop("failure"), "exactly case, human, judge, failure"),
        (lambda d: d["results"][2].update(case=d["results"][3]["case"]), "appears twice"),
        (lambda d: d["results"][2]["judge"].update(clarity=True), "integer from 1 to 5"),
        (lambda d: d["results"][2]["judge"].update(clarity=6), "integer from 1 to 5"),
        (lambda d: d["results"][2]["human"].update(clarity=0), "integer from 1 to 5"),
        (lambda d: d["results"][2]["human"].update(clarity=2.0), "integer from 1 to 5"),
        (lambda d: d["results"][2]["human"].pop("clarity"), "same criteria"),
        (lambda d: d["results"][2]["judge"].update(extra=3), "same criteria"),
        (lambda d: d["results"][2].update(failure="x"), "failure reason exactly when"),
        (lambda d: d["results"][0].update(failure=""), "failure reason exactly when"),
        (lambda d: d["overall"].update(kappa=0.99), "do not match the recorded scores"),
        (lambda d: d["overall"].update(within_one=d["overall"]["pairs"]), "do not match"),
        (lambda d: d["per_criterion"]["clarity"].update(exact=0), "do not match"),
        (lambda d: d.update(failed=0), "do not match"),
        (lambda d: d.update(cases=99), "do not match"),
    ],
)
def test_a_hand_edited_or_malformed_calibration_is_refused(tmp_path, edit, message):
    path, data = saved_data(tmp_path)
    edit(data)
    with pytest.raises(CalibrationError, match=message):
        Calibration.load(rewrite(path, data))


def test_an_unreadable_or_invalid_calibration_file_is_an_error(tmp_path):
    with pytest.raises(CalibrationError, match="cannot read"):
        Calibration.load(tmp_path / "none.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(CalibrationError, match="not valid JSON"):
        Calibration.load(bad)
    bad.write_text('{"format": 1, "format": 1}')
    with pytest.raises(CalibrationError, match="more than once"):
        Calibration.load(bad)
    bad.write_text("[]")
    with pytest.raises(CalibrationError, match="format 1"):
        Calibration.load(bad)


# --- the case files --------------------------------------------------------------------------


def case_line(**over):
    case = {
        "id": "one",
        "rubric": "stories",
        "artifact": "As a user I want it.",
        "context": "Idea: a thing",
        "scores": {"clarity": 4, "checkable": 3, "faithful": 5, "complete": 2},
    }
    return json.dumps(case | over)


def test_a_labelled_file_loads_into_cases_and_a_hash_of_its_bytes(tmp_path):
    path = tmp_path / "cases.jsonl"
    text = (
        case_line()
        + "\n\n"
        + case_line(id="two", scores={"complete": 1, "faithful": 2, "checkable": 3, "clarity": 4})
        + "\n"
    )
    path.write_bytes(text.encode())
    cases, sha = load_cases(path)
    assert [c.id for c in cases] == ["one", "two"] and cases[0].rubric == "stories"
    assert list(cases[1].scores) == ["clarity", "checkable", "faithful", "complete"]  # rubric order
    assert cases[0].artifact == "As a user I want it." and cases[0].context == "Idea: a thing"
    assert sha == hashlib.sha256(text.encode()).hexdigest()
    path.write_bytes(text.replace("one", "uno").encode())
    assert load_cases(path)[1] != sha


def test_a_file_with_windows_line_endings_loads(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_bytes((case_line() + "\r\n" + case_line(id="two") + "\r\n").encode())
    assert len(load_cases(path)[0]) == 2


def scored(**scores):
    return {"clarity": 4, "checkable": 3, "faithful": 5, "complete": 2} | scores


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        (["{not json"], r"line 1: not valid JSON"),
        (["[]"], r"line 1: must be an object with exactly"),
        (['"text"'], r"line 1: must be an object"),
        ([case_line(), '{"id": "a", "id": "b"}'], r"line 2: not valid JSON .*more than once"),
        ([json.dumps({"id": "x"})], r"line 1: must be an object with exactly"),
        ([case_line().replace("}}", '}, "extra": 1}')], r"line 1: must be an object with exactly"),
        ([case_line(rubric="nonexistent")], r"line 1: .*no rubric"),
        ([case_line(rubric=3)], r"line 1: rubric must be a rubric id"),
        ([case_line(rubric="../stories")], r"line 1: .*lower_snake_case"),
        (
            [case_line(), case_line(id="b", rubric="usage")],
            r"line 2: rubric 'usage' differs from 'stories'",
        ),
        ([case_line(id="")], r"line 1: id must be non-empty"),
        ([case_line(id=" a")], r"line 1: id must be non-empty"),
        ([case_line(id=4)], r"line 1: id must be non-empty"),
        ([case_line(), case_line()], r"line 2: id 'one' is already used on line 1"),
        ([case_line(artifact="")], r"line 1: artifact is empty"),
        ([case_line(artifact="  \n")], r"line 1: artifact is empty"),
        ([case_line(artifact=None)], r"line 1: artifact is empty"),
        ([case_line(context="")], r"line 1: context is empty; say what it is judged against"),
        ([case_line(scores=[1, 2])], r"line 1: scores must be an object"),
        ([case_line(scores=scored(style=3))], r"line 1: not criteria of stories: 'style'"),
        ([case_line(scores={"clarity": 4})], r"line 1: criterion 'checkable' is not scored yet"),
        (
            [case_line(scores=scored(complete=None))],
            r"line 1: criterion 'complete' is not scored yet",
        ),
        (
            [case_line(scores=scored(clarity=0))],
            r"line 1: 'clarity': must be an integer from 1 to 5, got 0",
        ),
        (
            [case_line(scores=scored(clarity=6))],
            r"line 1: 'clarity': must be an integer from 1 to 5, got 6",
        ),
        ([case_line(scores=scored(clarity=3.5))], r"line 1: 'clarity': must be an integer.*3.5"),
        ([case_line(scores=scored(clarity="4"))], r"line 1: 'clarity': must be an integer.*'4'"),
        ([case_line(scores=scored(clarity=True))], r"line 1: 'clarity': must be an integer.*True"),
        (["", "", case_line(context="")], r"line 3: context is empty"),
        ([case_line(), "", case_line(id="b", scores=scored(faithful=9))], r"line 3: 'faithful'"),
    ],
)
def test_every_malformed_case_line_is_an_error_naming_its_line(lines, message):
    with pytest.raises(CaseFileError, match=message):
        parse_cases("\n".join(lines) + "\n")


@pytest.mark.parametrize("text", ["", "\n\n", "   \n"])
def test_a_file_with_no_cases_is_an_error(text):
    with pytest.raises(CaseFileError, match="no cases"):
        parse_cases(text)


def test_load_cases_names_the_file_and_handles_unreadable_and_non_text_files(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(case_line(scores={"clarity": 4}) + "\n")
    with pytest.raises(CaseFileError, match=r"cases\.jsonl: line 1: criterion 'checkable'"):
        load_cases(path)
    with pytest.raises(CaseFileError, match="cannot read"):
        load_cases(tmp_path / "missing.jsonl")
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(CaseFileError, match="not UTF-8"):
        load_cases(path)


def test_the_template_has_one_unlabelled_case_per_artifact_and_asks_for_context_and_scores(
    tmp_path, rubric
):
    folder = tmp_path / "artifacts"
    folder.mkdir()
    (folder / "b.md").write_text('Second artifact, with "quotes" and unicode: \u00e9\n')
    (folder / "a.txt").write_text("First artifact.\nTwo lines.")
    (folder / ".hidden").write_text("skipped")
    (folder / "sub").mkdir()
    out = tmp_path / "cases.jsonl"
    assert write_template(rubric, folder, out) == 2
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in rows] == ["a.txt", "b.md"]
    assert rows[0] == {
        "id": "a.txt",
        "rubric": "stories",
        "artifact": "First artifact.\nTwo lines.",
        "context": "",
        "scores": {"clarity": None, "checkable": None, "faithful": None, "complete": None},
    }
    assert rows[1]["artifact"] == 'Second artifact, with "quotes" and unicode: \u00e9\n'
    with pytest.raises(CaseFileError, match=r"line 1: context is empty"):
        load_cases(out)  # an unlabelled template is not a labelled file
    rows[0]["context"] = rows[1]["context"] = "the idea"
    out.write_text("\n".join(json.dumps(r) for r in rows))
    with pytest.raises(CaseFileError, match=r"line 1: criterion 'clarity' is not scored yet"):
        load_cases(out)
    for row in rows:
        row["scores"] = dict.fromkeys(row["scores"], 3)
    out.write_text("\n".join(json.dumps(r) for r in rows))
    assert len(load_cases(out)[0]) == 2


def test_an_artifact_with_unicode_line_separators_stays_one_case(tmp_path, rubric):
    folder = tmp_path / "artifacts"
    folder.mkdir()
    text = "one\u2028two\x0bthree\x1cfour\x85five\u2029six"
    (folder / "a.txt").write_text(text, encoding="utf-8")
    out = tmp_path / "cases.jsonl"
    write_template(rubric, folder, out)
    row = json.loads(out.read_text(encoding="utf-8"))
    row["context"], row["scores"] = "idea", dict.fromkeys(row["scores"], 3)
    out.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    cases, _ = load_cases(out)
    assert [c.artifact for c in cases] == [text]


def test_the_template_never_overwrites_a_file_the_person_may_have_labelled(tmp_path, rubric):
    folder = tmp_path / "artifacts"
    folder.mkdir()
    (folder / "a.txt").write_text("text")
    out = tmp_path / "cases.jsonl"
    out.write_text("labelled by hand")
    with pytest.raises(CaseFileError, match="exists; not overwriting"):
        write_template(rubric, folder, out)
    assert out.read_text() == "labelled by hand"


def test_the_template_refuses_an_empty_folder_an_empty_file_and_a_binary_file(tmp_path, rubric):
    folder = tmp_path / "artifacts"
    folder.mkdir()
    with pytest.raises(CaseFileError, match="no artifact files"):
        write_template(rubric, folder, tmp_path / "o1.jsonl")
    (folder / "empty.txt").write_text(" \n")
    with pytest.raises(CaseFileError, match="empty.txt is empty"):
        write_template(rubric, folder, tmp_path / "o2.jsonl")
    (folder / "empty.txt").unlink()
    (folder / "bin.dat").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(CaseFileError, match="bin.dat is not UTF-8"):
        write_template(rubric, folder, tmp_path / "o3.jsonl")
    assert not list(tmp_path.glob("o*.jsonl"))


# --- the command line ------------------------------------------------------------------------

CLI_FAKE = """#!PYTHON
import json, sys
INIT_LINE = 'INITLINE'
spec = json.load(open("SPEC"))
print(INIT_LINE)
prompt = sys.argv[-1]
artifact = prompt.split("<artifact>\\n", 1)[1].rsplit("\\n</artifact>", 1)[0]
with open(spec["log"], "a") as log:
    log.write(json.dumps(sys.argv) + "\\n")
reply = spec["replies"].get(artifact)
if reply is None:
    print("not json at all")
else:
    print(json.dumps(spec["result"] | {"structured_output": reply}))
"""
N_CASES = 20


def human_scores(i):
    return {c: (i + k) % 5 + 1 for k, c in enumerate(CRITERIA)}


def artifact_of(i):
    return f"Story {i}: as a user I want feature {i} so that I gain value {i}."


def reply_for(i, scores=None):
    scores = human_scores(i) if scores is None else scores
    quote = f"as a user I want feature {i}"
    return {
        "scores": [{"criterion": c, "score": s, "evidence": quote} for c, s in scores.items()],
        "summary": "ok",
    }


@pytest.fixture
def cli_run(tmp_path, capsys):
    spec_path, log = tmp_path / "spec.json", tmp_path / "calls.jsonl"
    fake = tmp_path / "fake-claude"
    fake.write_text(
        CLI_FAKE.replace("PYTHON", sys.executable)
        .replace("SPEC", str(spec_path))
        .replace("INITLINE", BOSS_INIT_LINE)
    )
    fake.chmod(0o755)
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        "\n".join(
            json.dumps(
                {
                    "id": f"case{i}",
                    "rubric": "stories",
                    "artifact": artifact_of(i),
                    "context": "Idea: features",
                    "scores": human_scores(i),
                }
            )
            for i in range(N_CASES)
        )
        + "\n"
    )

    class Runner:
        out = tmp_path / "calibration.json"

        def __init__(self):
            self.cases, self.log, self.tmp = cases, log, tmp_path
            self.replies = {artifact_of(i): reply_for(i) for i in range(N_CASES)}

        def calls(self):
            return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []

        def __call__(self, *argv, environ=None):
            spec_path.write_text(
                json.dumps({"log": str(log), "result": RESULT, "replies": self.replies})
            )
            env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "BOSS_CLAUDE_BIN": str(fake)}
            code = main([str(a) for a in argv], environ=env if environ is None else environ)
            captured = capsys.readouterr()
            return code, captured.out, captured.err

    return Runner()


def test_a_dry_run_prints_the_calls_and_the_cost_ceiling_and_makes_none(cli_run):
    code, out, err = cli_run(
        "calibrate", "--cases", cli_run.cases, "--out", cli_run.out, "--dry-run"
    )
    assert code == 0 and err == ""
    assert "20 calls to model haiku" in out and "at most $3 in all" in out
    assert "cap: $0.15 a call" in out and "subscription billing" in out
    assert "dry run: no calls made" in out and "  case0\n" in out and "  case19" in out
    assert cli_run.calls() == [] and not cli_run.out.exists()


def test_the_ceiling_follows_the_model_and_the_number_of_cases(cli_run):
    cli_run.cases.write_text("\n".join(cli_run.cases.read_text().splitlines()[:3]) + "\n")
    code, out, _ = cli_run(
        "calibrate",
        "--cases",
        cli_run.cases,
        "--out",
        cli_run.out,
        "--dry-run",
        "--model",
        "sonnet",
    )
    assert code == 0 and "3 calls to model sonnet" in out and "at most $0.45 in all" in out


def test_a_calibration_run_makes_one_call_per_case_saves_and_reports(cli_run):
    code, out, err = cli_run("calibrate", "--cases", cli_run.cases, "--out", cli_run.out)
    assert code == 0 and err == ""
    calls = cli_run.calls()
    assert len(calls) == N_CASES
    assert all(
        c[c.index("--model") + 1] == "haiku" and c[c.index("--tools") + 1] == "" for c in calls
    )
    assert out.index("20 calls to model haiku") < out.index("case0: mean")  # ceiling first
    assert "spent $0.246 by the CLI's estimate" in out and f"wrote {cli_run.out}" in out
    assert "Meets the bar." in out and "| overall | 80/80 | 100% [95-100%]" in out
    saved = Calibration.load(cli_run.out)
    assert (saved.cases, saved.failed, saved.model) == (N_CASES, 0, "haiku")
    assert saved.cases_sha == hashlib.sha256(cli_run.cases.read_bytes()).hexdigest()
    assert saved.overall.exact == 80 and saved.overall.kappa == 1.0


def test_a_calibration_from_a_run_calibrates_the_judge_that_ran_and_no_other(cli_run, rubric):
    cli_run("calibrate", "--cases", cli_run.cases, "--out", cli_run.out, "--model", "sonnet")
    saved = Calibration.load(cli_run.out)
    assert applies_to(saved, rubric, "sonnet") and meets_bar(saved)
    assert not applies_to(saved, rubric, "haiku")
    assert [c[c.index("--model") + 1] for c in cli_run.calls()] == ["sonnet"] * N_CASES


def test_failed_calls_in_a_run_are_reported_and_counted_against_agreement(cli_run):
    for i in (3, 11):
        del cli_run.replies[artifact_of(i)]  # the fake prints text that is not JSON
    cli_run.replies[artifact_of(5)] = reply_for(5) | {"summary": ""}  # fails the gate
    code, out, err = cli_run("calibrate", "--cases", cli_run.cases, "--out", cli_run.out)
    assert code == 0 and err == ""
    assert "case3: failed" in out and "case11: failed" in out and "case5: failed" in out
    assert "cases 20, of which 3 failed" in out
    assert "Failed cases:" in out and "- case5: judge: output failed its gate: summary" in out
    saved = Calibration.load(cli_run.out)
    assert saved.failed == 3 and saved.overall.compared == 68 and saved.overall.exact == 68
    assert saved.overall.exact_rate == 68 / 80
    assert "Does not meet the bar" in out and "17 scored cases, needs 20" in out


def test_the_run_refuses_an_existing_output_before_spending_anything(cli_run):
    cli_run.out.write_text("earlier calibration")
    code, out, err = cli_run("calibrate", "--cases", cli_run.cases, "--out", cli_run.out)
    assert code == 1 and "cannot write" in err and out == ""
    assert cli_run.calls() == [] and cli_run.out.read_text() == "earlier calibration"
    code, _, err = cli_run(
        "calibrate", "--cases", cli_run.cases, "--out", cli_run.tmp / "no" / "dir.json"
    )
    assert code == 1 and "cannot write" in err and cli_run.calls() == []


def test_a_bad_cases_file_stops_the_run_before_any_call(cli_run):
    lines = cli_run.cases.read_text().splitlines()
    lines[6] = lines[6].replace('"context": "Idea: features"', '"context": ""')
    cli_run.cases.write_text("\n".join(lines) + "\n")
    code, out, err = cli_run("calibrate", "--cases", cli_run.cases, "--out", cli_run.out)
    assert code == 1 and "line 7: context is empty" in err and "cases.jsonl" in err
    assert cli_run.calls() == [] and out == ""


def test_the_claude_binary_override_is_used_and_a_missing_binary_is_a_failed_case_not_a_crash(
    cli_run,
):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(cli_run.tmp), "BOSS_CLAUDE_BIN": "/no/such/claude"}
    cli_run.cases.write_text("\n".join(cli_run.cases.read_text().splitlines()[:2]) + "\n")
    code, out, _ = cli_run("calibrate", "--cases", cli_run.cases, "--out", cli_run.out, environ=env)
    assert code == 0 and "cases 2, of which 2 failed" in out and "cannot run" in out
    assert "plus 2 calls of unknown cost" in out and cli_run.calls() == []


def test_the_template_command_writes_a_template_and_show_prints_a_calibration(cli_run):
    folder = cli_run.tmp / "artifacts"
    folder.mkdir()
    (folder / "one.md").write_text("Some artifact text.")
    out = cli_run.tmp / "template.jsonl"
    code, stdout, _ = cli_run(
        "template", "--rubric", "stories", "--artifacts", folder, "--out", out
    )
    assert code == 0 and f"wrote 1 unlabelled cases to {out}" in stdout
    assert json.loads(out.read_text())["id"] == "one.md"
    code, _, err = cli_run("template", "--rubric", "stories", "--artifacts", folder, "--out", out)
    assert code == 1 and "not overwriting" in err
    code, _, err = cli_run(
        "template",
        "--rubric",
        "nonexistent",
        "--artifacts",
        folder,
        "--out",
        cli_run.tmp / "t2.jsonl",
    )
    assert code == 1 and "no rubric" in err
    code, _, err = cli_run(
        "template",
        "--rubric",
        "stories",
        "--artifacts",
        cli_run.tmp / "nope",
        "--out",
        cli_run.tmp / "t3.jsonl",
    )
    assert code == 1 and "error:" in err

    bar_calibration().save(cli_run.out)
    code, shown, _ = cli_run("show", cli_run.out)
    assert code == 0 and "Calibration of stories v1 with model haiku" in shown
    assert "| criterion | pairs |" in shown and "Meets the bar." in shown
    code, _, err = cli_run("show", cli_run.tmp / "missing.json")
    assert code == 1 and "cannot read" in err


def test_the_module_runs_as_a_program(cli_run):
    bar_calibration().save(cli_run.out)
    done = subprocess.run(
        [sys.executable, "-m", "boss.roles.judge", "show", str(cli_run.out)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert done.returncode == 0 and "Meets the bar." in done.stdout


# --- rendering a calibration ------------------------------------------------------------------


def test_the_calibration_report_states_intervals_the_bar_and_its_own_limits():
    text = render_calibration(hand_calibration())
    low, high = wilson_interval(6, 12)
    assert f"| overall | 12/12 | 50% [{low * 100:.0f}-{high * 100:.0f}%] |" in text
    assert "| a | 6/6 |" in text and "| b | 6/6 |" in text
    assert "+0.25 | 0.83 |" in text and "| 0.79 |" in text  # overall and criterion a kappa
    assert "a starting point and not a claim about the right values" in text
    assert "Does not meet the bar: 6 scored cases, needs 20" in text
    assert "not independent" in text and "abababababab" in text  # the hash prefix
    assert "prompt judge_v1.md; skills judge/anchored-scoring@1, judge/known-judge-biases@1" in text


def test_the_report_marks_criteria_below_the_bar_and_lists_failures():
    results = [
        CaseResult(f"c{i}", {"a": 1 + i % 5, "b": 1 + i % 5}, {"a": 1 + i % 5, "b": 5 - i % 5})
        for i in range(20)
    ]
    results.append(CaseResult("odd\x1b[31m", {"a": 3, "b": 3}, None, "call\nfailed"))
    text = render_calibration(good_identity(results))
    assert "| a |" in text and "| b (below bar) |" in text
    assert "Failed cases:" in text and "- odd\\x1b[31m: call failed" in text
    assert (
        "\x1b" not in text and "of which 1 failed: a failed case counts against agreement" in text
    )


def test_a_calibration_that_meets_the_bar_says_so_plainly():
    assert "Meets the bar." in render_calibration(bar_calibration())
    assert "Does not meet" not in render_calibration(bar_calibration())
