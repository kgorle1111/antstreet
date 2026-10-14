"""bench/STANDARDS.md, the bar every experiment meets: twelve numbered standards, each saying how it
is held, linked from the method and the pre-registration."""

import re

from docs_support import ROOT, read

STANDARDS = ROOT / "bench" / "STANDARDS.md"
HELD = ("**Enforced**", "**Checked**", "**checked**", "**Rule**", "**rule**")


def test_there_are_twelve_standards_in_order():
    heads = re.findall(r"^## S(\d+)\. ", read(STANDARDS), re.M)
    assert heads == [str(n) for n in range(1, 13)]


def test_every_standard_says_how_it_is_held():
    sections = re.split(r"^## S\d+\. ", read(STANDARDS), flags=re.M)[1:]
    missing = [i + 1 for i, body in enumerate(sections) if not any(h in body for h in HELD)]
    assert not missing, f"standards that do not say how they are held: S{missing}"


def test_the_method_and_the_preregistration_link_the_standards():
    for doc in ("METHOD.md", "PREREG.md"):
        assert "[STANDARDS.md](STANDARDS.md)" in read(ROOT / "bench" / doc), doc
