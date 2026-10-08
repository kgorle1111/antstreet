"""The hand-labelling set under bench/calibration/ stays loadable by the judge's own loader and in
step with the rubrics. A rubric edit that adds, drops or renames a criterion fails here, so the set
is never found stale only after the person has spent an hour labelling it.

The files ship UNLABELLED (every score null). A null is filled with a stand-in before loading, so
the real `parse_cases` still checks everything else; once the owner labels a file its real scores
are checked the same way.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from antstreet.roles.judge import MIN_CASES, all_rubric_ids, load_rubric, parse_cases

ROOT = Path(__file__).resolve().parents[1] / "bench" / "calibration"
USED_BY_PIPELINE = ("stories", "usage")  # the rubrics antstreet.pipeline judges with


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


# --- the scoring helper -------------------------------------------------------------------------


def load_scorer():
    spec = importlib.util.spec_from_file_location("calibration_score", ROOT / "score.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def two_case_copy(tmp_path: Path) -> Path:
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(raw_lines("stories")[:2]) + "\n", encoding="utf-8")
    return path


def feeder(answers: list[str]):
    asked: list[str] = []
    it = iter(answers)

    def ask(prompt: str) -> str:
        asked.append(prompt)
        return next(it)

    return ask, asked


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_the_scorer_writes_scores_the_loader_accepts_and_changes_nothing_else(tmp_path):
    path = two_case_copy(tmp_path)
    before = read(path)
    ask, asked = feeder(["x", "0", "6", "4", "3", "5", "2", "1", "1", "1", "1"])
    scored, total = load_scorer().score_file(path, ask=ask, out=lambda _: None)
    assert (scored, total) == (2, 2)
    assert asked[0].startswith("clarity") and len(asked) == 11  # 3 bad answers were re-asked
    after = read(path)
    assert after[0]["scores"] == {"clarity": 4, "checkable": 3, "faithful": 5, "complete": 2}
    for old, new in zip(before, after, strict=True):
        assert {k: v for k, v in new.items() if k != "scores"} == {
            k: v for k, v in old.items() if k != "scores"
        }
    assert len(parse_cases(path.read_text(encoding="utf-8"))) == 2  # fully labelled: loads as is


def test_quitting_keeps_finished_cases_and_drops_a_half_scored_one(tmp_path):
    path = two_case_copy(tmp_path)
    ask, _ = feeder(["4", "3", "5", "2", "5", "5", "q"])
    scored, total = load_scorer().score_file(path, ask=ask, out=lambda _: None)
    assert (scored, total) == (1, 2)
    assert all(v is None for v in read(path)[1]["scores"].values())


def test_redo_replaces_only_that_case_and_a_quit_keeps_its_old_scores(tmp_path):
    path = two_case_copy(tmp_path)
    scorer = load_scorer()
    ask, _ = feeder(["4", "3", "5", "2", "1", "1", "1", "1"])
    scorer.score_file(path, ask=ask, out=lambda _: None)
    first_id = read(path)[0]["id"]
    ask, _ = feeder(["q"])
    scorer.score_file(path, redo=first_id, ask=ask, out=lambda _: None)
    assert read(path)[0]["scores"]["clarity"] == 4
    ask, _ = feeder(["2", "2", "2", "2"])
    scorer.score_file(path, redo=first_id, ask=ask, out=lambda _: None)
    lines = read(path)
    assert set(lines[0]["scores"].values()) == {2} and set(lines[1]["scores"].values()) == {1}


def test_the_rubric_card_shows_every_question_and_anchor():
    rubric = load_rubric("usage")
    card = load_scorer().rubric_card(rubric)
    for criterion in rubric.criteria:
        assert criterion.question in card
        assert all(anchor in card for anchor in criterion.anchors)
