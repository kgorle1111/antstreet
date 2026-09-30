"""The judge: rubrics as data, one structured call, a gate that refuses a score with no quote, and
(below) the calibration that decides whether a person may act on its scores. No model calls: a
fake `claude` plays the model."""

import copy
import json
import sys

import pytest

from boss.errors import Outcome
from boss.roles import registry
from boss.roles.base import RoleError, RoleOutputError, system_prompt
from boss.roles.judge import (
    ANCHOR_POINTS,
    JUDGE,
    JUDGE_SCHEMA,
    Judgement,
    RubricError,
    Score,
    UncalibratedJudgeError,
    all_rubric_ids,
    judge_artifact,
    judge_prompt,
    load_rubric,
    parse_rubric,
    render_judgement,
    require_calibrated,
    verdict_problems,
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
