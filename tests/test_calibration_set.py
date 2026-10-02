"""The hand-labelling set under bench/calibration/ stays loadable by the judge's own loader and in
step with the rubrics. A rubric edit that adds, drops or renames a criterion fails here, so the set
is never found stale only after the person has spent an hour labelling it.

The files ship UNLABELLED (every score null). A null is filled with a stand-in before loading, so
the real `parse_cases` still checks everything else; once the owner labels a file its real scores
are checked the same way.
"""

import json
from pathlib import Path

import pytest

from boss.roles.judge import MIN_CASES, all_rubric_ids, load_rubric, parse_cases

ROOT = Path(__file__).resolve().parents[1] / "bench" / "calibration"
USED_BY_PIPELINE = ("stories", "usage")  # the rubrics boss.pipeline judges with


def raw_lines(rubric_id: str) -> list[str]:
    return (ROOT / rubric_id / "cases.jsonl").read_text(encoding="utf-8").splitlines()


def with_stand_in_scores(rubric_id: str) -> str:
    out = []
    for line in raw_lines(rubric_id):
        case = json.loads(line)
        case["scores"] = {k: 3 if v is None else v for k, v in case["scores"].items()}
        out.append(json.dumps(case, ensure_ascii=False))
    return "\n".join(out)


def test_every_rubric_the_pipeline_uses_has_a_set():
    assert set(USED_BY_PIPELINE) <= set(all_rubric_ids())
    for rubric_id in USED_BY_PIPELINE:
        assert (ROOT / rubric_id / "cases.jsonl").is_file(), f"no calibration set for {rubric_id}"


@pytest.mark.parametrize("rubric_id", USED_BY_PIPELINE)
def test_the_set_loads_with_the_judges_own_loader(rubric_id):
    cases = parse_cases(with_stand_in_scores(rubric_id))
    # fewer scored cases than MIN_CASES can never meet the bar, so the set must hold at least that
    assert len(cases) >= MIN_CASES
    assert {c.rubric for c in cases} == {rubric_id}


@pytest.mark.parametrize("rubric_id", USED_BY_PIPELINE)
def test_every_case_scores_exactly_the_rubrics_criteria_in_order(rubric_id):
    wanted = [c.id for c in load_rubric(rubric_id).criteria]
    for line in raw_lines(rubric_id):
        case = json.loads(line)
        assert list(case["scores"]) == wanted, f"{case['id']}: criteria differ from the rubric"


@pytest.mark.parametrize("rubric_id", USED_BY_PIPELINE)
def test_every_score_is_empty_or_a_whole_number_from_1_to_5(rubric_id):
    for line in raw_lines(rubric_id):
        for name, value in json.loads(line)["scores"].items():
            assert value is None or (type(value) is int and 1 <= value <= 5), name


@pytest.mark.parametrize("rubric_id", USED_BY_PIPELINE)
def test_the_set_holds_nothing_personal(rubric_id):
    text = (ROOT / rubric_id / "cases.jsonl").read_text(encoding="utf-8")
    for marker in ("/Users/", "/home/", "@gmail", "@outlook", "C:\\Users"):
        assert marker not in text


def test_the_manifest_describes_exactly_the_cases_and_the_spread_is_wide():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == set(USED_BY_PIPELINE)
    for rubric_id in USED_BY_PIPELINE:
        ids = [json.loads(line)["id"] for line in raw_lines(rubric_id)]
        assert sorted(manifest[rubric_id]) == sorted(ids)
        criteria = {c.id for c in load_rubric(rubric_id).criteria}
        kinds = set()
        for entry in manifest[rubric_id].values():
            assert entry["origin"] in {"real", "hand-written"}
            weak = set(entry["weak"].split(",")) - {"none"}
            assert weak <= criteria, f"{entry['weak']} names a criterion the rubric lacks"
            kinds.add(entry["kind"].split("-")[0])
        # clearly good, clearly bad, borderline, adversarial: the scale is spanned on purpose
        assert {"good", "bad", "borderline", "adversarial"} <= kinds
