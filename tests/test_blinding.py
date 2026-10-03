"""The agents under test are blind to the test. No text any model is given (prompts, skills,
rubrics) may say that it is being benchmarked, graded by checks it cannot see, or compared with
another arm: a worker that knows it is measured can optimise for the measurement, and only one arm
would be told."""

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "boss"
GIVEN_TO_MODELS = sorted(
    [*(SRC / "prompts").glob("*.md"), *(SRC / "skills").rglob("*.md"), *(SRC / "rubrics").glob("*")]
)
TELLS = re.compile(
    r"bench(mark)?|hidden (check|test)|graded by|\barm\b|single[- ]agent|"
    r"evaluat(ed|ion) (run|set)|test set|leaderboard",
    re.IGNORECASE,
)
# Writing checks no builder sees is the examiner's own job; no builder or boss text may name them.
HELD_OUT = re.compile(r"held[- ]out", re.IGNORECASE)


def is_examiners(path: Path) -> bool:
    rel = path.relative_to(SRC).as_posix()
    return rel.startswith(("skills/examiner/", "prompts/examiner_"))


@pytest.mark.parametrize("path", GIVEN_TO_MODELS, ids=lambda p: str(p.relative_to(SRC)))
def test_no_text_a_model_is_given_says_it_is_being_measured(path):
    text = path.read_text(encoding="utf-8")
    found = [m.group(0) for m in TELLS.finditer(text)]
    if not is_examiners(path):
        found += [m.group(0) for m in HELD_OUT.finditer(text)]
    assert not found, f"{path.relative_to(SRC)} tells the model it is measured: {found}"


def test_the_screen_finds_a_tell_and_covers_every_kind_of_model_text():
    assert TELLS.search("in benchmark runs about half the cells")
    assert TELLS.search("checks you cannot see: the hidden checks")
    assert HELD_OUT.search("a held-out check") and not TELLS.search("a held-out check")
    assert is_examiners(SRC / "skills" / "examiner" / "x.md")
    assert not is_examiners(SRC / "skills" / "builder" / "x.md")
    kinds = {p.relative_to(SRC).parts[0] for p in GIVEN_TO_MODELS}
    assert kinds == {"prompts", "skills", "rubrics"}
