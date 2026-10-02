from headings import extract_headings
from inject import find_markers, update_toc
from toc import render_toc

DOC = """# Project

<!-- toc -->
<!-- /toc -->

## Install
Run it.

```bash
# not a heading
## still not
```

## Usage
### Options
### Options
## Install ##
#### Deep
# Appendix: Q&A [FAQ]
"""


def test_the_updated_document_embeds_exactly_render_toc():
    result = update_toc(DOC)
    start, end = find_markers(result)
    lines = result.split("\n")
    region = "\n".join(lines[start + 1 : end])
    expected = render_toc(extract_headings(DOC))
    assert region == "\n" + expected
    assert lines[end - 1] == ""


def test_every_link_in_the_toc_points_at_an_anchor_of_a_real_heading():
    result = update_toc(DOC)
    anchors = {h.anchor for h in extract_headings(DOC)}
    start, end = find_markers(result)
    links = [line for line in result.split("\n")[start + 1 : end] if line.strip()]
    assert len(links) == len(extract_headings(DOC)) == 8
    for line in links:
        anchor = line.rsplit("(#", 1)[1].rstrip(")")
        assert anchor in anchors


def test_the_full_toc_for_the_document():
    assert render_toc(extract_headings(DOC)) == (
        "- [Project](#project)\n"
        "  - [Install](#install)\n"
        "  - [Usage](#usage)\n"
        "    - [Options](#options)\n"
        "    - [Options](#options-1)\n"
        "  - [Install](#install-1)\n"
        "    - [Deep](#deep)\n"
        "- [Appendix: Q&A \\[FAQ\\]](#appendix-qa-faq)\n"
    )


def test_updating_after_editing_the_document_follows_the_edit():
    first = update_toc(DOC)
    edited = first.replace("## Usage\n", "## Usage\n### New part\n")
    second = update_toc(edited)
    assert "[New part](#new-part)" in second
    assert "[New part]" not in first
    assert update_toc(second) == second


def test_line_numbers_refer_to_the_document_they_were_extracted_from():
    result = update_toc(DOC)
    for text in (DOC, result):
        for heading in extract_headings(text):
            assert text.split("\n")[heading.line - 1].lstrip("# ").startswith(heading.text[:5])
